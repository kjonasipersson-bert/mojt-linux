#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Build a fresh VM image from exact local native Base and Kernel artifacts."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mojt_native_image import main

if __name__ == "__main__":
    raise SystemExit(main())
