# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Native package prototype: namespaced tar.zst, exact descriptor, no install.

Inputs are frozen, owner-controlled staging trees. No archive is extracted or
package hook executed. Production signing, extraction and deployment are separate.
"""
import copy
import difflib
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tarfile
import tempfile
import tomllib

from mpm_selection import NAME, RELEASE, components

FORMAT = "mojt-artifact-v1"
SPEC_FORMAT = "mojt-artifact-spec-v1"
KINDS = ("base", "system", "kernel", "port")
MAX_METADATA = 16 * 1024 * 1024
MAX_ENTRIES = 200000
MAX_CONTENT = 64 * 1024**3


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    """v1 JSON: ASCII escapes, code-point-sorted keys, no floats or whitespace."""
    def check(item):
        if isinstance(item, dict):
            require(all(isinstance(k, str) for k in item), "JSON keys must be strings")
            for v in item.values():
                check(v)
        elif isinstance(item, list):
            for v in item:
                check(v)
        else:
            require(item is None or type(item) in (str, int, bool), "metadata supports no floats/custom types")
    check(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def digest(value):
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


def file_sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, "duplicate JSON key: " + key)
        value[key] = item
    return value


def parse_json(raw):
    require(len(raw) <= MAX_METADATA, "metadata size exceeds prototype limit")
    value = json.loads(raw, object_pairs_hook=_pairs)
    canonical(value)
    return value


def read_json(path):
    with Path(path).open("rb") as stream:
        return parse_json(stream.read(MAX_METADATA + 1))


def fields(value, required, optional=()):
    require(isinstance(value, dict) and set(required) <= set(value) <= set(required) | set(optional),
            "unsupported metadata fields")


def clean_text(value):
    return isinstance(value, str) and bool(value) and not any(ord(c) < 32 or ord(c) == 127 for c in value)


def token(value, pattern=RELEASE):
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None and len(value) <= 160


def relative(value):
    require(clean_text(value) and not value.startswith("/") and
            str(PurePosixPath(value)) == value and
            all(p not in ("", ".", "..") for p in value.split("/")), "unsafe or noncanonical package path")
    return value


def version(value):
    fields(value, ("upstream", "scheme", "revision"))
    require(token(value["upstream"]), "invalid upstream release name")
    require(value["scheme"] in ("dotted-v1", "opaque-v1"), "unsupported version scheme")
    if value["scheme"] == "dotted-v1":
        components(value["upstream"])
    require(value["revision"] is None or type(value["revision"]) is int and value["revision"] >= 0,
            "package revision must be a nonnegative integer or null")
    release = value["upstream"] + ("-r" + str(value["revision"]) if value["revision"] is not None else "")
    require(token(release), "release identifier too long")
    return dict(value, release_id=release)


def validate_spec(value):
    fields(value, ("format", "kind", "name", "platform", "version", "dependencies",
                   "requirements", "provides", "provenance", "metadata"))
    require(value["format"] == SPEC_FORMAT and value["kind"] in KINDS, "unsupported artifact spec/kind")
    require(token(value["name"], NAME) and token(value["platform"]), "invalid package name/platform")
    version(value["version"])
    for key in ("requirements", "provides", "provenance", "metadata"):
        require(isinstance(value[key], dict), key + " must be an object")
    require(isinstance(value["dependencies"], list), "dependencies must be a list")
    seen = set()
    for dependency in value["dependencies"]:
        require(isinstance(dependency, dict) and clean_text(dependency.get("provider")), "dependency needs provider")
        if dependency["provider"] == "native":
            fields(dependency, ("provider", "artifact"))
            require(isinstance(dependency["artifact"], str) and
                    re.fullmatch(r"sha256:[0-9a-f]{64}", dependency["artifact"]), "native dependency must be exact")
        else:
            fields(dependency, ("provider", "identity"))
            require(isinstance(dependency["identity"], dict) and dependency["identity"], "external reference needs opaque identity")
        signature = canonical(dependency)
        require(signature not in seen, "duplicate dependency")
        seen.add(signature)
    if value["kind"] == "kernel":
        require(token(value["metadata"].get("kernel_release")), "Kernel requires actual kernel_release")
    if value["kind"] == "system":
        require(value["metadata"].get("system_role") in ("component", "generation"), "System needs component/generation role")
    canonical(value)
    return copy.deepcopy(value)


def inventory(source):
    """Preserve numeric owners, modes, symlinks and hardlinks. Do not follow links."""
    source = Path(source)
    require(source.is_dir() and not source.is_symlink(), "source must be a regular staging directory")
    rows, locations, links = [], {}, {}
    def visit(path, name):
        info = path.lstat()
        # Raw rootfs xattrs/ACLs/capabilities need an explicit future extension;
        # existing Base release archives carry them opaquely without alteration.
        require(not os.listxattr(path, follow_symlinks=False), "xattrs/ACLs require a supported metadata extension: " + name)
        row = dict(path=name, mode=stat.S_IMODE(info.st_mode), uid=info.st_uid, gid=info.st_gid)
        if stat.S_ISDIR(info.st_mode):
            row["type"] = "directory"
        elif stat.S_ISLNK(info.st_mode):
            row.update(type="symlink", target=os.readlink(path))
            require(clean_text(row["target"]), "invalid symlink target")
        elif stat.S_ISREG(info.st_mode):
            key = info.st_dev, info.st_ino
            if key in links:
                row.update(type="hardlink", target=links[key])
            else:
                row.update(type="file", size=info.st_size, sha256=file_sha(path))
                links[key] = name
                locations[name] = path
        else:
            raise ValueError("device/FIFO/socket payload is unsupported: " + name)
        rows.append(row)
        require(len(rows) <= MAX_ENTRIES, "too many payload entries")
        if row["type"] == "directory":
            for child in sorted(path.iterdir(), key=lambda p: p.name):
                relative(child.name)
                visit(child, name + "/" + child.name)
    visit(source, "payload")
    require(sum(row.get("size", 0) for row in rows) <= MAX_CONTENT, "payload exceeds prototype size limit")
    return rows, locations


def regular_row(rows, name):
    entries = {row["path"]: row for row in rows}
    require(name in entries, "missing required payload file: " + name)
    row = entries[name]
    if row["type"] == "hardlink":
        row = entries[row["target"]]
    require(row["type"] == "file", "required payload file is not regular: " + name)
    return row


def check_base_manifest(spec, body, rows):
    require(isinstance(body, dict) and isinstance(body.get("base"), dict) and isinstance(body.get("image"), dict) and body.get("format") == 1 and
            body.get("base", {}).get("version") == spec["version"]["upstream"], "Base release format/version differs")
    image = body.get("image", {})
    name = relative(image.get("file"))
    require("/" not in name, "Base image must be a release-local filename")
    require(regular_row(rows, "payload/" + name)["sha256"] == image.get("sha256"), "Base image hash differs")


def check_kernel_rows(spec, rows):
    release = spec["metadata"]["kernel_release"]
    expected = {"payload/boot/" + p + release for p in ("vmlinuz-", "config-", "System.map-")}
    files = {row["path"] for row in rows if row["type"] == "file"}
    root = "payload/lib/modules/" + release
    require(expected <= files and root + "/modules.dep" in files and
            any(p.startswith(root + "/") and re.search(r"\.ko(?:\.(?:xz|gz|zst))?$", p) for p in files),
            "Kernel image/config/map and matching module tree required")
    directories = {"payload", "payload/boot", "payload/lib", "payload/lib/modules", root}
    for row in rows:
        if not row["path"].startswith("payload"):
            continue
        require(row["type"] in ("file", "directory") and
                (row["path"] in (expected if row["type"] == "file" else directories)
                 or row["path"].startswith(root + "/")), "unexpected Kernel payload entry")


def check_payload(spec, source, rows):
    if spec["kind"] == "base":
        manifest = Path(source) / "manifest.toml"
        require(manifest.is_file() and not manifest.is_symlink(), "Base requires an existing release manifest.toml")
        body = tomllib.loads(manifest.read_text())
        check_base_manifest(spec, body, rows)
    if spec["kind"] == "kernel":
        check_kernel_rows(spec, rows)


def descriptor(spec, rows):
    body = dict(format=FORMAT, kind=spec["kind"], name=spec["name"], platform=spec["platform"],
                version=version(spec["version"]),
                payload_layout="base-release-v1" if spec["kind"] == "base" else "tree-v1",
                files=copy.deepcopy(rows), **{k: copy.deepcopy(spec[k]) for k in
                ("dependencies", "requirements", "provides", "provenance", "metadata")})
    body["id"] = digest(body)
    return body


def validate_descriptor(value):
    fields(value, ("format", "kind", "name", "platform", "version", "payload_layout", "files",
                   "dependencies", "requirements", "provides", "provenance", "metadata", "id"))
    require(value["format"] == FORMAT, "unsupported artifact format")
    raw = copy.deepcopy(value)
    identifier = raw.pop("id")
    require(identifier == digest(raw), "artifact identity differs")
    declared = dict(value["version"])
    release = declared.pop("release_id")
    spec = validate_spec(dict(format=SPEC_FORMAT, version=declared, **{k: value[k] for k in
        ("kind", "name", "platform", "dependencies", "requirements", "provides", "provenance", "metadata")}))
    require(version(declared)["release_id"] == release, "release identifier differs")
    require(value["payload_layout"] == ("base-release-v1" if value["kind"] == "base" else "tree-v1"), "unsupported payload layout")
    require(isinstance(value["files"], list) and len(value["files"]) <= MAX_ENTRIES, "invalid inventory")
    known = {}
    for row in value["files"]:
        fields(row, ("path", "type", "mode", "uid", "gid"), ("size", "sha256", "target"))
        name = relative(row["path"])
        require(name != "artifact.json" and name not in known and
                name.split("/")[0] in ("payload", "provenance"), "invalid/duplicate inventory path")
        require(all(type(row[k]) is int and row[k] >= 0 for k in ("mode", "uid", "gid")) and row["mode"] <= 0o7777,
                "invalid numeric file metadata")
        parent = str(PurePosixPath(name).parent)
        require(parent == "." or parent in known and known[parent]["type"] == "directory", "missing/non-directory ancestor")
        if row["type"] == "file":
            fields(row, ("path", "type", "mode", "uid", "gid", "size", "sha256"))
            require(type(row["size"]) is int and 0 <= row["size"] <= MAX_CONTENT and
                    isinstance(row["sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", row["sha256"]), "invalid file evidence")
        elif row["type"] in ("hardlink", "symlink"):
            fields(row, ("path", "type", "mode", "uid", "gid", "target"))
            require(clean_text(row["target"]), "invalid link target")
            if row["type"] == "hardlink":
                require(row["target"] in known and known[row["target"]]["type"] == "file", "hardlink must name a preceding regular file")
                require(all(row[k] == known[row["target"]][k] for k in ("uid", "gid", "mode")), "hardlink metadata differs")
        else:
            fields(row, ("path", "type", "mode", "uid", "gid"))
            require(row["type"] == "directory", "unsupported file type")
        known[name] = row
    require("payload" in known and known["payload"]["type"] == "directory", "missing payload root")
    require(sum(row.get("size", 0) for row in value["files"]) <= MAX_CONTENT, "declared content too large")
    if spec["kind"] == "kernel":
        check_kernel_rows(spec, value["files"])
    return spec


def _tar_info(name, row):
    entry = tarfile.TarInfo(name)
    entry.mode, entry.uid, entry.gid = row["mode"], row["uid"], row["gid"]
    entry.mtime = 0
    entry.type = {"file": tarfile.REGTYPE, "directory": tarfile.DIRTYPE,
                  "symlink": tarfile.SYMTYPE, "hardlink": tarfile.LNKTYPE}[row["type"]]
    entry.size = row.get("size", 0)
    return entry


def _write_tar(stream, body, locations):
    kind = body["kind"]
    root = "./" + kind
    raw = canonical(body) + b"\n"
    with tarfile.open(fileobj=stream, mode="w|", format=tarfile.PAX_FORMAT) as archive:
        archive.addfile(_tar_info(root, dict(type="directory", mode=0o755, uid=0, gid=0)))
        record = dict(type="file", mode=0o644, uid=0, gid=0, size=len(raw))
        archive.addfile(_tar_info(root + "/artifact.json", record), io.BytesIO(raw))
        for row in body["files"]:
            entry = _tar_info(root + "/" + row["path"], row)
            if row["type"] in ("symlink", "hardlink"):
                entry.linkname = (root + "/" if row["type"] == "hardlink" else "") + row["target"]
            if row["type"] == "file":
                with locations[row["path"]].open("rb") as source:
                    archive.addfile(entry, source)
            else:
                archive.addfile(entry)


def pack(source, spec, output, attachments=None):
    spec = validate_spec(spec)
    source, output = Path(source).absolute(), Path(output).absolute()
    require(not os.path.lexists(output), "output already exists")
    real_source, real_output = source.resolve(), output.resolve()
    require(not real_source.is_relative_to(real_output) and not real_output.is_relative_to(real_source), "source/output must be disjoint")
    rows, locations = inventory(source)
    check_payload(spec, source, rows)
    original = copy.deepcopy(rows)
    attachments = attachments or {}
    if attachments:
        rows.append(dict(path="provenance", type="directory", mode=0o755, uid=0, gid=0))
        for name, path in sorted(attachments.items()):
            relative(name)
            require("/" not in name, "attachment needs a plain filename")
            path = Path(path)
            require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_METADATA,
                    "attachment must be a bounded regular file")
            key = "provenance/" + name
            rows.append(dict(path=key, type="file", mode=0o644, uid=0, gid=0, size=path.stat().st_size, sha256=file_sha(path)))
            locations[key] = path
    body = descriptor(spec, rows)
    validate_descriptor(body)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".mojt-pack-", dir=output.parent) as temporary:
        stage = Path(temporary) / "package"
        stage.mkdir()
        filename = "-".join((body["kind"], body["name"], body["version"]["release_id"],
                             body["platform"], body["id"].split(":")[1][:12])) + ".tar.zst"
        require(len(filename.encode()) <= 240, "package filename too long")
        path = stage / filename
        with path.open("wb") as target, tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(["zstd", "-q", "-3", "-T1", "-c"], stdin=subprocess.PIPE, stdout=target, stderr=errors)
            try:
                _write_tar(process.stdin, body, locations)
                process.stdin.close()
                require(process.wait() == 0, "zstd packaging failed")
            except BaseException:
                process.stdin.close()
                process.terminate()
                process.wait()
                raise
            target.flush()
            os.fsync(target.fileno())
        require(inventory(source)[0] == original, "source tree changed while packaging")
        verified = verify(path)
        require(verified["id"] == body["id"], "packed descriptor changed")
        (stage / "artifact.json").write_bytes(canonical(body) + b"\n")
        transport = dict(format="mojt-archive-record-v1", artifact=body["id"], file=filename,
                         sha256=file_sha(path), size=path.stat().st_size)
        (stage / "archive.json").write_bytes(canonical(transport) + b"\n")
        for member in stage.iterdir():
            with member.open("rb") as stream:
                os.fsync(stream.fileno())
        require(not os.path.lexists(output), "output appeared during packaging")
        stage.rename(output)
    return dict(artifact=body, archive=transport)


def verify(path, expected_id=None):
    """Stream and compare every logical member; never extract or run code."""
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(["zstd", "-q", "-d", "-c", "--", str(path)], stdout=subprocess.PIPE, stderr=errors)
        try:
            with tarfile.open(fileobj=process.stdout, mode="r|", format=tarfile.PAX_FORMAT) as archive:
                root = archive.next()
                require(root is not None and root.name in ("./" + k for k in KINDS) and root.isdir(), "archive needs one category root")
                require(root.mode == 0o755 and root.uid == root.gid == root.mtime == 0, "invalid category metadata")
                require(not root.pax_headers, "unexpected category PAX metadata")
                member = archive.next()
                require(member is not None and member.name == root.name + "/artifact.json" and member.isfile()
                        and 0 <= member.size <= MAX_METADATA, "descriptor must be first file inside category")
                raw = archive.extractfile(member).read()
                body = parse_json(raw)
                spec = validate_descriptor(body)
                require(root.name == "./" + body["kind"] and raw == canonical(body) + b"\n", "category/descriptor encoding differs")
                require(member.mode == 0o644 and member.uid == member.gid == member.mtime == 0, "invalid descriptor metadata")
                require(not member.pax_headers, "unexpected descriptor PAX metadata")
                require(expected_id is None or expected_id == body["id"], "unexpected artifact identity")
                base_manifest = None
                base_manifest_path = (regular_row(body["files"], "payload/manifest.toml")["path"]
                                      if body["kind"] == "base" else None)
                for row in body["files"]:
                    member = archive.next()
                    require(member is not None, "missing payload entry")
                    expected = _tar_info(root.name + "/" + row["path"], row)
                    require(set(member.pax_headers) <= {"path", "linkpath"}, "unsupported PAX metadata")
                    require((member.name, member.type, member.mode, member.uid, member.gid, member.size, member.mtime) ==
                            (expected.name, expected.type, expected.mode, expected.uid, expected.gid, expected.size, 0),
                            "archive member differs: " + row["path"])
                    if row["type"] == "file":
                        if row["path"] == base_manifest_path:
                            require(member.size <= MAX_METADATA, "Base manifest too large")
                            content = archive.extractfile(member).read()
                            base_manifest = tomllib.loads(content.decode("utf-8"))
                            actual_hash = hashlib.sha256(content).hexdigest()
                        else:
                            actual_hash = hashlib.file_digest(archive.extractfile(member), "sha256").hexdigest()
                        require(actual_hash == row["sha256"], "payload hash differs")
                    elif row["type"] in ("hardlink", "symlink"):
                        target = (root.name + "/" if row["type"] == "hardlink" else "") + row["target"]
                        require(member.linkname == target, "link target differs")
                require(archive.next() is None, "unexpected archive member or second category")
                if body["kind"] == "base":
                    check_base_manifest(spec, base_manifest, body["files"])
                while True:
                    trailer = archive.fileobj.read(128 * 1024)
                    if not trailer:
                        break
                    require(not any(trailer), "nonzero data after tar end marker")
            # Drain the frame to require successful zstd checksum/truncation checks.
            while process.stdout.read(128 * 1024):
                pass
            require(process.wait() == 0, "zstd verification failed")
            return body
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.terminate()
                process.wait()


def kernel_input(build, revision):
    build = Path(build)
    require(not os.path.lexists(build / ".building"), "incomplete Kernel build")
    record = read_json(build / "kernel.json")
    require(isinstance(record, dict) and record.get("format") == "mojt-kernel-input-v1", "unsupported Kernel build record")
    saved = copy.deepcopy(record)
    identifier = saved.pop("id", None)
    require(identifier == digest(saved), "Kernel build record identity differs")
    release = record.get("release")
    require(token(release) and record.get("architecture") == "x86_64", "unsupported Kernel release/architecture")
    plan = record.get("plan", {})
    require(isinstance(plan, dict) and clean_text(plan.get("version")) and clean_text(plan.get("localversion")), "invalid Kernel build plan")
    require(plan.get("version", "") + plan.get("localversion", "") == release and
            plan.get("source") == record.get("source"), "Kernel source/version provenance differs")
    source_record = record.get("source", {})
    require(isinstance(source_record, dict) and set(source_record) == {"url", "tag", "commit"} and
            clean_text(source_record["url"]) and source_record["tag"] == "v" + plan["version"] and
            isinstance(source_record["commit"], str) and re.fullmatch(r"[0-9a-f]{40}", source_record["commit"]),
            "invalid pinned Kernel source evidence")
    rows, _ = inventory(build / "root")
    actual = {row["path"][len("payload/"):]: dict(sha256=row["sha256"], mode=row["mode"])
              for row in rows if row["type"] == "file"}
    require(all(row["type"] in ("file", "directory") for row in rows) and actual == record.get("files"),
            "Kernel staged files differ from build record")
    require(file_sha(build / "root/boot" / ("config-" + release)) == record.get("config_sha256"), "Kernel final config differs")
    require((build / "debian.config").is_file() and file_sha(build / "debian.config") == record.get("base_config_sha256"),
            "Kernel seed config differs or is missing")
    config = build / "root/boot" / ("config-" + release)
    expected_diff = "".join(difflib.unified_diff((build / "debian.config").read_text().splitlines(True),
                         config.read_text().splitlines(True), fromfile="debian.config", tofile="mojt.config"))
    require((build / "config.diff").is_file() and (build / "config.diff").read_text() == expected_diff,
            "Kernel config diff differs or is missing")
    require(isinstance(record.get("sample_vermagic"), str) and record["sample_vermagic"].split()[:1] == [release], "recorded module vermagic differs")
    spec = dict(format=SPEC_FORMAT, kind="kernel", name="linux", platform="x86_64-linux",
                version=dict(upstream=plan["version"], scheme="dotted-v1", revision=revision),
                dependencies=[], requirements={}, provides={},
                provenance=dict(kernel_build_id=identifier, source=record["source"],
                                config_sha256=record["config_sha256"],
                                base_config_sha256=record["base_config_sha256"],
                                compiler_environment_sha256=record.get("compiler_environment_sha256")),
                metadata=dict(kernel_release=release))
    attachments = {name: build / name for name in ("kernel.json", "debian.config", "config.diff")}
    return spec, attachments
