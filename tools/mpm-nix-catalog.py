#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Export a finite MPM catalog from already-local Nix outputs and pinned sources.

No channel refresh, payload realization, GC roots, MPM state or activation.
The backend owns all Nix paths/commands/evidence; mpm_selection knows none.
"""
import argparse
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import sys
import tomllib


def load_backend():
    loader = importlib.machinery.SourceFileLoader("_catalog_nix", str(Path(__file__).with_name("mpm-nix-prototype")))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    backend = importlib.util.module_from_spec(spec)
    loader.exec_module(backend)
    return backend


def prepare_catalog(backend, sources, name, attribute, *, catalog_name="ports-main", preferred_source=None, stability="unknown"):
    backend.require(sources, "provide at least one explicitly pinned source")
    core = backend.selection_core()
    records, candidates, platform = {}, [], None
    for source_id, manifest in sources:
        backend.require(source_id and source_id not in records, "empty or repeated source ID")
        path = Path(manifest)
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        backend.require(type(raw.get("format")) is int and raw["format"] == 1 and "nixpkgs" in raw, "expected a pinned source manifest")
        source = backend.source_from_fields(raw["nixpkgs"], path.parent)
        if platform is None:
            platform = source["system"]
        backend.require(platform == source["system"], "sources target different platforms")
        record = backend.resolve_package(source, name, attribute)
        backend.require(Path(record["output"]).exists(),
                        "output is not local; explicitly import it in an isolated lab first: " + record["output"])
        closure = sorted(backend.run("nix-store", "--query", "--requisites", record["output"]).splitlines())
        backend.require(record["output"] in closure, "output missing from closure")
        for output in closure:
            backend.store_path(output)
        hashes = backend.run("nix-store", "--query", "--hash", *closure).splitlines()
        backend.require(len(hashes) == len(closure) and all(hashes), "invalid closure evidence")
        records[source_id] = dict(backend="nix", identity=dict(source,
                                    attribute=attribute, output_selection="lib.getBin",
                                    evaluation=dict(config={}, overlays=[])))
        version = record["version"]
        try:
            core.components(version)
            scheme = "dotted-v1"
        except ValueError:
            scheme = "opaque-v1"
        # Stability is supplied explicitly by the catalog producer, not inferred
        # from numeric spelling or the name of a Nixpkgs channel.
        candidates.append(dict(name=name, release_id=version, upstream_version=version,
            version_scheme=scheme, stability=stability, source=source_id,
            artifact=record["output"], preferred=source_id == preferred_source,
            integrity=dict(closure=[dict(path=p, nar_hash=h) for p, h in zip(closure, hashes)])))
    backend.require(preferred_source is None or preferred_source in records, "unknown preferred source")
    result = dict(format=core.FORMAT, area="ports", name=catalog_name, channel="stable", platform=platform,
                  sources=records, candidates=candidates)
    core.Catalog.from_dict(result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", required=True, metavar="ID=MANIFEST")
    parser.add_argument("--name", default="hello")
    parser.add_argument("--attribute", default=None)
    parser.add_argument("--catalog-name", default="ports-main")
    parser.add_argument("--stability", choices=("stable", "preview", "unknown"), default="unknown",
                        help="explicit producer classification; default unknown (exact requests only)")
    parser.add_argument("--prefer-source", help="explicit preferred build source on equal-release builds")
    parser.add_argument("--output", type=Path, required=True, help="new JSON file; existing files are never replaced")
    args = parser.parse_args(argv)
    try:
        sources = []
        for value in args.source:
            source_id, separator, manifest = value.partition("=")
            if not separator or not source_id or not manifest:
                raise ValueError("--source must be ID=MANIFEST")
            sources.append((source_id, manifest))
        result = prepare_catalog(load_backend(), sources, args.name, args.attribute or args.name,
                                 catalog_name=args.catalog_name, preferred_source=args.prefer_source, stability=args.stability)
        # Create only after all backend reads and validation; O_EXCL also refuses symlinks.
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(result, indent=2) + "\n")
        print("Catalog written: " + str(args.output))
        print("Declared stability: " + args.stability + "; nonnumeric versions remain exact-only.")
        print("No payloads, roots, package state or activation changed.")
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print("mpm-nix-catalog: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
