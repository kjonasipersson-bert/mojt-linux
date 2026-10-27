#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Read-only System candidate inspection with explicit installation facts."""
import argparse
import json
from pathlib import Path
import sys
import tomllib
import importlib.util
spec = importlib.util.spec_from_file_location("mojt_system_manifest", Path(__file__).with_name("mojt_system_manifest.py"))
model = importlib.util.module_from_spec(spec)
previous_bytecode = sys.dont_write_bytecode
try:
    sys.dont_write_bytecode = True
    spec.loader.exec_module(model)
finally:
    sys.dont_write_bytecode = previous_bytecode


def context_from_target(target, base):
    root = Path(target)
    record = tomllib.loads((root / "releases" / ("base-" + base + ".toml")).read_text())
    if record.get("format") != 1 or record["base"]["version"] != base:
        raise ValueError("unsupported or mismatched Base release metadata")
    current = root / "state/var/lib/mojt/ports/current/state.json"
    ports = None
    # A dangling current/profile is an error, not absence of shared state.
    selection = current.parent
    if selection.is_symlink() or selection.exists():
        state = json.loads(current.read_text())
        ports = dict(format=state["format"], capabilities=state.get("capabilities", {}))
    passwd = root / "state/etc/passwd"
    paths = []
    if passwd.exists():
        for line in passwd.read_text().splitlines():
            parts = line.split(":")
            if len(parts) != 7:
                raise ValueError("malformed persistent passwd entry")
            if parts[6].startswith("/run/mojt-system/"):
                paths.append(parts[6])
    return dict(format=model.CONTEXT, architecture=record["base"]["architecture"],
                base_abi=record["abi"], state_layout=record["state"]["layout_version"],
                ports=ports, required_system_paths=sorted(set(paths)))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--running", type=Path, help="explicit running System manifest; not inferred")
    parser.add_argument("--selected", type=Path, help="explicit next-boot manifest; unknown if omitted")
    context = parser.add_mutually_exclusive_group(required=True)
    context.add_argument("--context", type=Path, help="explicit mojt-system-context-v1 JSON")
    context.add_argument("--target", type=Path, help="offline directory installation/assembled tree")
    parser.add_argument("--base", help="exact Base in --target")
    args = parser.parse_args(argv)
    try:
        read = lambda p: json.loads(p.read_text()) if p else None
        if args.target and not args.base:
            raise ValueError("--target requires --base")
        facts = read(args.context) if args.context else context_from_target(args.target, args.base)
        candidate = read(args.candidate)
        report = model.compare(candidate, read(args.running), read(args.selected))
        report.update(model.check(candidate, facts))
        print(json.dumps(report, indent=2))
        return 0 if report["compatible"] else 1
    except (ValueError, OSError, KeyError, TypeError) as error:
        print("mojt-system-inspect: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
