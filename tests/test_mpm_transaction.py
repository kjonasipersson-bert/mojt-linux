# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Real locks and rename/failure boundaries, without providers or machine writes."""
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import mpm_transaction as tx


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def contender(self, path):
        # This deliberately uses the old writers' flock protocol, not our helper.
        return subprocess.run([sys.executable, "-c", """
import fcntl,os,sys
fd=os.open(sys.argv[1],os.O_RDWR)
try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError: sys.exit(75)
""", str(path)], capture_output=True).returncode

    def test_lock_serializes_legacy_writers_and_keeps_inode_after_failure(self):
        path = self.root / ".lock"
        with self.assertRaisesRegex(RuntimeError, "abort"):
            with tx.file_lock(path):
                inode = path.stat().st_ino
                self.assertEqual(self.contender(path), 75)
                raise RuntimeError("abort")
        self.assertEqual(path.stat().st_ino, inode)
        self.assertEqual(self.contender(path), 0)

    def test_refuses_symlink_hardlink_and_writable_lock_without_truncation(self):
        original = self.root / "original"
        original.write_bytes(b"do not truncate")
        link = self.root / ".lock"
        link.symlink_to(original)
        with self.assertRaises(ValueError):
            with tx.file_lock(link): pass
        link.unlink()
        os.link(original, link)
        with self.assertRaises(ValueError):
            with tx.file_lock(link): pass
        link.unlink()
        original.chmod(0o666)
        with self.assertRaises(ValueError):
            with tx.file_lock(original): pass
        self.assertEqual(original.read_bytes(), b"do not truncate")

    def test_shared_read_does_not_create_missing_lock(self):
        path = self.root / "missing"
        with self.assertRaises(FileNotFoundError):
            with tx.file_lock(path, shared=True, create=False): pass
        self.assertFalse(path.exists())

    def test_replaced_lock_inode_is_rejected_after_wait(self):
        path = self.root / ".lock"
        flock = fcntl.flock
        def replace(fd, mode):
            flock(fd, mode)
            path.unlink()
            path.touch(mode=0o600)
        with mock.patch.object(tx.fcntl, "flock", side_effect=replace):
            with self.assertRaisesRegex(ValueError, "changed while waiting"):
                with tx.file_lock(path): pass

    def test_multi_resource_order_is_deterministic_and_duplicate_free(self):
        a, b = self.root / "a", self.root / "b"
        order = []
        original = tx.file_lock
        def acquire(path, **kwargs):
            order.append(path)
            return original(path, **kwargs)
        with mock.patch.object(tx, "file_lock", side_effect=acquire):
            with tx.resource_locks([b, a, b]):
                self.assertEqual(self.contender(a), 75)
                self.assertEqual(self.contender(b), 75)
        self.assertEqual(order, [a, b])

    def selection(self):
        old, new, target = (self.root / n for n in ("old", "new", "current"))
        old.mkdir()
        new.mkdir()
        target.symlink_to("old")
        source = self.root / ".current-new"
        source.symlink_to("new")
        return source, target

    def test_failure_before_rename_preserves_old_selection(self):
        source, target = self.selection()
        with mock.patch.object(tx.os, "replace", side_effect=OSError("rename failed")):
            with self.assertRaisesRegex(OSError, "rename failed") as error:
                tx.publish(source, target)
        self.assertNotIsInstance(error.exception, tx.PublicationUncertain)
        self.assertEqual(os.readlink(target), "old")
        self.assertTrue(source.is_symlink())

    def test_failure_after_rename_reports_commit_and_retains_both_generations(self):
        for failure in (OSError("flush failed"), KeyboardInterrupt()):
            with self.subTest(failure=type(failure).__name__):
                folder = self.root / type(failure).__name__
                folder.mkdir()
                with mock.patch.object(self, "root", folder):
                    source, target = self.selection()
                    with self.assertRaises(tx.PublicationUncertain) as error:
                        tx.publish(source, target, sync=mock.Mock(side_effect=failure))
                    self.assertTrue(error.exception.committed)
                    self.assertEqual(os.readlink(target), "new")
                    self.assertTrue((folder / "old").is_dir())
                    self.assertTrue((folder / "new").is_dir())

    def test_interruption_immediately_after_rename_is_not_reported_as_uncommitted(self):
        source, target = self.selection()
        original = os.replace
        def interrupt(a, b):
            original(a, b)
            raise KeyboardInterrupt()
        with mock.patch.object(tx.os, "replace", side_effect=interrupt):
            with self.assertRaises(tx.PublicationUncertain):
                tx.publish(source, target)
        self.assertEqual(os.readlink(target), "new")


if __name__ == "__main__":
    unittest.main()
