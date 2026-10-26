# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Local-account integration for newly assembled step 10 images."""

import json
import os
import stat

COMMANDS = ("login", "useradd", "usermod", "userdel", "groupadd", "groupmod",
            "groupdel", "gpasswd", "passwd", "pwck", "grpck")
PAM_MODULES = ("pam_unix", "pam_deny", "pam_permit", "pam_loginuid", "pam_motd")
SYSTEMD_PROGRAMS = ("systemd-logind", "systemd-user-runtime-dir", "systemd-sysctl")


def install(tree, profile, inputs, repo, write, add_default, put_unit, unit):
    """Prepare only the private new image; never create passwords or human users."""
    etc = tree / "state/etc"
    # The real builder runs as root; tests may stage images as their own user.
    owner = os.geteuid()
    for directory in (etc,) + tuple(etc / name for name in ("pam.d", "default", "systemd", "sysctl.d", "skel")):
        if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
            raise ValueError("unsafe account configuration directory: " + str(directory))
        if directory.exists():
            info = directory.stat()
            if info.st_uid != owner or stat.S_IMODE(info.st_mode) & 0o022:
                raise ValueError("unprotected account configuration directory: " + str(directory))
        else:
            directory.mkdir(mode=0o755)
    critical = ("passwd", "group", "shadow", "gshadow", "shells", "nsswitch.conf",
                "login.defs", "sudoers", "sudo.conf", "default/useradd", "systemd/logind.conf",
                "sysctl.d/60-mojt-accounts.conf") + tuple("pam.d/" + n for n in ("login", "passwd", "sudo", "systemd-user", "other"))
    for relative in critical:
        path = etc / relative
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError("unsafe account configuration file: " + str(path))
        if path.exists() and (path.stat().st_uid != owner or path.stat().st_mode & 0o022):
            raise ValueError("unprotected account configuration file: " + str(path))
    for name, path in inputs["shadow"].items():
        if name != "passwd":
            (profile / "bin" / name).symlink_to(path)
    (profile / "login").unlink(missing_ok=True)
    (profile / "login").symlink_to(inputs["shadow"]["login"])
    for name in ("sudo", "passwd"):
        (profile / "bin" / name).symlink_to("/run/mojt-privileged/" + name)
    for name in ("visudo", "loginctl"):
        (profile / "bin" / name).symlink_to(inputs[name])
    for name, path in inputs["pam"].items():
        target = profile / "pam" / (name + ".so")
        target.parent.mkdir(exist_ok=True)
        target.symlink_to(path)
    pam = "/run/mojt-system/pam/"
    unix = pam + "pam_unix.so"
    configs = {
        "login": (f"auth required {unix}\naccount required {unix}\n"
                  f"password required {unix} sha512 minlen=8\n"
                  f"session required {pam}pam_loginuid.so\n"
                  f"session required {unix}\nsession required {pam}pam_systemd.so\n"
                  f"session optional {pam}pam_motd.so motd=/run/mojt/motd\n"),
        "passwd": f"password required {unix} sha512 minlen=8\n",
        "sudo": f"auth required {unix}\naccount required {unix}\nsession required {unix}\n",
        "systemd-user": f"account required {unix}\nsession required {pam}pam_permit.so\n",
        "other": "".join(f"{kind} required {pam}pam_deny.so\n"
                         for kind in ("auth", "account", "password", "session")),
    }
    for name, text in configs.items():
        add_default(etc / "pam.d" / name, text)
    add_default(etc / "login.defs", """# Mojt initial local account policy
UID_MIN 1000
UID_MAX 60000
GID_MIN 1000
GID_MAX 60000
SYS_UID_MIN 100
SYS_UID_MAX 999
SYS_GID_MIN 100
SYS_GID_MAX 999
USERGROUPS_ENAB yes
CREATE_HOME yes
HOME_MODE 0700
UMASK 022
ENCRYPT_METHOD SHA512
ENV_PATH /run/mojt-system/bin:/usr/bin:/bin
ENV_SUPATH /run/mojt-system/bin:/usr/bin:/bin
""")
    add_default(etc / "default/useradd", "HOME=/home\nSHELL=/run/mojt-system/bin/bash\nCREATE_MAIL_SPOOL=no\n")
    add_default(etc / "sudoers", """# Mojt initial administration policy; edit with visudo
Defaults env_reset,use_pty,timestamp_timeout=0
Defaults secure_path="/run/mojt-system/bin:/usr/bin:/bin"
Defaults editor=/run/mojt-system/bin/vi
root ALL=(ALL:ALL) ALL
%sudo ALL=(ALL:ALL) ALL
""", 0o440)
    (profile / "sudo").mkdir()
    (profile / "sudo/sudoers.so").symlink_to(inputs["sudo_plugin"])
    add_default(etc / "sudo.conf", "Plugin sudoers_policy /run/mojt-system/sudo/sudoers.so"
                " sudoers_file=/etc/sudoers\nPlugin sudoers_io /run/mojt-system/sudo/sudoers.so\n")
    add_default(etc / "systemd/logind.conf", "[Login]\nKillUserProcesses=yes\nUserStopDelaySec=0\n")
    shells = etc / "shells"
    if shells.is_symlink() or (shells.exists() and not shells.is_file()):
        raise ValueError("unsafe /etc/shells")
    text = shells.read_text() if shells.exists() else "/bin/sh\n"
    if "/run/mojt-system/bin/bash" not in text.splitlines():
        write(shells, text + ("\n" if text and not text.endswith("\n") else "") +
              "/run/mojt-system/bin/bash\n")
    for name in ("passwd", "group", "shadow", "gshadow"):
        path = etc / name
        if (path.is_symlink() or (path.exists() and not path.is_file()) or
                (name in ("passwd", "group") and not path.exists())):
            raise ValueError("account stage requires a regular /etc/" + name)
        # Missing protected databases are provisioned later by the VM builder.
        if name in ("shadow", "gshadow") and path.exists() and path.stat().st_mode & 0o077:
            raise ValueError("unprotected /etc/" + name)
    nss_file = etc / "nsswitch.conf"
    if nss_file.is_symlink() or not nss_file.is_file():
        raise ValueError("account stage requires a regular /etc/nsswitch.conf")
    for database in ("passwd", "group", "shadow"):
        if not any(line.split("#", 1)[0].split()[:2] == [database + ":", "files"]
                   for line in nss_file.read_text().splitlines()):
            raise ValueError("account stage requires local NSS files for " + database)
    skel = etc / "skel"
    if skel.is_symlink() or (skel.exists() and not skel.is_dir()):
        raise ValueError("unsafe /etc/skel")
    skel.mkdir(exist_ok=True)
    write(profile / "privileged-inputs.json", json.dumps(inputs["helpers"], indent=2) + "\n")
    write(profile / "privileged-setup.py", (repo / "tools/mojt-privileged-setup.py").read_text())
    put_unit("mojt-privileged.service", unit("Mojt running-generation privileged helpers",
             inputs["python"] + " -I /run/mojt-system/privileged-setup.py",
             "Type=oneshot\nRemainAfterExit=yes\n",
             "Requires=mojt-setup.service\nAfter=mojt-setup.service\n"
             "Before=systemd-logind.service mojt-console.service mojt-serial-console.service\n"))
    put_unit("systemd-logind.service", unit("Mojt login sessions", inputs["systemd-logind"],
             "Type=notify\nBusName=org.freedesktop.login1\nRestart=on-failure\n"
             "RuntimeDirectory=systemd/sessions systemd/seats systemd/users systemd/inhibit systemd/shutdown\n"
             "StateDirectory=systemd/linger\n",
             "Requires=mojt-privileged.service dbus.service\nAfter=mojt-privileged.service dbus.service\n"))
    put_unit("systemd-user-sessions.service", "[Unit]\nDescription=Mojt login readiness\n"
             "Requires=mojt-privileged.service systemd-logind.service\n"
             "After=mojt-privileged.service systemd-logind.service\n"
             "[Service]\nType=oneshot\nRemainAfterExit=yes\nExecStart=/run/mojt-system/busybox true\n")
    add_default(etc / "sysctl.d/60-mojt-accounts.conf", "net.ipv4.ping_group_range = 1000 60000\n")
    put_unit("mojt-account-sysctl.service", unit("Mojt unprivileged ping sockets",
             inputs["systemd-sysctl"] + " --prefix=/net/ipv4/ping_group_range",
             "Type=oneshot\nRemainAfterExit=yes\n",
             "Requires=mojt-setup.service\nAfter=mojt-setup.service\n"
             "Before=mojt-console.service mojt-serial-console.service\n"))
    runtime = inputs["systemd-user-runtime-dir"]
    put_unit("user-runtime-dir@.service", unit("Mojt user runtime directory", runtime + " start %i",
             "ExecStop=" + runtime + " stop %i\nType=oneshot\nRemainAfterExit=yes\nSlice=user-%i.slice\n",
             "After=systemd-logind.service\n"))
    put_unit("user@.service", unit("Mojt user manager", inputs["systemd"] + " --user",
             "User=%i\nPAMName=systemd-user\nType=notify\nKillMode=mixed\nDelegate=yes\nSlice=user-%i.slice\n"
             "Environment=SYSTEMD_UNIT_PATH=/run/mojt-system/user-units\n"
             "Environment=XDG_RUNTIME_DIR=/run/user/%i\n"
             "Environment=PATH=/run/mojt-system/bin:/usr/bin:/bin\n",
             "Requires=user-runtime-dir@%i.service\nAfter=user-runtime-dir@%i.service systemd-logind.service\n"))
    write(profile / "user-units/default.target", "[Unit]\nDescription=Mojt user session\n")
    console = profile / "units/mojt-console.service"
    console.write_text(console.read_text().replace("[Unit]\n", "[Unit]\n"
                      "Requires=mojt-privileged.service systemd-logind.service mojt-account-sysctl.service\n"
                      "After=mojt-privileged.service systemd-logind.service mojt-account-sysctl.service\n", 1))
    sysusers = profile / "sysusers.conf"
    sysusers.write_text(sysusers.read_text() + "g sudo -\n")
    bus = profile / "dbus.conf"
    bus.write_text(bus.read_text().replace('<deny user="*"/>', '<allow user="*"/>', 1).replace(
        '<deny send_type="method_call"/>', '<deny send_type="method_call"/>\n'
        '    <allow send_destination="org.freedesktop.DBus"/>\n'
        '    <allow send_destination="org.freedesktop.login1"/>', 1))
    wrapper = profile / "bin/mpm"
    wrapper.write_text(wrapper.read_text().replace("#!/bin/sh\n", "#!/bin/sh\n"
        "umask 022\n"
        'if [ "$(/usr/bin/id -u)" != 0 ]; then\n'
        '    case "$1:$2" in ports:list) ;;\n'
        '        *) echo "mpm: shared Ports changes require an administrator" >&2; exit 1 ;;\n'
        '    esac\nfi\n', 1))
    return ["mojt-privileged.service", "systemd-logind.service", "systemd-user-sessions.service",
            "mojt-account-sysctl.service"]
