#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Owner acceptance on a separate copy of the accepted native VM disk."""
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import mojt_artifact as artifact
import mojt_system as system
import mojt_system_manifest as manifests
import mpm_deployment as deployment
import mpm_kernel as kernel
import mpm_kernel_boot as manager

ROOT = Path("/run/mojt-disk")
LAB = Path("/var/lib/mojt/kernel-deploy-test")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def write_state(value):
    path = LAB / "acceptance.json"
    temporary = LAB / "acceptance.tmp"
    with temporary.open("w") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    kernel.sync_directory(LAB)


def private_tools():
    """Use only a verified object already in the selected System closure."""
    label = Path("/run/mojt-system/version").read_text().strip()
    manifest = deployment.read_json(ROOT / "system" / label / "manifest.json")
    manifests.validate(manifest)
    native = []
    for item in manifest["description"]["artifacts"]["nix"]["objects"]:
        path = Path(item["path"])
        if (path / "bin/zstd").is_file():
            require(system.tree_hash(path) == item["tree_sha256"], "retained zstd object differs")
            native.append(path / "bin")
    require(len(native) == 1, "one retained System zstd executable is required; do not import a new provider")
    os.environ["PATH"] = str(native[0]) + os.pathsep + os.environ.get("PATH", "")


def prepare():
    require(not LAB.exists(), "acceptance lab exists; inspect it instead of overwriting")
    running = deployment.read_json(Path("/run/mojt/deployment.json"))
    d = deployment.validate_deployment(running)
    require(d["kernel"]["release"] == os.uname().release, "running release differs")
    baseline = "boot/mojt/" + d["system"]["generation"] + "/" + d["base"]["release"]
    state, entries, menu = manager.current(ROOT, baseline)
    require(state["selected"] == running["id"], "boot choice differs from the running native baseline")
    manager.live_context(ROOT, entries[state["selected"]])
    require(Path("/run/mojt/native-kernel-artifact").read_text().strip() == d["kernel"]["artifact"], "runtime Kernel identity differs")
    old = entries[state["selected"]]["body"]
    obj = ROOT / "kernel/installed" / kernel.identifier(old["id"])
    spec = {key: copy.deepcopy(old[key]) for key in
            ("kind", "name", "platform", "dependencies", "requirements", "provides", "provenance", "metadata")}
    spec["format"] = artifact.SPEC_FORMAT
    spec["version"] = {key: copy.deepcopy(old["version"][key]) for key in ("upstream", "scheme", "revision")}
    spec["version"]["revision"] = (spec["version"]["revision"] or 0) + 1
    spec["metadata"]["acceptance_only"] = "same-release-deployment-selection"
    LAB.mkdir(mode=0o700)
    attachments = {p.name: p for p in (obj / "provenance").iterdir()} if (obj / "provenance").exists() else {}
    package = artifact.pack(obj / "payload", spec, LAB / "package", attachments)
    identifier = package["artifact"]["id"]
    require(identifier != old["id"], "acceptance needs a distinct exact artifact")
    kernel.install(ROOT / "kernel", LAB / "package" / package["archive"]["file"], identifier, yes=True)
    require(manager.current(ROOT, baseline)[2] == menu, "installation changed boot selection")
    checkpoint = dict(format="mojt-kernel-boot-acceptance-v1", phase="prepared", baseline=baseline,
        old_deployment=state["selected"], old_kernel=old["id"], new_kernel=identifier,
        kernel_release=d["kernel"]["release"], base=d["base"], system=d["system"],
        machine_id=Path("/etc/machine-id").read_text().strip())
    write_state(checkpoint)
    print("PASS: installed a distinct test package; same compiled Kernel release and original build provenance")
    print("PASS: original deployment and boot selection unchanged")
    print("Test artifact:", identifier)


def verify(checkpoint, old=False):
    expected = checkpoint["old_deployment"] if old else checkpoint["new_deployment"]
    expected_kernel = checkpoint["old_kernel"] if old else checkpoint["new_kernel"]
    record = deployment.read_json(Path("/run/mojt/deployment.json"))
    d = deployment.validate_deployment(record)
    require(record["id"] == expected and d["kernel"]["artifact"] == expected_kernel, "wrong running deployment/artifact")
    require(Path("/run/mojt/native-kernel-artifact").read_text().strip() == expected_kernel, "wrong runtime Kernel record")
    require(os.uname().release == checkpoint["kernel_release"], "wrong actual Kernel release")
    require(d["base"] == checkpoint["base"] and d["system"] == checkpoint["system"], "Base/System userspace changed")
    require(Path("/etc/machine-id").read_text().strip() == checkpoint["machine_id"], "machine identity changed")
    report = manager.status(ROOT, running_record=Path("/run/mojt/deployment.json"))
    require(report["selected"] == expected and report["running_is_selected"], "running and selected do not agree")
    source = subprocess.run(["findmnt", "--json", "-T", "/lib/modules", "-o", "SOURCE,OPTIONS"],
                            check=True, text=True, capture_output=True)
    mount = json.loads(source.stdout)["filesystems"][0]
    require("/kernel/installed/" + kernel.identifier(expected_kernel) + "/payload/lib/modules" in mount["source"] and
            "ro" in mount["options"].split(","), "wrong or writable native module mount")
    failed = subprocess.run(["systemctl", "--failed", "--no-legend", "--no-pager"],
                            check=True, text=True, capture_output=True)
    require(not failed.stdout.strip(), "failed systemd units: " + failed.stdout)
    require(checkpoint["new_deployment"] in report["staged"], "retained test deployment missing")
    print("PASS: " + ("original deployment restored" if old else "new exact deployment is running"))
    print("PASS: correct read-only native module tree; Base/System and machine identity retained; no failed units")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("verify-transfer", "prepare", "stage", "select", "check", "rollback", "check-old"))
    args = parser.parse_args()
    require(os.geteuid() == 0 and ROOT.is_mount(), "run as root in the separate native VM copy")
    if args.action == "verify-transfer":
        directory = Path(__file__).resolve().parents[2]
        inventory = deployment.read_json(directory / "inventory.json")
        for name, expected in inventory.items():
            artifact.relative(name)
            path = directory / name
            require(path.is_file() and not path.is_symlink() and artifact.file_sha(path) == expected,
                    "transferred input differs: " + name)
        print("PASS: all transferred source files match their inventory")
        return
    private_tools()
    if args.action == "prepare":
        prepare()
        return
    checkpoint = deployment.read_json(LAB / "acceptance.json")
    require(checkpoint["format"] == "mojt-kernel-boot-acceptance-v1", "unsupported test checkpoint")
    if args.action == "stage":
        require(checkpoint["phase"] == "prepared", "stage requires the prepared checkpoint")
        before = (ROOT / "boot/mojt/grub.cfg").read_bytes()
        manager.stage(ROOT, checkpoint["new_kernel"], baseline=checkpoint["baseline"], dry_run=True)
        result = manager.stage(ROOT, checkpoint["new_kernel"], baseline=checkpoint["baseline"], yes=True)
        repeated = manager.stage(ROOT, checkpoint["new_kernel"], baseline=checkpoint["baseline"], yes=True)
        require(result["changed"] and not repeated["changed"] and repeated["deployment"] == result["deployment"], "staging repeat differs")
        require((ROOT / "boot/mojt/grub.cfg").read_bytes() == before, "staging changed next boot")
        checkpoint.update(phase="staged", new_deployment=result["deployment"])
        write_state(checkpoint)
        print("PASS: exact Kernel deployment staged; repeat is a no-op; next boot unchanged")
    elif args.action == "select":
        require(checkpoint["phase"] == "staged", "select requires the staged checkpoint")
        manager.select(ROOT, checkpoint["new_deployment"], expected_selected=checkpoint["old_deployment"],
                       baseline=checkpoint["baseline"], dry_run=True)
        manager.select(ROOT, checkpoint["new_deployment"], expected_selected=checkpoint["old_deployment"],
                       baseline=checkpoint["baseline"], yes=True)
        running = manager.status(ROOT, running_record=Path("/run/mojt/deployment.json"))
        require(not running["running_is_selected"] and running["running"]["artifact"] == checkpoint["old_kernel"],
                "selection confused running and next boot")
        checkpoint["phase"] = "selected"
        write_state(checkpoint)
        print("PASS: next boot selected; running Kernel still belongs to the old deployment")
        print("READY: power off and restart the SAME VM copy, then run check")
    elif args.action == "check":
        require(checkpoint["phase"] in ("selected", "checked"), "check requires a selected test deployment")
        verify(checkpoint)
        checkpoint["phase"] = "checked"
        write_state(checkpoint)
    elif args.action == "rollback":
        require(checkpoint["phase"] == "checked", "rollback requires successful new-deployment boot")
        manager.select(ROOT, None, expected_selected=checkpoint["new_deployment"], rollback=True, yes=True)
        checkpoint["phase"] = "rollback-selected"
        write_state(checkpoint)
        print("PASS: previous deployment selected; both deployments retained")
        print("READY: power off and restart the SAME VM copy, then run check-old")
    else:
        require(checkpoint["phase"] in ("rollback-selected", "complete"), "check-old requires rollback selection")
        verify(checkpoint, old=True)
        checkpoint["phase"] = "complete"
        write_state(checkpoint)
        print("PASS: existing-disk Kernel staging, selection, boot and rollback acceptance")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        print("kernel boot acceptance: " + str(error), file=sys.stderr)
        raise SystemExit(1)
