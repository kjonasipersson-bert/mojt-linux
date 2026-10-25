# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Experimental UEFI image assembly, using regular files only (no host mounts)."""

import hashlib
import json
import re
import shutil
import subprocess
import uuid


MIB = 1024 * 1024
SECTOR = 512
ESP_MIB = 128
COMMANDS = ("sfdisk", "mkfs.vfat", "mcopy", "grub-mkstandalone", "grub-script-check")
GRUB_MODULES = "part_gpt ext2 fat normal linux search search_fs_uuid serial terminal configfile halt"
SERIAL = "serial --unit=0 --speed=115200 --word=8 --parity=no --stop=1\n" \
         "terminal_input serial\nterminal_output serial\n"
DISK_MOUNT = '''tries=0
while [ ! -b /dev/vda ]; do
    tries=$((tries + 1))
    [ "$tries" -le 20 ] || panic "/dev/vda did not appear"
    sleep 1
done
mount -t ext4 -o rw /dev/vda /sysroot || panic "cannot mount Mojt ext4 disk"'''


def generation(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", value):
        raise ValueError("unsafe boot System generation")
    return value


def fs_uuid(value):
    if not isinstance(value, str):
        raise ValueError("boot filesystem UUID must be a string")
    if str(uuid.UUID(value)) != value:
        raise ValueError("noncanonical boot filesystem UUID")
    return value


def layout(size_mib):
    if type(size_mib) is not int or size_mib < 512:
        raise ValueError("UEFI disk must be at least 512 MiB")
    return {"disk_bytes": size_mib * MIB, "esp_offset": MIB,
            "esp_bytes": ESP_MIB * MIB, "root_offset": (ESP_MIB + 1) * MIB,
            "root_bytes": (size_mib - ESP_MIB - 2) * MIB}


def terminal(console):
    if console not in ("serial", "local"):
        raise ValueError("unsupported boot console")
    return SERIAL if console == "serial" else SERIAL.replace(
        "terminal_input serial", "terminal_input console serial").replace(
        "terminal_output serial", "terminal_output console serial")


def cmdline(root_uuid, system, console="serial"):
    terminal(console)
    return ("console=ttyS0,115200 " + ("console=tty0 " if console == "local" else "") +
            f"rdinit=/init root=UUID={fs_uuid(root_uuid)} mojt.system={generation(system)}")


def init_script(script, root_uuid, system):
    """Pin both the filesystem and System; do not follow a newer current link."""
    fs_uuid(root_uuid)
    generation(system)
    if script.count(DISK_MOUNT) != 1 or "/sysroot/system/current" not in script:
        raise ValueError("UEFI needs the reviewed System early-boot template")
    discover = '''IFS= read -r mojt_cmdline </proc/cmdline || panic "cannot read kernel command line"
mojt_root=
mojt_system=
for mojt_arg in $mojt_cmdline; do
    case "$mojt_arg" in
        root=*) mojt_root=${mojt_arg#root=} ;;
        mojt.system=*) mojt_system=${mojt_arg#mojt.system=} ;;
    esac
done
[ "$mojt_root" = "UUID=@UUID@" ] || panic "boot filesystem selection differs from initramfs"
[ "$mojt_system" = "@SYSTEM@" ] || panic "boot System selection differs from initramfs"
tries=0
while :; do
    mojt_device="$(findfs "$mojt_root" 2>/dev/null)" && [ -b "$mojt_device" ] && break
    tries=$((tries + 1))
    [ "$tries" -le 20 ] || panic "Mojt filesystem UUID did not appear"
    sleep 1
done
mount -t ext4 -o rw "$mojt_device" /sysroot || panic "cannot mount Mojt ext4 partition"'''
    return script.replace(DISK_MOUNT, discover.replace("@UUID@", root_uuid).replace("@SYSTEM@", system)) \
        .replace("/sysroot/system/current", "/sysroot/system/" + system)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def stage(tree, kernel, initramfs, modules, *, release, base, system, root_uuid, console="serial"):
    """Stage an image-owned boot pair and a record of its exact inputs."""
    generation(system)
    generation(release)
    path = tree / "boot/mojt" / system
    path.mkdir(parents=True)
    shutil.copy2(kernel, path / "vmlinuz")
    (path / "initramfs.cpio.gz").write_bytes(initramfs)
    record = {"format": 1, "boot_mode": "uefi", "system_generation": system,
              "base": base, "kernel_release": release, "root_uuid": fs_uuid(root_uuid),
              "kernel_sha256": digest(path / "vmlinuz"),
              "initramfs_sha256": digest(path / "initramfs.cpio.gz"),
              "module_inputs": [{"name": p.name, "sha256": digest(p)} for p in modules],
              "console": console, "cmdline": cmdline(root_uuid, system, console)}
    (path / "boot.json").write_text(json.dumps(record, indent=2) + "\n", encoding="ascii")
    prefix = "/boot/mojt/" + system
    config = terminal(console) + ("set gfxpayload=keep\n" if console == "local" else "") + \
        "set timeout=3\nset default=0\n" + \
        f"menuentry 'Mojt {system} (Linux {release})' {{\n" + \
        f"    linux {prefix}/vmlinuz {record['cmdline']}\n" + \
        f"    initrd {prefix}/initramfs.cpio.gz\n}}\n"
    (path / "grub.cfg").write_text(config, encoding="ascii")
    return record


def partition_script(parts):
    return "label: gpt\nunit: sectors\n\n" + \
        f"start={parts['esp_offset'] // SECTOR}, size={parts['esp_bytes'] // SECTOR}, type=U, name=MOJT-EFI\n" + \
        f"start={parts['root_offset'] // SECTOR}, size={parts['root_bytes'] // SECTOR}, type=L, name=MOJT\n"


def copy_partition(source, destination, offset, length):
    if source.stat().st_size != length:
        raise ValueError("partition image size differs from planned GPT extent")
    if offset < 0 or length <= 0 or offset + length > destination.stat().st_size:
        raise ValueError("partition extent outside disk image")
    with source.open("rb") as incoming, destination.open("r+b") as outgoing:
        outgoing.seek(offset)
        # Keep empty filesystem regions sparse; this is a fresh zero-filled image.
        while block := incoming.read(MIB):
            if block.strip(b"\0"):
                outgoing.write(block)
            else:
                outgoing.seek(len(block), 1)


def build_disk(disk, tree, work, size_mib, root_uuid, system, console="serial"):
    """Create a NEW regular GPT disk, with standalone GRUB in the EFI fallback path."""
    parts = layout(size_mib)
    fs_uuid(root_uuid)
    generation(system)
    if disk.is_symlink():
        raise ValueError("disk image must not be a symlink")
    with disk.open("xb") as stream:
        stream.truncate(parts["disk_bytes"])
    subprocess.run(["sfdisk", "--no-reread", "--no-tell-kernel", str(disk)],
                   input=partition_script(parts), text=True, check=True, capture_output=True)
    actual = json.loads(subprocess.run(["sfdisk", "--json", str(disk)],
                        text=True, capture_output=True, check=True).stdout)["partitiontable"]
    extents = [(p["start"] * SECTOR, p["size"] * SECTOR) for p in actual["partitions"]]
    if actual["label"] != "gpt" or actual.get("sectorsize") != SECTOR or extents != [
            (parts["esp_offset"], parts["esp_bytes"]), (parts["root_offset"], parts["root_bytes"])]:
        raise ValueError("written GPT differs from planned partition extents")
    root = work / "mojt.ext4"
    with root.open("xb") as stream:
        stream.truncate(parts["root_bytes"])
    subprocess.run(["mkfs.ext4", "-F", "-q", "-L", "MOJT", "-U", root_uuid,
                    "-d", str(tree), str(root)], check=True)
    config = tree / "boot/mojt" / system / "grub.cfg"
    subprocess.run(["grub-script-check", str(config)], check=True)
    stub = work / "grub-embedded.cfg"
    stub.write_text(terminal(console) + f"if search --no-floppy --fs-uuid --set=mojt_root {root_uuid}; then\n"
                    "    set root=$mojt_root\n"
                    f"    configfile ($mojt_root)/boot/mojt/{system}/grub.cfg\nfi\n"
                    "echo 'Mojt boot filesystem not found'\nhalt\n", encoding="ascii")
    subprocess.run(["grub-script-check", str(stub)], check=True)
    efi = work / "EFI/BOOT"
    efi.mkdir(parents=True)
    loader = efi / "BOOTX64.EFI"
    subprocess.run(["grub-mkstandalone", "-O", "x86_64-efi", "--modules=" + GRUB_MODULES,
                    "--locales=", "--fonts=", "-o", str(loader),
                    "boot/grub/grub.cfg=" + str(stub)], check=True)
    fat = work / "mojt.fat"
    with fat.open("xb") as stream:
        stream.truncate(parts["esp_bytes"])
    subprocess.run(["mkfs.vfat", "-F", "32", "-n", "MOJT-EFI", str(fat)], check=True)
    subprocess.run(["mcopy", "-i", str(fat), "-s", str(work / "EFI"), "::/"], check=True)
    copy_partition(fat, disk, parts["esp_offset"], parts["esp_bytes"])
    copy_partition(root, disk, parts["root_offset"], parts["root_bytes"])
    return {**parts, "root_uuid": root_uuid, "efi_loader_sha256": digest(loader)}


def run_script(network=False, local_console=False):
    script = '''#!/usr/bin/env bash
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
set -euo pipefail
here="$(cd -- "$(dirname -- "$0")" && pwd -P)"
OVMF_CODE="${OVMF_CODE:-/usr/share/OVMF/OVMF_CODE_4M.fd}"
OVMF_VARS_TEMPLATE="${OVMF_VARS_TEMPLATE:-/usr/share/OVMF/OVMF_VARS_4M.fd}"
if [[ ! -f "$OVMF_CODE" || ! -r "$OVMF_CODE" || ! -f "$OVMF_VARS_TEMPLATE" || ! -r "$OVMF_VARS_TEMPLATE" ]]; then
    echo 'OVMF firmware missing; install ovmf or set OVMF_CODE and OVMF_VARS_TEMPLATE to a matching pair.' >&2
    exit 1
fi
if [[ ! -e "$here/OVMF_VARS.fd" ]]; then
    (umask 077; set -o noclobber; cat -- "$OVMF_VARS_TEMPLATE" >"$here/OVMF_VARS.fd")
fi
exec qemu-system-x86_64 \\
    -machine q35,accel=kvm:tcg \\
    -m 1024 -smp 2 \\
    -drive "if=pflash,format=raw,readonly=on,file=$OVMF_CODE" \\
    -drive "if=pflash,format=raw,file=$here/OVMF_VARS.fd" \\
    -drive "file=$here/disk.img,if=virtio,format=raw" \\
    -nic ''' + ("user,model=virtio-net-pci" if network else "none") + ''' \\
    -display none -serial mon:stdio -no-reboot
'''
    if local_console:
        # Keep one image/launcher for both non-VirtIO probes. No host disk is exposed.
        script = script.replace('exec qemu-system-x86_64', '''disk_args=(-drive "file=$here/disk.img,if=none,id=mojt,format=raw")
case "${QEMU_DISK_BUS:-sata}" in
    sata) disk_args+=(-device ide-hd,drive=mojt,bus=ide.0,bootindex=1) ;;
    usb) disk_args+=(-device qemu-xhci,id=xhci -device usb-storage,drive=mojt,bus=xhci.0,bootindex=1) ;;
    *) echo 'QEMU_DISK_BUS must be sata or usb' >&2; exit 1 ;;
esac
exec qemu-system-x86_64''')
        script = script.replace('-drive "file=$here/disk.img,if=virtio,format=raw"', '"${disk_args[@]}"')
        script = script.replace('-display none', '-vga std -display "${QEMU_DISPLAY:-gtk}"')
        script = script.replace('user,model=virtio-net-pci', 'user,model=e1000e')
    return script
