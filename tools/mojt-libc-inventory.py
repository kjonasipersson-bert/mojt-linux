#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Read-only libc inventory inside a running Mojt VM or physical installation.

Standalone Python 3.11+; no current MPM modules, Nix commands or downloads.
Only selected installed programs and current process mappings are inspected.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys


def read_text(path):
    with Path(path).open() as stream:
        value = stream.read(131073)
    if len(value) > 131072:
        raise ValueError("inventory input exceeds 128 KiB: " + str(path))
    return value


def command(argv):
    # Loader inspection must not inherit LD_PRELOAD/LD_LIBRARY_PATH or tunables.
    try:
        result = subprocess.run(argv, env={"PATH": os.defpath, "LC_ALL": "C"},
                                capture_output=True, text=True, errors="replace", timeout=10)
        return dict(exit=result.returncode, stdout=result.stdout.strip(), stderr=result.stderr.strip())
    except (OSError, subprocess.TimeoutExpired) as error:
        return dict(error=str(error))


def interpreter(path):
    """Read PT_INTERP only, including when binutils is absent on an older VM."""
    with Path(path).open('rb') as stream:
        header = stream.read(64)
        if not header.startswith(b'\x7fELF'):
            return None
        if len(header) != 64 or header[4] not in (1, 2) or header[5] not in (1, 2):
            raise ValueError("unsupported ELF header")
        order = '<' if header[5] == 1 else '>'
        wide = header[4] == 2
        offset = struct.unpack_from(order + ('Q' if wide else 'I'), header, 32 if wide else 28)[0]
        size, count = struct.unpack_from(order + 'HH', header, 54 if wide else 42)
        if size < (56 if wide else 32) or size > 4096 or count > 1024:
            raise ValueError("unsupported ELF program-header table")
        for index in range(count):
            stream.seek(offset + index * size)
            row = stream.read(size)
            if len(row) != size:
                raise ValueError("truncated ELF program header")
            if struct.unpack_from(order + 'I', row)[0] != 3:  # PT_INTERP
                continue
            start = struct.unpack_from(order + ('Q' if wide else 'I'), row, 8 if wide else 4)[0]
            length = struct.unpack_from(order + ('Q' if wide else 'I'), row, 32 if wide else 16)[0]
            if not 1 < length <= 4096:
                raise ValueError("invalid ELF interpreter length")
            stream.seek(start)
            raw = stream.read(length)
            if len(raw) != length or raw[-1:] != b'\0':
                raise ValueError("truncated ELF interpreter")
            return raw[:-1].decode('utf-8')
    return None


def program(path, readelf):
    result = dict(path=str(path))
    try:
        target = Path(path).resolve(strict=True)
        result['resolved'] = str(target)
        loader = interpreter(target)
        result['interpreter'] = loader
        if loader:
            # --list resolves dependencies without running the program's entry point.
            result['loader_list'] = command([loader, '--list', str(target)])
        if readelf:
            dynamic = command([readelf, '--wide', '--dynamic', str(target)])
            versions = command([readelf, '--wide', '--version-info', str(target)])
            result['dynamic'] = dict(dynamic, stdout='\n'.join(
                line.strip() for line in dynamic.get('stdout', '').splitlines()
                if any(tag in line for tag in ('(NEEDED)', '(RPATH)', '(RUNPATH)'))))
            # Version definitions describe exports, not this executable's requirements.
            needs = versions.get('stdout', '').partition('Version needs section')[2]
            result['required_glibc_versions'] = sorted(set(re.findall(r'\bGLIBC_[\w.]+', needs)))
            if versions.get('exit') != 0:
                result['version_inspection'] = versions
        else:
            result['elf_details'] = 'not inspected: readelf unavailable; PT_INTERP and loader resolution only'
    except (OSError, ValueError, struct.error) as error:
        result['error'] = str(error)
    return result


def mappings(pid):
    try:
        rows = read_text(f'/proc/{pid}/maps').splitlines()
        return sorted({row.split(None, 5)[5] for row in rows if len(row.split(None, 5)) == 6
                       and re.search(r'/(?:libc[.-]|ld[.-]|libnss|pam_)', row.split(None, 5)[5])})
    except (OSError, ValueError) as error:
        return dict(error=str(error))


def inventory(dns_name=None):
    identities = {}
    for name, path in (('base', '/usr/lib/os-release'), ('system', '/run/mojt-system/version')):
        try:
            identities[name] = read_text(path).strip()
        except (OSError, ValueError) as error:
            identities[name] = dict(error=str(error))
    readelf = shutil.which('readelf')
    targets = ['/bin/sh', '/usr/bin/ls', '/usr/bin/getent', '/proc/1/exe',
               sys.executable, '/run/mojt-system/bin/python3', '/run/mojt-system/bin/bash',
               '/run/mojt-system/bin/login', '/run/mojt-system/bin/sshd',
               '/var/lib/mojt/ports/current/bin/git', '/var/lib/mojt/ports/current/bin/nvim']
    programs = []
    for path in dict.fromkeys(targets):
        print('Inspect: ' + path, file=sys.stderr, flush=True)
        programs.append(program(path, readelf))
    probes = {'base_libc': command(['/usr/bin/getconf', 'GNU_LIBC_VERSION']),
              'base_locales': command(['/usr/bin/locale', '-a'])}
    for name, database, key in (('account', 'passwd', 'root'), ('localhost', 'hosts', 'localhost')):
        result = command(['/usr/bin/getent', database, key])
        result.pop('stdout', None)  # Record success/failure, not account contents.
        probes['base_' + name] = result
    python = '/run/mojt-system/bin/python3'
    for name, code in (
        ('system_account', "import pwd; pwd.getpwnam('root')"),
        ('system_localhost', "import socket; socket.getaddrinfo('localhost', None)"),
        ('system_utf8_locale', "import locale; print(locale.setlocale(locale.LC_ALL, 'C.UTF-8'))"),
    ):
        probes[name] = command([python, '-I', '-B', '-c', code])
    if dns_name:
        probes['base_dns'] = command(['/usr/bin/getent', 'hosts', dns_name])
        probes['system_dns'] = command([python, '-I', '-B', '-c',
            'import socket,sys; socket.getaddrinfo(sys.argv[1], None)', dns_name])
    return dict(format='mojt-libc-inventory-v1', identities=identities, kernel=os.uname().release,
                readelf=readelf, programs=programs, probes=probes,
                mapped_libraries=dict(init=mappings(1), inventory_python=mappings('self')),
                scope='Observations of this running generation only; not a compatibility or boot guarantee. '
                      'Loader/probe commands use a clean environment. No installation or selection changes.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dns-name', help='also test name resolution for this hostname (optional network lookup)')
    args = parser.parse_args()
    print(json.dumps(inventory(args.dns_name), indent=2))


if __name__ == '__main__':
    main()
