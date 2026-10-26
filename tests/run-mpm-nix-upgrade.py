#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Opt-in real-Nix Ports upgrade acceptance in a NEW root; retains all roots.

One source tests no-ops and policies. Two pinned manifests can test changed
artifacts. No System mutation, implicit source refresh, source builds or GC.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--from-manifest", type=Path, default=(REPO / "ports.toml" if (REPO / "ports.toml").exists()
                                 else REPO / "manifests/mpm-nix-example.toml"))
    parser.add_argument("--to-manifest", type=Path)
    parser.add_argument("--name", default="hello")
    args = parser.parse_args()
    root = args.root.absolute()
    require(not root.is_symlink() and (not root.exists() or
            (root.is_dir() and not any(root.iterdir()))), "choose a NEW empty test root")

    def mpm(*arguments):
        result = subprocess.run([sys.executable, str(REPO / "tools/mpm-nix-prototype"),
                                 "--root", str(root), "ports", *arguments],
                                text=True, capture_output=True, check=True)
        print(result.stdout, end="", flush=True)
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        return result.stdout

    def state():
        return json.loads(mpm("status"))

    print(f"Retained upgrade lab: {root}", flush=True)
    mpm("update", "--manifest", str(args.from_manifest), "--dry-run")
    require(not root.exists(), "preview wrote the test root")
    mpm("update", "--manifest", str(args.from_manifest), "-y")
    mpm("install", args.name, "--attribute", args.name, "-y")
    old = state()
    key = old["active"][args.name]
    mpm("activate", key, "-y")  # Exact pin must survive a request upgrade.
    mpm("update", "--manifest", str(args.to_manifest or args.from_manifest), "-y")
    before = (root / "current").readlink()
    roots = sorted(p.name for p in (root / "gcroots").iterdir())
    mpm("upgrade", args.name, "--dry-run")
    require((root / "current").readlink() == before and
            sorted(p.name for p in (root / "gcroots").iterdir()) == roots, "preview changed state")
    mpm("upgrade", args.name, "-y")
    upgraded = state()
    target = upgraded["requests"][args.name + ":" + args.name]["target"]
    require(upgraded["active"][args.name] == key, "upgrade changed an exact pin")
    require(upgraded["installed"][key] == old["installed"][key], "old artifact changed")
    mpm("activate", target, "--follow", "-y")
    require(state()["active"][args.name] == target, "explicit follow did not select the target")
    before = (root / "current").readlink()
    mpm("upgrade", args.name, "-y")
    require((root / "current").readlink() == before, "repeat upgrade did not converge")
    rows = json.loads(mpm("history", "--json", "--limit", "1000"))
    require(rows and rows[0]["after"]["active"][args.name] == target, "history differs from selection")
    require(upgraded["catalog"] == state()["catalog"], "upgrade changed the source snapshot")
    if target == key:
        print("PASS: real import, no-op upgrade, exact/follow policy and history; NO changed artifact tested")
    else:
        require(any(r["action"] == "upgrade" for r in rows), "changed upgrade missing from history")
        print(f"PASS: real changed-artifact upgrade retained {key}; request now targets {target}")
    print("No System changes or physical collection performed; lab retained.")


if __name__ == "__main__":
    main()
