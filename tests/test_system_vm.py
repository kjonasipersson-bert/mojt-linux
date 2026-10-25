#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""System payload/VM integration regressions; no real Nix or QEMU acceptance."""

import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
import types
import xml.etree.ElementTree as ET


REPO = Path(__file__).resolve().parents[1]


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, REPO / "tools" / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


system = module("mojt_system_test", "mojt_system.py")
vm = module("mojt_system_vm_builder", "mojt-vm-build.py")


class SystemVmTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mojt-system-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.payload = self.root / "payload"
        self.payload.mkdir()
        self.tree = self.root / "vm"
        (self.tree / "state/etc").mkdir(parents=True)
        (self.tree / "state/var").mkdir()
        system.write(self.tree / "base/0.1.3/usr/bin/sh", "synthetic Base shell", 0o755)
        system.write(self.tree / "state/etc/passwd", "root:x:0:0:root:/root:/bin/sh\n")
        system.write(self.tree / "state/etc/inittab", "old persistent inittab\n")
        self.busybox = self.root / "fake-busybox"
        self.busybox.write_text("synthetic static BusyBox")

    def fixture(self, step):
        packages = {}
        for index, (role, attribute) in enumerate(system.roles(step).items(), 1):
            value = "/nix/store/" + "0123456789abcdfghijklmnpqrsvwxyz"[index] * 32 + "-" + role
            packages[role] = dict(attribute=attribute, output=value, version="test-version")
            base = self.payload / value.lstrip("/")
            names = {
                "systemd": ["lib/systemd/systemd", "bin/systemctl", "bin/journalctl",
                            "bin/udevadm", "bin/systemd-sysusers"],
                "dbus": ["bin/dbus-daemon"], "networkmanager": ["bin/NetworkManager", "bin/nmcli"],
                "curl": ["bin/curl"], "cacert": [], "iproute2": ["bin/ip"],
                "nix": ["bin/nix", "bin/nix-store", "bin/nix-instantiate"], "python": ["bin/python3"],
                "shell": ["bin/bash"],
                "kmod": ["bin/modprobe", "bin/lsmod"],
                "wpa-supplicant": ["bin/wpa_supplicant"], "iw": ["bin/iw"],
                **{role: ["bin/" + name for name in names]
                   for role, names in system.ADMIN_COMMANDS.items()},
            }[role]
            base.mkdir(parents=True)
            for name in names:
                system.write(base / name, "#!/bin/sh\nexit 0\n", 0o755)
            if role == "systemd":
                vendor = base / "example/systemd/system"
                for name in ("basic.target", "sysinit.target", "poweroff.target", "reboot.target",
                             "systemd-journald.service", "systemd-journald.socket",
                             "systemd-udevd.service", "systemd-udev-trigger.service"):
                    system.write(vendor / name, "[Unit]\nDescription=Synthetic vendor unit\n")
                system.write(base / "lib/udev/rules.d/50-synthetic.rules", "# synthetic\n")
            if role == "cacert":
                system.write(base / "etc/ssl/certs/ca-bundle.crt", "synthetic cert")
        source = dict(store="/nix/store/" + "a" * 32 + "-nixpkgs",
                      path="/nix/store/" + "a" * 32 + "-nixpkgs/nixpkgs",
                      revision="b" * 40, system="x86_64-linux")
        if step >= 3:
            system.write(self.payload / source["path"].lstrip("/") / ".git-revision", source["revision"])
        objects = [dict(path="/nix/store/" + p.name, tree_sha256=system.tree_hash(p), nar_hash="test")
                   for p in (self.payload / "nix/store").iterdir()]
        system.write(self.payload / "registration", "synthetic registration")
        record = dict(format=1, step=step, packages=packages, source=source, objects=objects,
                      registration_sha256=system.file_hash(self.payload / "registration"))
        system.write(self.payload / "system.json", json.dumps(record))
        return record

    def install(self, step, login="development"):
        record = self.fixture(step)
        self.assertEqual(system.load_payload(self.payload), record)
        with mock.patch.object(system.os, "chown"):
            key = system.install(self.tree, self.payload, record, self.busybox, login, REPO)
        return self.tree / "system" / key, record

    def test_steps_are_cumulative_and_explicit(self):
        self.assertEqual(set(system.roles(1)), {"systemd"})
        self.assertTrue(set(system.roles(1)) < set(system.roles(2)) < set(system.roles(3))
                        < set(system.roles(4)) < set(system.roles(5)) < set(system.roles(6)))
        for value in (0, 7, True, "1"):
            with self.assertRaises(ValueError):
                system.roles(value)

    def test_failed_uefi_assembly_publishes_nothing_and_preserves_source(self):
        self.fixture(5)
        for name in ("etc", "var", "dev", "proc", "sys"):
            (self.tree / "base/0.1.3" / name).mkdir()
        (self.tree / "base/current").symlink_to("0.1.3")
        system.write(self.tree / ".install-lock", "")
        system.write(self.tree / "state/layout-version", "1\n")
        system.write(self.tree / "releases/base-0.1.3.toml", "format = 1\n")
        before = system.tree_hash(self.tree)
        kernel = self.root / "vmlinuz-test"
        kernel.write_bytes(b"synthetic kernel")
        modules = self.root / "modules"
        modules.mkdir()
        self.busybox.write_text("#!/bin/sh\nprintf '%s\\n' cp ln umount halt\n")
        self.busybox.chmod(0o755)
        output = self.root / "output-vm"
        args = types.SimpleNamespace(boot_mode="uefi", system_payload=self.payload,
            disk_size_mib=512, target=self.tree, output=output, kernel=kernel,
            modules_dir=modules, busybox=self.busybox, login_mode="development", root_shell=None)

        def fail_assembly(disk, *unused, **options):
            disk.write_bytes(b"incomplete GPT image")
            raise ValueError("synthetic GRUB assembly failure")

        with mock.patch.object(vm.os, "geteuid", return_value=0), \
                mock.patch.object(vm.platform, "machine", return_value="x86_64"), \
                mock.patch.object(vm.os, "chown"), \
                mock.patch.object(vm.shutil, "which", return_value="/synthetic/command"), \
                mock.patch.object(vm, "static_x86_64_elf", return_value=True), \
                mock.patch.object(vm, "validate_busybox_applets"), \
                mock.patch.object(vm, "module_paths", return_value=[]), \
                mock.patch.object(vm, "make_initramfs", return_value=b"synthetic initramfs"), \
                mock.patch.object(vm.boot, "build_disk", side_effect=fail_assembly), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(ValueError, "synthetic GRUB"):
                vm.build(args)
        self.assertFalse(output.exists())
        self.assertEqual(list(self.root.glob(".mojt-vm-*")), [])
        self.assertEqual(system.tree_hash(self.tree), before)

    def test_transfer_digest_covers_bytes_mode_and_link_target(self):
        data = self.root / "objects"
        data.mkdir()
        file = data / "file"
        file.write_text("first")
        link = data / "link"
        link.symlink_to("/host/path/never/followed")
        before = system.tree_hash(data)
        file.write_text("second")
        self.assertNotEqual(system.tree_hash(data), before)
        before = system.tree_hash(data)
        file.chmod(0o755)
        self.assertNotEqual(system.tree_hash(data), before)
        before = system.tree_hash(data)
        link.unlink()
        link.symlink_to("/a/different/target")
        self.assertNotEqual(system.tree_hash(data), before)

    def test_special_files_rejected_without_opening_fifo(self):
        file = self.root / "fifo"
        os.mkfifo(file)
        with self.assertRaisesRegex(ValueError, "special file"):
            system.tree_hash(file)

    def test_guest_symlinks_resolve_inside_payload(self):
        data = self.root / "guest"
        system.write(data / "usr/bin/program", "synthetic")
        (data / "bin").symlink_to("/usr/bin")
        self.assertEqual(system.virtual_file(data, "/bin/program"), data / "usr/bin/program")
        (data / "usr/bin/escape").symlink_to("../../../../etc/passwd")
        with self.assertRaisesRegex(ValueError, "escapes"):
            system.virtual_file(data, "/bin/escape")

    def test_changed_payload_and_registration_are_rejected(self):
        record = self.fixture(1)
        system.load_payload(self.payload)
        file = self.payload / record["packages"]["systemd"]["output"].lstrip("/") / "bin/systemctl"
        file.write_text("changed")
        with self.assertRaisesRegex(ValueError, "payload changed"):
            system.load_payload(self.payload)
        record["objects"][0]["tree_sha256"] = system.tree_hash(file.parents[1])
        system.write(self.payload / "system.json", json.dumps(record))
        (self.payload / "registration").write_text("changed")
        with self.assertRaisesRegex(ValueError, "registration changed"):
            system.load_payload(self.payload)

    def test_missing_or_extra_store_objects_are_rejected(self):
        self.fixture(1)
        (self.payload / "nix/store/unexpected").mkdir()
        with self.assertRaisesRegex(ValueError, "unexpected store objects"):
            system.load_payload(self.payload)

    def test_step1_preserves_base_and_persistent_credentials(self):
        before = system.tree_hash(self.tree / "base")
        passwd = (self.tree / "state/etc/passwd").read_bytes()
        system_dir, record = self.install(1)
        self.assertEqual(system.tree_hash(self.tree / "base"), before)
        self.assertEqual((self.tree / "state/etc/passwd").read_bytes(), passwd)
        self.assertEqual((self.tree / "state/etc/inittab").read_text(), "old persistent inittab\n")
        self.assertNotIn("NetworkManager", (system_dir / "units/mojt.target").read_text())
        self.assertFalse((system_dir / "bin/mpm").exists())
        self.assertEqual((self.tree / "system/current").readlink().name, "0.2-step1")
        self.assertTrue((self.tree / "nix/store").is_dir())
        self.assertIn(record["packages"]["systemd"]["output"], (system_dir / "start").read_text())

    def test_password_console_uses_authenticated_login(self):
        directory, _ = self.install(1, "password")
        console = (directory / "units/mojt-console.service").read_text()
        self.assertIn("getty", console)
        self.assertIn("-l /run/mojt-system/login", console)
        self.assertNotIn("ExecStart=/bin/sh -i", console)
        self.assertEqual((directory / "login").readlink().name, "busybox")

    def test_setup_precedes_boot_services_and_keeps_admin_precedence(self):
        directory, _ = self.install(1)
        setup = (directory / "units/mojt-setup.service").read_text()
        self.assertIn("Before=sysinit.target systemd-journald.service", setup)
        self.assertIn("Requires=basic.target mojt-setup.service",
                      (directory / "units/mojt.target").read_text())
        self.assertIn("/etc/systemd/system:/run/systemd/system:/run/mojt-system/units",
                      (directory / "start").read_text())
        for script in ("start", "setup", "bin/mojt-system-check"):
            subprocess.run(["sh", "-n", str(directory / script)], check=True, capture_output=True)

    def test_vendor_dependency_directories_are_not_imported_through_symlinks(self):
        record = self.fixture(1)
        vendor = self.payload / record["packages"]["systemd"]["output"].lstrip("/") / "example/systemd/system"
        system.write(vendor / "sysinit.target.wants/optional.service", "upstream default dependency")
        for suffix in ("requires", "upholds"):
            (vendor / ("basic.target." + suffix)).symlink_to("sysinit.target.wants")
        with mock.patch.object(system.os, "chown"):
            key = system.install(self.tree, self.payload, record, self.busybox, "development", REPO)
        units = self.tree / "system" / key / "units"
        self.assertEqual(sorted(p.name for p in (units / "sysinit.target.wants").iterdir()),
                         ["mojt-setup.service"])
        for suffix in ("requires", "upholds"):
            self.assertFalse((units / ("basic.target." + suffix)).is_symlink())

    @unittest.skipUnless(Path("/usr/bin/systemctl").is_file(), "real systemctl unavailable")
    def test_first_boot_presets_leave_optional_units_disabled(self):
        directory, _ = self.install(1)
        start = (directory / "start").read_text()
        policy = "/run/systemd/system-preset/99-mojt-vm.preset"
        self.assertLess(start.index("cp /run/mojt-system/system-preset/99-mojt-vm.preset " + policy),
                        start.index("exec "))
        optional = {"optional.service": "[Service]\nExecStart=/bin/true\n",
                    "optional.socket": "[Socket]\nListenStream=/run/optional.sock\n",
                    "optional.mount": "[Mount]\nWhat=tmpfs\nWhere=/optional\nType=tmpfs\n"}
        for name, body in optional.items():
            system.write(directory / "units" / name,
                         body + "[Install]\nWantedBy=sysinit.target\n")
        (self.tree / "run").mkdir()
        (self.tree / "run/mojt-system").symlink_to("../system/current")
        (self.tree / "etc").symlink_to("state/etc")

        def preset():
            subprocess.run(["/usr/bin/systemctl", "--root", str(self.tree), "preset-all"],
                           env={**os.environ, "SYSTEMD_UNIT_PATH": "/run/mojt-system/units"},
                           check=True, capture_output=True, text=True)
            wants = self.tree / "etc/systemd/system/sysinit.target.wants"
            return {name for name in optional if (wants / name).is_symlink()}

        # Reproduce the missing-policy failure before applying the generated policy.
        self.assertEqual(preset(), set(optional))
        system.write(self.tree / policy.lstrip("/"),
                     (directory / "system-preset/99-mojt-vm.preset").read_text())
        self.assertEqual(preset(), set())
        self.assertTrue((directory / "units/sysinit.target.wants/mojt-setup.service").is_symlink())
        self.assertIn("systemd-journald.service", (directory / "units/mojt.target").read_text())
        system.write(self.tree / "etc/systemd/system-preset/00-local.preset", "enable optional.service\n")
        self.assertEqual(preset(), {"optional.service"})

    def test_step2_has_root_managed_bus_dhcp_and_dns(self):
        directory, _ = self.install(2)
        config = (self.tree / "state/etc/NetworkManager/conf.d/90-mojt-vm.conf").read_text()
        for line in ("dhcp=internal", "auth-polkit=root-only", "rc-manager=file"):
            self.assertIn(line, config)
        xml = ET.fromstring((directory / "dbus.conf").read_text())
        self.assertEqual(xml.find("listen").text, "systemd:")
        self.assertEqual(xml.find("user").text, "messagebus")
        service = (directory / "units/dbus.service").read_text()
        self.assertIn("Type=notify", service)
        self.assertIn("Requires=mojt-setup.service dbus.socket", service)
        self.assertIn("Requires=dbus.service", (directory / "units/NetworkManager.service").read_text())

    def run_network_check(self, address_after, route_after, interface=None):
        guest = Path(tempfile.mkdtemp(prefix="network-guest-", dir=self.root))
        tools, trace, count = guest / "bin", guest / "trace", guest / "queries"
        tools.mkdir()
        for name in ("cat", "sed", "head"):
            (tools / name).symlink_to(shutil.which(name))
        trace.write_text("")

        def command(name, body):
            system.write(tools / name, "#!/bin/sh\nset -eu\n" +
                         f"printf '%s\\n' \"{name} $*\" >>'{trace}'\n" + body + "\n", 0o755)

        command("id", "printf '0\\n'")
        command("systemctl", "exit 0")
        command("journalctl", "exit 0")
        command("nmcli", """case "$*" in
    '-t -f DEVICE,TYPE device status') printf 'eth0:ethernet\\n' ;;
    '-f GENERAL,IP4,DHCP4 device show eth0') echo 'diagnostic device state' ;;
    *) echo "Unexpected mutating or unsupported nmcli command: $*" >&2; exit 1 ;;
esac""")
        command("ip", f"""queries=0
if [ -f '{count}' ]; then read -r queries <'{count}'; fi
case "$*" in
    '-4 -o address show dev eth0 scope global')
        queries=$((queries + 1))
        printf '%s\\n' "$queries" >'{count}'
        if [ "$queries" -ge {address_after} ]; then
            echo '2: eth0 inet 10.0.2.15/24 scope global dynamic eth0'
        fi ;;
    '-4 route show default dev eth0')
        if [ "$queries" -ge {route_after} ]; then echo 'default via 10.0.2.2 dev eth0'; fi ;;
    *) echo "Unexpected ip command: $*" >&2; exit 1 ;;
esac""")
        command("sleep", "exit 0")
        command("getent", "echo '203.0.113.1 cache.nixos.org'")
        command("curl", "printf 'StoreDir: /nix/store\\n'")
        system.write(guest / "proc/1/comm", "systemd\n")
        system.write(guest / "run/mojt-system/record.json", "{}")
        system.write(guest / "run/mojt-system/environment", f"export PATH={tools}\n")
        for name in ("etc", "var"):
            (guest / name).mkdir()
        source = (REPO / "tests/check-mojt-system.sh").read_text()
        for path in ("/run/mojt-system", "/proc/1/comm", "/etc", "/var"):
            source = source.replace(path, str(guest / path.lstrip("/")))
        script = guest / "check.sh"
        script.write_text(source)
        result = subprocess.run(["/bin/sh", str(script), "network"], capture_output=True, text=True,
                                env={**os.environ, "PATH": str(tools),
                                     **({"MOJT_TEST_INTERFACE": interface} if interface else {})})
        return result, trace.read_text().splitlines()

    def test_network_check_accepts_an_explicit_interface_without_reconnecting(self):
        result, trace = self.run_network_check(1, 1, interface="eth0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("nmcli -t -f DEVICE,TYPE device status", trace)

    def test_step6_provides_supplicant_kmod_and_local_authenticated_console(self):
        record = self.fixture(6)
        system.load_payload(self.payload)
        before = system.tree_hash(self.tree / "base")
        with mock.patch.object(system.os, "chown"):
            key = system.install(self.tree, self.payload, record, self.busybox, "password", REPO,
                                 console="local", hardware_profile="thinkpad-x1-carbon-3")
        profile = self.tree / "system" / key
        self.assertIn("thinkpad-x1-carbon-3", key)
        self.assertEqual(before, system.tree_hash(self.tree / "base"))
        unit = (profile / "units/mojt-console.service").read_text()
        self.assertIn("TTYPath=/dev/tty1", unit)
        self.assertIn("38400 tty1 linux", unit)
        self.assertIn("/run/mojt-system/login", unit)
        self.assertNotIn("ttyS0", unit)
        supplicant = (profile / "units/wpa_supplicant.service").read_text()
        self.assertIn("BusName=fi.w1.wpa_supplicant1", supplicant)
        self.assertIn("Before=NetworkManager.service", supplicant)
        self.assertIn("wpa_supplicant.service", (profile / "units/mojt.target").read_text())
        for name in ("modprobe", "lsmod", "iw", "wpa_supplicant"):
            self.assertTrue((profile / "bin" / name).is_symlink())

    def test_network_check_observes_ready_or_delayed_ipv4_without_reconnecting(self):
        for address_after, route_after, sleeps in ((1, 1, 0), (3, 4, 3)):
            with self.subTest(address_after=address_after, route_after=route_after):
                result, trace = self.run_network_check(address_after, route_after)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(trace[0], "id -u")
                self.assertIn("PASS: NetworkManager, IPv4, routing, DNS and HTTPS", result.stdout)
                self.assertEqual(trace.count("sleep 1"), sleeps)
                self.assertTrue(trace[-2].startswith("getent hosts "))
                self.assertTrue(trace[-1].startswith("curl --ipv4 --fail "))

    def test_network_check_times_out_without_address_or_route_before_dns_and_https(self):
        for address_after, route_after in ((100, 1), (1, 100), (100, 100)):
            with self.subTest(address_after=address_after, route_after=route_after):
                result, trace = self.run_network_check(address_after, route_after)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("IPv4 address and default route not ready", result.stderr)
                self.assertEqual(trace.count("sleep 1"), 30)
                self.assertEqual(trace[-1], "nmcli -f GENERAL,IP4,DHCP4 device show eth0")
                self.assertFalse(any(line.startswith(("getent ", "curl ")) for line in trace))

    def test_persistence_check_with_minimal_tools_rejects_invalid_markers(self):
        guest = self.root / "persistence-guest"
        tools = self.root / "minimal-bin"
        system.write(tools / "id", "#!/bin/sh\nprintf '0\\n'\n", 0o755)
        (tools / "cat").symlink_to(shutil.which("cat"))
        system.write(guest / "run/mojt-system/record.json", "{}")
        system.write(guest / "run/mojt-system/environment", f"export PATH={tools}\n")
        source = (REPO / "tests/check-mojt-system.sh").read_text()
        for path in ("/run/mojt-system", "/etc/mojt-system-persistence-test",
                     "/var/lib/mojt", "/proc/sys/kernel/random/boot_id"):
            source = source.replace(path, str(guest / path.lstrip("/")))
        script = self.root / "check-in-fixture.sh"
        script.write_text(source)
        boot = "22222222-2222-4222-8222-222222222222\n"
        previous = "11111111-1111-4111-8111-111111111111\n"
        system.write(guest / "proc/sys/kernel/random/boot_id", boot)
        for label, etc, var, expected in (
                ("persisted", previous, previous, "PASS:"),
                ("same boot", boot, boot, "a second boot is required"),
                ("mismatch", previous, boot, "/etc and /var markers differ"),
                ("empty", "", "", "empty persistence marker"),
                ("missing etc", None, previous, "cannot read /etc marker"),
                ("missing var", previous, None, "cannot read /var marker")):
            with self.subTest(label=label):
                for name, value in (("etc/mojt-system-persistence-test", etc),
                                    ("var/lib/mojt/system-persistence-test", var)):
                    path = guest / name
                    if value is None:
                        path.unlink(missing_ok=True)
                    else:
                        system.write(path, value)
                result = subprocess.run(["/bin/sh", str(script), "persistence-check"],
                                        capture_output=True, text=True,
                                        env={**os.environ, "PATH": str(tools)})
                self.assertEqual(result.returncode == 0, label == "persisted", result.stderr)
                self.assertIn(expected, result.stdout + result.stderr)

    def test_conflicting_dns_link_is_preserved_and_stops_build(self):
        record = self.fixture(2)
        resolv = self.tree / "state/etc/resolv.conf"
        resolv.symlink_to("/run/some-existing-resolver")
        with mock.patch.object(system.os, "chown"), self.assertRaisesRegex(ValueError, "resolv.conf"):
            system.install(self.tree, self.payload, record, self.busybox, "development", REPO)
        self.assertEqual(resolv.readlink().as_posix(), "/run/some-existing-resolver")

    def test_existing_system_configuration_is_not_overwritten(self):
        config = self.tree / "state/etc/NetworkManager/conf.d/90-mojt-vm.conf"
        system.write(config, "administrator configuration")
        record = self.fixture(2)
        with mock.patch.object(system.os, "chown"), self.assertRaisesRegex(ValueError, "conflicts"):
            system.install(self.tree, self.payload, record, self.busybox, "development", REPO)
        self.assertEqual(config.read_text(), "administrator configuration")

    def test_step3_keeps_registration_and_system_roots_with_prototype_tools(self):
        directory, record = self.install(3)
        setup = (directory / "setup").read_text()
        self.assertIn("nix-store --load-db", setup)
        self.assertIn(".mojt-registration-loaded", setup)
        for obj in record["objects"]:
            self.assertIn(obj["path"], setup)
        config = (self.tree / "state/etc/nix/nix.conf").read_text()
        self.assertIn("require-sigs = true", config)
        self.assertIn("max-jobs = 0", config)
        wrapper = (directory / "bin/mpm").read_text()
        self.assertIn("--root /var/lib/mojt/ports", wrapper)
        self.assertIn('--source-manifest /run/mojt-system/ports.toml "$@"', wrapper)
        self.assertNotIn('ports "$@"', wrapper)
        self.assertIn(" -I ", wrapper)
        self.assertIn("/var/lib/mojt/ports/current/bin:/run/mojt-system/bin",
                      (directory / "environment").read_text())
        self.assertIn("/run/mojt-system/environment",
                      (self.tree / "state/etc/profile.d/mojt-system.sh").read_text())
        self.assertEqual((directory / "tools/mpm-nix-prototype").read_bytes(),
                         (REPO / "tools/mpm-nix-prototype").read_bytes())
        self.assertEqual((directory / "tests/run-mpm-nix-python.py").read_bytes(),
                         (REPO / "tests/run-mpm-nix-python.py").read_bytes())
        self.assertEqual((directory / "tests/run-mpm-nix-ports.py").read_bytes(),
                         (REPO / "tests/run-mpm-nix-ports.py").read_bytes())
        self.assertIn(record["source"]["revision"], (directory / "ports.toml").read_text())

    def test_early_boot_mounts_store_before_systemd_and_moves_backing_disk_last(self):
        script = system.init_script(vm.INIT)
        self.assertIn("/run/mojt-system/start", script)
        self.assertNotIn("prototype-init", script)
        last_read = script.rindex("/sysroot/state/")
        move = script.index("mount --move /sysroot")
        self.assertLess(last_read, move)
        self.assertLess(script.index("mount --bind /sysroot/nix"), move)
        self.assertIn("remount,bind,ro", script)
        self.assertIn("/run/initramfs/shutdown", script)
        subprocess.run(["sh", "-n"], input=script, text=True, check=True, capture_output=True)
        subprocess.run(["sh", "-n"], input=system.SHUTDOWN, text=True, check=True, capture_output=True)

    def test_step3_preserves_administrator_login_profile(self):
        profile = self.tree / "state/etc/profile"
        profile.write_text("# administrator login profile\nexport EDITOR=vi\n")
        self.install(3)
        self.assertEqual(profile.read_text(), "# administrator login profile\nexport EDITOR=vi\n")
        self.assertTrue((self.tree / "state/etc/profile.d/mojt-system.sh").is_file())

    def test_step4_exports_admin_commands_without_base_changes_or_new_services(self):
        before = system.tree_hash(self.tree / "base")
        directory, record = self.install(4)
        self.assertEqual(system.tree_hash(self.tree / "base"), before)
        commands = (directory / "admin-commands").read_text().splitlines()
        self.assertEqual(set(commands), {n for group in system.ADMIN_COMMANDS.values() for n in group})
        for role, names in system.ADMIN_COMMANDS.items():
            for name in names:
                self.assertEqual(os.readlink(directory / "bin" / name),
                                 record["packages"][role]["output"] + "/bin/" + name)
        self.assertTrue((directory / "bin/mpm").is_file())
        self.assertIn("nix-store --load-db", (directory / "setup").read_text())
        self.assertIn("/var/lib/mojt/ports/current/bin:", (directory / "environment").read_text())
        wants = (directory / "units/mojt.target").read_text()
        for role in system.ADMIN_COMMANDS:
            self.assertNotIn(role + ".service", wants)
        subprocess.run(["sh", "-n", str(directory / "environment")], check=True)

    def test_step4_supports_mount_commands_in_a_separate_retained_output(self):
        record = self.fixture(4)
        package = record["packages"]["util-linux"]["output"]
        split = "/nix/store/" + "d" * 32 + "-util-linux-mount"
        for name in ("mount", "umount"):
            system.write(self.payload / split.lstrip("/") / "bin" / name, "#!/bin/sh\nexit 0\n", 0o755)
            path = self.payload / package.lstrip("/") / "bin" / name
            path.unlink()
            path.symlink_to(split + "/bin/" + name)
        for item in record["objects"]:
            if item["path"] == package:
                item["tree_sha256"] = system.tree_hash(self.payload / package.lstrip("/"))
        record["objects"].append(dict(path=split, tree_sha256=system.tree_hash(
            self.payload / split.lstrip("/")), nar_hash="synthetic"))
        system.write(self.payload / "system.json", json.dumps(record))
        self.assertEqual(system.load_payload(self.payload), record)
        with mock.patch.object(system.os, "chown"):
            key = system.install(self.tree, self.payload, record, self.busybox, "development", REPO)
        link = self.tree / "system" / key / "bin/mount"
        self.assertEqual(system.virtual_file(self.tree, os.readlink(link)),
                         self.tree / split.lstrip("/") / "bin/mount")

    def test_step4_rejects_missing_admin_executable_even_with_valid_transfer_hash(self):
        record = self.fixture(4)
        output = record["packages"]["procps"]["output"]
        (self.payload / output.lstrip("/") / "bin/ps").unlink()
        for item in record["objects"]:
            if item["path"] == output:
                item["tree_sha256"] = system.tree_hash(self.payload / output.lstrip("/"))
        system.write(self.payload / "system.json", json.dumps(record))
        with self.assertRaisesRegex(ValueError, "missing procps executable"):
            system.load_payload(self.payload)

    def test_step5_keeps_bash_in_system_and_can_select_it_for_copied_root_account(self):
        before = system.tree_hash(self.tree / "base")
        directory, record = self.install(5)
        target = record["packages"]["shell"]["output"] + "/bin/bash"
        self.assertEqual(os.readlink(directory / "bin/bash"), target)
        with mock.patch.object(vm.os, "chown"):
            vm.prepare_vm_root_shell(self.tree, "0.1.3", "/run/mojt-system/bin/bash", system_shell=target)
        self.assertIn("root:x:0:0:root:/root:/run/mojt-system/bin/bash\n",
                      (self.tree / "state/etc/passwd").read_text())
        self.assertEqual(system.tree_hash(self.tree / "base"), before)
        history = self.tree / "state/var/lib/mojt/console"
        self.assertEqual(history.stat().st_mode & 0o777, 0o700)
        self.assertEqual((history / "root.history").stat().st_mode & 0o777, 0o600)
        self.assertEqual((directory / "bashrc").read_text(), system.BASH_RC)
        self.assertIn('. /etc/profile.d/mojt-bash.sh',
                      (self.tree / "state/etc/profile").read_text())
        subprocess.run(["bash", "-n", str(directory / "bashrc")], check=True)

    def test_system_shell_is_not_adopted_without_explicit_account_selection(self):
        (self.tree / "base/0.1.3/bin").symlink_to("usr/bin")
        directory, record = self.install(5)
        before = (self.tree / "state/etc/passwd").read_bytes()
        target = record["packages"]["shell"]["output"] + "/bin/bash"
        self.assertEqual(vm.prepare_vm_root_shell(self.tree, "0.1.3", system_shell=target), "/bin/sh")
        self.assertEqual((self.tree / "state/etc/passwd").read_bytes(), before)

    def test_system_bash_selection_rejects_missing_metadata_and_changed_export(self):
        directory, record = self.install(5)
        before = (self.tree / "state/etc/passwd").read_bytes()
        with self.assertRaisesRegex(ValueError, "requires a step 5 payload"):
            vm.prepare_vm_root_shell(self.tree, "0.1.3", "/run/mojt-system/bin/bash")
        (directory / "bin/bash").unlink()
        (directory / "bin/bash").symlink_to("/usr/bin/bash")
        with self.assertRaisesRegex(ValueError, "differs from selected payload"):
            vm.prepare_vm_root_shell(self.tree, "0.1.3", "/run/mojt-system/bin/bash",
                                     system_shell=record["packages"]["shell"]["output"] + "/bin/bash")
        self.assertEqual((self.tree / "state/etc/passwd").read_bytes(), before)

    def test_step5_preserves_local_bash_configuration_and_existing_history(self):
        local_rc = self.tree / "state/etc/bashrc"
        local_rc.write_text("# administrator configuration\n")
        history = self.tree / "state/var/lib/mojt/console/root.history"
        system.write(history, "retained history\n", 0o600)
        self.install(5)
        self.assertEqual(local_rc.read_text(), "# administrator configuration\n")
        self.assertEqual(history.read_text(), "retained history\n")

    def test_step5_history_directory_cannot_follow_a_link_outside_staging(self):
        outside = self.root / "outside-history"
        outside.mkdir()
        (outside / "root.history").write_text("keep\n")
        link = self.tree / "state/var/lib/mojt/console"
        link.parent.mkdir(parents=True)
        link.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "unsafe console history directory"):
            self.install(5)
        self.assertEqual((outside / "root.history").read_text(), "keep\n")

    def run_admin_check(self, *, fail_mount_query=False):
        guest = self.root / "admin-guest"
        tools = guest / "run/mojt-system/bin"
        trace, mounted = guest / "trace", guest / "mounted"

        def command(name, body):
            system.write(tools / name, "#!/bin/sh\nset -eu\n"
                         f"printf '%s\\n' \"{name} $*\" >>'{trace}'\n" + body + "\n", 0o755)

        for name in ("top", "free", "pgrep", "uptime", "lsblk", "blkid", "less", "dmesg", "vi"):
            command(name, "echo 'synthetic admin output'")
        command("id", "echo 0")
        command("systemctl", "exit 0")
        command("journalctl", "echo 'synthetic journal'")
        command("ps", "case \"$*\" in '-p 1 -o comm=') echo systemd ;; *) echo '1 0 systemd' ;; esac")
        command("mount", f"touch '{mounted}'")
        command("umount", f"rm '{mounted}'")
        command("findmnt", "case \"$*\" in *--mountpoint*) " +
                ("exit 1" if fail_mount_query else f"test -f '{mounted}'; echo tmpfs") +
                " ;; *) echo '/ ext4' ;; esac")
        command("ex", "cat >/dev/null\nprintf '%s\\n' 'Mojt System vi probe' >\"$2\"")
        system.write(guest / "proc/1/comm", "systemd\n")
        system.write(guest / "run/mojt-system/record.json", "{}")
        system.write(guest / "run/mojt-system/environment", f"export PATH={tools}:/usr/bin:/bin\n")
        system.write(guest / "run/mojt-system/admin-commands", "\n".join(
            name for group in system.ADMIN_COMMANDS.values() for name in group) + "\n")
        for name in ("etc", "var", "tmp"):
            (guest / name).mkdir()
        source = (REPO / "tests/check-mojt-system.sh").read_text()
        for path in ("/run/mojt-system", "/proc/1/comm", "/etc", "/var"):
            source = source.replace(path, str(guest / path.lstrip("/")))
        source = source.replace("/tmp/mojt-admin.", str(guest / "tmp/mojt-admin."))
        script = guest / "check.sh"
        script.write_text(source)
        result = subprocess.run(["/bin/sh", str(script), "admin"], capture_output=True, text=True,
                                env={**os.environ, "PATH": str(tools) + ":/usr/bin:/bin"})
        return result, trace.read_text().splitlines(), mounted.exists(), list((guest / "tmp").iterdir())

    def test_admin_check_exercises_tools_and_cleans_temporary_mount_and_editor_file(self):
        result, trace, mounted, temporary = self.run_admin_check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS: System process, memory, disk, mount, pager and vi tools", result.stdout)
        self.assertIn("top -b -n 1 -w 80", trace)
        self.assertIn("pgrep -x systemd", trace)
        self.assertTrue(any(line.startswith("ex -s ") for line in trace))
        self.assertEqual(sum(line.startswith("mount ") for line in trace), 1)
        self.assertEqual(sum(line.startswith("umount ") for line in trace), 1)
        self.assertFalse(mounted)
        self.assertEqual(temporary, [])

    def test_admin_check_failure_after_mount_unmounts_and_removes_probe(self):
        result, trace, mounted, temporary = self.run_admin_check(fail_mount_query=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("temporary tmpfs mount not visible", result.stderr)
        self.assertNotIn("PASS: System process", result.stdout)
        self.assertEqual(sum(line.startswith("umount ") for line in trace), 1)
        self.assertFalse(mounted)
        self.assertEqual(temporary, [])

    def test_init_hook_fails_if_legacy_handover_changes(self):
        with self.assertRaisesRegex(ValueError, "handover changed"):
            system.init_script(vm.INIT.replace("exec switch_root", "changed switch_root"))

    def test_system_initramfs_includes_the_added_file_utility_applets(self):
        initroot = self.root / "initroot"
        with mock.patch.object(vm.os, "mknod"), \
                mock.patch.object(vm.subprocess, "run", return_value=types.SimpleNamespace(stdout=b"archive")):
            vm.make_initramfs(initroot, self.busybox, [],
                             system.init_script(vm.INIT), system.SHUTDOWN)
        for name in ("cp", "ln", "sh", "mount"):
            self.assertEqual((initroot / "bin" / name).readlink().as_posix(), "busybox")
        self.assertEqual((initroot / "shutdown").read_text(), system.SHUTDOWN)
        self.assertTrue((initroot / "shutdown").stat().st_mode & 0o111)

    def test_qemu_network_is_explicit_and_has_no_forwarded_ports(self):
        self.assertIn("-nic none", vm.run_script())
        network = vm.run_script(True)
        self.assertIn("-nic user,model=virtio-net-pci", network)
        self.assertNotIn("hostfwd", network)
        subprocess.run(["bash", "-n"], input=network, text=True, check=True, capture_output=True)

    def prepare_with_fake_nix(self, *, dry_run=False, fail_import=False, step=1):
        record = self.fixture(step)
        with mock.patch.dict("sys.modules", {"mojt_system": system}):
            prepare = module("mojt_system_export_test", "mojt-system-prepare.py")
        calls = []

        def run(*args):
            calls.append(args)
            if args[0] == "nix-instantiate":
                return json.dumps([dict(name=name, commands=[], **item)
                                   for name, item in record["packages"].items()])
            if args[1:3] == ("--query", "--requisites"):
                return "\n".join(item["path"] for item in record["objects"])
            if args[1:3] == ("--query", "--hash"):
                return "sha256:synthetic"
            return ""

        def retain(root, value):
            calls.append(("retain", value))
            if fail_import and value == record["packages"]["systemd"]["output"]:
                raise ValueError("binary substitute unavailable")

        fake = types.SimpleNamespace(
            EVALUATE="synthetic evaluation", run=run, retain=retain,
            catalog_from_manifest=lambda _: dict(source=record["source"]))

        def command(args, **kwargs):
            if args[0] == "cp":
                source, dest = args[-2:]
                source = self.payload / source.lstrip("/")
                shutil.copytree(source, dest, symlinks=True)
            elif args[1] == "--dump-db":
                kwargs["stdout"].write(b"synthetic exported registration")
            else:
                self.fail(str(args))
            return types.SimpleNamespace(returncode=0)

        args = types.SimpleNamespace(output=self.root / "export", step=step, yes=True,
                                     dry_run=dry_run, source_manifest=Path("synthetic.toml"))
        with mock.patch.object(prepare.os, "geteuid", return_value=1000), \
                mock.patch.object(prepare.shutil, "which", return_value="/synthetic/tool"), \
                mock.patch.object(prepare, "nix_adapter", return_value=fake), \
                mock.patch.object(prepare.subprocess, "run", side_effect=command), \
                contextlib.redirect_stdout(io.StringIO()):
            if fail_import:
                with self.assertRaisesRegex(ValueError, "substitute unavailable"):
                    prepare.prepare(args)
            else:
                prepare.prepare(args)
        return args.output, calls

    def test_exporter_copies_verified_closure_and_subset_registration(self):
        output, calls = self.prepare_with_fake_nix()
        record = system.load_payload(output)
        self.assertEqual(record["step"], 1)
        self.assertTrue(any(c[1:2] == ("--verify-path",) for c in calls))
        self.assertTrue(all(not any(str(a).endswith(".drv") for a in c) for c in calls))
        self.assertEqual((output / "registration").read_text(), "synthetic exported registration")

    def test_step4_export_keeps_nixpkgs_source_and_all_admin_roles(self):
        output, calls = self.prepare_with_fake_nix(step=4)
        record = system.load_payload(output)
        self.assertEqual(record["step"], 4)
        self.assertTrue(set(system.ADMIN_COMMANDS) <= set(record["packages"]))
        self.assertIn(record["source"]["store"], {item["path"] for item in record["objects"]})
        query = next(c for c in calls if c[:3] == ("nix-store", "--query", "--requisites"))
        self.assertIn(record["source"]["store"], query[3:])

    def test_export_preview_does_not_write_or_retain(self):
        output, calls = self.prepare_with_fake_nix(dry_run=True)
        self.assertFalse(output.exists())
        self.assertFalse(any(c[0] == "retain" for c in calls))

    def test_missing_binary_does_not_publish_partial_payload(self):
        output, _ = self.prepare_with_fake_nix(fail_import=True)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
