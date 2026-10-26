#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Export binary System inputs inside the existing Nix Distrobox, without sudo."""

import argparse
from datetime import datetime, timezone
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import mojt_system as system


REPO = Path(__file__).resolve().parents[1]


def nix_adapter():
    loader = importlib.machinery.SourceFileLoader("mojt_nix_backend", str(REPO / "tools/mpm-nix-prototype"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def prepare(args):
    system.require(os.geteuid() != 0, "prepare inside the Nix Distrobox as the ordinary user, without sudo")
    for name in ("nix-store", "nix-instantiate", "cp"):
        system.require(shutil.which(name), "missing preparation tool: " + name)
    output = args.output.absolute()
    system.require(not os.path.lexists(output), "System output must not exist")
    system.require(not output.is_relative_to("/nix"), "export outside /nix")
    nix = nix_adapter()
    source = nix.catalog_from_manifest(args.source_manifest)["source"]
    system.require(source["system"] == "x86_64-linux", "System VM requires x86_64-linux")
    requests = [dict(name=name, attribute=attribute, commands=[])
                for name, attribute in system.roles(args.step).items()]
    selected = json.loads(nix.run(
        "nix-instantiate", "--eval", "--strict", "--json",
        "--option", "allow-import-from-derivation", "false",
        "--expr", nix.EVALUATE, "--argstr", "requestJSON",
        json.dumps(dict(source=source, ports=requests))))
    packages = {item["name"]: {k: item[k] for k in ("attribute", "version", "output")}
                for item in selected}
    system.require(set(packages) == set(system.roles(args.step)), "invalid evaluated System roles")
    for name, package in packages.items():
        system.require(package["attribute"] == system.roles(args.step)[name], "evaluated attribute changed")
        system.store_path(package["output"])
        print(f"{name}: {package['version']} -> {package['output']}", flush=True)
        nix.run("nix-store", "--realise", package["output"], "--dry-run")
    if args.dry_run:
        print("Preview only. No payload or GC roots written.")
        return
    if not args.yes and input("Import binary outputs and export the System payload? [y/N] ").lower() != "y":
        print("Cancelled.")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".mojt-system-", dir=output.parent) as temporary:
        work = Path(temporary)
        roots = work / "roots"
        (roots / "gcroots").mkdir(parents=True)
        # The source must survive evaluation/export even when only metadata is exported.
        nix.retain(roots, source["store"])
        outputs = [p["output"] for p in packages.values()]
        for value in outputs:
            nix.retain(roots, value)
        if args.step >= 3:
            outputs.append(source["store"])
        closure = sorted(set(nix.run("nix-store", "--query", "--requisites", *outputs).splitlines()))
        system.require(set(outputs) <= set(closure), "incomplete System closure")
        payload = work / "payload"
        store = payload / "nix/store"
        store.mkdir(parents=True)
        objects = []
        for index, value in enumerate(closure, 1):
            original = system.store_path(value)
            print(f"Export {index}/{len(closure)}: {original.name}", flush=True)
            # Nix verifies registered source contents before the transfer.
            nix.run("nix-store", "--verify-path", value)
            subprocess.run(["cp", "-a", "--no-preserve=ownership", "--reflink=auto", "--",
                            value, str(store / original.name)], check=True)
            objects.append(dict(path=value, nar_hash=nix.run("nix-store", "--query", "--hash", value),
                                tree_sha256=system.tree_hash(store / original.name)))
        with (payload / "registration").open("wb") as stream:
            subprocess.run(["nix-store", "--dump-db", *closure], stdout=stream, check=True)
        record = dict(format=1, step=args.step, source=source, packages=packages, objects=objects,
                      registration_sha256=system.file_hash(payload / "registration"),
                      prepared_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        system.write(payload / "system.json", json.dumps(record, indent=2) + "\n")
        system.load_payload(payload)
        system.require(not os.path.lexists(output), "System output appeared during preparation")
        payload.rename(output)
    print(f"System payload: {output}")
    print(f"Step: {args.step}; exported store objects: {len(closure)}")
    print("Prepared inputs only. Boot/service/network acceptance must run in the Mojt VM.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step", type=int, choices=tuple(system.ROLES), required=True)
    parser.add_argument("--source-manifest", type=Path,
                        default=REPO / "manifests/mpm-nix-example.toml")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("-y", "--yes", action="store_true")
    args = parser.parse_args()
    try:
        prepare(args)
        return 0
    except (OSError, ValueError, KeyError, TypeError, EOFError, subprocess.CalledProcessError) as error:
        print(f"mojt-system-prepare: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
