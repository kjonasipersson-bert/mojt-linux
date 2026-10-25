# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""One explicit hardware profile; staged only into a fresh image, never the host."""

import json
import os
from pathlib import Path
import shutil
import stat


PROFILE = "thinkpad-x1-carbon-3"
# Dependency closure is resolved by the builder's host kmod. No GPU/Wi-Fi
# probing before the System firmware and complete module tree are mounted.
EARLY_MODULES = ("virtio_pci", "virtio_blk", "ahci", "xhci_pci", "ehci_pci",
                 "usb_storage", "uas", "sd_mod", "ext4", "i8042", "atkbd",
                 "hid_generic", "usbhid")
RUNTIME_MODULES = ("i915", "e1000e", "iwlwifi", "iwlmvm")
LICENSE_PACKAGES = ("firmware-iwlwifi", "firmware-intel-graphics", "wireless-regdb")


def checked_tree(root, ignore=()):
    """Reject special files and escaping/broken links without following directory links."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"hardware input must be a real directory: {root}")
    root = root.resolve(strict=True)
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs[:] + files:
            path = Path(directory) / name
            if path.parent == root and name in ignore:
                if name in dirs:
                    dirs.remove(name)
                continue
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                resolved = path.resolve(strict=True)
                if not resolved.is_relative_to(root) or os.readlink(path).startswith("/"):
                    raise ValueError(f"hardware link escapes input tree: {path}")
            elif not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise ValueError(f"special file in hardware input: {path}")
    return root


def firmware_inputs(root):
    """Read an extracted Debian firmware root, retaining the upstream copyright files."""
    if root is None:
        raise ValueError("hardware profile requires --firmware-root (extracted Debian firmware packages)")
    root = root.resolve(strict=True)
    candidates = (root / "usr/lib/firmware", root / "lib/firmware")
    firmware = next((p for p in candidates if p.is_dir()), None)
    if firmware is None:
        raise ValueError("firmware root has no usr/lib/firmware or lib/firmware")
    checked_tree(firmware)
    if not list(firmware.glob("iwlwifi-7265*.ucode*")):
        raise ValueError("firmware root lacks Intel 7265 firmware")
    docs = root / "usr/share/doc"
    for name in ("regulatory.db", "regulatory.db.p7s"):
        if not (firmware / name).is_file() and not (firmware / (name + "-debian")).is_file():
            raise ValueError(f"firmware root lacks signed Wi-Fi regulatory database: {name}")
    for package in LICENSE_PACKAGES:
        checked_tree(docs / package)
        if not (docs / package / "copyright").is_file():
            raise ValueError(f"firmware root lacks upstream license: {package}/copyright")
    return firmware, docs


def stage(tree, system, modules_dir, release, firmware_root, support):
    """Retain complete versioned modules, firmware, licenses and transfer hashes."""
    modules = checked_tree(modules_dir, ignore=("build", "source"))
    firmware, docs = firmware_inputs(firmware_root)
    profile = tree / "system" / system
    kernel = profile / "kernel"
    destination = kernel / "lib/modules" / release
    destination.parent.mkdir(parents=True)
    shutil.copytree(modules, destination, symlinks=True,
                    ignore=lambda path, names: {"build", "source"} if Path(path) == modules else set())
    shutil.copytree(firmware, kernel / "lib/firmware", symlinks=True)
    # dpkg-deb extraction does not run update-alternatives. Select Debian's
    # signed regulatory database explicitly, without importing /etc/alternatives.
    for name in ("regulatory.db", "regulatory.db.p7s"):
        dest = kernel / "lib/firmware" / name
        if not dest.exists():
            shutil.copy2(firmware / (name + "-debian"), dest)
    for package in LICENSE_PACKAGES:
        shutil.copytree(docs / package, kernel / "licenses" / package, symlinks=True)
    kernel_docs = docs / ("linux-image-" + release)
    if kernel_docs.is_dir():
        checked_tree(kernel_docs)
        shutil.copytree(kernel_docs, kernel / "licenses" / kernel_docs.name, symlinks=True)
    for name in ("packages.txt", "SHA256SUMS"):
        source = firmware_root / name
        if source.exists():
            if source.is_symlink() or not source.is_file():
                raise ValueError(f"unsafe hardware provenance: {source}")
            (kernel / "provenance").mkdir(exist_ok=True)
            shutil.copy2(source, kernel / "provenance" / name)
    # Only empty mountpoint scaffolding in the copied Base; releases stay untouched.
    for name in ("modules", "firmware"):
        base = tree / "base" / os.readlink(tree / "base/current")
        point = support.virtual_file(base, "/lib/" + name)
        if point.is_symlink() or (point.exists() and (not point.is_dir() or any(point.iterdir()))):
            raise ValueError(f"conflicting Base /lib/{name} mountpoint")
        point.mkdir(parents=True, exist_ok=True)
    # Explicit known devices first; udev can load additional drivers from the same tree.
    support.write(profile / "load-hardware", "#!/bin/sh\nset -eu\n"
                  ". /run/mojt-system/environment\n" +
                  "".join("modprobe " + name + "\n" for name in RUNTIME_MODULES), 0o755)
    support.write(profile / "units/mojt-hardware.service", support.unit(
        "Mojt hardware drivers", "/run/mojt-system/load-hardware",
        "Type=oneshot\nRemainAfterExit=yes",
        "Requires=mojt-setup.service\nAfter=mojt-setup.service\n"
        "Before=NetworkManager.service mojt-console.service\n"))
    wants = profile / "units/mojt.target.wants"
    wants.mkdir()
    (wants / "mojt-hardware.service").symlink_to("../mojt-hardware.service")
    metadata = dict(format=1, profile=PROFILE, kernel_release=release,
                    modules_tree_sha256=support.tree_hash(destination),
                    firmware_tree_sha256=support.tree_hash(kernel / "lib/firmware"),
                    licenses_tree_sha256=support.tree_hash(kernel / "licenses"),
                    early_modules=list(EARLY_MODULES), runtime_modules=list(RUNTIME_MODULES))
    support.write(profile / "hardware.json", json.dumps(metadata, indent=2) + "\n")
    return metadata


def init_script(script):
    hook = 'mount --bind /sysroot/nix /newroot/nix || panic "cannot attach Nix store"'
    if script.count(hook) != 1:
        raise ValueError("hardware System mount hook needs review")
    return script.replace(hook, hook + '''
mount --bind /sysroot/system/current/kernel/lib/modules /newroot/lib/modules ||
    panic "cannot attach kernel modules"
mount -o remount,bind,ro /sysroot/system/current/kernel/lib/modules /newroot/lib/modules ||
    panic "cannot protect kernel modules"
mount --bind /sysroot/system/current/kernel/lib/firmware /newroot/lib/firmware ||
    panic "cannot attach kernel firmware"
mount -o remount,bind,ro /sysroot/system/current/kernel/lib/firmware /newroot/lib/firmware ||
    panic "cannot protect firmware"''')
