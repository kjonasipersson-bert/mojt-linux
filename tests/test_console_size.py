#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Real PTY geometry/query/timeout checks; no QEMU acceptance."""
import fcntl
import importlib.util
from pathlib import Path
import os
import pty
import struct
import termios
import threading
import unittest

spec = importlib.util.spec_from_file_location("console_size", Path(__file__).parents[1] / "tools/mojt-console-size.py")
console = importlib.util.module_from_spec(spec)
spec.loader.exec_module(console)


class ConsoleSizeTests(unittest.TestCase):
    def setUp(self):
        self.master, self.slave = pty.openpty()
        self.addCleanup(os.close, self.master)
        self.addCleanup(os.close, self.slave)

    def size(self):
        return struct.unpack("HHHH", fcntl.ioctl(self.slave, termios.TIOCGWINSZ, b"\0" * 8))[:2]

    def test_explicit_size_and_invalid_size(self):
        self.assertEqual(console.resize(self.slave, 40, 140), (40, 140))
        self.assertEqual(self.size(), (40, 140))
        with self.assertRaises(ValueError):
            console.resize(self.slave, 0, 140)
        self.assertEqual(self.size(), (40, 140))

    def test_query_sets_size_and_restores_terminal_flags(self):
        original = termios.tcgetattr(self.slave)
        query = []
        def terminal():
            query.append(os.read(self.master, 5))
            os.write(self.master, b"\x1b[8;48;160t")
        thread = threading.Thread(target=terminal, daemon=True)
        thread.start()
        self.assertEqual(console.resize(self.slave), (48, 160))
        thread.join(timeout=1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(query, [b"\x1b[18t"])
        self.assertEqual(self.size(), (48, 160))
        self.assertEqual(termios.tcgetattr(self.slave), original)

    def test_timeout_restores_flags_and_keeps_geometry(self):
        console.resize(self.slave, 25, 80)
        original = termios.tcgetattr(self.slave)
        with self.assertRaisesRegex(ValueError, "no terminal-size response"):
            console.resize(self.slave, timeout=0.02)
        self.assertEqual(termios.tcgetattr(self.slave), original)
        self.assertEqual(self.size(), (25, 80))


if __name__ == "__main__":
    unittest.main()
