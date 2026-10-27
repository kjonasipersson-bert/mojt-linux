#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Prepare a pinned binary image-build toolset beside System; never activate Ports."""
import argparse
import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

ROLES = {
    "python": ("python3", ["python3"]),
    "shell": ("bash", ["bash"]),
    "git": ("git", ["git"]),
    "coreutils": ("coreutils", ["cp", "du", "mkdir", "rm", "cat", "chmod", "sha256sum", "env", "dirname", "basename", "readlink", "realpath", "head", "tail", "sort", "tr", "cut", "touch", "install", "mktemp", "ln", "ls", "stat", "id", "truncate", "sync"]),
    "findutils": ("findutils", ["find", "xargs"]),
    "grep": ("gnugrep", ["grep"]),
    "sed": ("gnused", ["sed"]),
    "awk": ("gawk", ["awk"]),
    "tar": ("gnutar", ["tar"]),
    "cpio": ("cpio", ["cpio"]),
    "zstd": ("zstd", ["zstd"]),
    "kmod": ("kmod", ["modprobe", "depmod"]),
    "e2fsprogs": ("e2fsprogs", ["mkfs.ext4", "e2fsck", "debugfs"]),
    "util-linux": ("util-linux", ["sfdisk", "fallocate"]),
    "dosfstools": ("dosfstools", ["mkfs.vfat"]),
    "mtools": ("mtools", ["mcopy"]),
    "grub": ("grub2_efi", ["grub-mkstandalone", "grub-script-check"]),
    "openssl": ("openssl", ["openssl"]),
    "binutils": ("binutils", ["readelf"]),
    "busybox": ("pkgsStatic.busybox", []),
    "cacert": ("cacert", []),
}
EXPRESSION = r'''
{ requestJSON }:
let r = builtins.fromJSON requestJSON;
    pkgs = import (builtins.toPath r.source.path) { system = r.source.system; config = {}; overlays = []; };
in map (item: let p = pkgs.lib.attrByPath (pkgs.lib.splitString "." item.attribute)
    (throw "missing image-build tool attribute") pkgs;
  in { inherit (item) role attribute; version = p.version or "unknown";
       output = (pkgs.lib.getBin p).outPath; }) r.items
'''


def require(ok, message):
    if not ok:
        raise ValueError(message)


def backend():
    loader = importlib.machinery.SourceFileLoader("build_nix", str(Path(__file__).with_name("mpm-nix-prototype")))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def clean_environment(bin_dir, certificate, home=None):
    # env -i equivalent: no inherited LD_*, plugin, Python or locale-archive paths.
    result = dict(PATH=str(bin_dir), HOME=home or os.environ.get("HOME", "/root"),
                  LANG="C", LC_ALL="C", PYTHONNOUSERSITE="1", TZ="UTC",
                  SSL_CERT_FILE=certificate, NIX_SSL_CERT_FILE=certificate, TMPDIR="/tmp")
    if os.environ.get("TERM"):
        result["TERM"] = os.environ["TERM"]
    return result


def execute(args, environment):
    p = subprocess.run(args, env=environment, text=True, capture_output=True)
    require(p.returncode == 0, "tool failed: " + str(args[0]) + "\n" + p.stderr)
    return p.stdout


def member(path, closure):
    resolved = Path(path).resolve(strict=True)
    require(any(resolved.is_relative_to(Path(root)) for root in closure),
            "runtime reference outside pinned closure: " + str(resolved))
    return resolved


def audit_program(program, readelf, closure, environment, seen=None):
    """Trusted imported files only. Inspect ELF and ask its own loader for resolution."""
    path = member(program, closure)
    seen = set() if seen is None else seen
    require(str(path) not in seen, "interpreter cycle")
    seen.add(str(path))
    with path.open("rb") as f:
        header = f.read(4096)
    if header.startswith(b"#!"):
        parts = shlex.split(header.splitlines()[0][2:].decode())
        require(parts and parts[0].startswith("/nix/store/"), "non-store script interpreter: " + str(path))
        return dict(path=str(path), kind="script", shebang=parts,
                    interpreter=audit_program(parts[0], readelf, closure, environment, seen))
    require(header.startswith(b"\x7fELF"), "unsupported executable format: " + str(path))
    headers = execute([str(readelf), "--wide", "--program-headers", str(path)], environment)
    match = re.search(r"Requesting program interpreter:\s*([^\]]+)\]", headers)
    dynamic = execute([str(readelf), "--wide", "--dynamic", str(path)], environment)
    if not match:
        require("(NEEDED)" not in dynamic, "ELF needs libraries without an interpreter")
        return dict(path=str(path), kind="static-elf")
    loader = member(match[1].strip(), closure)
    listing = execute([str(loader), "--list", str(path)], environment)
    require("not found" not in listing, "missing loader dependency: " + str(path))
    libraries = re.findall(r"=>\s+(/\S+)|^\s*(/\S+)\s+\(", listing, flags=re.M)
    resolved = sorted({str(member(a or b, closure)) for a,b in libraries})
    return dict(path=str(path), kind="dynamic-elf", loader=str(loader), libraries=resolved,
                dynamic=dynamic, loader_listing=listing,
                libc=[p for p in resolved if Path(p).name.startswith("libc.so")])


def verify_runtime_maps(maps, closure):
    libraries = set()
    for line in maps.splitlines():
        fields = line.split(maxsplit=5)
        if len(fields) == 6 and fields[5].startswith("/"):
            path = fields[5]
            if re.search(r"\.so(?:\.|$)", Path(path).name) or "ld-linux" in Path(path).name:
                libraries.add(str(member(path, closure)))
    require(any("libc.so" in Path(p).name or Path(p).name.startswith("libc-") for p in libraries),
            "Python runtime did not expose its libc mapping")
    return sorted(libraries)


def find_command(output, command):
    matches = [Path(output)/directory/command for directory in ("bin", "sbin")
               if (Path(output)/directory/command).is_file() and os.access(Path(output)/directory/command, os.X_OK)]
    require(matches, "missing executable " + command + " in " + output)
    return matches[0]


def launcher(busybox, output, certificate):
    # The FIRST interpreter is static, so inherited loader settings cannot affect it.
    q = shlex.quote
    return ("#!" + str(busybox) + " sh\nset -eu\n"
        "[ ! -e " + q(str(output/".preparing")) + " ] || { echo 'Build environment incomplete' >&2; exit 1; }\n"
        "exec " + q(str(busybox)) + " env -i " +
        "PATH=" + q(str(output/"bin")) + ' HOME="${HOME:-/root}" TERM="${TERM:-dumb}" ' +
        "LANG=C LC_ALL=C TZ=UTC TMPDIR=/tmp PYTHONNOUSERSITE=1 " +
        "SSL_CERT_FILE=" + q(certificate) + " NIX_SSL_CERT_FILE=" + q(certificate) + ' "$@"\n')


def prepare(args, nix=None):
    nix = nix or backend()
    require(not os.path.lexists(args.output), "build environment output must not exist")
    output = args.output.resolve()
    require(not any(output.is_relative_to(prefix) for prefix in
            ("/nix", "/run/mojt-system", "/run/mojt-disk/base", "/run/mojt-disk/system",
             "/var/lib/mojt/ports", "/usr", "/bin", "/lib", "/etc")), "use a private build directory")
    require(not any(os.environ.get(n) for n in ("LD_LIBRARY_PATH", "LD_PRELOAD", "LD_AUDIT")),
            "prepare from a shell without LD_LIBRARY_PATH/LD_PRELOAD/LD_AUDIT overrides")
    source = nix.catalog_from_manifest(args.source_manifest)["source"]
    require(source["system"] == "x86_64-linux", "first image build requires x86_64-linux")
    rows = nix.evaluate(EXPRESSION, source=source,
        items=[dict(role=k, attribute=v[0]) for k,v in ROLES.items()])
    require(isinstance(rows,list) and len(rows)==len(ROLES), "invalid build-tool evaluation")
    packages={}
    for row in rows:
        require(row["role"] in ROLES and row["role"] not in packages and
                row["attribute"] == ROLES[row["role"]][0], "build-tool mapping differs")
        nix.store_path(row["output"])
        packages[row["role"]]=row
        print(row["role"] + ": " + row["version"] + " -> " + row["output"], flush=True)
        nix.run("nix-store", "--realise", row["output"], "--dry-run", "--option", "max-jobs", "0", "--option", "builders", "")
    if args.dry_run:
        print("Preview only; no payloads, roots, profiles or build environment written.")
        return
    if not args.yes and input("Import binary image-build tools into a new private environment? [y/N] ").lower()!="y":
        return
    output.mkdir(parents=True)
    (output/".preparing").write_text("Incomplete; do not use or move this directory.\n")
    (output/"gcroots").mkdir()
    (output/"bin").mkdir()
    try:
        nix.retain(output, source["store"])
        for row in rows:
            nix.retain(output,row["output"])
        closure=sorted(set(nix.run("nix-store","--query","--requisites",source["store"],
                                   *[r["output"] for r in rows]).splitlines()))
        require(set([source["store"]]+[r["output"] for r in rows])<=set(closure),"incomplete tool closure")
        for path in closure:
            nix.store_path(path)
            nix.run("nix-store","--verify-path",path)
        hashes=nix.run("nix-store","--query","--hash",*closure).splitlines()
        require(len(hashes)==len(closure) and all(hashes),"incomplete tool closure hashes")
        for role,(_,commands) in ROLES.items():
            for command in commands:
                path=find_command(packages[role]["output"],command)
                require(not os.path.lexists(output/"bin"/command),"build-tool alias collision")
                (output/"bin"/command).symlink_to(path)
        busybox=find_command(packages["busybox"]["output"],"busybox")
        cert=packages["cacert"]["output"]+"/etc/ssl/certs/ca-bundle.crt"
        require(Path(cert).is_file(),"missing CA bundle")
        env=clean_environment(output/"bin",cert)
        readelf=output/"bin/readelf"
        audit={p.name:audit_program(p,readelf,closure,env) for p in sorted((output/"bin").iterdir())}
        bb_audit=audit_program(busybox,readelf,closure,env)
        require(bb_audit["kind"]=="static-elf", "build launcher/initramfs BusyBox must be static")
        applets=set(execute([str(busybox),"--list"],env).splitlines())
        require({"sh","env","switch_root","mount","findfs","cp","ln"}<=applets,"static BusyBox lacks required applets")
        probes={}
        for command,options in {"python3":["--version"],"bash":["--version"],"git":["--version"],
            "cpio":["--version"],"sfdisk":["--version"],"grub-mkstandalone":["--version"],
            "openssl":["version"]}.items():
            probes[command]=execute([str(output/"bin"/command),*options],env)
        runtime_code='import json,os,pwd; print(json.dumps(dict(uid=os.getuid(), user=pwd.getpwuid(os.getuid()).pw_name, maps=open("/proc/self/maps").read())))'
        probes["python-runtime"]=json.loads(execute([str(output/"bin/python3"),"-I","-c",runtime_code],env))
        probes["python-runtime"]["verified_libraries"] = verify_runtime_maps(probes["python-runtime"]["maps"], closure)
        record=dict(format="mojt-build-env-nix-v1", source=source, packages=packages,
            preparer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            adapter_sha256=hashlib.sha256(Path(__file__).with_name("mpm-nix-prototype").read_bytes()).hexdigest(),
            closure=[dict(path=p,nar_hash=h) for p,h in zip(closure,hashes)],
            busybox=str(busybox), certificate=cert, elf=audit, busybox_audit=bb_audit, probes=probes,
            scope="Tool loader resolution and limited execution evidence, not general libc/ABI certification.")
        (output/"environment.json").write_text(json.dumps(record,indent=2)+"\n")
        (output/"run").write_text(launcher(busybox,output,cert))
        (output/"run").chmod(0o755)
        (output/".preparing").unlink()
        print("Build environment ready: " + str(output))
        print("No Ports/System activation or Base libc changes. Keep this directory at its original location.")
    except BaseException:
        print("Incomplete environment retained for inspection: " + str(output),file=sys.stderr)
        raise


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-manifest",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--dry-run",action="store_true")
    p.add_argument("-y","--yes",action="store_true")
    args=p.parse_args(argv)
    try:
        prepare(args)
        return 0
    except (ValueError,OSError,KeyError,TypeError,EOFError) as error:
        print("mojt-build-env: "+str(error),file=sys.stderr)
        return 1


if __name__=="__main__":
    sys.exit(main())
