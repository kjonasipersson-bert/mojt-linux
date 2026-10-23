#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Opt-in real Nix test: parallel Python versions and a captured project reference.

Imports binary packages and changes profiles only under a new/empty --root.
Retains the experiment and Nix GC roots after completion or failure.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib


REPO = Path(__file__).resolve().parents[1]
ADAPTER = REPO / "tools/mpm-nix-prototype"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="new/empty directory; keep it after the run")
    parser.add_argument("--source-manifest", type=Path,
                        default=REPO / "manifests/mpm-nix-example.toml")
    args = parser.parse_args()
    root = args.root.absolute()
    try:
        require(not root.is_symlink(), "test root must not be a symlink")
        require(not root.exists() or (root.is_dir() and not any(root.iterdir())),
                "choose a new/empty test root; existing experiments are never reset")
        template = tomllib.loads(args.source_manifest.read_text())
        source = dict(template["nixpkgs"])
        supplied = Path(source["path"]).expanduser()
        source["path"] = str((supplied if supplied.is_absolute()
                              else args.source_manifest.parent / supplied).resolve(strict=True))

        def mpm(*arguments, capture=False):
            result = subprocess.run([sys.executable, str(ADAPTER), "--root", str(root),
                                     "ports", *arguments], text=True, check=True,
                                    stdout=subprocess.PIPE if capture else None)
            return result.stdout

        def state():
            return json.loads(mpm("status", capture=True))

        def manifest(directory, attribute):
            path = directory / (attribute + ".toml")
            source_text = "\n".join(key + " = " + json.dumps(source[key])
                                    for key in ("path", "revision", "system"))
            with path.open("x") as stream:
                stream.write("format = 1\n\n[nixpkgs]\n" + source_text + "\n\n"
                             '[[ports]]\nname = "python"\nattribute = ' + json.dumps(attribute)
                             + '\ncommands = ["python3"]\n')
            return str(path)

        def interpreter(command, minor):
            code = ("import ssl, sys, zlib; "
                    f"assert sys.version_info[:2] == (3, {minor}), sys.version; "
                    "print(sys.version.split()[0], ssl.OPENSSL_VERSION, zlib.ZLIB_VERSION)")
            subprocess.run([str(command), "-I", "-c", code], check=True)

        print(f"Retained test root: {root}", flush=True)
        with tempfile.TemporaryDirectory(prefix="mojt-python-manifests-") as temporary:
            directory = Path(temporary)
            mpm("update", "--manifest", manifest(directory, "python312"), "-y")
            initial = state()
            require(not initial["installed"] and not initial["active"], "update installed applications")
            mpm("install", "python", "--dry-run")
            require(state() == initial, "preview changed the selected state")
            mpm("install", "python", "-y")
            first = state()
            first_key = first["active"]["python"]
            first_record = first["installed"][first_key]
            require(first_record["attribute"] == "python312", "wrong first interpreter")
            interpreter(root / "current/bin/python3", 12)

            generation = (root / "current").resolve(strict=True)
            project = root / "test-project"
            project.mkdir()
            pin = project / "pin.json"
            with pin.open("x") as stream:
                json.dump(dict(format=1, purpose="experiment-reference-only",
                               generation=str(generation), identity=first_key,
                               artifact=first_record), stream, indent=2)
                stream.write("\n")
            pin_bytes = pin.read_bytes()

            mpm("update", "--manifest", manifest(directory, "python313"), "-y")
            require(state()["installed"] == first["installed"], "update changed installed objects")
            mpm("install", "python", "--dry-run")
            mpm("install", "python", "-y")
            second = state()
            require(second["active"] == first["active"], "second install retargeted activation")
            require(len(second["installed"]) == 2, "expected exactly two retained interpreters")
            second_key = next(key for key, record in second["installed"].items()
                              if record["attribute"] == "python313")
            require(second_key != first_key, "interpreter identities are not distinct")
            require(second["installed"][first_key] == first_record, "first artifact metadata changed")
            interpreter(root / "current/bin/python3", 12)
            print("PASS: two Python versions installed; default remains Python 3.12", flush=True)

            for key, minor in ((first_key, 12), (second_key, 13)):
                record = second["installed"][key]
                suffix = key.split("@=", 1)[1]
                interpreter(root / "current/bin" / ("python3-" + suffix), minor)
                roots = subprocess.check_output(
                    ["nix-store", "--query", "--roots", record["output"]], text=True)
                expected = str(root / "gcroots" / Path(record["output"]).name)
                require(expected in {line.split(" -> ", 1)[0] for line in roots.splitlines()},
                        "MPM GC root not registered for " + key)

            mpm("activate", second_key, "-y")
            interpreter(root / "current/bin/python3", 13)
            require(state()["active"]["python"] == second_key, "activation selected wrong identity")
            require(pin.read_bytes() == pin_bytes, "captured project reference changed")
            saved = json.loads(pin.read_text())
            require(state()["installed"][first_key] == saved["artifact"], "pinned closure metadata changed")
            require(state()["installed"] == second["installed"], "activation changed installed objects")
            interpreter(Path(saved["generation"]) / "bin/python3", 12)
            print("PASS: default is Python 3.13; captured project still runs Python 3.12", flush=True)

            current = os.readlink(root / "current")
            mpm("install", "python", "-y")
            require(os.readlink(root / "current") == current, "repeat install published a new generation")
            require(pin.read_bytes() == pin_bytes, "repeat install changed project reference")
            interpreter(Path(saved["generation"]) / "bin/python3", 12)
            print("PASS: repeat installation preserved profile and captured project reference", flush=True)
            print(f"Retained experiment reference: {pin}")
            print("Production project profiles/locks and upgrade policies are not implemented.")
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError, StopIteration) as error:
        print(f"Python/Nix acceptance test failed: {error}\nRetained test root: {root}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
