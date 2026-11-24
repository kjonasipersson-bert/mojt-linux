# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Install Mojt interactively from local installer inputs onto one whole disk."""

import argparse
from contextlib import ExitStack, contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time
import uuid

import mojt_boot as boot
import mojt_bootstrap as bootstrap
import mojt_bootstrap_inputs as inputs
import mojt_mounted_install as mounted
import mojt_native_image as native

MIB = boot.MIB
GIB = 1024 * MIB
SWAP_TYPE = '0657fd6d-a4ab-43c4-84e5-0933c84b4f4f'
require = mounted.require


def device_number(info, *, block=False):
    number = info.st_rdev if block else info.st_dev
    return f'{os.major(number)}:{os.minor(number)}'


def in_use():
    numbers = set()
    for row in mounted.mounts():
        numbers.add(row['device'])
        if row['source'].startswith('/dev/'):
            path = Path(row['source'])
            if path.exists() and stat.S_ISBLK((info := path.stat()).st_mode):
                numbers.add(device_number(info, block=True))
    for line in Path('/proc/swaps').read_text().splitlines()[1:]:
        info = Path(mounted.unescape(line.split()[0])).stat()
        numbers.add(device_number(info, block=stat.S_ISBLK(info.st_mode)))
    # A multi-device Btrfs source can report only one member in mountinfo.
    for entry in Path('/sys/fs/btrfs').glob('*/devices/*/dev'):
        numbers.add(entry.read_text().strip())
    return numbers


def disks():
    output = mounted.run('lsblk', '--json', '--list', '--bytes', '--paths',
                         '--output', 'NAME,TYPE,SIZE,MODEL,SERIAL,RO,MAJ:MIN',
                         capture_output=True, text=True, timeout=30)
    busy = in_use()
    available = []
    for row in json.loads(output.stdout)['blockdevices']:
        if row['type'] != 'disk' or row['ro'] or row['size'] < 2 * GIB:
            continue
        path = Path(row['name'])
        if not re.fullmatch(r'/dev/[A-Za-z0-9._-]+', str(path)):
            continue
        point = (Path('/sys/dev/block')/row['maj:min']).resolve(strict=True)
        related = [point, *(part for part in point.iterdir() if (part/'partition').is_file())]
        if any((part/'dev').read_text().strip() in busy or any((part/'holders').iterdir())
               for part in related):
            continue
        if mounted.device(path) != (path, row['maj:min']):
            continue
        available.append(dict(path=str(path), number=row['maj:min'], bytes=row['size'],
                              model=row['model'] or '', serial=row['serial'] or '',
                              sequence=(point/'diskseq').read_text().strip()))
    return available


def layout(swap_gib):
    rows = [('MOJT-EFI', mounted.ESP_TYPE, f'{boot.ESP_MIB}MiB')]
    if swap_gib:
        rows.append(('MOJT-SWAP', SWAP_TYPE, f'{swap_gib}GiB'))
    rows.append(('MOJT', mounted.ROOT_TYPE, ''))
    return [(name, kind, size, str(uuid.uuid4())) for name, kind, size in rows]


def partition(disk, rows):
    label = str(uuid.uuid4())
    specification = f'label: gpt\nlabel-id: {label}\n\n'
    for name, kind, size, guid in rows:
        specification += (f'size={size}, ' if size else '') + f'type={kind}, uuid={guid}, name={name}\n'
    mounted.run('sfdisk', '--lock=no', '--wipe=always', '--wipe-partitions=always', disk['path'],
                input=specification, text=True, timeout=60)
    table = json.loads(mounted.run('sfdisk', '--json', disk['path'], capture_output=True,
                                  text=True, timeout=30).stdout)['partitiontable']
    require(table['label'] == 'gpt' and mounted.gpt_uuid(table['id']) == label and
            [(part['name'], part['type'].lower(), mounted.gpt_uuid(part['uuid']))
             for part in table['partitions']] == [(name, kind, guid) for name, kind, _, guid in rows],
            'written partition table differs from the installation plan')
    devices = {}
    for part in table['partitions']:
        node = Path(part['node'])
        for _ in range(50):
            if node.exists():
                break
            time.sleep(0.2)
        path, number = mounted.device(node)
        require(path == node and mounted.parent_disk(number) == (disk['path'], disk['number']),
                'partition device differs from the reviewed target')
        sysfs = Path('/sys/dev/block')/number
        sector = table['sectorsize']
        require(all(int((sysfs/key).read_text())*512 == part[key]*sector for key in ('start', 'size')),
                'kernel partition extent differs from the reviewed target')
        devices[part['name']] = path
    return devices


def swap_config(tree, partuuid):
    units = tree/'state/etc/systemd/system'
    wants = units/'sysinit.target.wants'
    for directory in (units, wants):
        require(directory.resolve() == directory, 'linked swap configuration directory')
        directory.mkdir(parents=True, exist_ok=True)
    # Unit names escape literal hyphens in device paths. Mojt disables
    # generators, so this is an explicit machine-local systemd swap unit.
    name = r'dev-disk-by\x2dpartuuid-' + partuuid.replace('-', r'\x2d') + '.swap'
    with (units/name).open('x') as unit:
        unit.write(f'[Swap]\nWhat=/dev/disk/by-partuuid/{partuuid}\n')
    (wants/name).symlink_to('../'+name)


@contextmanager
def workspace():
    work = Path(tempfile.mkdtemp(prefix='mojt-install-', dir='/run'))
    root, esp = work/'root', work/'esp'
    try:
        root.mkdir(); esp.mkdir()
        yield work, root, esp
    finally:
        # Never recursively clean up here: a failed umount can leave the
        # installation filesystem mounted beneath this directory.
        for directory in (esp, root, work):
            try:
                directory.rmdir()
            except FileNotFoundError:
                pass
            except OSError as error:
                print(f'Installation mountpoint retained: {error}', file=sys.stderr)


def install(kit):
    require(os.geteuid() == 0, 'installation requires an administrator')
    require(sys.stdin.isatty() and sys.stdout.isatty(), 'installation requires an interactive terminal')
    require(Path('/sys/firmware/efi').is_dir(), 'start the installation medium in UEFI mode')
    for command in ('lsblk', 'sfdisk', 'mkfs.btrfs', 'mkfs.vfat', 'mkswap', 'mount', 'umount'):
        mounted.command(command)

    supported_filesystems = set(Path('/proc/filesystems').read_text().split())
    for filesystem in ('btrfs', 'vfat'):
        if filesystem not in supported_filesystems:
            mounted.run('modprobe', filesystem, timeout=30)

    candidates = disks()
    require(candidates, 'no unused writable target disk found')
    for i, disk in enumerate(candidates, 1):
        details = ' '.join(f'{value!r}' for value in (disk['model'], disk['serial']) if value)
        print(f"{i}. {disk['path']}  {disk['bytes']/GIB:.1f} GiB  {details}")
    choice = input('Disk number (Enter cancels): ').strip()
    if not choice:
        return
    require(re.fullmatch(r'[1-9][0-9]{0,5}', choice) and int(choice) <= len(candidates),
            'invalid disk number')
    disk = candidates[int(choice)-1]

    swap = input('Swap size in GiB [0]: ').strip() or '0'
    require(re.fullmatch(r'[0-9]{1,6}', swap), 'enter a whole number of GiB')
    swap_gib = int(swap)
    require(swap_gib*GIB + (boot.ESP_MIB+2)*MIB + GIB <= disk['bytes'],
            'swap leaves less than 1 GiB for the Mojt filesystem')

    with workspace() as (work, root, esp):
        origin = {}
        argv = inputs.expand(['--inputs', str(kit), '--target-root', str(root),
                              '--efi-directory', str(esp), '--root-fs', 'btrfs'], details=origin)
        args = bootstrap.parser().parse_args(argv)
        args.installer_inputs_id = origin['id']
        args.output = work/'unused-image'
        mounted.check_storage(mounted.storage_drivers(disk['number']), args.hardware_profile)
        evidence = native.preview(args)
        bootstrap.preflight(args, evidence, mounted=True)
        from mpm_kernel_boot import vm_module
        release = evidence['kernel']['metadata']['kernel_release']
        module_tree = (args.kernel_registry/'installed'/args.kernel_artifact[7:]/
                       'payload/lib/modules'/release)
        vm_module().module_paths(release, module_tree, network=True, root_fs='btrfs',
                                 names=native.hardware.early_modules(args.hardware_profile, root_fs='btrfs')
                                 if args.hardware_profile else None)
        print(f"Erase {disk['path']} ({disk['bytes']/GIB:.1f} GiB) and install "
              f"Base {evidence['base']['version']['upstream']} with Linux {release}.")
        print(f"EFI: {boot.ESP_MIB} MiB  Swap: {swap_gib} GiB  Btrfs: remaining space")
        if input(f"Type {disk['path']} to erase the entire disk: ").strip() != disk['path']:
            print('Installation cancelled.')
            return

        rows = layout(swap_gib)
        fd = os.open(disk['path'], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb', buffering=0) as device:
            fcntl.flock(device, fcntl.LOCK_EX | fcntl.LOCK_NB)
            require(device_number(os.fstat(device.fileno()), block=True) == disk['number']
                    and disk in disks(), 'target disk identity or usage changed')
            parts = partition(disk, rows)
            mounted.run('mkfs.vfat', '-F', '32', '-n', 'MOJT-EFI', parts['MOJT-EFI'], timeout=60)
            mounted.run('mkfs.btrfs', '-L', 'MOJT', parts['MOJT'], timeout=300)
            if swap_gib:
                mounted.run('mkswap', parts['MOJT-SWAP'], timeout=60)
        with ExitStack() as cleanup:
            for path, node, fs, options in (
                (root, parts['MOJT'], 'btrfs', 'subvolid=5'),
                (esp, parts['MOJT-EFI'], 'vfat', 'umask=0077'),
            ):
                mounted.run('mount', '-t', fs, '-o', options, node, path, timeout=60)
                cleanup.callback(mounted.run, 'umount', path, timeout=60)
            target = mounted.inspect(root, esp, root_fs='btrfs')
            require(target['root']['partuuid'] == rows[-1][3] and
                    target['efi']['partuuid'] == rows[0][3] and
                    target['root']['disk_device'] == disk['number'], 'mounted target differs from the reviewed disk')
            args.expected_root_uuid = target['root']['uuid']
            args.expected_efi_partuuid = rows[0][3]
            if swap_gib:
                partuuid = rows[1][3]
                mounted.build(args, configure=lambda tree: swap_config(tree, partuuid))
            else:
                mounted.build(args)
        print('Mojt installed. Shut down and remove the installation medium before booting.')


def main(argv=None, *, prog='mbt install'):
    parser = argparse.ArgumentParser(prog=prog, description=__doc__, allow_abbrev=False)
    parser.add_argument('--inputs', type=Path, default=Path('/var/lib/mojt/installer-inputs'),
                        help='local installer input kit (default: %(default)s)')
    args = parser.parse_args(argv)
    try:
        install(args.inputs)
        return 0
    except (OSError, ValueError, KeyError, TypeError, EOFError, subprocess.SubprocessError, KeyboardInterrupt) as error:
        print(f'{prog}: {error or "interrupted"}', file=sys.stderr)
        return 1
