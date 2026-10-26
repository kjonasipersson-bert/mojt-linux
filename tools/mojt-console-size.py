#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Set tty geometry explicitly, or query a terminal supporting CSI 18 t."""

import argparse
import fcntl
import os
import re
import select
import struct
import termios
import time
import tty


def resize(fd, rows=None, cols=None, timeout=2.0):
    if rows is None:
        original = termios.tcgetattr(fd)
        if select.select([fd], [], [], 0)[0]:
            raise ValueError("terminal input pending; retry at an idle prompt")
        data = b""
        try:
            tty.setcbreak(fd, termios.TCSANOW)
            os.write(fd, b"\x1b[18t")
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                remaining = max(0, deadline - time.monotonic())
                if not select.select([fd], [], [], remaining)[0]:
                    break
                chunk = os.read(fd, 1)
                if not chunk:
                    break
                data += chunk
                if len(data) > 64:
                    break
                match = re.fullmatch(rb"\x1b\[8;([0-9]{1,5});([0-9]{1,5})t", data)
                if match:
                    rows, cols = map(int, match.groups())
                    break
        finally:
            termios.tcsetattr(fd, termios.TCSANOW, original)
        if rows is None:
            raise ValueError("no terminal-size response; use mojt-console-size ROWS COLS")
    if not (1 <= rows <= 1000 and 1 <= cols <= 1000):
        raise ValueError("rows and columns must each be between 1 and 1000")
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    return rows, cols


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("size", nargs="*", type=int, metavar="SIZE")
    args = parser.parse_args()
    if len(args.size) not in (0, 2):
        parser.error("supply both ROWS COLS, or neither")
    try:
        fd = os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY)
        try:
            dimensions = resize(fd, *args.size) if args.size else resize(fd)
        finally:
            os.close(fd)
    except (OSError, ValueError, termios.error) as error:
        parser.exit(1, f"mojt-console-size: {error}\n")
    print(*dimensions)


if __name__ == "__main__":
    main()
