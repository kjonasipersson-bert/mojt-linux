#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Boot a built Base with retained System package inputs and Kernel in a NEW VM."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'tools'))
import mojt_artifact as artifact
shared = runpy.run_path(str(Path(__file__).with_name('prepare-kernel-source-boot.py')))
require = shared['require']
read = artifact.read_json


def read_build_result(path):
    """Build reports contain floating-point timings, unlike canonical metadata."""
    with path.open('rb') as stream:
        raw = stream.read(artifact.MAX_METADATA + 1)
    require(len(raw) <= artifact.MAX_METADATA, 'Base build result exceeds size limit')
    result = json.loads(raw)
    require(isinstance(result, dict), 'expected a Base build result object')
    return result


def inputs(args):
    """Saved metadata supplies locators, never commands, output paths or authority."""
    seed = read(args.from_check)
    require(seed.get('format') == 'mojt-boot-test-input-check-v1' and seed.get('profile') == 'system-v2',
            'expected the saved native-v2 VM input-check.json')
    build = args.base_build.resolve(strict=True)
    require(not (build/'INCOMPLETE').exists(), 'Base build is incomplete')
    result = read_build_result(build/'result.json')
    require(result.get('format') == 'mojt-base-source-build-v1', 'unsupported Base build result')
    release = Path(result['release'])
    require(release.is_absolute() and release == release.resolve(strict=True)
            and release.parent == build/'releases', 'release must belong to this Base build')
    kernel = seed['kernel']; system = seed['system']
    require(re.fullmatch(r'sha256:[0-9a-f]{64}', kernel['artifact']) is not None, 'invalid retained Kernel identity')
    require(re.fullmatch(r'[0-9a-f]{64}', system['record_sha256']) is not None, 'invalid retained System input checksum')
    kernel_file = Path(kernel['path']); payload = Path(system['path'])
    require(kernel_file.is_absolute() and kernel_file.is_file(), 'retained Kernel archive missing: '+str(kernel_file))
    require(payload.is_absolute() and (payload/'system.json').is_file(), 'retained System export missing: '+str(payload))
    with (payload/'system.json').open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    require(actual == system['record_sha256'],
            'System export record changed since the saved VM input check')
    args.base_release = release; args.kernel_package = kernel_file
    args.expected_kernel = kernel['artifact']; args.system_payload = payload; args.path_file = None
    update=getattr(args,'update_package',None)
    if update is not None:
        require(update.is_file() and not update.is_symlink(),'regular native Base update archive required')
        body=artifact.verify(update)
        require(body['kind']=='base' and body['name']=='mojt','update input must be a complete Mojt Base package')
    output = shared['fresh_output'](args.output, (REPO, args.from_check, build, kernel_file, payload))
    return seed, output


def bootstrap_command(args, output, packed):
    command = [sys.executable, '-I', '-B', REPO/'tools/mojt_bootstrap.py',
        '--base-package', output/'base-package'/packed['archive']['file'],
        '--base-artifact', packed['artifact']['id'], '--base-context', output/'base-context.json',
        '--kernel-registry', output/'kernel-registry', '--kernel-artifact', args.expected_kernel,
        '--system-payload', args.system_payload, '--system-generation', 'system-source-base-test',
        '--busybox', args.busybox, '--output', output/'image']
    if getattr(args,'with_build_tools',False):command.append('--with-build-tools')
    return command


def update_disk(output, package):
    """Attach one frozen package read-only; the guest uses ordinary MPM."""
    import mojt_boot
    data=output/'update-input';data.mkdir()
    body=artifact.verify(package)
    frozen=data/'base.tar.zst';shutil.copyfile(package,frozen)
    require(artifact.verify(frozen)==body,'Base update package changed while copying')
    disk=output/'update-input.img'
    with disk.open('xb') as stream:stream.truncate((frozen.stat().st_size//1024**2+32)*1024**2)
    subprocess.run(['mkfs.ext4','-F','-q','-L','MOJT_BASE_UPDATE','-d',str(data),str(disk)],check=True)
    disk.chmod(0o400)
    original=(output/'image/run-qemu.sh').read_text()
    script=shared['launcher'](original,output/'image',disk)
    launcher=output/'run-qemu.sh';launcher.write_text(script);launcher.chmod(0o755)
    subprocess.run(['bash','-n',str(launcher)],check=True)
    return launcher


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from-check', type=Path, required=True)
    parser.add_argument('--base-build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--busybox', type=Path, default=Path('/usr/bin/busybox'))
    parser.add_argument('--with-build-tools',action='store_true',help='include the current MBT frontend and fixed build resources')
    parser.add_argument('--update-package',type=Path,help='attach this native Base package on a separate read-only input disk')
    parser.add_argument('--check-inputs', action='store_true', help='read/verify inputs without sudo or output writes')
    args = parser.parse_args(argv)
    require(os.geteuid() != 0, 'run as the ordinary Debian user; only new-image assembly invokes sudo')
    require(args.check_inputs or sys.stdin.isatty(), 'run directly in an interactive terminal for password entry')
    seed, output = inputs(args)
    os.environ['PATH'] = shared['HOST_PATH']
    commands = (*shared['COMMANDS'], 'unshare', 'mount', 'umount', 'chroot')
    missing = [name for name in commands if not shutil.which(name)]
    require(not missing, 'missing host commands: '+', '.join(missing))
    for path in (*shared['FIRMWARE'], args.busybox):require(path.is_file(), 'missing host input: '+str(path))
    management = shared['check_source']()
    if args.check_inputs:
        report = shared['input_report'](args, 'system-v2', management)
        print(json.dumps(report, indent=2))
        print('PASS: source Base and retained inputs verified; no image or output written')
        return
    os.umask(0o077); output.mkdir(mode=0o700)
    (output/'INCOMPLETE').write_text('Private VM preparation incomplete; inspect the failure log.\n')
    (output/'seed-input-check.json').write_text(json.dumps(seed, indent=2)+'\n')
    python = [sys.executable, '-I', '-B']
    run = shared['run']
    print('Package the built Base release...', flush=True)
    packed = run([*python, REPO/'tools/mojt-artifact-pack.py', 'base', '--release', args.base_release,
        '--revision', '1', '--output', output/'base-package'], result=output/'base-package-result.json')
    print('Retain the exact existing Kernel; no Kernel build...', flush=True)
    run([*python, REPO/'tools/mpm', '--root', output/'kernel-registry', 'kernel', 'install',
        '--from-file', args.kernel_package, '--expected-id', args.expected_kernel, '-y'], result=output/'kernel-install.json')
    sys.path.insert(0, str(REPO/'tools'))
    import mpm_catalog as catalog
    body = read(output/'kernel-registry/installed'/args.expected_kernel.split(':')[1]/'artifact.json')
    bounds = shared['context'](packed['artifact'], body, catalog.BASE_FORMAT); catalog.base_context(bounds)
    (output/'base-context.json').write_text(json.dumps(bounds, indent=2)+'\n')
    print('Bootstrap one native-v2 System on the NEW image; sudo and a new VM root password may be requested...', flush=True)
    run(['sudo', 'env', 'PATH='+shared['HOST_PATH'], *bootstrap_command(args, output, packed)])
    result = read(output/'image/bootstrap.json')['description']
    require(result['base'] == packed['artifact']['id'] and result['kernel'] == args.expected_kernel,
            'completed bootstrap differs from requested Base/Kernel')
    launcher = output/'image/run-qemu.sh'
    require(launcher.is_file(), 'completed VM launcher missing')
    if args.update_package is not None:launcher=update_disk(output,args.update_package)
    (output/'INCOMPLETE').unlink()
    print('READY: '+str(launcher))
    print('One fresh VM; retained System package inputs and exact Kernel. Start it separately.')


if __name__ == '__main__':
    try:main()
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        raise SystemExit('Source Base boot preparation: '+str(error))
