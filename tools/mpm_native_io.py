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


def unpack_regular(path, body, target, *, symlinks=False):
    """Second pass over our frozen verified archive; no extract/extractall calls."""
    artifact.validate_descriptor(body)
    require(all(r["type"] in (("file", "directory", "symlink") if symlinks else ("file", "directory")) for r in body["files"]), "materialization requires regular entries")
    kind = body["kind"]
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(["zstd", "-q", "-d", "-c", "--", str(path)], stdout=subprocess.PIPE, stderr=errors)
        try:
            with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
                member = archive.next()
                require(member is not None and member.name == "./" + kind and member.isdir(), "native category differs")
                member = archive.next()
                require(member is not None and member.name == "./" + kind + "/artifact.json" and member.isfile()
                        and member.size <= artifact.MAX_METADATA, "native descriptor missing")
                require(archive.extractfile(member).read() == artifact.canonical(body) + b"\n", "frozen descriptor differs")
                for row in body["files"]:
                    member = archive.next()
                    require(member is not None and member.name == "./" + kind + "/" + row["path"], "frozen member differs")
                    destination = target / row["path"]
                    if row["type"] == "directory":
                        require(member.isdir(), "directory type differs")
                        destination.mkdir(mode=0o700)
                    elif row["type"] == "symlink":
                        require(member.issym() and member.linkname == row['target'], 'link target differs')
                        # Descriptor validation prohibits descendants of a link.
                        # No extraction/chmod/open operation follows this entry.
                        destination.symlink_to(row['target'])
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

