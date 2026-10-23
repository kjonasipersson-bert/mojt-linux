# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Shared helpers for the opt-in System/Nix VM experiment."""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat


STORE_NAME = r"[0-9abcdfghijklmnpqrsvwxyz]{32}-[A-Za-z0-9+._?=-]+"
ROLES = {
    1: {"systemd": "systemd"},
    2: {"dbus": "dbus", "networkmanager": "networkmanager", "curl": "curl",
        "cacert": "cacert", "iproute2": "iproute2"},
    3: {"nix": "nix", "python": "python3"},
}
VERSION = "0.2"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def roles(step):
    require(type(step) is int and step in ROLES, "System step must be 1, 2 or 3")
    return {key: value for n in range(1, step + 1) for key, value in ROLES[n].items()}


def store_path(value):
    require(isinstance(value, str) and re.fullmatch("/nix/store/" + STORE_NAME, value),
            f"invalid System store object: {value!r}")
    require(not value.endswith(".drv"), "System experiment imports binary outputs only")
    return Path(value)


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def tree_hash(root):
    """Transfer integrity, including symlinks and modes; never follow symlinks."""
    digest = hashlib.sha256()
    pending = [root]
    while pending:
        path = pending.pop()
        info = path.lstat()
        name = "." if path == root else path.relative_to(root).as_posix()
        mode = stat.S_IMODE(info.st_mode)
        if stat.S_ISLNK(info.st_mode):
            entry = [name, mode, "link", os.readlink(path)]
        elif stat.S_ISDIR(info.st_mode):
            entry = [name, mode, "dir"]
            pending.extend(sorted(path.iterdir(), reverse=True))
        elif stat.S_ISREG(info.st_mode):
            entry = [name, mode, "file", file_hash(path)]
        else:
            raise ValueError(f"special file in System payload: {path}")
        digest.update(json.dumps(entry, ensure_ascii=True).encode() + b"\n")
    return digest.hexdigest()


def virtual_file(root, absolute):
    """Resolve a guest path, interpreting absolute symlinks inside the guest."""
    require(absolute.startswith("/"), "expected absolute guest path")
    pending, done, followed = list(PurePosixPath(absolute).parts[1:]), [], 0
    while pending:
        part = pending.pop(0)
        if part in ("", "."):
            continue
        if part == "..":
            require(done, "guest symlink escapes root")
            done.pop()
            continue
        candidate = root.joinpath(*done, part)
        if candidate.is_symlink():
            followed += 1
            require(followed <= 40, "guest symlink loop")
            link = os.readlink(candidate)
            target = PurePosixPath(link)
            if link.startswith("/"):
                done = []
            pending = list(target.parts[1:] if link.startswith("/") else target.parts) + pending
        else:
            done.append(part)
    return root.joinpath(*done)


def executable(payload, record, role, *candidates):
    output = record["packages"][role]["output"]
    for suffix in candidates:
        value = output + "/" + suffix
        path = virtual_file(payload, value)
        if path.is_file() and path.stat().st_mode & 0o111:
            return value
    raise ValueError(f"missing {role} executable: {candidates}")


def load_payload(path):
    require(path.is_dir() and not path.is_symlink(), "System payload must be a real directory")
    record_file = path / "system.json"
    require(record_file.is_file() and not record_file.is_symlink(), "missing System payload metadata")
    record = json.loads(record_file.read_text())
    require(record["format"] == 1, "unsupported System payload format")
    expected = roles(record["step"])
    require(set(record["packages"]) == set(expected), "unexpected System package roles")
    seen = set()
    for item in record["objects"]:
        obj = store_path(item["path"])
        require(str(obj) not in seen, "duplicate System store object")
        seen.add(str(obj))
        local = path / "nix/store" / obj.name
        require(tree_hash(local) == item["tree_sha256"], f"System payload changed: {obj.name}")
    require(seen and {p.name for p in (path / "nix/store").iterdir()}
            == {Path(p).name for p in seen}, "System payload has unexpected store objects")
    for role, package in record["packages"].items():
        require(package["attribute"] == expected[role], "System package attribute changed")
        require(str(store_path(package["output"])) in seen, "System output absent from closure")
    require(file_hash(path / "registration") == record["registration_sha256"],
            "System store registration changed")
    source = record["source"]
    require(re.fullmatch(r"[0-9a-f]{40}", source["revision"]), "invalid Nixpkgs revision")
    source_store = str(store_path(source["store"]))
    require(source["system"] == "x86_64-linux", "System VM requires x86_64-linux")
    require(source["path"] == source_store or source["path"].startswith(source_store + "/"),
            "Nixpkgs source path outside its store object")
    if record["step"] == 3:
        require(source_store in seen, "step 3 must retain its Nixpkgs source")
        require((virtual_file(path, source["path"]) / ".git-revision").read_text().strip()
                == source["revision"], "exported Nixpkgs revision changed")
    executable(path, record, "systemd", "lib/systemd/systemd", "bin/systemd")
    for name in ("systemctl", "journalctl", "udevadm", "systemd-sysusers"):
        executable(path, record, "systemd", "bin/" + name)
    vendor = record["packages"]["systemd"]["output"] + "/example/systemd/system"
    for name in ("basic.target", "sysinit.target", "poweroff.target", "reboot.target",
                 "systemd-journald.service", "systemd-journald.socket",
                 "systemd-udevd.service", "systemd-udev-trigger.service"):
        require(virtual_file(path, vendor + "/" + name).is_file(),
                f"missing exported vendor unit: {name}")
    if record["step"] >= 2:
        for role, name in (("dbus", "dbus-daemon"), ("networkmanager", "NetworkManager"),
                           ("networkmanager", "nmcli"), ("curl", "curl"), ("iproute2", "ip")):
            executable(path, record, role, "bin/" + name, "sbin/" + name)
        require(virtual_file(path, record["packages"]["cacert"]["output"] +
                             "/etc/ssl/certs/ca-bundle.crt").is_file(), "missing exported CA bundle")
    if record["step"] == 3:
        for name in ("nix", "nix-store", "nix-instantiate"):
            executable(path, record, "nix", "bin/" + name)
        executable(path, record, "python", "bin/python3")
    return record


def write(path, text, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(mode)


def add_default(path, contents, mode=0o644):
    """Machine-local defaults are add-missing; reject incompatible probe setup."""
    require(not path.is_symlink() and (not path.exists() or path.is_file()),
            f"unsafe System default: {path}")
    if path.exists():
        require(path.read_text() == contents, f"existing configuration conflicts with System probe: {path}")
    else:
        write(path, contents, mode)


def unit(description, executable_path, extra="", dependencies=""):
    return (f"[Unit]\nDescription={description}\n{dependencies}\n"
            f"[Service]\nExecStart={executable_path}\n{extra}\n")


def install(tree, payload, record, busybox, login_mode, repo):
    """Install only into a NEW copied VM tree. Original Base/state stay intact."""
    step = record["step"]
    key = VERSION + "-step" + str(step)
    system = tree / "system" / key
    system.mkdir(parents=True)
    (tree / "system/current").symlink_to(key)
    shutil.copytree(payload / "nix", tree / "nix", symlinks=True)
    for directory, dirs, files in os.walk(tree / "nix", followlinks=False):
        os.chown(directory, 0, 0)
        for name in dirs + files:
            os.chown(Path(directory) / name, 0, 0, follow_symlinks=False)
    shutil.copy2(payload / "registration", system / "registration")
    write(system / "record.json", json.dumps(record, indent=2) + "\n")
    shutil.copy2(busybox, system / "busybox")
    (system / "busybox").chmod(0o755)
    (system / "bin").mkdir()
    (system / "empty").mkdir()
    (system / "units").mkdir()
    (system / "version").write_text(key + "\n")
    write(system / "bin/mojt-system-check", (repo / "tests/check-mojt-system.sh").read_text(), 0o755)

    def export(name, role, *candidates):
        value = executable(payload, record, role, *candidates)
        (system / "bin" / name).symlink_to(value)
        return value

    init = executable(payload, record, "systemd", "lib/systemd/systemd", "bin/systemd")
    sd = record["packages"]["systemd"]["output"]
    for name in ("systemctl", "journalctl", "udevadm", "systemd-sysusers"):
        export(name, "systemd", "bin/" + name)
    # Reuse upstream units, but not their .wants directories or NixOS activation.
    vendor = Path(sd) / "example/systemd/system"
    vendor_local = virtual_file(payload, str(vendor))
    require(vendor_local.is_dir(), "expected Nixpkgs systemd example units")
    for file in vendor_local.iterdir():
        if file.is_file() or file.is_symlink():
            (system / "units" / file.name).symlink_to(str(vendor / file.name))
    for name in ("basic.target", "sysinit.target", "poweroff.target", "reboot.target",
                 "systemd-journald.service", "systemd-journald.socket",
                 "systemd-udevd.service", "systemd-udev-trigger.service"):
        require(virtual_file(payload, str(vendor / name)).is_file(), f"missing upstream unit: {name}")

    def put_unit(name, contents):
        path = system / "units" / name
        path.unlink(missing_ok=True)
        write(path, contents)

    console = ("/run/mojt-system/busybox getty -L -f /run/mojt/issue "
               "-l /run/mojt-system/login 115200 ttyS0 vt100"
               if login_mode == "password" else "/bin/sh -i")
    if login_mode == "password":
        (system / "login").symlink_to("busybox")
    put_unit("mojt-console.service", unit(
        "Mojt serial console (" + login_mode + ")", console,
        "Restart=always\nRestartSec=1\nEnvironment=PATH=/run/mojt-system/bin:/usr/bin:/bin\n"
        "StandardInput=tty\nStandardOutput=tty\n"
        "StandardError=journal\nTTYPath=/dev/ttyS0\nTTYReset=yes\nTTYVHangup=yes",
        "After=systemd-user-sessions.service\n"))
    setup = [
        "#!/bin/sh", "set -eu", "PATH=/run/mojt-system/bin:/usr/bin:/bin",
        "export PATH", "systemd-sysusers /run/mojt-system/sysusers.conf",
        "mkdir -p /run/udev/rules.d /run/log/journal",
        f"for rule in {sd}/lib/udev/rules.d/*; do",
        '    [ -f "$rule" ] || continue',
        '    ln -sfn "$rule" "/run/udev/rules.d/$(basename "$rule")"', "done",
    ]
    write(system / "sysusers.conf", 'g systemd-journal -\n' +
          ('u messagebus - "D-Bus system bus" /var/empty\n' if step >= 2 else ""))
    wanted = ["mojt-console.service", "systemd-journald.socket", "systemd-journald.service",
              "systemd-udevd.service", "systemd-udev-trigger.service"]
    if step >= 2:
        dbus = export("dbus-daemon", "dbus", "bin/dbus-daemon")
        nm = export("NetworkManager", "networkmanager", "bin/NetworkManager", "sbin/NetworkManager")
        export("nmcli", "networkmanager", "bin/nmcli")
        export("curl", "curl", "bin/curl")
        export("ip", "iproute2", "bin/ip", "sbin/ip")
        setup += ["mkdir -p /run/dbus /var/lib/dbus /var/lib/NetworkManager /etc/dbus-1/system.d",
                  "chown messagebus:messagebus /run/dbus"]
        write(system / "dbus.conf", """<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
  <type>system</type>
  <user>messagebus</user>
  <listen>systemd:</listen>
  <auth>EXTERNAL</auth>
  <policy context="default">
    <deny user="*"/>
    <allow user="root"/>
    <deny own="*"/>
    <deny send_type="method_call"/>
    <allow send_type="method_return"/>
    <allow send_type="error"/>
    <allow send_type="signal"/>
    <allow receive_type="method_call"/>
    <allow receive_type="method_return"/>
    <allow receive_type="error"/>
    <allow receive_type="signal"/>
  </policy>
  <policy user="root">
    <allow own="*"/>
    <allow send_destination="*"/>
  </policy>
  <includedir>/etc/dbus-1/system.d</includedir>
</busconfig>
""")
        add_default(tree / "state/etc/NetworkManager/conf.d/90-mojt-vm.conf",
                    "[main]\nplugins=keyfile\ndhcp=internal\ndns=default\nrc-manager=file\n"
                    "auth-polkit=root-only\nhostname-mode=none\n[connectivity]\nenabled=false\n",
                    0o600)
        resolv = tree / "state/etc/resolv.conf"
        require(not resolv.is_symlink() and (not resolv.exists() or resolv.is_file()),
                "VM networking needs a regular /etc/resolv.conf; existing symlink preserved")
        if not resolv.exists():
            write(resolv, "")
        put_unit("dbus.socket", "[Unit]\nDescription=Mojt system bus socket\n"
                 "Requires=mojt-setup.service\nAfter=mojt-setup.service\n"
                 "Before=sockets.target\nDefaultDependencies=no\n"
                 "[Socket]\nListenStream=/run/dbus/system_bus_socket\n"
                 "SocketMode=0666\nDirectoryMode=0755\n")
        put_unit("dbus.service", unit("Mojt system D-Bus",
                 dbus + " --nofork --nopidfile --systemd-activation --config-file=/run/mojt-system/dbus.conf",
                 "Type=notify\nNotifyAccess=main\nRestart=on-failure",
                 "Requires=mojt-setup.service dbus.socket\nAfter=mojt-setup.service dbus.socket\n"))
        put_unit("NetworkManager.service", unit("Mojt NetworkManager", nm + " --no-daemon",
                 "Type=dbus\nBusName=org.freedesktop.NetworkManager\nRestart=on-failure",
                 "Requires=dbus.service\nAfter=dbus.service systemd-udev-trigger.service\n"))
        wanted += ["dbus.service", "NetworkManager.service"]
        cert = record["packages"]["cacert"]["output"] + "/etc/ssl/certs/ca-bundle.crt"
        require(virtual_file(payload, cert).is_file(), "missing exported CA bundle")
        write(system / "ca-path", cert + "\n")
    if step == 3:
        for name in ("nix", "nix-store", "nix-instantiate"):
            export(name, "nix", "bin/" + name)
        python = export("python3", "python", "bin/python3")
        write(system / "tools/mpm-nix-prototype", (repo / "tools/mpm-nix-prototype").read_text(), 0o755)
        write(system / "tests/run-mpm-nix-python.py",
              (repo / "tests/run-mpm-nix-python.py").read_text(), 0o755)
        write(system / "bin/mpm", "#!/bin/sh\nexec " + python +
              ' /run/mojt-system/tools/mpm-nix-prototype --root /var/lib/mojt/ports ports "$@"\n', 0o755)
        source = record["source"]
        write(system / "ports.toml", 'format = 1\n[nixpkgs]\n' +
              "".join(f'{k} = "{source[k]}"\n' for k in ("path", "revision", "system")) +
              '\n[[ports]]\nname = "hello"\nattribute = "hello"\ncommands = ["hello"]\n')
        add_default(tree / "state/etc/nix/nix.conf",
                    "build-users-group =\nmax-jobs = 0\nrequire-sigs = true\n"
                    "substituters = https://cache.nixos.org/\n"
                    "trusted-public-keys = cache.nixos.org-1:6NCHdD59X431o0gWypbMrAURkbJ16ZPMQFGspcDShjY=\n")
        setup += [
            "mkdir -p /nix/var/nix/db /nix/var/nix/gcroots/mojt-system",
            "if [ ! -f /nix/var/nix/.mojt-registration-loaded ]; then",
            "    nix-store --load-db </run/mojt-system/registration",
            "    touch /nix/var/nix/.mojt-registration-loaded", "fi",
        ]
        for obj in record["objects"]:
            name = Path(obj["path"]).name
            setup.append(f"ln -sfn {obj['path']} /nix/var/nix/gcroots/mojt-system/{name}")
    setup += ['echo "Mojt System setup complete"']
    write(system / "setup", "\n".join(setup) + "\n", 0o755)
    put_unit("mojt-setup.service", unit("Mojt System setup", "/run/mojt-system/setup",
             "Type=oneshot\nRemainAfterExit=yes",
             "DefaultDependencies=no\nBefore=sysinit.target systemd-journald.service "
             "systemd-udevd.service systemd-udev-trigger.service\n"))
    wants = system / "units/sysinit.target.wants"
    wants.mkdir()
    (wants / "mojt-setup.service").symlink_to("../mojt-setup.service")
    put_unit("mojt.target", "[Unit]\nDescription=Mojt experimental System\n"
             "Requires=basic.target mojt-setup.service\nAfter=basic.target mojt-setup.service\n"
             "Wants=" + " ".join(wanted) + "\nAllowIsolate=yes\n")
    (system / "units/default.target").unlink(missing_ok=True)
    (system / "units/default.target").symlink_to("mojt.target")
    write(system / "environment", "export PATH=/run/mojt-system/bin:/usr/bin:/bin\n" +
          ("export SSL_CERT_FILE=" + cert + "\nexport NIX_SSL_CERT_FILE=" + cert + "\n"
           if step >= 2 else "") +
          ("export NIX_REMOTE=local\n" if step == 3 else ""))
    write(system / "start", "#!/bin/sh\n. /run/mojt-system/environment\n"
          "export SYSTEMD_UNIT_PATH=/etc/systemd/system:/run/systemd/system:/run/mojt-system/units\n"
          "export SYSTEMD_GENERATOR_PATH=/run/mojt-system/empty\n"
          "export SYSTEMD_ENVIRONMENT_GENERATOR_PATH=/run/mojt-system/empty\n"
          "exec " + init + " --system --unit=mojt.target\n", 0o755)
    return key


def init_script(legacy):
    """Keep the proven disk/Base/state boot and add System/store mounts."""
    old = """[ -x /sysroot/system/prototype-init/busybox ] ||
    panic "missing System init binary"
mount --bind /sysroot/system/prototype-init /newroot/run/mojt-system ||
    panic "cannot attach System init\""""
    new = """[ -x /sysroot/system/current/start ] || panic "missing System start"
mount --bind /sysroot/system/current /newroot/run/mojt-system ||
    panic "cannot attach System profile"
mount -o remount,bind,ro /newroot/run/mojt-system || panic "cannot protect System profile"
mount --bind /sysroot/nix /newroot/nix || panic "cannot attach Nix store"
mount -t tmpfs -o mode=1777,nodev,nosuid tmpfs /newroot/tmp || panic "cannot mount /tmp"
mkdir -p /newroot/run/initramfs/bin || panic "cannot create shutdown runtime"
cp /bin/busybox /newroot/run/initramfs/bin/busybox || panic "cannot stage shutdown BusyBox"
ln -s busybox /newroot/run/initramfs/bin/sh || panic "cannot stage shutdown shell"
cp /shutdown /newroot/run/initramfs/shutdown || panic "cannot stage shutdown script\""""
    require(old in legacy, "VM init template changed; System mount hook needs review")
    result = legacy.replace(old, new).replace("system/prototype-init/version", "system/current/version")
    result = result.replace("system/prototype-init/assembled-at-utc", "system/current/assembled-at-utc")
    handover = 'exec switch_root -c /dev/console /newroot /run/mojt-system/busybox init'
    require(handover in result, "VM init handover changed")
    result = result.replace(handover,
              'mkdir /newroot/run/mojt-disk || panic "cannot create backing disk mount"\n'
              'mount --move /sysroot /newroot/run/mojt-disk || panic "cannot move backing disk"\n'
              'exec switch_root -c /dev/console /newroot /run/mojt-system/start')
    return result.replace("mode=0755 tmpfs", "mode=0755,nodev,nosuid,strictatime tmpfs")


SHUTDOWN = """#!/bin/sh
PATH=/bin
export PATH
busybox sync
if ! busybox umount -a -r; then
    echo "Mojt shutdown: some mounts could only be left read-only" >/dev/console
fi
busybox sync
case "$1" in
    reboot) exec busybox reboot -f ;;
    halt) exec busybox halt -f ;;
    *) exec busybox poweroff -f ;;
esac
"""
