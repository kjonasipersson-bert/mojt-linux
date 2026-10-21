#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Build an experimental QEMU direct-kernel boot from an installed Mojt Base.

Host: root, Python 3.11+, cp, cpio, mkfs.ext4, modprobe, zstd,
a kernel image and matching modules, and a static x86_64 BusyBox.
Does not overwrite releases or existing VM disks. No bootloader/partitions.
"""

import argparse
import fcntl
import gzip
import json
import lzma
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import stat
import struct
import subprocess
import tempfile


LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*\Z")
INIT = r"""#!/bin/sh
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
PATH=/bin
export PATH
umask 022
exec </dev/console >/dev/console 2>&1
panic() {
    echo "Mojt early boot: $*" >&2
    echo "Dropping into initramfs shell." >&2
    exec /bin/sh
}
echo "Mojt Linux - early boot"
mount -t devtmpfs devtmpfs /dev || panic "cannot mount /dev"
mount -t proc proc /proc || panic "cannot mount /proc"
mount -t sysfs sysfs /sys || panic "cannot mount /sys"
while IFS= read -r module; do
    [ -n "$module" ] || continue
    insmod "$module" || panic "module load failed: $module"
done </modules.list
tries=0
while [ ! -b /dev/vda ]; do
    tries=$((tries + 1))
    [ "$tries" -le 20 ] || panic "/dev/vda did not appear"
    sleep 1
done
mount -t ext4 -o rw /dev/vda /sysroot || panic "cannot mount Mojt ext4 disk"
version="$(readlink /sysroot/base/current)" || panic "missing base/current"
case "$version" in
    ""|"."|".."|*[!A-Za-z0-9._+-]*) panic "invalid Base version" ;;
esac
root="/sysroot/base/$version"
[ -d "$root" ] || panic "Base generation missing: $version"
[ ! -L "$root" ] || panic "Base generation is a symlink"
[ -f "/sysroot/releases/base-$version.toml" ] || panic "Base metadata missing"
[ -d /sysroot/state/etc ] && [ -d /sysroot/state/var ] ||
    panic "persistent state missing"
[ -d "$root/etc" ] && [ -d "$root/var" ] ||
    panic "Base mount points missing"
echo "Selected Base: $version"
mount --bind "$root" /newroot || panic "cannot bind Base root"
mount --bind /sysroot/state/etc /newroot/etc || panic "cannot mount /etc"
mount --bind /sysroot/state/var /newroot/var || panic "cannot mount /var"
mount --move /dev /newroot/dev || panic "cannot move /dev"
mount --move /proc /newroot/proc || panic "cannot move /proc"
mount --move /sys /newroot/sys || panic "cannot move /sys"
echo "Switching to Mojt Base..."
exec switch_root -c /dev/console /newroot /bin/sh
"""


def fail(message):
    raise ValueError(message)


def label(value):
    if not isinstance(value, str) or not LABEL.fullmatch(value) or value in (".", ".."):
        fail(f"unsafe version/kernel label: {value!r}")
    return value


def require_directory(path, what):
    if path.is_symlink() or not path.is_dir():
        fail(f"{what} must be a real directory: {path}")
    return path


def static_x86_64_elf(path):
    """A static BusyBox must not require the host's dynamic linker."""
    with path.open("rb") as stream:
        header = stream.read(64)
        if len(header) != 64 or header[:6] != b"\x7fELF\x02\x01":
            return False
        if struct.unpack_from("<H", header, 18)[0] != 62:
            return False
        offset = struct.unpack_from("<Q", header, 32)[0]
        size, count = struct.unpack_from("<HH", header, 54)
        if size < 56 or count == 0 or count > 1000:
            return False
        stream.seek(offset)
        for _ in range(count):
            ph = stream.read(size)
            if len(ph) != size or struct.unpack_from("<I", ph, 0)[0] == 3:
                return False
    return True


def kernel_release_from_path(path):
    if not path.name.startswith("vmlinuz-"):
        fail("kernel filename must be vmlinuz-<kernel-release>")
    return label(path.name[len("vmlinuz-"):])


def module_paths(release, modules_dir):
    """Use kmod on the host for dependency ordering; do not load modules."""
    root = modules_dir.resolve(strict=True)
    seen = set()
    paths = []
    for name in ("virtio_pci", "virtio_blk", "ext4"):
        result = subprocess.run(
            ["modprobe", "--set-version", release, "--show-depends", name],
            check=True, capture_output=True, text=True,
        )
        for line in result.stdout.splitlines():
            words = shlex.split(line)
            if not words or words[0] == "builtin":
                continue
            if len(words) != 2 or words[0] != "insmod":
                fail(f"unexpected modprobe dependency instruction: {line!r}")
            path = Path(words[1]).resolve(strict=True)
            if root not in path.parents:
                fail(f"module outside selected kernel tree: {path}")
            if path not in seen:
                paths.append(path)
                seen.add(path)
    return paths


def module_bytes(path):
    if path.suffix == ".zst":
        return subprocess.run(["zstd", "-dc", str(path)], check=True,
                              stdout=subprocess.PIPE).stdout
    if path.suffix == ".xz":
        return lzma.decompress(path.read_bytes())
    if path.suffix == ".gz":
        return gzip.decompress(path.read_bytes())
    if path.suffix == ".ko":
        return path.read_bytes()
    fail(f"unsupported module compression: {path}")


def make_initramfs(root, busybox, modules):
    root.mkdir()
    for name in ("bin", "dev", "proc", "sys", "sysroot", "newroot", "modules"):
        (root / name).mkdir()
    shutil.copy2(busybox, root / "bin/busybox")
    for name in ("sh", "mount", "insmod", "readlink", "sleep", "switch_root"):
        (root / "bin" / name).symlink_to("busybox")
    init = root / "init"
    init.write_text(INIT, encoding="ascii")
    init.chmod(0o755)
    for name, major, minor in (("console", 5, 1), ("null", 1, 3)):
        os.mknod(root / "dev" / name, stat.S_IFCHR | 0o600,
                 os.makedev(major, minor))
    module_list = []
    for index, module in enumerate(modules):
        name = f"{index:04d}.ko"
        (root / "modules" / name).write_bytes(module_bytes(module))
        module_list.append(f"/modules/{name}")
    (root / "modules.list").write_text(
        "\n".join(module_list) + ("\n" if module_list else ""), encoding="ascii"
    )
    entries = ["."] + [
        "./" + path.relative_to(root).as_posix()
        for path in sorted(root.rglob("*"))
    ]
    records = b"\x00".join(os.fsencode(name) for name in entries) + b"\x00"
    archive = subprocess.run(
        ["cpio", "--create", "--format=newc", "--null", "--quiet"],
        cwd=root, input=records, stdout=subprocess.PIPE, check=True,
    ).stdout
    return gzip.compress(archive, mtime=0)


def populate_disk_tree(target, version, tree):
    (tree / "base").mkdir(parents=True)
    (tree / "state").mkdir()
    (tree / "releases").mkdir()
    for origin, dest in (
        (target / "base" / version, tree / "base" / version),
        (target / "state/etc", tree / "state/etc"),
        (target / "state/var", tree / "state/var"),
    ):
        subprocess.run(["cp", "-a", "--", str(origin), str(dest)], check=True)
    (tree / "base/current").symlink_to(version)
    shutil.copy2(target / "state/layout-version", tree / "state/layout-version")
    shutil.copy2(target / "releases" / f"base-{version}.toml",
                 tree / "releases" / f"base-{version}.toml")
    os.chown(tree, 0, 0)
    tree.chmod(0o755)


def run_script():
    return """#!/usr/bin/env bash
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
set -euo pipefail
here="$(cd -- "$(dirname -- "$0")" && pwd -P)"
exec qemu-system-x86_64 \\
    -machine q35,accel=kvm:tcg \\
    -m 1024 -smp 2 \\
    -kernel "$here/vmlinuz" \\
    -initrd "$here/initramfs.cpio.gz" \\
    -append "console=ttyS0,115200 rdinit=/init" \\
    -drive "file=$here/disk.img,if=virtio,format=raw" \\
    -display none -serial mon:stdio -no-reboot
"""


def build(args):
    if os.geteuid() != 0:
        fail("run as root (sudo) to preserve Base ownership and create /dev nodes")
    if platform.machine() != "x86_64":
        fail("first VM builder supports x86_64 only")
    for command in ("cp", "cpio", "mkfs.ext4", "modprobe", "zstd"):
        if not shutil.which(command):
            fail(f"missing host command: {command}")
    target = args.target.resolve(strict=True)
    require_directory(target, "installation")
    lock_file = target / ".install-lock"
    if lock_file.is_symlink() or not lock_file.is_file():
        fail("source is not a Mojt installed target (missing .install-lock)")
    output = args.output.absolute()
    if output.exists() or output.is_symlink():
        fail(f"refusing to overwrite VM output: {output}")
    if output == target or output in target.parents or target in output.parents:
        fail("VM output and source installation must be separate")
    if args.disk_size_mib < 256:
        fail("disk must be at least 256 MiB")
    kernel = args.kernel.resolve(strict=True)
    if not kernel.is_file():
        fail(f"not a regular kernel image: {kernel}")
    release = kernel_release_from_path(kernel)
    modules_dir = args.modules_dir or Path("/lib/modules") / release
    require_directory(modules_dir, "matching kernel modules")
    busybox = args.busybox.resolve(strict=True)
    if not busybox.is_file() or not static_x86_64_elf(busybox):
        fail(f"requires a static x86_64 BusyBox (Debian: busybox-static): {busybox}")

    with lock_file.open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_SH)
        link = target / "base/current"
        if not link.is_symlink():
            fail("source has no base/current symlink")
        version = label(os.readlink(link))
        generation = target / "base" / version
        require_directory(generation, "Base generation")
        for name in ("state/etc", "state/var"):
            require_directory(target / name, name)
        for name in ("state/layout-version", f"releases/base-{version}.toml"):
            path = target / name
            if path.is_symlink() or not path.is_file():
                fail(f"required installation metadata missing: {path}")
        for name in ("etc", "var", "dev", "proc", "sys"):
            require_directory(generation / name, f"Base /{name}")
        modules = module_paths(release, modules_dir)
        output.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix=".mojt-vm-", dir=output.parent) as temp:
            temp = Path(temp)
            result = temp / "result"
            result.mkdir(mode=0o700)
            tree = temp / "filesystem"
            tree.mkdir()
            populate_disk_tree(target, version, tree)
            disk = result / "disk.img"
            with disk.open("wb") as stream:
                stream.truncate(args.disk_size_mib * 1024 * 1024)
            subprocess.run(
                ["mkfs.ext4", "-F", "-q", "-L", "MOJT", "-d", str(tree), str(disk)],
                check=True,
            )
            (result / "initramfs.cpio.gz").write_bytes(
                make_initramfs(temp / "initroot", busybox, modules)
            )
            shutil.copy2(kernel, result / "vmlinuz")
            (result / "run-qemu.sh").write_text(run_script(), encoding="ascii")
            (result / "run-qemu.sh").chmod(0o755)
            (result / "build.json").write_text(
                json.dumps({"format": 1, "base": version, "kernel_release": release,
                            "disk_size_mib": args.disk_size_mib,
                            "modules_in_initramfs": len(modules)}, indent=2) + "\n",
                encoding="ascii",
            )
            # The disk contains persistent state; keep it private to the caller.
            uid = int(os.environ.get("SUDO_UID", "0"))
            gid = int(os.environ.get("SUDO_GID", "0"))
            os.chown(result, uid, gid)
            result.chmod(0o700)
            for item in result.iterdir():
                os.chown(item, uid, gid)
                item.chmod(0o600 if item.name == "disk.img" else
                           0o755 if item.name == "run-qemu.sh" else 0o644)
            if output.exists() or output.is_symlink():
                fail(f"VM output appeared during build; not overwriting: {output}")
            result.rename(output)
    print(f"VM:      {output}")
    print(f"Base:    {version}")
    print(f"Kernel:  {release}")
    print(f"Modules: {len(modules)}")
    print(f"Launch:  {output / 'run-qemu.sh'}")
    print("Experimental direct-kernel boot; no bootloader or partitions.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True,
                        help="existing Mojt installation with base/current and state")
    parser.add_argument("--output", type=Path, required=True,
                        help="new VM output directory (must not exist)")
    parser.add_argument("--kernel", type=Path, required=True,
                        help="Debian /boot/vmlinuz-<kernel-release>")
    parser.add_argument("--modules-dir", type=Path,
                        help="matching kernel modules (default /lib/modules/<release>)")
    parser.add_argument("--busybox", type=Path, default=Path("/usr/bin/busybox"),
                        help="static x86_64 BusyBox (Debian: busybox-static)")
    parser.add_argument("--disk-size-mib", type=int, default=1024)
    args = parser.parse_args()
    try:
        build(args)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"mojt-vm-build: {error}\n")


if __name__ == "__main__":
    main()
