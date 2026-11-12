# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Fresh native-v2 installation on explicitly mounted, empty GPT partitions."""
from contextlib import ExitStack, contextmanager
import copy
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import uuid

import mojt_artifact as artifact
import mojt_boot as boot
import mojt_native_image as native
import mpm_boot_selection as selection
import mpm_transaction as tx

require = artifact.require
ROOT_TYPE = '0fc63daf-8483-4772-8e79-3d69d8477de4'
ESP_TYPE = 'c12a7328-f81f-11d2-ba4b-00a0c93ec93b'
MARKER = '.mojt-bootstrap-incomplete'
RECEIPT = 'state/var/lib/mojt/mounted-install.json'


def command(name):
    value = shutil.which(name)
    require(value is not None, 'missing mounted installation tool: ' + name)
    path = Path(value).absolute()
    shared = Path('/var/lib/mojt/ports')
    require(not path.is_relative_to(shared) and not path.resolve().is_relative_to(shared),
            'mounted installation tools must not come from shared Ports')
    return str(path)


def run(name, *args, **kwargs):
    return subprocess.run([command(name), *map(str, args)], check=True, **kwargs)


def unescape(value):
    return re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), value)


def mounts():
    rows = []
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        fields = line.split(); separator = fields.index('-')
        rows.append(dict(id=int(fields[0]), device=fields[2], root=unescape(fields[3]),
                         path=unescape(fields[4]), options=fields[5].split(','),
                         fstype=fields[separator+1], source=unescape(fields[separator+2])))
    return rows


def device(path):
    path = Path(path).resolve(strict=True)
    info = path.stat()
    require(path.is_relative_to('/dev') and stat.S_ISBLK(info.st_mode),
            'mounted source must be a block device: ' + str(path))
    return path, f'{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}'


def parent_disk(number):
    point = (Path('/sys/dev/block') / number).resolve(strict=True)
    require((point/'partition').is_file(), 'target must be a partition, not a whole disk or logical volume')
    parent = point.parent
    values = dict(line.split('=', 1) for line in (parent/'uevent').read_text().splitlines() if '=' in line)
    name = values.get('DEVNAME', '')
    require(re.fullmatch(r'[A-Za-z0-9._-]+', name), 'unsupported parent disk name')
    disk, actual = device(Path('/dev')/name)
    require(actual == (parent/'dev').read_text().strip(), 'parent disk device identity differs')
    return str(disk), actual


def storage_drivers(number):
    point = (Path('/sys/dev/block')/number).resolve(strict=True)
    return sorted({(p/'driver').resolve().name for p in (point,*point.parents) if (p/'driver').is_symlink()})


def gpt_uuid(value):
    # sfdisk emits GPT identifiers in uppercase; boot filesystem UUIDs have
    # their own stricter canonical spelling and must not be conflated with it.
    require(type(value) is str, 'GPT UUID must be a string')
    return boot.fs_uuid(value.lower())


def probe_partition(row, *, role):
    path, number = device(row['source'])
    require(number == row['device'], 'mount and source device differ')
    disk, parent = parent_disk(number)
    raw = run('sfdisk', '--json', disk, capture_output=True, text=True, timeout=30).stdout
    require(len(raw) <= 1024*1024, 'unbounded GPT metadata')
    table = json.loads(raw)['partitiontable']
    require(table.get('label') == 'gpt', 'mounted installation requires GPT')
    disk_id = gpt_uuid(table['id'])
    parts = table['partitions']
    require(type(parts) is list and 1 <= len(parts) <= 128, 'unbounded GPT partition list')
    matches = [p for p in parts if device(p['node'])[1] == number]
    require(len(matches) == 1, 'mounted partition missing or duplicated in GPT')
    part = matches[0]; part_id = gpt_uuid(part['uuid'])
    require(part['type'].lower() == (ROOT_TYPE if role == 'root' else ESP_TYPE),
            'wrong GPT partition type for ' + role)
    text = run('blkid', '-p', '-o', 'export', path, capture_output=True, text=True, timeout=30).stdout
    require(len(text) <= 65536, 'unbounded filesystem probe')
    pairs = [line.split('=', 1) for line in text.splitlines() if '=' in line]
    require(len({k for k, v in pairs}) == len(pairs), 'duplicate filesystem probe fields')
    filesystem = dict(pairs)
    require(filesystem.get('TYPE') == row['fstype'], 'mounted filesystem differs from block probe')
    identifier = filesystem.get('UUID')
    if role == 'root':boot.fs_uuid(identifier)
    else:
        require(filesystem.get('VERSION') == 'FAT32' and type(identifier) is str and
                re.fullmatch(r'[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}', identifier), 'FAT32 ESP identity required')
    return dict(source=str(path), device=number, disk=disk, disk_device=parent,
                disk_id=disk_id, partuuid=part_id, uuid=identifier,
                start=part['start'], sectors=part['size'], sector_size=table.get('sectorsize', 512))


def empty(path, *, root=False):
    for point in path.iterdir():
        require(root and point.name == 'lost+found' and not point.is_symlink()
                and point.is_dir() and point.stat().st_uid == 0 and not any(point.iterdir()),
                'target is not empty: ' + str(point))


def inspect(root, esp, *, fresh=True):
    require(os.geteuid() == 0, 'mounted target inspection requires an administrator')
    root, esp = (Path(os.path.abspath(p)) for p in (root, esp))
    require(root != esp and root not in esp.parents and esp not in root.parents,
            'root and ESP require separate, nonnested mountpoints')
    protected = ('/', '/etc', '/var', '/home', '/root', '/usr', '/nix', '/run/mojt-disk', '/run/mojt-system')
    for path in (root, esp):
        require(str(path) not in protected and not any(path.is_relative_to(p) for p in protected[1:]),
                'refusing a running-system target path')
        tx.protected_directory(path, write=True, label='mounted bootstrap target')
        require(path.is_dir(), 'mounted target must already exist')
    rows = mounts(); targets = []
    for path, role in ((root, 'root'), (esp, 'efi')):
        selected = [r for r in rows if r['path'] == str(path)]
        require(len(selected) == 1, 'target must be one exact mountpoint: ' + str(path))
        row = selected[0]
        require(row['root'] == '/' and 'rw' in row['options'] and
                row['fstype'] == ('ext4' if role == 'root' else 'vfat'),
                'target must be a writable whole ext4 filesystem or FAT32 ESP')
        require(sum(r['device'] == row['device'] for r in rows) == 1,
                'target filesystem is also mounted elsewhere')
        require(not any(Path(r['path']) != path and path in Path(r['path']).parents for r in rows),
                'nested target mounts are unsupported')
        entry = probe_partition(row, role=role)
        info = path.stat()
        require(f'{os.major(info.st_dev)}:{os.minor(info.st_dev)}' == entry['device'], 'mountpoint device changed')
        entry.update(path=str(path), mount_id=row['id'], directory=[info.st_dev, info.st_ino])
        targets.append(entry)
        if fresh:empty(path, root=role == 'root')
    r, e = targets
    require(r['device'] != e['device'] and r['disk_device'] == e['disk_device'] and r['disk_id'] == e['disk_id'],
            'root and ESP must be distinct partitions on the same GPT disk')
    # UUID discovery is the boot contract. A mounted installer/source copy must
    # not compete with the target, even when it has a different device name.
    matches = run('blkid', '-c', '/dev/null', '-t', 'UUID='+r['uuid'], '-o', 'device',
                  capture_output=True, text=True, timeout=30).stdout.splitlines()
    require({device(p)[1] for p in matches} == {r['device']}, 'target root UUID is missing or duplicated on another device')
    for row in rows:
        if row['device'] in (r['device'], e['device']):continue
        point = Path('/sys/dev/block')/row['device']
        if (point/'partition').is_file():
            require(parent_disk(row['device'])[1] != r['disk_device'],
                    'target disk contains another mounted partition (possibly the running installation)')
    for line in Path('/proc/swaps').read_text().splitlines()[1:]:
        path = Path(unescape(line.split()[0]))
        info = path.stat()
        number = f'{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}' if stat.S_ISBLK(info.st_mode) else \
                 f'{os.major(info.st_dev)}:{os.minor(info.st_dev)}'
        if (Path('/sys/dev/block')/number/'partition').is_file():
            require(parent_disk(number)[1] != r['disk_device'], 'target disk contains active swap')
    return dict(format='mojt-mounted-target-v1', root=r, efi=e, storage_drivers=storage_drivers(r['disk_device']))


def recheck(value, *, fresh):
    actual = inspect(value['root']['path'], value['efi']['path'], fresh=fresh)
    require(actual == value, 'mounted target identity changed; repeat preview')


@contextmanager
def locked(value):
    with ExitStack() as stack:
        names = {value['root']['disk']:value['root']['disk_device'],
                 value['root']['source']:value['root']['device'], value['efi']['source']:value['efi']['device']}
        for name in sorted(names):
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            stack.callback(os.close, fd)
            info = os.fstat(fd)
            require(stat.S_ISBLK(info.st_mode) and
                    f'{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}' == names[name], 'target device changed')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for role in ('root', 'efi'):
            fd = os.open(value[role]['path'], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            stack.callback(os.close, fd)
        recheck(value, fresh=True)
        yield


def write_json(path, value):
    with path.open('xb') as stream:
        stream.write(artifact.canonical(value) + b'\n')
        os.fchmod(stream.fileno(), 0o600); os.fsync(stream.fileno())


def publish(value, *, tree, result, bootstrap, inputs_id=None):
    """Write verified content first. The fallback EFI directory is published last."""
    from mojt_bootstrap import inspect_result
    root, esp = Path(value['root']['path']), Path(value['efi']['path'])
    checked = inspect_result(result, base_artifact=bootstrap['base'], kernel_artifact=bootstrap['kernel'])
    require(checked == bootstrap, 'mounted constructor result differs')
    inputs = checked['deployment']['description']['inputs']['description']
    require(inputs['boot']['root_uuid'] == value['root']['uuid'], 'deployment UUID differs from target filesystem')
    choice, entries, unused = selection.current(tree)
    require(choice == checked['selection'], 'prepared selection differs from bootstrap result')
    work = result.parent/'mounted-efi'; work.mkdir()
    loader = boot.efi_loader(tree/'boot/mojt/grub.cfg', work, value['root']['uuid'], inputs['boot']['console'])
    used = int(run('du', '-s', '--block-size=1', tree, capture_output=True, text=True).stdout.split()[0])
    free = os.statvfs(root)
    require(used + 128*1024*1024 < free.f_bavail*free.f_frsize, 'insufficient target filesystem free space')
    efi_free = os.statvfs(esp)
    require(loader.stat().st_size + 1024*1024 < efi_free.f_bavail*efi_free.f_frsize, 'insufficient ESP free space')
    recheck(value, fresh=True)
    write_json(root/MARKER, dict(format='mojt-mounted-install-incomplete-v1', target=value,
                                deployment=checked['deployment']['id']))
    published = False
    try:
        print('Mojt bootstrap: copying completed native installation to mounted target...', flush=True)
        run('cp', '-a', '--', str(tree)+'/.', str(root)+'/')
        recheck(value, fresh=False)
        chosen, installed, unused = selection.current(root, verify=True)
        require(chosen == checked['selection'] and
                installed[chosen['description']['selected']]['record'] == checked['deployment'],
                'copied native installation differs from constructed selection')
        run('sync', '-f', root)
        staging = esp/('.mojt-bootstrap-'+uuid.uuid4().hex)
        (staging/'EFI/BOOT').mkdir(parents=True)
        destination = staging/'EFI/BOOT/BOOTX64.EFI'
        with loader.open('rb') as source, destination.open('xb') as output:
            shutil.copyfileobj(source, output); output.flush(); os.fsync(output.fileno())
        require(artifact.file_sha(destination) == artifact.file_sha(loader), 'copied EFI loader differs')
        run('sync', '-f', esp)
        recheck(value, fresh=False)
        require(not os.path.lexists(esp/'EFI'), 'ESP destination appeared; refusing replacement')
        (staging/'EFI').rename(esp/'EFI'); published = True
        run('sync', '-f', esp)
        staging.rmdir()
        receipt = dict(format='mojt-mounted-install-v1', target=value, bootstrap=checked,
                       efi_sha256=artifact.file_sha(loader), inputs_id=inputs_id, boot_acceptance=False)
        path = root/RECEIPT; path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, receipt)
        execution = result/'builder-runtime.json'
        if execution.is_file():
            with (path.parent/'mounted-builder-runtime.json').open('xb') as output:
                output.write(execution.read_bytes()); os.fchmod(output.fileno(), 0o444); os.fsync(output.fileno())
        (root/MARKER).unlink(); run('sync', '-f', root)
    except BaseException as error:
        if published:
            raise tx.PublicationUncertain('EFI loader was published; target retained and may be bootable. '
                                          'Inspect installation receipt/state before any retry: ' + str(error)) from error
        raise
    return dict(format='mojt-mounted-bootstrap-result-v1', target=value, deployment=checked['deployment']['id'],
                base=checked['base'], system=checked['system'], kernel=checked['kernel'],
                receipt=str(root/RECEIPT), boot_acceptance=False)


def build(args):
    from mojt_bootstrap import finalize, preflight
    require(args.efi_directory is not None, '--target-root requires --efi-directory')
    value = inspect(args.target_root, args.efi_directory)
    supported = {'virtio_blk'} if getattr(args,'hardware_profile',None) is None else {'virtio_blk','ahci','usb-storage','uas'}
    require(bool(supported & set(value['storage_drivers'])),
            'target storage driver is outside the selected initial boot profile: '+', '.join(value['storage_drivers']))
    if args.expected_root_uuid is not None:
        require(args.expected_root_uuid == value['root']['uuid'], 'expected root UUID differs')
    if args.expected_efi_partuuid is not None:
        require(args.expected_efi_partuuid == value['efi']['partuuid'], 'expected ESP PARTUUID differs')
    if not args.dry_run:
        require(args.expected_root_uuid is not None and args.expected_efi_partuuid is not None,
                'mounted writes require --expected-root-uuid and --expected-efi-partuuid from preview')
    prepared = copy.copy(args)
    parent = native.WORK_PARENT.resolve(strict=True)
    tx.protected_directory(parent/('.mounted-check-'+uuid.uuid4().hex), label='mounted bootstrap workspace')
    if args.dry_run:
        prepared.output = parent/('.mojt-mounted-preview-'+uuid.uuid4().hex)
        evidence = native.preview(prepared)
        checks = preflight(prepared, evidence, mounted=True)
        recheck(value, fresh=True)
        return dict(format='mojt-mounted-bootstrap-preview-v1', target=value, preflight=checks,
                    base=evidence['base']['id'], kernel=evidence['kernel']['id'],
                    target_written=False, boot_acceptance=False)
    with locked(value), tempfile.TemporaryDirectory(prefix='mojt-mounted-', dir=parent) as temporary:
        prepared.output = Path(temporary)/'unused-image-output'
        def check(evidence):
            preflight(prepared, evidence, mounted=True); recheck(value, fresh=True)
        def finish(**values):
            return finalize(system_version=args.system_version, system_revision=args.system_revision, **values)
        def writer(**values):return publish(value, inputs_id=getattr(args,'installer_inputs_id',None), **values)
        return native.build(prepared, finalize_tree=finish, preflight=check,
                            filesystem_uuid=value['root']['uuid'], filesystem_writer=writer)
