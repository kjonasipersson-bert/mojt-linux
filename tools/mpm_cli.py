# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Shared source/System frontend; optional providers are loaded only on demand."""
from contextlib import contextmanager
from dataclasses import dataclass
import argparse
import json
import os
from pathlib import Path
import runpy
import sys


@dataclass(frozen=True)
class Runtime:
    ports: Path = Path("/var/lib/mojt/ports")
    source: Path = Path("/run/mojt-system/ports.toml")
    disk: Path = Path("/run/mojt-disk")
    running: Path = Path("/run/mojt/deployment.json")
    helpers: Path = Path("/run/mojt-system/libexec/mpm/bin")
    system_bin: Path = Path("/run/mojt-system/bin")


def option(args, name):
    return any(a == name or a.startswith(name + "=") for a in args)


def help_text():
    print("usage: mpm {catalog,kernel,ports,base,system} ...\n"
          "  catalog                 explicit local catalog discovery\n"
          "  kernel                  install, status, plan, stage, select, rollback, resolve\n"
          "  ports                   install, activate, upgrade, update, list, history, ...\n"
          "  base/system             search, show, versions with --catalog FILE\n"
          "Base/System mutation commands are not implemented.\n"
          "Install retains content; Kernel selection changes next boot, never the running Kernel.")


def require_codec(runtime, args):
    if runtime is not None and "--help" not in args and "-h" not in args:
        codec = runtime.helpers / "zstd"
        if not codec.is_file() or not os.access(codec, os.X_OK):
            raise ValueError("selected System has no retained zstd helper; native verification is unavailable")


def resolve_ports(args):
    """Resolve the explicit finite catalog without importing its provider."""
    from mpm_selection import Catalog, resolve, render_selector
    parser = argparse.ArgumentParser(prog="mpm ports resolve")
    parser.add_argument("selector")
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    request = parser.parse_args(args)
    catalog = Catalog.from_dict(json.loads(request.catalog.read_text(encoding="utf-8")))
    if catalog.area != "ports":
        raise ValueError("release catalog belongs to another MPM area")
    selection = resolve(catalog, request.selector)
    if request.json:
        print(json.dumps(selection.to_dict(), indent=2))
    else:
        row = selection.candidate
        print("Request: " + render_selector(selection.selector))
        print("Catalog: " + selection.catalog_name + " (" + selection.channel + ", " + selection.platform + ")")
        print("View: " + selection.catalog_digest + "\nRelease: " + row.release_id)
        print("Artifact: " + row.backend + ":" + row.artifact)
        print("Sources: " + ", ".join(p["source"] for p in selection.provenance))
        print("Compatibility: " + row.compatibility + " (declared, not runtime verified)")
        print("Read-only resolution; no package, state or activation changes.")
    return 0


@contextmanager
def runtime_path(runtime):
    previous = os.environ.get("PATH")
    if runtime is not None:
        os.environ["PATH"] = ":".join((str(runtime.helpers), str(runtime.system_bin), "/usr/bin", "/bin"))
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = previous


def boot_options(args, runtime):
    """Defaults bind this installation, never a separately specified disk."""
    args = list(args)
    if runtime is None or option(args, "--disk-root") or "--help" in args or "-h" in args:
        return args
    args += ["--disk-root", str(runtime.disk)]
    if not option(args, "--baseline"):
        import mpm_deployment as deployment
        import mpm_kernel_boot as boot
        menu = boot.checked_file(runtime.disk / "boot/mojt/grub.cfg")
        if not menu.startswith(boot.HEADER.encode()):
            # An explicit runtime record binds the fresh native baseline.
            # current() still checks the complete menu; uname never adopts it.
            record = deployment.read_json(runtime.running)
            d = deployment.validate_deployment(record)
            relative = "boot/mojt/" + d["system"]["generation"] + "/" + d["base"]["release"]
            if deployment.read_json(runtime.disk / relative / "deployment.json") != record:
                raise ValueError("running record does not bind the native baseline; specify --baseline")
            args += ["--baseline", relative]
    if args[0] == "status" and not option(args, "--running-record") and runtime.running.is_file():
        args += ["--running-record", str(runtime.running)]
    return args


def dispatch(args, runtime):
    if not args or args in (["--help"], ["-h"]):
        help_text()
        return 0
    offset, roots = 0, []
    if len(args) >= 2 and args[0] == "--root":
        offset, roots = 2, args[:2]
    elif args[0].startswith("--root="):
        offset, roots = 1, args[:1]
    command = args[offset:]
    area = command[0] if command else None
    action = command[1] if len(command) > 1 else None
    if runtime is not None and os.geteuid() != 0:
        readonly = (command[2:] in (["--help"], ["-h"]) or
            area == "catalog" and action in ("search", "show", "versions", "resolve-kernel", "--help", "-h") or
            area == "kernel" and action in (None, "status", "plan", "resolve", "--help", "-h") or
            area == "ports" and action in (None, "status", "list", "history", "resolve", "search", "info", "--help", "-h") or
            area in ("base", "system", "ports", "kernel") and
                action in ("search", "show", "versions") and option(command, "--catalog"))
        if not readonly:
            raise ValueError("shared installation changes require an administrator")
    if area == "kernel" and action in (None, "-h", "--help"):
        help_text()
        return 0
    if area == "kernel" and action in ("stage", "select", "rollback", "status"):
        boot_status = action == "status" and (option(command, "--disk-root") or
            runtime is not None and not roots and not option(command, "--root") and
            (runtime.running.is_file() or (runtime.disk / "boot/mpm/format").is_file()))
        if action != "status" or boot_status:
            if roots:
                raise ValueError("kernel boot commands use --disk-root, not --root")
            require_codec(runtime, command)
            if (runtime is not None and action == "stage" and "--dry-run" not in command
                    and "--help" not in command and "-h" not in command):
                tool = runtime.system_bin / "modprobe"
                if not tool.is_file() or not os.access(tool, os.X_OK):
                    raise ValueError("selected System has no modprobe; Kernel staging is unavailable")
            from mpm_kernel_boot import main
            return main(boot_options(command[1:], runtime))
    if area == "kernel" and action in ("install", "status", "plan"):
        if action != "status" or "--verify" in command:
            require_codec(runtime, command)
        if runtime is not None and not roots and not option(command, "--root"):
            if "--help" not in command and "-h" not in command and not (runtime.disk / "boot/mojt").is_dir():
                raise ValueError("running installation disk is unavailable; use an explicit --root")
            roots = ["--root", str(runtime.disk / "kernel")]
        if action == "plan":
            from mpm_deployment import main
            return main([*roots, *command[2:]])
        from mpm_kernel import main
        return main([*roots, *command[1:]])
    if area == "catalog" and not roots:
        from mpm_catalog import main
        return main(command[1:])
    if area == "ports" and action == "resolve":
        return resolve_ports(command[2:])
    if area in ("base", "system", "kernel", "ports") and (
            action in ("search", "show", "versions") and option(command, "--catalog")
            or area == "kernel" and action == "resolve"):
        if roots or option(command, "--area"):
            raise ValueError("catalog area is specified by command; do not use --root or --area")
        from mpm_catalog import main
        return main(["resolve-kernel" if action == "resolve" else action, *command[2:], "--area", area])
    if area in ("base", "system", "kernel"):
        raise ValueError("unsupported " + area + " operation; use mpm --help")
    backend_args = list(args)
    if runtime is not None:
        prefix = []
        if not option(backend_args, "--root"):
            prefix += ["--root", str(runtime.ports)]
        if not option(backend_args, "--source-manifest"):
            prefix += ["--source-manifest", str(runtime.source)]
        backend_args = prefix + backend_args
    adapter = runpy.run_path(str(Path(__file__).with_name("mpm-nix-prototype")), run_name="mpm_nix_adapter")
    return adapter["main"](backend_args)


def main(argv=None, *, runtime=None):
    try:
        with runtime_path(runtime):
            return dispatch(list(sys.argv[1:] if argv is None else argv), runtime)
    except (OSError, ValueError, KeyError, TypeError, EOFError) as error:
        print("mpm: " + str(error), file=sys.stderr)
        return 1
