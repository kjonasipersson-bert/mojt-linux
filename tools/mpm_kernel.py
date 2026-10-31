# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Local exact Kernel import/install/status. No provider, deployment or boot writes."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile

import mojt_artifact as artifact
import mpm_transaction as transaction

DEFAULT_ROOT = Path("/var/lib/mojt/kernel")
REGISTRY = "mpm-kernel-registry-v1\n"
RECORD = "mpm-kernel-install-v1"
MARKER = ".mojt-kernel-registry"
MAX_ARCHIVE = artifact.MAX_CONTENT + 4 * artifact.MAX_METADATA


def require(value, message):
    if not value:
        raise ValueError(message)


def identifier(value):
    require(isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value), "require a full sha256 artifact ID")
    return value.split(":")[1]


def directory(path):
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode), "not a regular directory: " + str(path))
    return info


def regular(path):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "not a private regular file: " + str(path))
    return info


def root_path(value, *, write=False):
    root = Path(os.path.abspath(value))
    require(root == root.resolve(), "registry path must not traverse symlinks")
    if write:
        if root == DEFAULT_ROOT:
            require(os.geteuid() == 0, "shared Kernel changes require an administrator")
        for parent in (root, *root.parents):
            try:
                info = directory(parent)
            except FileNotFoundError:
                continue
            require(info.st_uid in (0, os.geteuid()), "untrusted registry ancestor owner")
            sticky_temporary = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
            require(not info.st_mode & 0o022 or sticky_temporary, "writable registry ancestor")
    return root


def inspect_root(root, *, allow_empty=False):
    try:
        info = directory(root)
    except FileNotFoundError:
        return False
    require(not info.st_mode & 0o022, "registry is writable by another user/group")
    entries = {p.name for p in root.iterdir()}
    if not entries and allow_empty:
        return False
    require(entries == {MARKER, ".lock", "installed", "staging"}, "unmanaged/incomplete Kernel registry")
    for name in (MARKER, ".lock"):
        item = regular(root / name)
        require(item.st_uid == info.st_uid and not item.st_mode & 0o022, "unsafe registry metadata")
    require((root / MARKER).read_bytes() == REGISTRY.encode(), "unsupported Kernel registry format")
    for name in ("installed", "staging"):
        item = directory(root / name)
        require(item.st_uid == info.st_uid and not item.st_mode & 0o022, "unsafe registry directory")
    return True


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_json(path, value):
    with path.open("xb") as stream:
        stream.write(artifact.canonical(value) + b"\n")
        os.fchmod(stream.fileno(), 0o444)
        os.fsync(stream.fileno())


@contextmanager
def registry_lock(root):
    root_path(root, write=True)
    root.mkdir(parents=True, exist_ok=True, mode=0o755)
    root_path(root, write=True)  # Also inspect ancestors newly created under the caller's umask.
    require(not directory(root).st_mode & 0o022, "unsafe registry permissions")
    require(os.geteuid() == root.stat().st_uid, "registry mutations require its owner")
    with transaction.file_lock(root / ".lock"):
        if not os.path.lexists(root / MARKER):
            require({p.name for p in root.iterdir()} == {".lock"}, "refuse to adopt an unmanaged directory")
            (root / "installed").mkdir(mode=0o755)
            (root / "staging").mkdir(mode=0o755)
            with (root / MARKER).open("xb") as stream:
                stream.write(REGISTRY.encode())
                os.fchmod(stream.fileno(), 0o644)
                os.fsync(stream.fileno())
            sync_directory(root)
        inspect_root(root)
        yield


def acceptable(body):
    artifact.validate_descriptor(body)
    require(body["kind"] == "kernel" and body["name"] == "linux", "local Kernel installer requires a linux Kernel artifact")
    require(body["platform"] == os.uname().machine + "-linux", "Kernel package platform differs from host")
    require(not body["dependencies"], "Kernel dependency acquisition is not implemented; dependencies cannot be ignored")
    require(not body["requirements"], "Kernel requirement evaluation is not implemented; requirements cannot be ignored")
    require(all(row["type"] in ("file", "directory") for row in body["files"]), "local Kernel import accepts only regular files/directories")
    require(all(len(row["path"].split("/")) <= 64 and len(os.fsencode(row["path"])) <= 4096
                for row in body["files"]), "Kernel path exceeds local import limits")


def stored_mode(row):
    return 0o555 if row["type"] == "directory" else 0o444 | row["mode"] & 0o111


def frozen_copy(source, destination):
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    checksum = hashlib.sha256()
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_size <= MAX_ARCHIVE, "input must be a bounded regular archive")
        with os.fdopen(fd, "rb", closefd=False) as origin, destination.open("xb") as target:
            total = 0
            while chunk := origin.read(128 * 1024):
                total += len(chunk)
                require(total <= MAX_ARCHIVE, "input archive exceeds size limit")
                checksum.update(chunk)
                target.write(chunk)
            require(total == info.st_size, "input archive changed size during copying")
            os.fchmod(target.fileno(), 0o444)
            os.fsync(target.fileno())
        return checksum.hexdigest(), total
    finally:
        os.close(fd)


def unpack_kernel(path, body, target):
    """Second pass over our frozen verified archive; no extract/extractall calls."""
    acceptable(body)
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(["zstd", "-q", "-d", "-c", "--", str(path)], stdout=subprocess.PIPE, stderr=errors)
        try:
            with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
                member = archive.next()
                require(member is not None and member.name == "./kernel" and member.isdir(), "Kernel category differs")
                member = archive.next()
                require(member is not None and member.name == "./kernel/artifact.json" and member.isfile()
                        and member.size <= artifact.MAX_METADATA, "Kernel descriptor missing")
                require(archive.extractfile(member).read() == artifact.canonical(body) + b"\n", "frozen descriptor differs")
                for row in body["files"]:
                    member = archive.next()
                    require(member is not None and member.name == "./kernel/" + row["path"], "frozen member differs")
                    destination = target / row["path"]
                    if row["type"] == "directory":
                        require(member.isdir(), "directory type differs")
                        destination.mkdir(mode=0o700)
                    else:
                        require(member.isfile() and member.size == row["size"], "file type/size differs")
                        checksum = hashlib.sha256()
                        with destination.open("xb") as output:
                            with archive.extractfile(member) as source:
                                while chunk := source.read(128 * 1024):
                                    checksum.update(chunk)
                                    output.write(chunk)
                            require(checksum.hexdigest() == row["sha256"], "extracted file checksum differs")
                            os.fchmod(output.fileno(), stored_mode(row))
                            os.fsync(output.fileno())
                require(archive.next() is None, "unexpected frozen member")
            while process.stdout.read(128 * 1024):
                pass
            require(process.wait() == 0, "zstd extraction failed")
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.terminate()
                process.wait()
    for row in reversed(body["files"]):
        if row["type"] == "directory":
            entry = target / row["path"]
            entry.chmod(stored_mode(row))
            sync_directory(entry)


def object_record(path, expected_id, *, verify=False):
    owner = directory(path).st_uid
    for name in ("artifact.json", "installed.json", "archive.tar.zst"):
        info = regular(path / name)
        require(info.st_uid == owner and stat.S_IMODE(info.st_mode) == 0o444, "unsafe installed metadata")
    body = artifact.read_json(path / "artifact.json")
    acceptable(body)
    require((path / "artifact.json").read_bytes() == artifact.canonical(body) + b"\n", "stored descriptor encoding differs")
    require(body["id"] == expected_id, "installed artifact identity differs")
    record = artifact.read_json(path / "installed.json")
    artifact.fields(record, ("format", "artifact", "archive_sha256", "archive_size", "installed_utc", "uid", "trust", "storage"))
    require(record["format"] == RECORD and record["artifact"] == expected_id and
            record["storage"] == "readonly-kernel-tree-v1", "unsupported/mismatched install record")
    require(isinstance(record["archive_sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", record["archive_sha256"])
            and type(record["archive_size"]) is int and record["archive_size"] >= 0, "invalid installed archive evidence")
    require(type(record["uid"]) is int and record["uid"] == owner and isinstance(record["installed_utc"], str)
            and record["trust"] == dict(kind="explicit-local-file", expected_id=expected_id), "invalid installed trust record")
    require(stat.S_IMODE(path.stat().st_mode) == 0o555, "installed directory must be read-only")
    if verify:
        require((path / "archive.tar.zst").stat().st_size == record["archive_size"] and
                artifact.file_sha(path / "archive.tar.zst") == record["archive_sha256"], "retained archive is damaged")
        expected = {"artifact.json", "installed.json", "archive.tar.zst", *(r["path"] for r in body["files"])}
        found = set()
        for parent, dirs, files in os.walk(path, followlinks=False):
            for name in dirs + files:
                item = Path(parent) / name
                relative = item.relative_to(path).as_posix()
                require(not item.is_symlink(), "unexpected link in installed object")
                found.add(relative)
        require(found == expected, "installed tree inventory differs")
        for row in body["files"]:
            item = path / row["path"]
            info = directory(item) if row["type"] == "directory" else regular(item)
            require(info.st_uid == owner and stat.S_IMODE(info.st_mode) == stored_mode(row), "installed file metadata differs")
            if row["type"] == "file":
                require(info.st_size == row["size"] and artifact.file_sha(item) == row["sha256"], "installed file content differs")
    return body, record


def clean_stage(path):
    if not path.exists():
        return
    for parent, dirs, files in os.walk(path, topdown=True, followlinks=False):
        Path(parent).chmod(0o700)
    shutil.rmtree(path)


def install(root, archive, expected_id, *, dry_run=False, yes=False):
    key = identifier(expected_id)
    root = root_path(root, write=True)
    managed = inspect_root(root, allow_empty=True)
    archive = Path(archive)
    require(not archive.is_symlink() and stat.S_ISREG(archive.stat().st_mode)
            and archive.stat().st_size <= MAX_ARCHIVE, "input must be a bounded regular archive")
    body = artifact.verify(archive, expected_id=expected_id)
    acceptable(body)
    destination = root / "installed" / key
    exists = managed and os.path.lexists(destination)
    if exists:
        object_record(destination, expected_id, verify=True)
    plan = dict(action="no-change" if exists else "install", artifact=expected_id, version=body["version"],
                kernel_release=body["metadata"]["kernel_release"], root=str(root),
                compatibility="not-evaluated-for-a-deployment", selected="unchanged", running="unchanged")
    if dry_run or exists:
        return dict(plan=plan, changed=False, dry_run=dry_run)
    if not yes:
        print(json.dumps(plan, indent=2))
        if input("Retain this exact local Kernel and register it as installed? [y/N] ").lower() != "y":
            return dict(plan=plan, changed=False, cancelled=True)
    with registry_lock(root):
        if os.path.lexists(destination):
            object_record(destination, expected_id, verify=True)
            return dict(plan=dict(plan, action="no-change"), changed=False)
        # A read-only directory cannot portably move between parents (the '..'
        # update needs write permission). A sibling rename publishes it read-only
        # in one step; status explicitly distinguishes these incomplete names.
        stage = Path(tempfile.mkdtemp(prefix=".install-", dir=root / "installed"))
        try:
            checksum, size = frozen_copy(archive, stage / "archive.tar.zst")
            copied = artifact.verify(stage / "archive.tar.zst", expected_id=expected_id)
            require(copied == body, "input changed after planning")
            unpack_kernel(stage / "archive.tar.zst", body, stage)
            write_json(stage / "artifact.json", body)
            write_json(stage / "installed.json", dict(format=RECORD, artifact=expected_id,
                archive_sha256=checksum, archive_size=size, installed_utc=datetime.now(timezone.utc).isoformat(),
                uid=os.geteuid(), trust=dict(kind="explicit-local-file", expected_id=expected_id),
                storage="readonly-kernel-tree-v1"))
            stage.chmod(0o555)
            sync_directory(stage)
            stage.rename(destination)
            sync_directory(root / "installed")
        finally:
            clean_stage(stage)
    return dict(plan=plan, changed=True, installed_path=str(destination))


def status(root, *, verify=False):
    root = root_path(root)
    managed = inspect_root(root, allow_empty=True)
    running = os.uname().release
    rows, staging = [], []
    if managed:
        owner = root.stat().st_uid
        for path in sorted((root / "installed").iterdir()):
            if path.name.startswith(".install-"):
                require(directory(path).st_uid == owner, "unsafe staging entry")
                staging.append("installed/" + path.name)
                continue
            require(re.fullmatch(r"[0-9a-f]{64}", path.name) and directory(path).st_uid == owner, "unknown installed entry")
            body, record = object_record(path, "sha256:" + path.name, verify=verify)
            rows.append(dict(artifact=body["id"], version=body["version"], kernel_release=body["metadata"]["kernel_release"],
                platform=body["platform"], installed_utc=record["installed_utc"], path=str(path),
                integrity="verified-now" if verify else "verified-at-installation", release_matches_running=body["metadata"]["kernel_release"] == running))
        staging += sorted(path.name for path in (root / "staging").iterdir())
    return dict(format="mpm-kernel-status-v1", root=str(root), installed=rows, staging_entries=staging,
        selected=dict(state="unknown", artifact=None, reason="deployment selection not integrated"),
        running=dict(release=running, artifact=None, reason="uname does not identify an exact build"),
        compatibility="installation is not deployment compatibility or boot readiness")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    commands = parser.add_subparsers(dest="action", required=True)
    add = commands.add_parser("install")
    add.add_argument("--from-file", type=Path, required=True)
    add.add_argument("--expected-id", required=True)
    add.add_argument("--dry-run", action="store_true")
    add.add_argument("-y", "--yes", action="store_true")
    show = commands.add_parser("status")
    show.add_argument("--verify", action="store_true")
    for command in (add, show):
        command.add_argument("--root", dest="action_root", type=Path)
        command.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        require(args.root is None or args.action_root is None, "specify root only once")
        root = args.root or args.action_root or DEFAULT_ROOT
        result = (install(root, args.from_file, args.expected_id, dry_run=args.dry_run, yes=args.yes)
                  if args.action == "install" else status(root, verify=args.verify))
        if args.json or args.action == "install":
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("Kernel registry:", result["root"])
            for row in result["installed"]:
                print(f"Installed: {row['version']['release_id']} / {row['kernel_release']} / {row['artifact']} ({row['integrity']})")
            if not result["installed"]:
                print("Installed: none in this registry")
            print("Selected: unknown (deployment selection not integrated)")
            print("Running:", result["running"]["release"], "(exact artifact unknown)")
            if result["staging_entries"]:
                print("Incomplete or active staging entries:", ", ".join(result["staging_entries"]))
            print(result["compatibility"])
    except (OSError, ValueError, KeyError, TypeError, RecursionError, tarfile.TarError, EOFError) as error:
        print("mpm kernel: " + str(error), file=sys.stderr)
        return 1
    return 0

