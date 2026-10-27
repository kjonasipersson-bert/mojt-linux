#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Isolated real selector transaction acceptance using an already-exported hello catalog.

Retains its new lab/GC roots. Never points at shared Ports state or changes System.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def invoke(command, *args, json_output=False):
    result = subprocess.run([*command, *args], text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    if json_output:
        return json.loads(result.stdout)
    print(result.stdout, end="", flush=True)
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result.stdout


def exercise(root, catalog_path, old, new, series, tool):
    if root.exists():
        raise ValueError("acceptance root must not exist; supply a new lab directory")
    value = json.loads(catalog_path.read_text())
    rows = [r for r in value["candidates"] if r["name"] == "hello" and r["release_id"] == old]
    if len(rows) != 1:
        raise ValueError("acceptance requires one old hello build in the catalog")
    if len([r for r in value["candidates"] if r["name"] == "hello" and r["release_id"] == new]) != 1:
        raise ValueError("acceptance requires one new hello build in the catalog")
    root.parent.mkdir(parents=True, exist_ok=True)
    old_view = root.parent / (root.name + "-old-catalog.json")
    with old_view.open("x") as stream:
        json.dump(dict(value, candidates=rows), stream)
    command = [sys.executable, "-I", str(tool), "--root", str(root), "ports"]
    def call(*args, **kwargs):
        return invoke(command, *args, **kwargs)
    def state():
        return call("status", json_output=True)
    def snapshot():
        return (state(), (root / "current").readlink(),
                sorted(p.name for p in (root / "gcroots").iterdir()),
                call("history", "--json", json_output=True))
    def check(condition, message):
        if not condition:
            raise AssertionError(message)
        print("PASS: " + message, flush=True)

    call("metadata", "--catalog", str(old_view), "--dry-run")
    check(not root.exists(), "metadata preview did not initialize state")
    call("metadata", "--catalog", str(old_view), "-y")
    call("install", "hello@" + series, "hello@=" + old, "-y")
    old_state = state()
    old_id = old_state["active"]["hello"]
    call("metadata", "--catalog", str(catalog_path), "-y")
    before = snapshot()
    call("install", "hello@" + series, "--dry-run")
    check(snapshot() == before, "install preview preserved profile, state, roots and history")
    call("install", "hello@" + series, "-y")
    installed = state()
    check(len(installed["installed"]) == 2 and installed["active"]["hello"] == old_id,
          "later install retained new artifact without moving accepted default")
    call("activate", old_id, "-y")
    before = snapshot()
    call("upgrade", "hello", "--dry-run")
    check(snapshot() == before, "upgrade preview preserved profile, state, roots and history")
    call("upgrade", "hello", "-y")
    upgraded = state()
    exact = [r for r in upgraded["requests"].values() if r["selector"]["kind"] == "exact"]
    moving = [r for r in upgraded["requests"].values() if r["selector"]["kind"] == "series"]
    check(exact[0]["target"] == old_id and upgraded["active"]["hello"] == old_id,
          "upgrade preserved exact request and pinned default")
    new_id = moving[0]["target"]
    check(upgraded["installed"][new_id]["version"] == new and new_id != old_id,
          "series request advanced to new release")
    alias = root / "current/bin" / ("hello-" + series)
    check(alias.resolve() == Path(upgraded["installed"][new_id]["output"]) / "bin/hello",
          "series alias advanced independently of pinned default")
    call("activate", "hello@" + series, "-y")
    check(state()["active"]["hello"] == new_id, "installed series activation selected new artifact")
    before = snapshot()
    call("upgrade", "-y")
    check(snapshot() == before, "repeat upgrade was a complete no-op")
    for key in (old_id, new_id):
        output = Path(state()["installed"][key]["output"]) / "bin/hello"
        print(subprocess.check_output([str(output), "--version"], text=True).splitlines()[0])
    check(old_id in state()["installed"], "both executable hello artifacts retained")
    print("No System changes or physical collection performed; selector lab retained: " + str(root))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--old", default="2.12.1")
    parser.add_argument("--new", default="2.12.3")
    parser.add_argument("--series", default="2.12")
    args = parser.parse_args()
    exercise(args.root.absolute(), args.catalog.absolute(), args.old, args.new, args.series,
             Path(__file__).resolve().parents[1] / "tools/mpm-nix-prototype")


if __name__ == "__main__":
    main()
