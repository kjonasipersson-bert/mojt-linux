#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Privilege staging regressions; no claim of actual setuid/PAM authentication."""

import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location("mojt_privileged_test",
    Path(__file__).parents[1] / "tools/mojt-privileged-setup.py")
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)


class PrivilegedHelperTests(unittest.TestCase):
    def record(self, content=b"\x7fELFsynthetic"):
        return {name: {"source": "/nix/store/" + "a" * 32 + "-package/bin/" + name,
                       "sha256": hashlib.sha256(content).hexdigest()} for name in helpers.NAMES}

    def test_verified_inputs_reject_corruption_scripts_and_unmanaged_paths(self):
        with mock.patch.object(Path, "read_bytes", return_value=b"\x7fELFsynthetic"):
            self.assertEqual(set(helpers.verified_inputs(self.record())), helpers.NAMES)
            bad = self.record()
            bad["sudo"]["sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "integrity"):
                helpers.verified_inputs(bad)
        with mock.patch.object(Path, "read_bytes", return_value=b"#!/bin/sh\n"):
            with self.assertRaisesRegex(ValueError, "integrity"):
                helpers.verified_inputs(self.record(b"#!/bin/sh\n"))
        bad = self.record()
        bad["sudo"]["source"] = "/home/user/sudo"
        with self.assertRaisesRegex(ValueError, "unsafe"):
            helpers.verified_inputs(bad)

    def test_extra_privileged_helper_is_rejected(self):
        record = self.record()
        record["shell"] = record["sudo"]
        with self.assertRaisesRegex(ValueError, "selection"):
            helpers.verified_inputs(record)

    def test_staged_files_are_private_and_never_follow_preexisting_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = {name: b"\x7fELFsynthetic" for name in helpers.NAMES}
            with mock.patch.object(os, "fchown"):
                helpers.stage_helpers(data, root)
            for name in helpers.NAMES:
                self.assertEqual((root / name).read_bytes(), data[name])
                self.assertEqual((root / name).stat().st_mode & 0o7777, 0o600)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / "keep"
            outside.write_text("keep")
            stage = root / "stage"
            stage.mkdir()
            for name in helpers.NAMES:
                (stage / name).symlink_to(outside)
            with mock.patch.object(os, "fchown"), self.assertRaises(FileExistsError):
                helpers.stage_helpers(data, stage)
            self.assertEqual(outside.read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
