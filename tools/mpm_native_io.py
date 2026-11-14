# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Shared bounded native archive I/O; no selection, state effects or package hooks."""
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile

import mojt_artifact as artifact

MAX_ARCHIVE = artifact.MAX_CONTENT + 4 * artifact.MAX_METADATA


def require(ok, message):
    if not ok:raise ValueError(message)


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


def stored_mode(row):
    return 0o555 if row["type"] == "directory" else 0o444 | row["mode"] & 0o111


def frozen_copy(source, destination, *, maximum=MAX_ARCHIVE):
    require(type(maximum) is int and 0 < maximum <= MAX_ARCHIVE, "invalid copy size limit")
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    checksum = hashlib.sha256()
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_size <= maximum, "input must be a bounded regular archive")
        with os.fdopen(fd, "rb", closefd=False) as origin, destination.open("xb") as target:
            total = 0
            while chunk := origin.read(128 * 1024):
                total += len(chunk)
                require(total <= maximum, "input archive exceeds size limit")
                checksum.update(chunk)
                target.write(chunk)
            require(total == info.st_size, "input archive changed size during copying")
            os.fchmod(target.fileno(), 0o444)
            os.fsync(target.fileno())
        return checksum.hexdigest(), total
    finally:
        os.close(fd)


def unpack_regular(path, body, target, *, symlinks=False, verify=True, expected_id=None, budget=artifact.MAX_CONTENT):
    """Bounded one-pass materialization; payload hashing is explicitly selectable.

    A missing descriptor is read from the archive. Paths, links, types, sizes,
    member order and decompressor errors are checked even without a content audit.
    """
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(["zstd", "-q", "-d", "-c", "--", str(path)], stdout=subprocess.PIPE, stderr=errors)
        try:
            with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
                root = archive.next()
                require(root is not None and root.name in ("./" + k for k in artifact.KINDS) and root.isdir(), "native category differs")
                require(root.mode == 0o755 and root.uid == root.gid == root.mtime == 0 and not root.pax_headers, "invalid category metadata")
                member = archive.next()
                require(member is not None and member.name == root.name + "/artifact.json" and member.isfile()
                        and 0 <= member.size <= artifact.MAX_METADATA, "native descriptor missing")
                require(member.mode == 0o644 and member.uid == member.gid == member.mtime == 0 and not member.pax_headers,
                        "invalid descriptor metadata")
                raw = archive.extractfile(member).read();found = artifact.parse_json(raw)
                artifact.validate_descriptor(found)
                require(raw == artifact.canonical(found) + b"\n" and root.name == "./" + found['kind'], "native descriptor encoding differs")
                require(body is None or found == body, "frozen descriptor differs")
                require(expected_id is None or found['id'] == expected_id, "unexpected artifact identity")
                body = found
                require(sum(row.get('size',0) for row in body['files']) <= budget, 'native dependency bundle exceeds content budget')
                require(all(r["type"] in (("file", "directory", "symlink") if symlinks else ("file", "directory")) for r in body["files"]), "materialization requires regular entries")
                for row in body["files"]:
                    member = archive.next();expected = artifact._tar_info(root.name + "/" + row['path'], row)
                    require(member is not None and set(member.pax_headers) <= {'path','linkpath'}
                            and (member.name,member.type,member.mode,member.uid,member.gid,member.size,member.mtime) ==
                                (expected.name,expected.type,expected.mode,expected.uid,expected.gid,expected.size,0),
                            "frozen member differs: " + row['path'])
                    destination = target / row["path"]
                    if row["type"] == "directory":destination.mkdir(mode=0o700)
                    elif row["type"] == "symlink":
                        require(member.linkname == row['target'], 'link target differs')
                        destination.symlink_to(row['target'])
                    else:
                        checksum = hashlib.sha256() if verify else None
                        with destination.open("xb") as output, archive.extractfile(member) as source:
                            while chunk := source.read(128 * 1024):
                                if checksum is not None:checksum.update(chunk)
                                output.write(chunk)
                            require(output.tell() == row['size'], 'extracted file size differs')
                            if checksum is not None:require(checksum.hexdigest() == row["sha256"], "extracted file checksum differs")
                            os.fchmod(output.fileno(), stored_mode(row));os.fsync(output.fileno())
                require(archive.next() is None, "unexpected frozen member")
                while trailer := archive.fileobj.read(128 * 1024):
                    require(not any(trailer), 'nonzero data after tar end marker')
            while process.stdout.read(128 * 1024):pass
            require(process.wait() == 0, "zstd extraction failed")
        finally:
            process.stdout.close()
            if process.poll() is None:process.terminate();process.wait()
    for row in reversed(body["files"]):
        if row["type"] == "directory":
            entry = target / row["path"];entry.chmod(stored_mode(row));sync_directory(entry)
    return body


def copy_regular(source, destination, size, mode):
    """Copy required bytes once, without a separate hash/readback pass."""
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_size == size, 'source file type/size differs')
        with os.fdopen(fd,'rb',closefd=False) as origin, destination.open('xb') as output:
            remaining = size
            while remaining:
                chunk = origin.read(min(128*1024,remaining))
                require(chunk, 'source file truncated during copy')
                output.write(chunk);remaining -= len(chunk)
            require(not origin.read(1), 'source file grew during copy')
            os.fchmod(output.fileno(),mode);os.fsync(output.fileno())
    finally:os.close(fd)


def clean_stage(path):
    if not path.exists():
        return
    for parent, dirs, files in os.walk(path, topdown=True, followlinks=False):
        Path(parent).chmod(0o700)
    shutil.rmtree(path)


def acquisition_trust(value, expected_id, checksum=None, size=None):
    """Validate retained origin evidence; live source authorization is external."""
    if value is None:
        return dict(kind="explicit-local-file", expected_id=expected_id)
    import mpm_native_cache as cache
    artifact.fields(value, ("source", "name", "verification", "max_expanded"))
    identifier(value["source"]); cache.model.token(value["name"])
    require(type(value["max_expanded"]) is int and 0 < value["max_expanded"] <= 2 * artifact.MAX_CONTENT,
            "invalid acquired archive expansion limit")
    receipt = cache.envelope(value["verification"], cache.RECORD)
    artifact.fields(receipt, ("artifact", "archive", "source_snapshot", "acquisition_map",
                             "descriptor", "trust_policy", "verified_utc"))
    for key in ("source_snapshot", "acquisition_map", "trust_policy"):
        identifier(receipt[key])
    require(receipt["artifact"] == receipt["descriptor"] == expected_id, "acquisition artifact differs")
    artifact.fields(receipt["archive"], ("sha256", "size"))
    cache.hex_sha(receipt["archive"]["sha256"]); cache.size(receipt["archive"]["size"], MAX_ARCHIVE)
    require(type(receipt["verified_utc"]) is str and
            datetime.fromisoformat(receipt["verified_utc"]).utcoffset() == timezone.utc.utcoffset(None),
            "invalid acquisition verification time")
    require(checksum is None or receipt["archive"] == dict(sha256=checksum, size=size),
            "acquired archive encoding differs")
    return dict(kind="registered-native-source", expected_id=expected_id,
                source=value["source"], verification=value["verification"]["id"])

