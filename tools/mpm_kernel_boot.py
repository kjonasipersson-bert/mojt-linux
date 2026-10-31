# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Experimental native-disk Kernel staging and explicit next-boot selection."""
import argparse
from contextlib import contextmanager
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import uuid

import mojt_artifact as artifact
import mojt_boot as boot
import mojt_native_image as native
import mojt_system as system
import mojt_system_manifest as manifests
import mpm_deployment as deployment
import mpm_kernel as kernel
import mpm_transaction as transaction

FORMAT = "mpm-kernel-boot-v1"
HEADER = "# " + FORMAT + "\n"
FILES = ("deployment.json", "base-context.json", "system-manifest.json", "initramfs-binding.json",
         "native-build-inputs.json", "vmlinuz", "initramfs.cpio.gz")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def disk_root(value, write=False):
    root = kernel.root_path(value, write=write)
    kernel.directory(root)
    require((root / "boot/mojt").is_dir() and not (root / "boot/mojt").is_symlink(), "native Mojt disk required")
    if write:
        require(os.geteuid() == 0, "boot changes require an administrator")
    return root


def read(path):
    return deployment.read_json(path)


def checked_file(path, maximum=artifact.MAX_METADATA):
    with deployment.local_file(path) as stream:
        data = stream.read(maximum + 1)
    require(len(data) <= maximum, "boot file exceeds limit")
    return data


def entry_path(root, relative):
    require(isinstance(relative, str) and bool(re.fullmatch(
        r"boot/(?:mpm/slots/[0-9a-f]{32}|mojt/[A-Za-z0-9][A-Za-z0-9._+-]*/[A-Za-z0-9][A-Za-z0-9._+-]*)", relative)),
        "unsupported deployment location")
    path = root / relative
    require(path == path.resolve() and path.is_dir(), "missing or linked deployment location")
    return path


def inspect_entry(root, relative):
    path = entry_path(root, relative)
    record = read(path / "deployment.json")
    d = deployment.validate_deployment(record)
    require(d["boot"]["console"] == "serial", "first existing-disk increment supports serial UEFI only")
    image = checked_file(path / "vmlinuz", native.MAX_INITRAMFS)
    initramfs = checked_file(path / "initramfs.cpio.gz", native.MAX_INITRAMFS)
    require(hashlib.sha256(image).hexdigest() == d["kernel"]["image_sha256"], "deployment Kernel image differs")
    archive = dict(sha256=hashlib.sha256(initramfs).hexdigest(), size=len(initramfs))
    require(archive == d["initramfs"]["archive"], "deployment initramfs differs")
    binding = read(path / "initramfs-binding.json")
    expected = dict(platform=d["platform"], base=d["base"], system=d["system"], kernel=d["kernel"],
                    boot=d["boot"], archive=archive)
    require(deployment.identified(binding, deployment.BINDING) == expected and
            binding["id"] == d["initramfs"]["binding"], "deployment initramfs binding differs")
    registry = root / "kernel"
    require(kernel.inspect_root(kernel.root_path(registry)), "native Kernel registry required")
    obj = registry / "installed" / kernel.identifier(d["kernel"]["artifact"])
    body, unused = kernel.object_record(obj, d["kernel"]["artifact"], verify=True)
    require(deployment.kernel_identity(body) == d["kernel"], "deployment Kernel identity differs")
    return dict(record=record, relative=relative, path=path, body=body)


def live_context(root, entry):
    d = entry["record"]["description"]
    base, selected_system = d["base"]["release"], d["system"]["generation"]
    profile = root / "system" / selected_system
    require(profile == profile.resolve(), "linked System generation")
    manifest = read(profile / "manifest.json")
    manifests.validate(manifest)
    require(d["system"] == dict(generation=manifest["description"]["label"], manifest=manifest["id"]),
            "selected System manifest differs")
    require(read(entry["path"] / "system-manifest.json") == manifest, "retained System manifest differs")
    native.verify_profile(profile, manifest)
    objects = manifest["description"]["artifacts"]["nix"]["objects"]
    for item in objects:
        require(system.tree_hash(root / "nix/store" / Path(item["path"]).name) == item["tree_sha256"],
                "selected System provider object differs")
    # Ports may legitimately have added other store objects; do not reject them.
    receipt = read(entry["path"] / "native-build-inputs.json")
    base_path = root / "base" / base
    require(base_path == base_path.resolve(), "linked Base generation")
    require(artifact.digest(native.base_inventory(base_path)) == receipt["base_copy"]["assembled"],
            "selected Base content/metadata differs")
    spec = importlib.util.spec_from_file_location("kernel_boot_inspector", Path(__file__).with_name("mojt-system-inspect.py"))
    inspector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(inspector)
    facts = dict(format=deployment.CONTEXT, selected=entry["record"]["id"], base=d["base"],
                 root_uuid=d["boot"]["root_uuid"], facts=inspector.context_from_target(root, base))
    bounds = read(entry["path"] / "base-context.json")
    deployment.compose(entry["record"], entry["body"], bounds, manifest, facts,
                       read(entry["path"] / "initramfs-binding.json"), d["initramfs"]["archive"])
    return manifest, facts, receipt


def menu(state, entries):
    require(set(state) == {"format", "selected", "previous", "entries"} and state["format"] == FORMAT,
            "unsupported boot selection metadata")
    require(state["selected"] in state["entries"] and
            (state["previous"] is None or state["previous"] in state["entries"]), "unknown selected/previous deployment")
    require(set(entries) == set(state["entries"]), "boot menu entries differ")
    require(0 < len(entries) <= 128, "boot menu entry limit exceeded")
    d = entries[state["selected"]]["record"]["description"]
    raw = HEADER + "# " + artifact.canonical(state).decode("ascii") + "\n"
    raw += boot.terminal("serial") + "set timeout=10\nset default='mpm-" + kernel.identifier(state["selected"]) + "'\n"
    for identifier in [state["selected"], *sorted(set(entries) - {state["selected"]})]:
        entry = entries[identifier]
        candidate = entry["record"]["description"]
        require(all(candidate[k] == d[k] for k in ("base", "system", "platform", "boot")),
                "Kernel menu must preserve exact Base/System/root/console")
        prefix = "/" + entry["relative"]
        raw += (f"menuentry 'Mojt Linux {candidate['kernel']['release']} / {identifier[7:19]}' "
                f"--id 'mpm-{kernel.identifier(identifier)}' {{\n"
                f"    linux {prefix}/vmlinuz {candidate['boot']['cmdline']}\n"
                f"    initrd {prefix}/initramfs.cpio.gz\n}}\n")
    return raw.encode("ascii")


def current(root, baseline=None):
    raw = checked_file(root / "boot/mojt/grub.cfg")
    if raw.startswith(HEADER.encode()):
        lines = raw.decode("ascii").splitlines()
        require(len(lines) >= 2 and lines[1].startswith("# "), "missing boot selection metadata")
        state = artifact.parse_json(lines[1][2:].encode("ascii"))
        require(isinstance(state, dict), "boot selection must be an object")
        require(isinstance(state.get("entries"), dict) and 0 < len(state["entries"]) <= 128, "invalid boot entry count")
        entries = {identifier: inspect_entry(root, relative) for identifier, relative in state["entries"].items()}
        require(all(e["record"]["id"] == i for i, e in entries.items()), "boot entry identity differs")
        require(menu(state, entries) == raw, "boot menu differs from selection metadata")
    else:
        require(baseline is not None, "unmanaged boot menu; specify the exact native --baseline directory")
        entry = inspect_entry(root, baseline)
        d = entry["record"]["description"]
        expected = boot.terminal("serial") + "set timeout=10\nset default=0\n"
        expected += (f"menuentry 'Mojt Base {d['base']['release']} / System {d['system']['generation']} "
                     f"(Linux {d['kernel']['release']})' {{\n"
                     f"    linux /{baseline}/vmlinuz {d['boot']['cmdline']}\n"
                     f"    initrd /{baseline}/initramfs.cpio.gz\n}}\n")
        require(raw == expected.encode("ascii"), "baseline does not match the complete existing boot menu")
        state = dict(format=FORMAT, selected=entry["record"]["id"], previous=None,
                     entries={entry["record"]["id"]: baseline})
        entries = {entry["record"]["id"]: entry}
    return state, entries, raw


@contextmanager
def locked(root):
    disk_root(root, write=True)
    directory = root / "boot/mpm"
    directory.mkdir(mode=0o755, exist_ok=True)
    kernel.root_path(directory, write=True)
    # Use the same inodes as the individual writers, including older writers.
    # Kernel content must already be installed; never initialize it here.
    require(kernel.inspect_root(root / "kernel"), "installed Kernel registry required")
    ports = root / "state/var/lib/mojt/ports"
    kernel.root_path(ports, write=True)
    ports.mkdir(parents=True, exist_ok=True, mode=0o755)
    kernel.root_path(ports, write=True)
    with transaction.resource_locks(transaction.boot_lock_paths(root), modes={root / ".install-lock": 0o644}):
        initialize_boot_registry(directory)
        yield


def initialize_boot_registry(directory):
    marker = directory / "format"
    if marker.exists() or marker.is_symlink():
        require(checked_file(marker) == (FORMAT + "\n").encode(), "unsupported boot registry")
    else:
        require({p.name for p in directory.iterdir()} == {".lock"}, "refuse unmanaged boot registry")
        with marker.open("xb") as stream:
            stream.write((FORMAT + "\n").encode())
            stream.flush()
            os.fsync(stream.fileno())
        (directory / "slots").mkdir(mode=0o755)
    require((directory / "slots").is_dir() and not (directory / "slots").is_symlink(), "unsafe boot slots")
    kernel.root_path(directory / "slots", write=True)


def vm_module():
    spec = importlib.util.spec_from_file_location("kernel_boot_vm", Path(__file__).with_name("mojt-vm-build.py"))
    vm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vm)
    return vm


def write_initramfs(root):
    """Bounded newc/gzip for the private init tree; no cpio installation needed."""
    result = bytearray()
    def append(name, mode, uid, gid, content=b"", major=0, minor=0, inode=0):
        encoded = os.fsencode(name) + b"\0"
        require(len(encoded) <= 4096, "initramfs filename exceeds limit")
        values = [inode, mode, uid, gid, 1, 0, len(content), 0, 0, major, minor, len(encoded), 0]
        require(all(type(v) is int and 0 <= v <= 0xffffffff for v in values), "newc metadata exceeds limit")
        result.extend(b"070701" + b"".join(f"{v:08x}".encode("ascii") for v in values) + encoded)
        result.extend(b"\0" * (-len(result) % 4))
        result.extend(content)
        result.extend(b"\0" * (-len(result) % 4))
        require(len(result) <= native.MAX_INITRAMFS, "initramfs exceeds size limit")
    for number, path in enumerate((root, *sorted(root.rglob("*"))), 1):
        info = path.lstat()
        name = "." if path == root else "./" + path.relative_to(root).as_posix()
        require(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)
                or stat.S_ISCHR(info.st_mode), "unsupported private initramfs node")
        require(info.st_size <= native.MAX_INITRAMFS, "initramfs member exceeds limit")
        data = path.read_bytes() if path.is_file() and not path.is_symlink() else \
            os.fsencode(os.readlink(path)) if path.is_symlink() else b""
        append(name, info.st_mode, info.st_uid, info.st_gid, data,
               os.major(info.st_rdev), os.minor(info.st_rdev), number)
    append("TRAILER!!!", 0, 0, 0)
    result.extend(b"\0" * (-len(result) % 512))
    raw = gzip.compress(bytes(result), mtime=0)
    native.inspect_initramfs(raw, root)
    return raw


def build_initramfs(root, body, selected, slot, busybox, work):
    vm = vm_module()
    require(vm.static_x86_64_elf(busybox), "requires a trusted static x86_64 BusyBox")
    vm.validate_busybox_applets(busybox, "password", extra=("findfs", *system.SHUTDOWN_APPLETS))
    d = selected["record"]["description"]
    release, base, label = body["metadata"]["kernel_release"], d["base"]["release"], d["system"]["generation"]
    payload = root / "kernel/installed" / kernel.identifier(body["id"]) / "payload"
    modules = vm.module_paths(release, payload / "lib/modules" / release, network=True)
    script = native.init_script(system.init_script(vm.INIT), body["id"], release, base, label)
    old = "/sysroot/boot/mojt/" + label + "/" + base + "/deployment.json"
    require(script.count(old) == 1, "native deployment record hook changed")
    script = script.replace(old, "/sysroot/boot/mpm/slots/" + slot + "/deployment.json")
    script = boot.init_script(script, d["boot"]["root_uuid"], label, base)
    initroot = work / "initroot"
    raw = vm.make_initramfs(initroot, busybox, modules, script, system.SHUTDOWN,
                           extra_applets=("findfs",), archive_writer=write_initramfs)
    early = []
    for index, source in enumerate(modules):
        row = artifact.regular_row(body["files"], "payload/" + source.relative_to(payload).as_posix())
        decoded = hashlib.sha256(vm.module_bytes(source)).hexdigest()
        require(artifact.file_sha(source) == row["sha256"] and
                artifact.file_sha(initroot / "modules" / f"{index:04d}.ko") == decoded, "early module differs")
        early.append(dict(path=row["path"], stored_sha256=row["sha256"], initramfs_sha256=decoded))
    return raw, dict(initramfs_inventory=native.inspect_initramfs(raw, initroot), early_modules=early)


def stage(root, identifier, *, baseline=None, base_context=None, busybox=None,
          dry_run=False, yes=False, builder=build_initramfs):
    root = disk_root(root, write=not dry_run)
    state, entries, old_menu = current(root, baseline)
    selected = entries[state["selected"]]
    manifest, facts, receipt = live_context(root, selected)
    busybox = busybox or root / "system" / manifest["description"]["label"] / "busybox"
    obj = root / "kernel/installed" / kernel.identifier(identifier)
    body, unused = kernel.object_record(obj, identifier, verify=True)
    bounds = read(base_context or selected["path"] / "base-context.json")
    # Exercise the same compatibility gates before any staging writes.
    d = selected["record"]["description"]
    fake_archive = d["initramfs"]["archive"]
    binding = deployment.create(dict(platform=d["platform"], base=d["base"], system=d["system"],
        kernel=deployment.kernel_identity(body), boot=d["boot"], archive=fake_archive), deployment.BINDING)
    deployment.compose(selected["record"], body, bounds, manifest, facts, binding, fake_archive)
    plan = dict(action="stage", kernel=identifier, selected=state["selected"], base=d["base"], system=d["system"],
                selection_changes=False, running_changes=False)
    producer = artifact.digest(dict(busybox=artifact.file_sha(busybox), code={name: artifact.file_sha(
        Path(__file__).with_name(name)) for name in ("mpm_kernel_boot.py", "mojt-vm-build.py", "mojt_native_image.py",
                                                    "mojt_system.py", "mojt_boot.py", "mpm_transaction.py")}))
    retained_entries, unused = available(root, state, entries)
    for existing in retained_entries.values():
        old = existing["record"]["description"]
        evidence = read(existing["path"] / "native-build-inputs.json")
        if (evidence.get("kernel_boot_producer") == producer and old["kernel"] == deployment.kernel_identity(body)
                and all(old[k] == d[k] for k in ("base", "system", "platform", "boot"))
                and read(existing["path"] / "base-context.json") == bounds):
            return dict(plan=dict(plan, action="no-change"), dry_run=dry_run, changed=False,
                        deployment=existing["record"]["id"], slot=existing["relative"], selected=state["selected"])
    if dry_run:
        return dict(plan=plan, dry_run=True, changed=False)
    if not yes:
        require(input("Stage this exact Kernel without changing next boot? [y/N] ").lower() == "y", "staging cancelled")
    with locked(root):
        require(checked_file(root / "boot/mojt/grub.cfg") == old_menu, "selection changed; repeat preview")
        slot = uuid.uuid4().hex
        slots = root / "boot/mpm/slots"
        with tempfile.TemporaryDirectory(prefix="mojt-kernel-init-") as temporary:
            frozen_busybox = Path(temporary) / "busybox"
            shutil.copyfile(busybox, frozen_busybox)
            frozen_busybox.chmod(0o755)
            raw, evidence = builder(root, body, selected, slot, frozen_busybox, Path(temporary))
        archive = dict(sha256=hashlib.sha256(raw).hexdigest(), size=len(raw))
        binding = deployment.create(dict(platform=d["platform"], base=d["base"], system=d["system"],
            kernel=deployment.kernel_identity(body), boot=d["boot"], archive=archive), deployment.BINDING)
        result = deployment.compose(selected["record"], body, bounds, manifest, facts, binding, archive)
        record = result["candidate"]
        stage_path = Path(tempfile.mkdtemp(prefix=".stage-", dir=slots))
        try:
            values = {"deployment.json": record, "base-context.json": bounds, "system-manifest.json": manifest,
                      "initramfs-binding.json": binding,
                      "native-build-inputs.json": dict(receipt, selection_origin="existing-disk-stage",
                                                       kernel_boot_producer=producer, **evidence)}
            for name, value in values.items():
                kernel.write_json(stage_path / name, value)
            for name, data in (("vmlinuz", checked_file(obj / "payload/boot" /
                                   ("vmlinuz-" + body["metadata"]["kernel_release"]), native.MAX_INITRAMFS)),
                               ("initramfs.cpio.gz", raw)):
                with (stage_path / name).open("xb") as stream:
                    stream.write(data)
                    os.fchmod(stream.fileno(), 0o444)
                    os.fsync(stream.fileno())
            kernel.object_record(obj, identifier, verify=True)
            require(artifact.file_sha(stage_path / "vmlinuz") == record["description"]["kernel"]["image_sha256"] and
                    artifact.file_sha(stage_path / "initramfs.cpio.gz") == archive["sha256"],
                    "copied boot content differs before publication")
            # Reverify once at publication, not on every intermediate helper call.
            fresh_selected = inspect_entry(root, selected["relative"])
            fresh_manifest, fresh_facts, fresh_receipt = live_context(root, fresh_selected)
            require(fresh_selected["record"] == selected["record"] and
                    (fresh_manifest, fresh_facts, fresh_receipt) == (manifest, facts, receipt),
                    "selected installation changed during staging")
            require(checked_file(root / "boot/mojt/grub.cfg") == old_menu,
                    "selection changed during staging")
            kernel.sync_directory(stage_path)
            stage_path.chmod(0o555)
            stage_path.rename(slots / slot)
            kernel.sync_directory(slots)
        finally:
            kernel.clean_stage(stage_path)
        retained = inspect_entry(root, "boot/mpm/slots/" + slot)
        require(retained["record"] == record, "published deployment differs")
    return dict(plan=plan, changed=True, deployment=record["id"], slot="boot/mpm/slots/" + slot,
                selected=state["selected"], running="unchanged")


def available(root, state, verified_entries=None):
    """Inspect each distinct slot once; reuse entries verified by current() in this operation."""
    if verified_entries is None:
        entries = {i: inspect_entry(root, p) for i, p in state["entries"].items()}
    else:
        require(set(verified_entries) == set(state["entries"]) and all(
            verified_entries[i]["relative"] == p and verified_entries[i]["record"]["id"] == i
            for i, p in state["entries"].items()), "boot entry snapshot differs")
        entries = dict(verified_entries)
    by_path = {entry["relative"]: entry for entry in entries.values()}
    slots = root / "boot/mpm/slots"
    incomplete = []
    if slots.exists():
        require(not slots.is_symlink(), "linked boot slots")
        for path in sorted(slots.iterdir()):
            if path.name.startswith(".stage-"):
                incomplete.append(path.name)
                continue
            require(re.fullmatch(r"[0-9a-f]{32}", path.name), "unknown boot slot")
            relative = "boot/mpm/slots/" + path.name
            entry = by_path.get(relative)
            if entry is None:
                entry = inspect_entry(root, relative)
                by_path[relative] = entry
            require(entry["record"]["id"] not in entries or entries[entry["record"]["id"]]["relative"] == entry["relative"],
                    "duplicate deployment identity")
            entries[entry["record"]["id"]] = entry
    return entries, incomplete


def select(root, identifier, *, expected_selected, baseline=None, dry_run=False, yes=False, rollback=False):
    root = disk_root(root, write=not dry_run)
    state, old_entries, old_menu = current(root, baseline)
    require(state["selected"] == expected_selected, "selected deployment changed; repeat preview")
    if rollback:
        identifier = state["previous"]
        require(identifier is not None, "no previous selected deployment")
    kernel.identifier(identifier)
    entries, unused = available(root, state, old_entries)
    require(identifier in entries, "deployment is not completely staged")
    selected, candidate = old_entries[state["selected"]], entries[identifier]
    manifest, facts, unused = live_context(root, selected)
    d = candidate["record"]["description"]
    result = deployment.compose(selected["record"], candidate["body"], read(candidate["path"] / "base-context.json"),
        manifest, facts, read(candidate["path"] / "initramfs-binding.json"), d["initramfs"]["archive"])
    require(result["candidate"] == candidate["record"], "staged deployment does not preserve selected Base/System")
    plan = dict(action="no-change" if identifier == state["selected"] else "select", before=state["selected"],
                after=identifier, kernel=d["kernel"]["artifact"], running="unchanged until boot")
    if dry_run or identifier == state["selected"]:
        return dict(plan=plan, changed=False, dry_run=dry_run)
    if not yes:
        require(input("Select this deployment for next boot? [y/N] ").lower() == "y", "selection cancelled")
    with locked(root):
        require(checked_file(root / "boot/mojt/grub.cfg") == old_menu, "boot selection changed; repeat preview")
        new = dict(state, selected=identifier, previous=state["selected"], entries=dict(state["entries"]))
        new["entries"][identifier] = candidate["relative"]
        raw = menu(new, {i: entries[i] for i in new["entries"]})
        path = root / "boot/mojt/grub.cfg"
        fd, temporary = tempfile.mkstemp(prefix=".grub-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                os.fchmod(stream.fileno(), 0o644)
                os.fsync(stream.fileno())
            require(checked_file(path) == old_menu, "boot menu changed before publication")
            # The menu is unchanged, but the candidate and the selected recovery
            # entry must still be intact immediately before publication.
            fresh_selected = inspect_entry(root, selected["relative"])
            fresh_candidate = (fresh_selected if candidate["relative"] == selected["relative"]
                               else inspect_entry(root, candidate["relative"]))
            require(fresh_selected["record"] == selected["record"] and
                    fresh_candidate["record"] == candidate["record"],
                    "boot deployment changed; repeat preview")
            fresh_manifest, fresh_facts, unused = live_context(root, fresh_selected)
            require(fresh_manifest == manifest and fresh_facts == facts,
                    "installation compatibility facts changed; repeat preview")
            fresh_result = deployment.compose(
                fresh_selected["record"], fresh_candidate["body"],
                read(fresh_candidate["path"] / "base-context.json"),
                fresh_manifest, fresh_facts,
                read(fresh_candidate["path"] / "initramfs-binding.json"),
                fresh_candidate["record"]["description"]["initramfs"]["archive"])
            require(fresh_result["candidate"] == fresh_candidate["record"],
                    "deployment compatibility changed; repeat preview")
            transaction.publish(temporary, path, sync=kernel.sync_directory)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return dict(plan=plan, changed=True, selected=identifier, previous=state["selected"])


def status(root, *, baseline=None, running_record=None):
    root = disk_root(root)
    state, entries, unused = current(root, baseline)
    all_entries, incomplete = available(root, state, entries)
    running = dict(release=os.uname().release, artifact=None, deployment=None, evidence="unknown")
    if running_record is not None:
        record = read(running_record)
        d = deployment.validate_deployment(record)
        require(d["kernel"]["release"] == os.uname().release, "runtime record differs from running release")
        running.update(artifact=d["kernel"]["artifact"], deployment=record["id"], evidence="explicit-runtime-record")
    return dict(format=FORMAT, selected=state["selected"], selected_kernel=entries[state["selected"]]["record"]["description"]["kernel"],
        previous=state["previous"], running=running, staged=sorted(all_entries), incomplete=incomplete,
        installed=kernel.status(root / "kernel")["installed"], running_is_selected=running["deployment"] == state["selected"]
        if running["deployment"] is not None else None)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("stage", "select", "rollback", "status"))
    parser.add_argument("--disk-root", type=Path, required=True)
    parser.add_argument("--baseline", help="exact initial native boot-pair directory, relative to disk root")
    parser.add_argument("--artifact")
    parser.add_argument("--deployment")
    parser.add_argument("--expected-selected")
    parser.add_argument("--base-context", type=Path)
    parser.add_argument("--busybox", type=Path, help="default: verified selected System's static BusyBox")
    parser.add_argument("--running-record", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("-y", "--yes", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.action == "stage":
            require(args.artifact is not None, "stage requires --artifact")
            result = stage(args.disk_root, args.artifact, baseline=args.baseline, base_context=args.base_context,
                           busybox=args.busybox, dry_run=args.dry_run, yes=args.yes)
        elif args.action in ("select", "rollback"):
            require(args.expected_selected is not None, "selection requires --expected-selected")
            require(args.action == "rollback" or args.deployment is not None, "select requires --deployment")
            result = select(args.disk_root, args.deployment, baseline=args.baseline, expected_selected=args.expected_selected,
                            rollback=args.action == "rollback", dry_run=args.dry_run, yes=args.yes)
        else:
            result = status(args.disk_root, baseline=args.baseline, running_record=args.running_record)
        print(json.dumps(result, indent=2, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError, RecursionError, EOFError,
            tarfile.TarError, subprocess.CalledProcessError) as error:
        print("mpm kernel boot: " + str(error), file=sys.stderr)
        return 1
    return 0

