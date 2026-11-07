#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Prepare a NEW native VM and read-only Base acceptance input disk on Debian."""
from pathlib import Path
import runpy
import subprocess
import sys

if __name__ == '__main__':
    try:
        runpy.run_path(str(Path(__file__).with_name('prepare-kernel-source-boot.py')))['main'](profile='base')
    except (OSError,ValueError,KeyError,subprocess.CalledProcessError) as error:
        print('Base boot preparation:',error,file=sys.stderr)
        print('Private output retained if already created; no previous VM disk was attached.',file=sys.stderr)
        sys.exit(1)
