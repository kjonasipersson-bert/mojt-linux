#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Real offline GPT/ext4 serial-console copies; no host mounts or credentials."""

import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("mojt_serial_test", REPO / "tools/mojt-vm-serial.py")
serial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(serial)
boot = serial.boot
UUID = "38ae152c-b81a-44da-b23a-3341398debe6"
TOOLS = serial.COMMANDS + boot.COMMANDS + ("mkfs.ext4",)


def pending_inode_journal(image,work):
    """Commit old inode-table blocks without checkpointing them to home blocks."""
    fs=serial.Ext4(image,work)
    block=int(re.search(r'block\s+(\d+),',fs.run('imap /state/etc/systemd')).group(1))
    with image.open('rb') as stream:
        stream.seek(1024+24);size=1024 << int.from_bytes(stream.read(4),'little')
        commands=['journal_open -c']
        for index in (block,block+1):
            stream.seek(index*size);name='old-inodes-'+str(index)
            (work/name).write_bytes(stream.read(size))
            commands.append('journal_write -b '+str(index)+' '+name)
    commands.append('journal_close');script=work/'journal-commands'
    script.write_text('\n'.join(commands)+'\n')
    subprocess.run(['debugfs','-w','-f',str(script),str(image)],cwd=work,capture_output=True,check=True)


class BuildRecordTests(unittest.TestCase):
    def record(self):
        import test_mpm_boot_v2 as fixtures
        source=fixtures.fixture();d=copy.deepcopy(source['description'])
        d['boot'].update(console='local',profile=fixtures.model.HARDWARE_PROFILE,root_uuid=UUID)
        value=fixtures.bound(fixtures.record(fixtures.model.INPUTS,d))
        return dict(boot_layout='native-v2',boot_record=value,additional_boot_records=[],disk_layout=dict(root_uuid=UUID))

    def test_native_v2_is_validated_without_rewriting_the_bound_console_or_id(self):
        record=self.record();before=copy.deepcopy(record)
        self.assertTrue(serial.local_console(record));self.assertEqual(record,before)
        record['boot_record']['id']='sha256:'+'0'*64
        with self.assertRaises(ValueError):serial.local_console(record)

    def test_native_root_mismatch_additional_records_and_unknown_layout_are_refused(self):
        record=self.record();record['disk_layout']['root_uuid']='12345678-1234-1234-1234-123456789abc'
        with self.assertRaisesRegex(ValueError,'UUID differs'):serial.local_console(record)
        record=self.record();record['additional_boot_records']=[{}]
        with self.assertRaisesRegex(ValueError,'additional build records'):serial.local_console(record)
        with self.assertRaisesRegex(ValueError,'unsupported build boot layout'):serial.local_console(dict(boot_layout='future'))


@unittest.skipUnless(all(shutil.which(c) for c in ('mkfs.ext4','debugfs','e2fsck')), 'requires ext4 tools')
class JournalRecoveryTests(unittest.TestCase):
    def test_pending_transactions_must_be_replayed_before_debugfs_console_writes(self):
        with tempfile.TemporaryDirectory(prefix='mojt-journal-test-') as temporary:
            work=Path(temporary);etc=work/'tree/state/etc';(etc/'systemd').mkdir(parents=True)
            (etc/'shadow').write_text('root:!:0:0:99999:7:::\n');(etc/'shadow').chmod(0o600)
            (etc/'marker').write_text('retained state\n')
            source=work/'source.ext4'
            with source.open('xb') as stream:stream.truncate(64*boot.MIB)
            subprocess.run(['mkfs.ext4','-F','-q','-b','4096','-d',str(work/'tree'),str(source)],check=True)
            # Commit real, checksummed journal transactions containing the old
            # inode-table blocks. Home metadata remains consistent until replay.
            # A later raw mkdir allocates inodes in these same blocks.
            pending_inode_journal(source,work)
            before=boot.digest(source)
            def check(path):
                return subprocess.run(['e2fsck','-f','-n',str(path)],capture_output=True,text=True)
            self.assertEqual(check(source).returncode,0)
            with self.assertRaisesRegex(ValueError,'pending journal/orphan recovery'):serial.clean_filesystem(source)
            # Reproduce the old implementation: both read-only checks pass,
            # then journal replay destroys freshly allocated console inodes.
            old=work/'old.ext4';shutil.copyfile(source,old);serial.configure(old,work)
            self.assertEqual(check(old).returncode,0)
            replay=subprocess.run(['e2fsck','-p','-E','journal_only',str(old)],capture_output=True,text=True)
            self.assertIn(replay.returncode,(0,1),replay.stdout+replay.stderr)
            broken=check(old);self.assertEqual(broken.returncode,4)
            self.assertIn("Entry 'system'",broken.stdout)
            self.assertIn('deleted/unused inode',broken.stdout)
            # The corrected order replays only in a disposable copy, before
            # console writes; no committed source transaction remains pending.
            fixed=work/'fixed.ext4';shutil.copyfile(source,fixed)
            serial.check_filesystem(fixed,recover=True);serial.configure(fixed,work);serial.check_filesystem(fixed)
            self.assertIn(b'115200 ttyS0 vt100',serial.Ext4(fixed,work).read(serial.SERVICE))
            self.assertEqual(serial.Ext4(fixed,work).read('/state/etc/marker'),b'retained state\n')
            self.assertEqual(boot.digest(source),before)


@unittest.skipUnless(all(shutil.which(c) for c in TOOLS), "offline image tools unavailable")
class SerialCopyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="mojt-serial-test-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def source(self, *, conflict=False, linked_securetty=False, pending_journal=False):
        source, tree, work = (self.root / n for n in ("source VM", "tree", "work"))
        for p in (source, tree, work):
            p.mkdir()
        etc = tree / "state/etc"
        etc.mkdir(parents=True)
        (tree / "state/var").mkdir()
        (etc / "shadow").write_text("root:$6$synthetic-test-fixture:0:0:99999:7:::\n")
        (etc / "shadow").chmod(0o600)
        (etc / "generation-marker").write_text("retained etc\n")
        (tree / "state/var/generation-marker").write_text("retained var\n")
        if pending_journal:(etc/'systemd').mkdir()
        if linked_securetty:
            (etc / "securetty").symlink_to("/some/machine/policy")
        else:
            (etc / "securetty").write_text("# Machine policy\ntty1\n")
        if conflict:
            unit = etc / "systemd/system/mojt-serial-console.service"
            unit.parent.mkdir(parents=True)
            unit.write_text("administrator service\n")
        kernel = self.root / "vmlinuz-test"
        kernel.write_bytes(b"synthetic kernel")
        records = []
        for selected, base in (("A", "base-A"), ("B", "base-A"), ("B", "base-B")):
            records.append(boot.stage(tree, kernel, b"synthetic initramfs", [], release="test",
                                      base=base, system=selected, root_uuid=UUID, console="local"))
        parts = boot.build_disk(source / "disk.img", tree, work, 512, UUID, "A", "base-A", console="local")
        if pending_journal:
            root=work/'mojt.ext4';pending_inode_journal(root,work)
            boot.copy_partition(root,source/'disk.img',parts['root_offset'],parts['root_bytes'])
        record = dict(format=1, boot_mode="uefi", login_mode="password", disk_layout=parts,
                      system_step=6, hardware={"profile": "thinkpad-x1-carbon-3"},
                      boot_record=records[0], additional_boot_records=records[1:])
        (source / "build.json").write_text(json.dumps(record))
        (source / "OVMF_VARS.fd").write_bytes(b"retained firmware fixture")
        return source, record

    @contextlib.contextmanager
    def root_partition(self, directory):
        record = json.loads((directory / "build.json").read_text())
        with tempfile.TemporaryDirectory(prefix="inspect-", dir=self.root) as temp:
            work = Path(temp)
            image = work / "root.ext4"
            parts = record["disk_layout"]
            serial.extract_partition(directory / "disk.img", image, parts["root_offset"], parts["root_bytes"])
            yield serial.Ext4(image, work)

    def prepare(self, source, output):
        with contextlib.redirect_stdout(io.StringIO()):
            serial.prepare(source, output)

    def test_real_copy_preserves_source_credentials_state_boot_pairs_and_firmware(self):
        source, record = self.source()
        before = boot.digest(source / "disk.img")
        output = self.root / "serial VM"
        self.prepare(source, output)
        self.assertEqual(boot.digest(source / "disk.img"), before)
        self.assertEqual((output / "disk.img").stat().st_size, (source / "disk.img").stat().st_size)
        self.assertEqual(output.stat().st_mode & 0o777, 0o700)
        self.assertEqual((output / "disk.img").stat().st_mode & 0o777, 0o600)
        self.assertEqual((output / "OVMF_VARS.fd").read_bytes(), b"retained firmware fixture")
        with self.root_partition(output) as fs:
            self.assertIn(b"IgnoreSIGPIPE=no", fs.read(serial.SERVICE))
            self.assertEqual(fs.read("/state/etc/securetty"), b"# Machine policy\ntty1\nttyS0\n")
            self.assertEqual(fs.read("/state/etc/shadow"), b"root:$6$synthetic-test-fixture:0:0:99999:7:::\n")
            self.assertEqual(fs.inode("/state/etc/shadow")["mode"], 0o600)
            self.assertEqual(fs.read("/state/etc/generation-marker"), b"retained etc\n")
            self.assertEqual(fs.read("/state/var/generation-marker"), b"retained var\n")
            self.assertEqual(fs.read(serial.SERVICE), serial.UNIT.encode())
            self.assertIn('Fast link dest: "../mojt-serial-console.service"', fs.inode(serial.LINK)["text"])
            for r in [record["boot_record"], *record["additional_boot_records"]]:
                prefix = f"/boot/mojt/{r['system_generation']}/{r['base']}"
                self.assertEqual(json.loads(fs.read(prefix + "/boot.json")), r)
                self.assertEqual(fs.read(prefix + "/vmlinuz"), b"synthetic kernel")
                self.assertEqual(fs.read(prefix + "/initramfs.cpio.gz"), b"synthetic initramfs")
        script = (output / "run-qemu.sh").read_text()
        self.assertIn('${QEMU_DISPLAY:-none}', script)
        self.assertIn('-serial mon:stdio', script)
        self.assertIn('user,model=e1000e', script)
        subprocess.run(["bash", "-n", str(output / "run-qemu.sh")], check=True)

    def test_native_v2_copy_preserves_boot_metadata_sidecars_and_original_disk(self):
        # Exercise the format join and real ext4 modification. Opaque fixture
        # boot bytes are retained; this is not native guest boot acceptance.
        source,record=self.source(pending_journal=True);native=BuildRecordTests().record();native.pop('disk_layout')
        record.update(native,system_step=10)
        for name in serial.SIDECARS:
            data=json.dumps(record['boot_record']).encode() if name in ('deployment.json','selected-deployment.json') else b'retained '+name.encode()
            (source/name).write_bytes(data)
        (source/'build.json').write_text(json.dumps(record))
        output=self.root/'native serial';selected=source/'selected-deployment.json';original=selected.read_bytes()
        selected.write_text('{}')
        with self.assertRaisesRegex(ValueError,'deployment sidecar differs'):self.prepare(source,output)
        self.assertFalse(output.exists());selected.write_bytes(original)
        before={p.name:boot.digest(p) for p in source.iterdir()}
        self.prepare(source,output)
        self.assertEqual(before,{p.name:boot.digest(p) for p in source.iterdir()})
        self.assertEqual(json.loads((output/'build.json').read_text())['boot_record'],record['boot_record'])
        for name in serial.SIDECARS:self.assertEqual((output/name).read_bytes(),(source/name).read_bytes())
        with self.root_partition(output) as fs:
            serial.clean_filesystem(fs.image)
            unit=fs.read(serial.SERVICE)
            self.assertIn(b'Requires=mojt-privileged.service systemd-logind.service',unit)
            self.assertIn(b'115200 ttyS0 vt100',unit)
            self.assertEqual(fs.read('/state/etc/generation-marker'),b'retained etc\n')
            self.assertEqual(fs.read('/state/var/generation-marker'),b'retained var\n')

    def test_linked_securetty_and_conflicting_unit_do_not_publish_or_mutate_source(self):
        for option in ("conflict", "linked_securetty"):
            with self.subTest(option=option), tempfile.TemporaryDirectory(dir=self.root) as temp:
                original = self.root
                self.root = Path(temp)
                try:
                    source, unused = self.source(**{option: True})
                    before = boot.digest(source / "disk.img")
                    output = self.root / "output"
                    with self.assertRaisesRegex(ValueError, "unsafe guest file|conflicting guest"):
                        self.prepare(source, output)
                    self.assertFalse(output.exists())
                    self.assertEqual(boot.digest(source / "disk.img"), before)
                finally:
                    self.root = original

    def test_late_partition_failure_leaves_source_and_output_untouched(self):
        source, unused = self.source()
        before = boot.digest(source / "disk.img")
        output = self.root / "output"
        with mock.patch.object(boot, "copy_partition", side_effect=OSError("injected write failure")):
            with self.assertRaisesRegex(OSError, "injected"):
                self.prepare(source, output)
        self.assertFalse(output.exists())
        self.assertEqual(list(self.root.glob(".mojt-serial-*")), [])
        self.assertEqual(boot.digest(source / "disk.img"), before)

    def test_reconstructed_partition_mismatch_prevents_publication(self):
        source,unused=self.source();before=boot.digest(source/'disk.img');output=self.root/'output'
        copy_partition=boot.copy_partition
        def corrupt(image,disk,offset,length):
            copy_partition(image,disk,offset,length)
            with disk.open('r+b') as stream:
                stream.seek(offset+length-1);byte=stream.read(1)
                stream.seek(-1,1);stream.write(bytes([byte[0]^1]))
        with mock.patch.object(boot,'copy_partition',side_effect=corrupt):
            with self.assertRaisesRegex(ValueError,'reconstructed root partition differs'):self.prepare(source,output)
        self.assertFalse(output.exists());self.assertEqual(boot.digest(source/'disk.img'),before)

    def test_existing_output_and_symlink_are_refused(self):
        source, unused = self.source()
        output = self.root / "keep"
        output.mkdir()
        (output / "marker").write_text("keep")
        with self.assertRaisesRegex(ValueError, "existing output"):
            self.prepare(source, output)
        self.assertEqual((output / "marker").read_text(), "keep")
        link = self.root / "link"
        link.symlink_to(self.root / "absent")
        with self.assertRaisesRegex(ValueError, "symlink output"):
            self.prepare(source, link)
        self.assertFalse((self.root / "absent").exists())

    def test_unauthenticated_source_and_wrong_partition_extent_are_refused(self):
        source, record = self.source()
        output = self.root / "output"
        changed = dict(record, login_mode="development")
        (source / "build.json").write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError, "password-login"):
            self.prepare(source, output)
        changed = json.loads(json.dumps(record))
        changed["boot_record"]["console"] = "serial"
        (source / "build.json").write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError, "local-console"):
            self.prepare(source, output)
        record["disk_layout"]["root_offset"] += 4096
        (source / "build.json").write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, "GPT differs"):
            self.prepare(source, output)
        self.assertFalse(output.exists())

    @unittest.skipUnless(shutil.which("qemu-system-x86_64"), "QEMU lock probe unavailable")
    def test_qemu_running_source_is_refused_by_image_locking(self):
        source, unused = self.source()
        output = self.root / "output"
        process = subprocess.Popen([
            "qemu-system-x86_64", "-machine", "q35,accel=tcg", "-m", "64", "-S",
            "-nodefaults", "-display", "none", "-qmp", "stdio",
            "-drive", f"file={source / 'disk.img'},if=virtio,format=raw"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            process.stdin.write(b'{"execute":"qmp_capabilities"}\n{"execute":"query-status"}\n')
            process.stdin.flush()
            buffer = bytearray()
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                deadline = time.monotonic() + 10
                while b'"status":' not in buffer and time.monotonic() < deadline:
                    for key, unused in selector.select(timeout=1):
                        data = os.read(key.fileobj.fileno(), 65536)
                        if not data:
                            break
                        buffer.extend(data)
                self.assertIn(b'"status":', buffer, "QEMU did not acquire its disk")
            with self.assertRaises(subprocess.CalledProcessError):
                self.prepare(source, output)
            self.assertFalse(output.exists())
        finally:
            process.kill()
            process.wait()
            process.stdin.close()
            process.stdout.close()
            process.stderr.close()


if __name__ == "__main__":
    unittest.main()
