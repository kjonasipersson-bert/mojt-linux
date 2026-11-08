#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Debian-host preparation of one private native source/Kernel reboot test."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import uuid

REPO = Path(__file__).resolve().parents[1]
HOST_PATH = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
COMMANDS = ('git','bash','cp','du','tar','zstd','cpio','busybox','modprobe','mkfs.ext4','sfdisk',
            'mkfs.vfat','mcopy','grub-mkstandalone','grub-script-check','openssl','qemu-system-x86_64','sudo')


def require(ok, message):
    if not ok:raise ValueError(message)


def check_source(tools=None):
    """Fail before packaging/password entry; never change checkout permissions."""
    sys.path.insert(0,str(REPO/'tools'))
    import mpm_management
    import mojt_system
    return mpm_management.produce(Path(tools) if tools is not None else REPO/'tools',mojt_system.MPM_FILES)


def fresh_output(value, inputs):
    output = Path(value).absolute()
    require(output == output.resolve() and not os.path.lexists(output), 'output must be a new nonsymlink directory')
    require(output.parent.is_dir(), 'output parent must exist')
    for path in inputs:
        path = Path(path).resolve()
        require(output != path and output not in path.parents and path not in output.parents,
                'output must be separate from repository and all input trees/files')
    return output


def context(base, kernel, fmt):
    require(base['platform'] == kernel['platform'], 'Base/Kernel platforms differ')
    upstream = kernel['version']['upstream']
    # Narrow owner-test bounds for this already accepted pair, not published
    # compatibility policy for arbitrary later upstream Kernel versions.
    return dict(format=fmt, base=dict(artifact=base['id'], release=base['version']['upstream']),
                platform=base['platform'], kernel_min=upstream, kernel_max=upstream)


def launcher(original, image, inputs):
    here = 'here="$(cd -- "$(dirname -- "$0")" && pwd -P)"'
    drive = '    -drive "file=$here/disk.img,if=virtio,format=raw" \\\n'
    require(original.count(here) == original.count(drive) == 1, 'unexpected native QEMU launcher; no guessed rewrite')
    return original.replace(here, 'here='+shlex.quote(str(image))).replace(drive, drive +
        '    -drive '+shlex.quote('file='+str(inputs)+',if=virtio,format=raw,readonly=on')+' \\\n')


def run(command, *, result=None):
    if result is None:
        subprocess.run([str(v) for v in command], check=True)
        return None
    completed = subprocess.run([str(v) for v in command], text=True, capture_output=True)
    require(completed.returncode == 0, completed.stderr + completed.stdout)
    value = json.loads(completed.stdout)
    result.write_text(json.dumps(value, indent=2)+'\n')
    return value


def save_path(path, output):
    path = Path(path).absolute()
    require(path.parent.is_dir() and not path.is_symlink(), 'unsafe/missing path-file parent or linked path file')
    if path.exists():
        require(path.is_file() and path.stat().st_uid == os.geteuid(), 'path file is not owned by this user')
    temporary = path.parent/('.'+path.name+'-'+uuid.uuid4().hex)
    try:
        with temporary.open('x') as stream:
            stream.write(str(output)+'\n'); stream.flush(); os.fsync(stream.fileno())
        temporary.replace(path)
    finally:temporary.unlink(missing_ok=True)


def publish(output, image, *, scripts, volume, record_format, base, kernel, kernel_release, path_file=None):
    """Publish the existing completed image and its read-only acceptance input."""
    inputs = output/'acceptance-files'; (inputs/'tests').mkdir(parents=True)
    inventory = {}
    for name in scripts:
        target = inputs/'tests'/name
        shutil.copyfile(REPO/'tests'/name,target)
        inventory['tests/'+name] = hashlib.sha256(target.read_bytes()).hexdigest()
    (inputs/'inventory.json').write_text(json.dumps(inventory,indent=2)+'\n')
    data_disk = output/'acceptance-inputs.img'
    with data_disk.open('xb') as stream:stream.truncate(32*1024**2)
    run(['mkfs.ext4','-F','-q','-L',volume,'-d',inputs,data_disk])
    data_disk.chmod(0o400)
    script = launcher((image/'run-qemu.sh').read_text(), image, data_disk)
    (output/'run-qemu.sh').write_text(script); (output/'run-qemu.sh').chmod(0o755)
    run(['bash','-n',output/'run-qemu.sh'])
    revision = subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD'],text=True).strip()
    (output/'preparation.json').write_text(json.dumps(dict(format=record_format,
        source_revision=revision, base=base, kernel=kernel,
        kernel_release=kernel_release, inputs=inventory),indent=2)+'\n')
    if path_file:save_path(path_file,output)
    print('READY:',output/'run-qemu.sh')
    print('Fresh native VM plus separate read-only test-input disk; previous VM disks are not attached.')


def main(*, profile='kernel-source', finish=None):
    profiles = {
        'kernel-source': ('system-source-kernel-boot', ('run-kernel-source-boot.py','run-kernel-source-acceptance.py'),
                          'MOJT_SOURCE_BOOT', 'mojt-kernel-source-boot-preparation-v1'),
        'base': ('system-base-boot-test', ('run-base-boot-acceptance.py',),
                 'MOJT_BASE_BOOT', 'mojt-base-boot-preparation-v1'),
        'system-v2': ('system-v2-bootstrap', ('run-system-boot-acceptance.py',),
                      'MOJT_SYSTEM_BOOT', 'mojt-system-boot-preparation-v1'),
    }
    require(profile in profiles, 'unknown acceptance profile')
    generation, scripts, volume, record_format = profiles[profile]
    p = argparse.ArgumentParser(description=("Debian-host preparation of a fresh changed-Base boot/return test." if profile == "base" else __doc__))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--base-release', type=Path, required=True)
    p.add_argument('--kernel-package', type=Path, required=True)
    p.add_argument('--expected-kernel', required=True)
    p.add_argument('--system-payload', type=Path, required=True)
    p.add_argument('--busybox', type=Path, default=Path('/usr/bin/busybox'))
    p.add_argument('--path-file', type=Path)
    args = p.parse_args()
    print('Checking host prerequisites and frozen input paths...', flush=True)
    require(os.geteuid() != 0, 'run as the ordinary Debian user, without sudo; only image assembly invokes sudo')
    require(sys.stdin.isatty(), 'run this file directly in an interactive terminal, not through a heredoc or pipe')
    require(sys.version_info >= (3,11), 'Python 3.11+ required')
    check_source()
    os.environ['PATH'] = HOST_PATH
    commands = COMMANDS + (('losetup','mount','umount','unshare','chroot','blkid') if profile == 'system-v2' else ())
    missing = [name for name in commands if not shutil.which(name)]
    require(not missing, 'missing host commands: '+', '.join(missing))
    for path in (args.base_release/'manifest.toml', args.base_release/'rootfs.tar.zst',
                 args.kernel_package, args.system_payload/'system.json', args.busybox,
                 Path('/usr/share/OVMF/OVMF_CODE_4M.fd'), Path('/usr/share/OVMF/OVMF_VARS_4M.fd')):
        require(path.is_file(), 'missing input: '+str(path))
    if profile in ('base','system-v2'):
        sys.path.insert(0,str(REPO/'tools'))
        import mojt_system
        payload = mojt_system.load_payload(args.system_payload)
        require('tar' in payload['packages'],
                'native boot test needs a verified System payload with retained GNU tar')
    require((profile == 'system-v2') == (finish is not None), 'System-v2 preparation requires its offline finalizer')
    output = fresh_output(args.output, (REPO,args.base_release,args.kernel_package,args.system_payload))
    # Validate the actual future registry ancestry before packaging any inputs.
    sys.path.insert(0,str(REPO/'tools'))
    import mpm_kernel
    mpm_kernel.root_path(output/'kernel-registry', write=True)
    os.umask(0o077); output.mkdir(mode=0o700)
    print('Test directory:', output, flush=True)
    python = [sys.executable,'-I','-B']
    print('Packaging the retained Base release; original release remains unchanged...', flush=True)
    packed = run([*python,REPO/'tools/mojt-artifact-pack.py','base','--release',args.base_release,
        '--revision','1','--output',output/'base-package'], result=output/'base-package-result.json')
    print('Retaining the exact existing Kernel in a private host registry...', flush=True)
    run([*python,REPO/'tools/mpm','--root',output/'kernel-registry','kernel','install',
        '--from-file',args.kernel_package,'--expected-id',args.expected_kernel,'-y'], result=output/'kernel-install.json')
    sys.path.insert(0,str(REPO/'tools'))
    from mpm_catalog import BASE_FORMAT, base_context
    kernel = json.loads((output/'kernel-registry/installed'/args.expected_kernel.split(':')[1]/'artifact.json').read_bytes())
    bounds = context(packed['artifact'], kernel, BASE_FORMAT); base_context(bounds)
    (output/'base-context.json').write_text(json.dumps(bounds,indent=2)+'\n')
    image = output/('.unpublished-image' if finish is not None else 'image')
    command = [*python,REPO/'tools/mojt-native-image.py',
        '--base-package',output/'base-package'/packed['archive']['file'], '--base-artifact',packed['artifact']['id'],
        '--base-context',output/'base-context.json', '--kernel-registry',output/'kernel-registry',
        '--kernel-artifact',args.expected_kernel,'--system-payload',args.system_payload.resolve(),
        '--output',image,'--system-generation',generation,'--disk-size-mib','8192',
        '--busybox',args.busybox]
    print('Verifying native image preview (System hashing may take a while)...',flush=True)
    run([*command,'--dry-run'],result=output/'image-preview.json')
    print('Building the NEW image; sudo and a new VM root password may be requested...',flush=True)
    run(['sudo','env','PATH='+HOST_PATH,*command])
    if finish is not None:
        finish(image=image, base_package=output/'base-package'/packed['archive']['file'],
               base_artifact=packed['artifact']['id'], generation=generation)
        image.rename(output/'image');image = output/'image'
    publish(output,image,scripts=scripts,volume=volume,record_format=record_format,
            base=packed['artifact']['id'],kernel=args.expected_kernel,
            kernel_release=kernel['metadata']['kernel_release'],path_file=args.path_file)


if __name__ == '__main__':
    try:main()
    except (OSError,ValueError,KeyError,subprocess.CalledProcessError) as error:
        print('Native source-boot preparation:',error,file=sys.stderr)
        print('Preparation stopped; private output is retained if it was already created.',file=sys.stderr)
        sys.exit(1)

