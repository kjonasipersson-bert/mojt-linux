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
from datetime import datetime, timezone
import fcntl
import getpass
import gzip
import json
import lzma
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shlex
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import time


LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*\Z")
# Temporary System prototype; BusyBox is not Mojt's intended production init.
SYSTEM_INIT = "prototype-init"
SYSTEM_VERSION = "0.1"
SYSTEM_INITTAB = """# Mojt Linux - experimental System init (unauthenticated VM console)
# BusyBox init uses the first field as the device name under /dev.
# This is a development-only root shell. No login/password check is done.
ttyS0::respawn:/bin/sh -i
::ctrlaltdel:/run/mojt-system/busybox reboot
::shutdown:/run/mojt-system/busybox sync
"""
SYSTEM_LOGIN_INITTAB = """# Mojt Linux - System prototype authenticated serial login
# The getty applet invokes the *login* applet; it never bypasses authentication.
ttyS0::respawn:/run/mojt-system/busybox getty -L -f /run/mojt/issue -l /run/mojt-system/login 115200 ttyS0 vt100
::ctrlaltdel:/run/mojt-system/busybox reboot
::shutdown:/run/mojt-system/busybox sync
"""
LOGIN_APPLETS = frozenset({"getty", "login", "passwd"})
REQUIRED_APPLETS = frozenset({
    "init", "poweroff", "reboot", "sync", "sh", "mount", "insmod",
    "readlink", "sleep", "switch_root", "mkdir", "hostname",
})
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
# /run is System runtime state, never a mutable part of Base.
mount -t tmpfs -o mode=0755 tmpfs /newroot/run ||
    panic "cannot mount /run"
mkdir /newroot/run/mojt-system || panic "cannot create System runtime mountpoint"
[ -x /sysroot/system/prototype-init/busybox ] ||
    panic "missing System init binary"
mount --bind /sysroot/system/prototype-init /newroot/run/mojt-system ||
    panic "cannot attach System init"
mount --bind /sysroot/state/etc /newroot/etc || panic "cannot mount /etc"
mount --bind /sysroot/state/var /newroot/var || panic "cannot mount /var"
# System identity is assembled at boot from independently selected releases.
IFS= read -r mojt_system_version </sysroot/system/prototype-init/version ||
    panic "missing System version"
IFS= read -r mojt_vm_built </sysroot/system/prototype-init/assembled-at-utc ||
    panic "missing System build metadata"
IFS= read -r mojt_hostname </sysroot/state/etc/hostname ||
    panic "missing persistent hostname"
case "$mojt_hostname" in
    ""|*[!A-Za-z0-9.-]*) panic "invalid hostname in persistent state" ;;
esac
hostname "$mojt_hostname" || panic "cannot set hostname"
IFS= read -r mojt_kernel </proc/sys/kernel/osrelease ||
    panic "cannot identify kernel"
mkdir /newroot/run/mojt || panic "cannot create runtime identity directory"
printf 'Mojt Linux %s/%s (x86_64)\n\n' "$mojt_system_version" "$version" \
    >/newroot/run/mojt/issue || panic "cannot write System issue"
printf 'Welcome to Mojt Linux\n\nSystem:       %s\nBase:         %s\nVM built UTC: %s\nKernel:       %s\n\nMojt Linux is an experimental distribution.\n' \
    "$mojt_system_version" "$version" "$mojt_vm_built" "$mojt_kernel" \
    >/newroot/run/mojt/motd || panic "cannot write System MOTD"
mount --move /dev /newroot/dev || panic "cannot move /dev"
mount --move /proc /newroot/proc || panic "cannot move /proc"
mount --move /sys /newroot/sys || panic "cannot move /sys"
echo "Switching to Mojt Base..."
exec switch_root -c /dev/console /newroot /run/mojt-system/busybox init
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


def validate_busybox_applets(binary, login_mode="development"):
    """Check that the chosen BusyBox supports every used applet."""
    result = subprocess.run(
        [str(binary), "--list"], check=True, capture_output=True, text=True,
    )
    required = REQUIRED_APPLETS
    if login_mode == "password":
        required |= LOGIN_APPLETS
    missing = required - set(result.stdout.splitlines())
    if missing:
        fail(f"static BusyBox missing applets: {', '.join(sorted(missing))}")


def install_system_init(tree, busybox, login_mode="development"):
    """Stage System-owned init and the requested machine-local inittab.

    Password mode cannot inherit an old unauthenticated development inittab.
    """
    if login_mode not in ("development", "password"):
        fail(f"unsupported login mode: {login_mode}")
    system = tree / "system" / SYSTEM_INIT
    system.mkdir(parents=True, exist_ok=True)
    binary = system / "busybox"
    shutil.copy2(busybox, binary)
    os.chown(binary, 0, 0)
    binary.chmod(0o755)
    if login_mode == "password":
        (system / "login").symlink_to("busybox")
    contents = SYSTEM_LOGIN_INITTAB if login_mode == "password" else SYSTEM_INITTAB
    template = system / "inittab"
    template.write_text(contents, encoding="ascii")
    template.chmod(0o644)
    assembled_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    (system / "version").write_text(SYSTEM_VERSION + "\n", encoding="ascii")
    (system / "assembled-at-utc").write_text(assembled_at + "\n", encoding="ascii")

    inittab = tree / "state/etc/inittab"
    if inittab.is_symlink() or (inittab.exists() and not inittab.is_file()):
        fail(f"refusing conflicting persistent /etc/inittab: {inittab}")
    if inittab.exists():
        if login_mode == "password" and inittab.read_text(encoding="utf-8") != contents:
            fail("existing /etc/inittab is not the authenticated login configuration; "
                 "refusing to enable password mode alongside an unchecked root shell")
    else:
        # A new default is added only to the copied VM state.
        with inittab.open("x", encoding="ascii") as stream:
            stream.write(contents)
        inittab.chmod(0o644)
    return assembled_at


def prepare_system_identity(tree):
    """Initialize missing VM-only defaults without changing existing /etc files."""
    etc = require_directory(tree / "state/etc", "copied persistent /etc")
    hostname = etc / "hostname"
    if hostname.is_symlink() or (hostname.exists() and not hostname.is_file()):
        fail(f"unsafe persistent hostname: {hostname}")
    if hostname.exists():
        raw = hostname.read_text(encoding="utf-8")
        name = raw.removesuffix("\n")
        if raw not in (name, name + "\n"):
            fail("hostname must be exactly one line")
    else:
        name = "mojt"
        with hostname.open("x", encoding="ascii") as stream:
            stream.write(name + "\n")
        hostname.chmod(0o644)
    if len(name) > 253 or not re.fullmatch(
        r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", name
    ):
        fail("invalid persistent hostname: expected an ASCII DNS-style name")

    # Existing MOTD files (including local customizations) are admin-owned.
    # Only a missing file gets a link to the volatile System-generated MOTD.
    motd = etc / "motd"
    if not motd.exists() and not motd.is_symlink():
        motd.symlink_to("/run/mojt/motd")


def password_hash_from_terminal():
    """Use host OpenSSL's SHA512-crypt implementation; never pass a password as argv."""
    if not sys.stdin.isatty():
        fail("password mode needs an interactive terminal (do not pass secrets via flags)")
    try:
        first = getpass.getpass("New Mojt VM root password: ")
        second = getpass.getpass("Confirm Mojt VM root password: ")
    except (EOFError, KeyboardInterrupt):
        fail("password entry aborted")
    if first != second:
        fail("passwords did not match")
    if len(first) < 8 or "\n" in first or "\r" in first or "\x00" in first:
        fail("use a password of at least eight characters without control line breaks")
    result = subprocess.run(
        ["openssl", "passwd", "-6", "-stdin"],
        input=first + "\n", text=True, capture_output=True, check=True,
    )
    digest = result.stdout.strip()
    if not digest.startswith("$6$") or ":" in digest or "\n" in digest:
        fail("openssl did not return a valid SHA512-crypt hash")
    return digest


def virtual_root_file(root, path):
    """Resolve a guest-absolute shell path without following host-absolute links.

    The path is interpreted relative to the copied Base tree, including
    absolute symbolic links that refer to paths inside the guest filesystem.
    """
    if not isinstance(path, str) or not path.startswith("/") or path == "/":
        fail(f"root shell must be an absolute path inside Base: {path!r}")
    if any(ord(char) < 32 or char == ":" for char in path):
        fail(f"invalid root shell: {path!r}")
    pure = PurePosixPath(path)
    if ".." in pure.parts or "." in path.split("/"):
        fail(f"unsafe root shell: {path!r}")

    pending = list(pure.parts[1:])
    resolved = []
    followed = 0
    while pending:
        component = pending.pop(0)
        if component in ("", ".", ".."):
            fail(f"invalid root shell component: {path!r}")
        candidate = root.joinpath(*resolved, component)
        if candidate.is_symlink():
            followed += 1
            if followed > 32:
                fail(f"root shell symlink loop: {path!r}")
            link = os.readlink(candidate)
            target = PurePosixPath(link)
            if link.startswith("/"):
                resolved = []
            pending = list(target.parts[1:] if link.startswith("/") else target.parts) + pending
            # Relative '..' is valid in the Base tree but must not escape it.
            normalized = []
            for part in resolved + pending:
                if part == "..":
                    if not normalized:
                        fail(f"root shell symlink escapes Base: {path!r}")
                    normalized.pop()
                elif part not in ("", ".", "/"):
                    normalized.append(part)
            pending = normalized
            resolved = []
        else:
            resolved.append(component)
    result = root.joinpath(*resolved)
    if result.is_symlink() or not result.is_file() or not (result.stat().st_mode & 0o111):
        fail(f"root shell not executable in installed Base: {path}")
    return result


def prepare_vm_root_shell(tree, version, replacement=None):
    """Validate root login shell, or explicitly correct *copied* /etc/passwd.

    This never writes to the source installation or to any Base generation.
    Preserve other account records, ownership, mode and original line endings.
    """
    rootfs = require_directory(tree / "base" / version, "copied Base generation")
    passwd = tree / "state/etc/passwd"
    if passwd.is_symlink() or not passwd.is_file():
        fail(f"missing or unsafe persistent account file: {passwd}")
    original = passwd.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    root_indices = [index for index, line in enumerate(lines)
                    if line.startswith("root:")]
    if len(root_indices) != 1:
        fail("expected exactly one root record in copied /etc/passwd")
    index = root_indices[0]
    line = lines[index]
    fields = line.rstrip("\n").split(":")
    if len(fields) != 7 or fields[1:4] != ["x", "0", "0"]:
        fail("malformed root account in copied /etc/passwd")
    old_shell = fields[6]
    chosen = replacement if replacement is not None else old_shell
    try:
        virtual_root_file(rootfs, chosen)
    except ValueError as error:
        if replacement is None:
            fail(f"{error}; configure the copied VM account explicitly "
                 "with --root-shell /bin/sh")
        raise
    if replacement is None or replacement == old_shell:
        return old_shell

    fields[6] = replacement
    new_line = ":".join(fields) + ("\n" if line.endswith("\n") else "")
    lines[index] = new_line
    mode = stat.S_IMODE(passwd.stat().st_mode)
    owner = passwd.stat()
    # Only the staged VM tree is modified; an existing passwd is not discarded.
    fd, tmp_name = tempfile.mkstemp(prefix=".mojt-passwd-", dir=passwd.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.writelines(lines)
        os.chmod(tmp_name, mode)
        os.chown(tmp_name, owner.st_uid, owner.st_gid)
        os.replace(tmp_name, passwd)
    finally:
        Path(tmp_name).unlink(missing_ok=True)
    print(f"mojt-vm-build: copied VM root shell: {old_shell} -> {replacement}")
    return replacement


def provision_vm_root_login(tree, password_hash=None):
    """Initialize *copied* guest shadow files, never host credentials.

    Existing shadow files are preserved; a missing one needs an explicitly
    supplied hash (normally gathered from the terminal). Other accounts
    are locked rather than accidentally receiving usable passwords.
    """
    etc = require_directory(tree / "state/etc", "copied persistent /etc")
    passwd = etc / "passwd"
    group = etc / "group"
    shadow = etc / "shadow"
    gshadow = etc / "gshadow"
    for path in (passwd, group):
        if path.is_symlink() or not path.is_file():
            fail(f"required regular account file missing: {path}")
    for path in (shadow, gshadow):
        if path.is_symlink() or (path.exists() and not path.is_file()):
            fail(f"refusing unsafe account file: {path}")
    names = []
    root_count = 0
    for line in passwd.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        fields = line.split(":")
        if len(fields) != 7 or not fields[0] or fields[0] in names:
            fail("invalid or duplicate /etc/passwd account")
        names.append(fields[0])
        if fields[0] == "root":
            root_count += 1
            if fields[1] != "x" or fields[2] != "0" or fields[3] != "0":
                fail("expected root:x:0:0 in copied /etc/passwd")
    if root_count != 1:
        fail("expected exactly one root account")
    if shadow.exists():
        if password_hash is not None:
            fail("refusing to overwrite existing /etc/shadow with new credentials")
        root_entries = [
            line.split(":")[1] for line in shadow.read_text(encoding="utf-8").splitlines()
            if line.startswith("root:")
        ]
        if len(root_entries) != 1 or not root_entries[0].startswith("$"):
            fail("root account is locked or missing from existing /etc/shadow")
        if stat.S_IMODE(shadow.stat().st_mode) & 0o077:
            fail("/etc/shadow has unsafe read/write permissions")
    else:
        if password_hash is None or not password_hash.startswith("$6$"):
            fail("root password has not been provisioned")
        today = int(time.time() // 86400)  # Shadow uses days since Unix epoch.
        lines = [
            f"{name}:{password_hash if name == 'root' else '!'}:"
            f"{today if name == 'root' else 0}:0:99999:7:::"
            for name in names
        ]
        fd = os.open(shadow, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write("\n".join(lines) + "\n")
        os.chown(shadow, 0, 0)
        shadow.chmod(0o600)

    if not gshadow.exists():
        groups = []
        for line in group.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            fields = line.split(":")
            if len(fields) != 4 or not fields[0] or fields[0] in groups:
                fail("invalid or duplicate /etc/group entry")
            groups.append(fields[0])
        fd = os.open(gshadow, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write("".join(f"{name}:!::\n" for name in groups))
        os.chown(gshadow, 0, 0)
        gshadow.chmod(0o600)

    securetty = etc / "securetty"
    if securetty.is_symlink() or (securetty.exists() and not securetty.is_file()):
        fail("unsafe /etc/securetty")
    if securetty.exists():
        allowed = {
            line.strip() for line in securetty.read_text(encoding="utf-8").splitlines()
        }
        if "ttyS0" not in allowed:
            fail("existing /etc/securetty does not permit root on ttyS0")
    else:
        with securetty.open("x", encoding="ascii") as stream:
            stream.write("ttyS0\n")
        securetty.chmod(0o644)


def warn_missing_shadow(tree):
    """Diagnose inconsistent source account state, without altering credentials."""
    passwd = tree / "state/etc/passwd"
    shadow = tree / "state/etc/shadow"
    if passwd.is_file() and not passwd.is_symlink() and not shadow.exists():
        for line in passwd.read_text(encoding="utf-8").splitlines():
            parts = line.split(":")
            if len(parts) > 1 and parts[0] == "root" and parts[1] == "x":
                print("mojt-vm-build: note: root expects /etc/shadow, "
                      "but it is missing. The development console bypasses "
                      "authentication; login is NOT configured.",
                      file=sys.stderr)
                return


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
    for name in ("sh", "mount", "insmod", "readlink", "sleep", "switch_root", "mkdir", "hostname"):
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
    commands = ["cp", "cpio", "mkfs.ext4", "modprobe", "zstd"]
    if args.login_mode == "password":
        commands.append("openssl")
    for command in commands:
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
    validate_busybox_applets(busybox, args.login_mode)

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
            assembled_at = install_system_init(tree, busybox, args.login_mode)
            prepare_system_identity(tree)
            if args.login_mode == "password":
                prepare_vm_root_shell(tree, version, args.root_shell)
                copied_shadow = tree / "state/etc/shadow"
                password_hash = None
                if not copied_shadow.exists() and not copied_shadow.is_symlink():
                    password_hash = password_hash_from_terminal()
                provision_vm_root_login(tree, password_hash)
            else:
                warn_missing_shadow(tree)
                print("mojt-vm-build: WARNING: development mode gives unauthenticated "
                      "root access on the VM console.", file=sys.stderr)
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
                            "modules_in_initramfs": len(modules),
                            "system_init": "busybox-prototype",
                            "system_version": SYSTEM_VERSION,
                            "vm_assembled_utc": assembled_at,
                            "login_mode": args.login_mode}, indent=2) + "\n",
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
    parser.add_argument("--root-shell", metavar="PATH",
                        help="password mode only: explicitly select root's shell "
                             "in the NEW VM's copied /etc/passwd (e.g. /bin/sh)")
    parser.add_argument("--login-mode", choices=("development", "password"),
                        default="development",
                        help="password: prompt for a new root password if guest shadow "
                             "is missing; development: unsafe unauthenticated console")
    args = parser.parse_args()
    try:
        if args.root_shell and args.login_mode != "password":
            fail("--root-shell requires --login-mode password")
        build(args)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"mojt-vm-build: {error}\n")


if __name__ == "__main__":
    main()
