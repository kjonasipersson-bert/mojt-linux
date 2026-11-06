#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Opt-in real Nix acceptance: ordinary programs, automatic exports and removal.

Use a new/empty --root. Retains all profiles, objects and GC roots.
No source builds, destructive GC, System changes or interactive editor startup.
"""

import argparse
import json
import os
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
    parser.add_argument("--source-manifest", type=Path,
                        default=REPO / "manifests/mpm-nix-example.toml")
    args = parser.parse_args()
    root = args.root.absolute()
    try:
        require(not root.is_symlink() and
                (not root.exists() or (root.is_dir() and not any(root.iterdir()))),
                "choose a new/empty test root; existing experiments are never reset")

        def mpm(*arguments, capture=False):
            result = subprocess.run([sys.executable, str(REPO / "tools/mpm-nix-prototype"),
                                     "--root", str(root), "ports", *arguments], text=True,
                                    check=True, stdout=subprocess.PIPE if capture else None)
            return result.stdout

        def state():
            return json.loads(mpm("status", capture=True))

        def execute(command, *arguments, generation=None):
            selected = generation or (root / "current").resolve(strict=True)
            subprocess.run([str(selected / "bin" / command),
                            *arguments], check=True)

        print(f"Retained ordinary-Ports lab: {root}", flush=True)
        mpm("update", "--manifest", str(args.source_manifest), "--dry-run")
        require(not (root / "current").exists(), "preview wrote a profile")
        mpm("update", "--manifest", str(args.source_manifest), "-y")
        initial = state()
        matches = json.loads(mpm("search", "hello", "--json", capture=True))
        require(any(r["attribute"] == "hello" for r in matches["matches"]), "hello not found")
        require(matches["source"] == initial["catalog"]["source"], "search source changed")
        # None of these need a per-package TOML entry; --attribute also exercises
        # automatic discovery even if the historical source manifest curates hello.
        for package in ("hello", "less", "git", "vim"):
            mpm("info", package)
            mpm("install", package, "--attribute", package, "--dry-run")
            require(package not in state()["active"], "preview activated an application")
            mpm("install", package, "--attribute", package, "-y")
        execute("hello")
        execute("less", "--version")
        execute("git", "--version")
        execute("vim", "--version")
        require((root / "current/bin/vi").is_file(), "vim output did not export vi")
        print("PASS: ordinary programs imported without per-package manifests; vi exported", flush=True)
        mpm("list")

        mpm("install", "python", "--attribute", "python312", "-y")
        first = state()["active"]["python"]
        saved = (root / "current").resolve(strict=True)
        project = root / "test-project"
        project.mkdir()
        pin = project / "pin.json"
        pin.write_text(json.dumps(dict(generation=str(saved), identity=first)) + "\n")
        pin_bytes = pin.read_bytes()
        mpm("install", "python", "--attribute", "python313", "-y")
        second = next(k for k, r in state()["installed"].items() if r["attribute"] == "python313")
        require(state()["active"]["python"] == first, "second install changed activation")
        mpm("activate", second, "-y")
        before = os.readlink(root / "current")
        preview = mpm("remove", second, "--dry-run", capture=True)
        require("Activate: python -> " + first in preview, "preview omitted exact fallback")
        require(os.readlink(root / "current") == before, "remove preview changed current")
        mpm("remove", second, "-y")
        require(state()["active"]["python"] == first, "historical fallback was not selected")
        require(second not in state()["installed"], "removed interpreter remains in current profile")
        execute("python3", "-I", "-c", "import sys; assert sys.version_info[:2] == (3,12)")
        # Remove the remaining interpreter too: it stays usable through the saved
        # generation and its GC roots, while disappearing from the current set.
        mpm("remove", "python", "-y")
        require("python" not in state()["active"], "last removal retained default")
        require(not os.path.lexists(root / "current/bin/python3"), "last removal retained alias")
        require(pin.read_bytes() == pin_bytes, "captured project reference changed")
        execute("python3", "-I", "-c", "import ssl,sys; assert sys.version_info[:2] == (3,12)",
                generation=saved)
        current = os.readlink(root / "current")
        mpm("install", "less", "-y")
        require(os.readlink(root / "current") == current, "repeat install changed profile")
        print("PASS: removal restores prior activation; last removal preserves captured profile", flush=True)
        print("No physical collection performed; production project locks and GC remain deferred.")
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, StopIteration, subprocess.CalledProcessError) as error:
        print(f"Ordinary Ports acceptance failed: {error}\nRetained lab: {root}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
