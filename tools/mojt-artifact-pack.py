#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Package frozen native artifacts, or inspect/verify them without installation."""
import argparse
import json
from pathlib import Path
import sys
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mojt_artifact as artifact


def main(argv=None, *, prog=None):
    parser = argparse.ArgumentParser(prog=prog,description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    generic = commands.add_parser("pack")
    generic.add_argument("--source", type=Path, required=True)
    generic.add_argument("--spec", type=Path, required=True)
    generic.add_argument("--attachment", action="append", default=[], metavar="NAME=FILE")
    port = commands.add_parser("port")
    port.add_argument("--manifest", type=Path, required=True)
    kernel = commands.add_parser("kernel")
    kernel.add_argument("--build", type=Path, default=Path("kernel-result"))
    kernel.add_argument("--revision", type=int, default=1)
    kernel.add_argument("--attachment", action="append", default=[], metavar="NAME=FILE")
    base = commands.add_parser("base")
    base.add_argument("--release", type=Path, required=True)
    base.add_argument("--revision", type=int, required=True)
    base.add_argument("--attachment", action="append", default=[], metavar="NAME=FILE")
    system = commands.add_parser("system")
    system_input=system.add_mutually_exclusive_group(required=True)
    system_input.add_argument("--tree",type=Path)
    system_input.add_argument("--running",action="store_true",help="package a component-based successor of the running native System")
    system.add_argument("--firmware",choices=("none","keep"),default="none",help="component System firmware selection (default: none)")
    system.add_argument("--user-bus", action="store_true", help="add or repair the reviewed D-Bus user units in a running-System successor")
    system.add_argument("--expected-running", help="require this exact running System artifact when packaging a successor")
    system.add_argument("--openssl-output",help="retain an exact installed Nix OpenSSL output in the new running-System successor")
    system.add_argument("--generation")
    system.add_argument("--version")
    system.add_argument("--revision", type=int)
    system.add_argument("--nix-store", type=Path)
    for command in (generic, kernel, base, system, port):
        command.add_argument("--output", type=Path, required=command is not kernel,
                             default=Path("kernel-package") if command is kernel else None)
    verify = commands.add_parser("verify")
    verify.add_argument("archive", type=Path)
    verify.add_argument("--expected-id")
    args = parser.parse_args(argv)
    try:
        if args.action == "verify":
            result = artifact.verify(args.archive, args.expected_id)
        elif args.action == "port":
            with args.manifest.open('rb') as stream:
                spec = tomllib.load(stream)
            artifact.require(spec['kind'] == 'port', 'manifest must describe a Port')
            spec['version'].setdefault('revision', None)
            result = artifact.pack(args.manifest.parent / 'payload', spec, args.output, numeric_owner=(0, 0))
        elif args.action == "system":
            if args.running:
                from mojt_system_package import package_installed,local_reference
                import mpm_base as base
                import mpm_system as system
                from mpm_cli import Runtime
                from mpm_boot_status import read_running,description
                artifact.require(args.nix_store is None,'--nix-store belongs to assembled-tree packaging')
                runtime=Runtime();running=read_running(runtime)
                artifact.require(running is not None,'running native System identity required')
                baseline=description(running)['system']['artifact']
                artifact.require(args.expected_running is None or baseline == args.expected_running,
                                 'running System artifact differs from --expected-running')
                body,_=system.object_record(runtime.disk,baseline)
                revision=1 if args.revision is None else args.revision
                version = args.version if args.version is not None else body['version']['upstream']
                release_revision = revision if args.version is not None else body['version']['revision'] + revision
                label = args.generation or f"system-{version}-r{release_revision}"
                crypto=adapter=None
                if args.openssl_output is not None:
                    from mpm_nix_binary import NixBinaryAdapter
                    adapter=NixBinaryAdapter(runtime.system_bin/'nix-store')
                    crypto=local_reference(adapter,args.openssl_output)
                    adapter.verify_path(crypto,args.openssl_output+'/bin/openssl',executable=True)
                result=package_installed(runtime.disk,baseline,args.output,label=label,revision=revision,
                    firmware=args.firmware,openssl_reference=crypto,adapter=adapter,
                    user_bus=args.user_bus,upstream=args.version)
            else:
                artifact.require(args.openssl_output is None and not args.user_bus and args.expected_running is None,
                                 '--openssl-output, --user-bus and --expected-running require --running')
                from mojt_system_package import package
                from mpm_nix_binary import NixBinaryAdapter
                artifact.require(all(v is not None for v in (args.generation,args.version,args.revision,args.nix_store)),
                                 'assembled tree packaging requires --generation, --version, --revision and --nix-store')
                artifact.require(args.nix_store.is_absolute(),'select an absolute retained nix-store helper')
                result=package(args.tree,args.generation,args.version,args.revision,args.output,adapter=NixBinaryAdapter(args.nix_store))
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
