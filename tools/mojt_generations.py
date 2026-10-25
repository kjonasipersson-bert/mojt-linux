# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Additional explicitly selected boot pairs for a NEW experimental VM image."""

from pathlib import Path
import stat
import subprocess
import tomllib


PATHS = ("kernel", "modules_dir", "system_payload", "firmware_root")


def plan(path, validate):
    """Paths in a plan are relative to its containing directory, never the cwd."""
    if path is None:
        return []
    path = Path(path).resolve(strict=True)
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    if (set(data) != {"format", "boot"} or type(data["format"]) is not int or
            data["format"] != 1 or not isinstance(data["boot"], list) or not data["boot"]):
        raise ValueError("generation plan needs format = 1 and [[boot]] entries")
    result, seen = [], set()
    for entry in data["boot"]:
        if not isinstance(entry, dict) or not {"base", "system"} <= set(entry) or \
                set(entry) - {"base", "system", *PATHS}:
            raise ValueError("generation entry needs explicit base/system and supported input paths")
        value = {key: validate(entry[key]) for key in ("base", "system")}
        pair = value["base"], value["system"]
        if pair in seen:
            raise ValueError("duplicate boot pair in generation plan")
        seen.add(pair)
        for key in PATHS:
            if key in entry:
                if not isinstance(entry[key], str) or not entry[key]:
                    raise ValueError("generation input path must be a nonempty string")
                value[key] = (path.parent / entry[key]).resolve(strict=True)
        result.append(value)
    return result


def compatible_base(target, first, second):
    """Conservative experiment gate, not a general Base/System ABI policy."""
    records = []
    for version in (first, second):
        source = target / "releases" / f"base-{version}.toml"
        if source.is_symlink() or not source.is_file():
            raise ValueError("additional Base requires committed release metadata")
        records.append(tomllib.loads(source.read_text(encoding="utf-8")))
    for record in records:
        if (type(record.get("format")) is not int or record["format"] != 1 or
                record.get("base", {}).get("architecture") != "x86_64" or
                record.get("abi", {}).get("libc") != "glibc" or
                not record.get("abi", {}).get("libc_version") or
                record.get("state", {}).get("layout_version") != 1):
            raise ValueError("additional Base metadata outside generation experiment contract")
    if (records[0]["abi"] != records[1]["abi"] or records[0]["state"] != records[1]["state"]):
        raise ValueError("generation experiment requires identical declared Base ABI and state policy")
    if any(record["base"]["version"] != version for record, version in zip(records, (first, second))):
        raise ValueError("Base metadata version differs from selected generation")


def copy_new(source, destination):
    subprocess.run(["cp", "-a", "--", str(source), str(destination)], check=True)


def identical_or_copy(source, destination, tree_hash):
    """Whole immutable objects must agree, including links and modes."""
    if destination.is_symlink():
        raise ValueError(f"generation destination is a symlink: {destination}")
    if destination.exists():
        if source.is_dir() and not source.is_symlink() and destination.is_dir():
            equal = tree_hash(source) == tree_hash(destination)
        else:
            equal = (source.is_file() and not source.is_symlink() and destination.is_file() and
                     source.read_bytes() == destination.read_bytes() and
                     stat.S_IMODE(source.stat().st_mode) == stat.S_IMODE(destination.stat().st_mode))
        if not equal:
            raise ValueError(f"conflicting immutable generation/object: {destination.name}")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        copy_new(source, destination)


def add_missing(source, destination):
    """Copy missing state entries without traversing existing machine symlinks."""
    for item in source.iterdir():
        target = destination / item.name
        mode = item.lstat().st_mode
        if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode) or stat.S_ISLNK(mode)):
            raise ValueError("special file in additional configuration defaults")
        if not target.exists() and not target.is_symlink():
            copy_new(item, target)
        elif stat.S_ISDIR(mode) and target.is_dir() and not target.is_symlink():
            add_missing(item, target)


def merge(tree, candidate, base, system, tree_hash):
    """Called on private staging only; nothing is published until the image is complete."""
    for name in (f"base/{base}", f"releases/base-{base}.toml", f"system/{system}"):
        identical_or_copy(candidate / name, tree / name, tree_hash)
    store = tree / "nix/store"
    store.mkdir(parents=True, exist_ok=True)
    for obj in (candidate / "nix/store").iterdir():
        identical_or_copy(obj, store / obj.name, tree_hash)
    roots = f"nix/var/nix/gcroots/mojt-system/{system}"
    if (candidate / roots).is_dir():
        identical_or_copy(candidate / roots, tree / roots, tree_hash)
    # Retain the first pair's state and selection links. Existing bytes always win.
    for name in ("etc", "var"):
        add_missing(candidate / "state" / name, tree / "state" / name)


def scaffold(base, require_directory):
    for name in ("etc", "var", "dev", "proc", "sys"):
        require_directory(base / name, f"Base /{name}")
    for name in ("nix", "run", "tmp"):
        point = base / name
        if point.is_symlink() or (point.exists() and
                (not point.is_dir() or any(point.iterdir()))):
            raise ValueError(f"conflicting Base mountpoint /{name}")
        point.mkdir(exist_ok=True)
