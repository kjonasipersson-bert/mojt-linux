#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Package frozen native artifacts, or inspect/verify them without installation."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mojt_artifact as artifact


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    generic = commands.add_parser("pack")
    generic.add_argument("--source", type=Path, required=True)
    generic.add_argument("--spec", type=Path, required=True)
    generic.add_argument("--attachment", action="append", default=[], metavar="NAME=FILE")
    kernel = commands.add_parser("kernel")
    kernel.add_argument("--build", type=Path, required=True)
    kernel.add_argument("--revision", type=int, required=True)
    kernel.add_argument("--attachment", action="append", default=[], metavar="NAME=FILE")
    base = commands.add_parser("base")
    base.add_argument("--release", type=Path, required=True)
    base.add_argument("--revision", type=int, required=True)
    base.add_argument("--attachment", action="append", default=[], metavar="NAME=FILE")
    for command in (generic, kernel, base):
        command.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("archive", type=Path)
    verify.add_argument("--expected-id")
    args = parser.parse_args(argv)
    try:
        if args.action == "verify":
            result = artifact.verify(args.archive, args.expected_id)
        else:
            if args.action == "kernel":
                spec, attachments = artifact.kernel_input(args.build, args.revision)
                source = args.build / "root"
            elif args.action == "base":
                spec, attachments = artifact.base_input(args.release, args.revision)
                source = args.release
            else:
                spec, attachments = artifact.read_json(args.spec), {}
                source = args.source
            for value in args.attachment:
                name, separator, path = value.partition("=")
                artifact.require(separator and name not in attachments, "invalid/duplicate attachment")
                attachments[name] = Path(path)
            result = artifact.pack(source, spec, args.output, attachments)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, RecursionError, artifact.tarfile.TarError) as error:
        print("mojt-artifact-pack: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
