#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Opt-in real test of two frozen Arch userspaces; downloads binary packages.

Run as the ordinary user in the dedicated Arch Distrobox. Requires a new/empty
--root and retains all environment/profile roots after success or failure.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


REPO = Path(__file__).resolve().parents[1]
ADAPTER = REPO / "tools/mpm-pacman-prototype"
PROGRAM = '''
import ctypes, errno, json, ssl, subprocess, sys, zlib
from pathlib import Path
libc = ctypes.CDLL(None)
libc.gnu_get_libc_version.restype = ctypes.c_char_p
environment = Path('/etc/mojt-environment').read_text().strip()
try:
    Path('/usr/mojt-readonly-probe').write_text('unexpected')
    readonly = False
except OSError as error:
    readonly = error.errno == errno.EROFS
child = subprocess.check_output(
    ['/usr/bin/python', '-I', '-B', '-c',
     "from pathlib import Path; print(Path('/etc/mojt-environment').read_text().strip())"],
    text=True).strip()
assert Path('input.txt').read_text() == 'shared work directory\\n'
Path('output.txt').write_text(environment + '\\n')
print(json.dumps(dict(version=sys.version.split()[0], prefix=sys.prefix,
    glibc=libc.gnu_get_libc_version().decode(), openssl=ssl.OPENSSL_VERSION,
    zlib=zlib.ZLIB_VERSION, environment=environment, child=child, readonly=readonly)))
'''


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.absolute()
    try:
        require(not root.is_symlink() and (not root.exists() or (root.is_dir() and not any(root.iterdir()))),
                "choose a new/empty test root; existing roots are never reset")

        def mpm(*arguments, capture=False, cwd=None):
            result = subprocess.run([sys.executable, str(ADAPTER), "--root", str(root),
                                     "ports", *map(str, arguments)], text=True, check=True, cwd=cwd,
                                    stdout=subprocess.PIPE if capture else None)
            return result.stdout.strip() if capture else ""

        def state():
            return json.loads(mpm("status", capture=True))

        mpm("check")
        print(f"Retained pacman lab: {root}", flush=True)
        mpm("update", "--manifest", REPO / "manifests/mpm-pacman-a.toml", "-y")
        require(not state()["installed"], "update installed payloads")
        mpm("install", "--dry-run")
        require(not state()["installed"], "preview installed payloads")
        mpm("install", "-y")
        first = state()
        first_key = first["active"]["cli"]
        old_profile = (root / "current").resolve()
        project = root / "test-project"
        project.mkdir()
        (project / "input.txt").write_text("shared work directory\n")
        pin = project / "pin.json"
        pin.write_text(json.dumps(dict(purpose="experiment-reference-only", generation=str(old_profile),
                                       identity=first_key, record=first["installed"][first_key]), indent=2) + "\n")
        pin_bytes = pin.read_bytes()

        def probe(key):
            result = json.loads(mpm("run", key, "python3", "--", "-I", "-B", "-c", PROGRAM,
                                    capture=True, cwd=project))
            require(result["environment"] == result["child"] == key, "wrong parent or child runtime root")
            require(result["readonly"], "environment /usr is not mounted read-only")
            require((project / "output.txt").read_text().strip() == key, "work directory bind failed")
            print(json.dumps(result, indent=2), flush=True)
            return result

        a = probe(first_key)
        mpm("update", "--manifest", REPO / "manifests/mpm-pacman-b.toml", "-y")
        require(state()["installed"] == first["installed"], "refresh changed installed environments")
        mpm("install", "--dry-run")
        mpm("install", "-y")
        second = state()
        require(second["active"] == first["active"], "second install changed activation")
        require(len(second["installed"]) == 2, "expected two retained environments")
        second_key = next(k for k in second["installed"] if k != first_key)
        b = probe(second_key)
        require(a["version"] != b["version"], "snapshots did not yield different Python versions")
        print("PASS: two binary environments run different Python versions with their own runtime roots", flush=True)

        mpm("activate", second_key, "-y")
        require(state()["active"]["cli"] == second_key, "activation selected wrong environment")
        require(state()["installed"] == second["installed"], "activation changed retained environments")
        # Exercise the generated launcher itself, not only the explicit run API.
        current = json.loads(subprocess.check_output(
            [str(root / "current/bin/python3"), "-I", "-B", "-c", PROGRAM], cwd=project, text=True))
        saved = json.loads(subprocess.check_output(
            [str(old_profile / "bin/python3"), "-I", "-B", "-c", PROGRAM], cwd=project, text=True))
        require(current["environment"] == second_key and saved["environment"] == first_key,
                "active or saved profile selected wrong runtime")
        require(pin.read_bytes() == pin_bytes, "captured project reference changed")
        print("PASS: active profile uses B; captured profile still uses A", flush=True)

        for key in (first_key, second_key):
            mpm("run", key, "curl", "--", "-q", "--fail", "--silent", "--show-error", "--max-time", "30",
                "--output", "/dev/null", "https://cache.nixos.org/nix-cache-info", cwd=project)
        print("PASS: HTTPS succeeds in both runtime roots", flush=True)
        before = os.readlink(root / "current")
        mpm("install", "-y")
        require(os.readlink(root / "current") == before, "repeat install changed selected profile")
        require(pin.read_bytes() == pin_bytes, "repeat install changed project reference")
        print("PASS: repeat install preserves selection and captured project reference", flush=True)
        print(f"Retained experiment reference: {pin}")
        print("Environment-level probe only; package-level profiles/upgrades and production project locks remain open.")
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError, StopIteration) as error:
        print(f"Pacman environment acceptance failed: {error}\nRetained lab: {root}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
