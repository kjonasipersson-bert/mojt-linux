#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Prepare one unpublished native-v2 A/B VM; never attach an existing VM disk."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parents[1]


def require(ok, message):
    if not ok:raise ValueError(message)


def run(*args, **kwargs):
    return subprocess.run([str(v) for v in args], check=True, **kwargs)


def root_extent(size, table):
    """Validate the builder's GPT, then map only its exact root byte extent."""
    sys.path.insert(0,str(REPO/'tools'))
    import mojt_boot
    require(type(size) is int and size % mojt_boot.MIB == 0,'unexpected disk byte length')
    expected = mojt_boot.layout(size//mojt_boot.MIB)
    require(type(table) is dict and table.get('label') == 'gpt' and table.get('sectorsize') == mojt_boot.SECTOR
            and table.get('unit','sectors') == 'sectors','unsupported disk partition table')
    parts = table.get('partitions')
    require(type(parts) is list and len(parts) == 2,'expected exactly the EFI and root partitions')
    require(all(type(p) is dict and all(type(p.get(k)) is int for k in ('start','size')) for p in parts),'invalid partition extent')
    actual = [(p['start']*mojt_boot.SECTOR,p['size']*mojt_boot.SECTOR) for p in parts]
    require(actual == [(expected['esp_offset'],expected['esp_bytes']),(expected['root_offset'],expected['root_bytes'])],
            'GPT extents differ from the native image layout')
    return actual[1]


def attach_root(disk, expected_uuid):
    """Return a UUID-checked root-only loop mapping, without partition nodes."""
    require(not subprocess.check_output(['losetup','--associated',str(disk)],text=True).strip(),
            'unpublished disk already has a loop mapping; inspect it before retrying')
    table = json.loads(subprocess.check_output(['sfdisk','--json',str(disk)],text=True))['partitiontable']
    offset,length = root_extent(disk.stat().st_size,table)
    loop = subprocess.check_output(['losetup','--find','--show','--offset',str(offset),
        '--sizelimit',str(length),str(disk)],text=True).strip()
    try:
        require(loop.startswith('/dev/loop') and Path(loop).is_block_device(), 'root filesystem loop device unavailable: '+loop)
        actual_uuid = subprocess.check_output(['blkid','--probe','--match-tag','UUID','--output','value',loop],text=True).strip()
        require(actual_uuid == expected_uuid,'mapped root filesystem UUID differs from the bootstrap deployment')
    except BaseException:
        detach_root(loop,disk);raise
    return loop


def detach_root(loop, disk):
    """Kernel loop detach is deferred; wait only for this mapping to vanish."""
    run('losetup','--detach',loop)
    deadline = time.monotonic()+5
    while True:
        rows = subprocess.check_output(['losetup','--associated',str(disk)],text=True).splitlines()
        if not any(row.startswith(loop+':') for row in rows):return
        require(time.monotonic() < deadline,'root loop mapping still pending/in use: '+loop+' for '+str(disk))
        time.sleep(0.05)


def isolated(command, proc, **kwargs):
    """PID-namespace init exit kills only this construction's descendants.

    Nix can start helpers which otherwise outlive a failed constructor and pin
    its store mount. The private proc mount also matches the child PID namespace.
    No host process is signalled and no lazy/forced unmount is used.
    """
    binary = shutil.which('unshare');require(binary is not None,'host unshare unavailable')
    return run(binary,'--pid','--fork','--kill-child','--mount-proc='+str(proc),*command,**kwargs)


@contextmanager
def workspace(parent):
    work = Path(tempfile.mkdtemp(prefix='.system-v2-finalize-',dir=parent))
    try:yield work
    except BaseException:
        print('Private preparation workspace retained:',work,file=sys.stderr)
        raise
    else:shutil.rmtree(work)


def finalize(image, package, identifier, generation):
    """Internal root helper, called in a private mount namespace before publication.

    Execute only the explicitly supplied bootstrap System, not either new
    candidate. Its Nix store and the target's store are the same bind-mounted
    filesystem: no host Nix database or guessed offline adapter is substituted.
    """
    require(os.geteuid() == 0, 'offline finalization requires root')
    image = image.absolute();package = package.absolute()
    require(image == image.resolve() and image.name == '.unpublished-image', 'only the unpublished test image is accepted')
    require((image/'disk.img').is_file() and not (image/'disk.img').is_symlink(), 'regular new disk required')
    require(package == package.resolve() and package.is_file(), 'regular exact Base archive required')
    require(generation == 'system-v2-bootstrap', 'unexpected bootstrap generation')
    sys.path.insert(0,str(REPO/'tools'))
    import mojt_artifact as artifact
    import mpm_deployment as deployment
    original = artifact.read_json(image/'selected-deployment.json');old = deployment.validate_deployment(original)
    require(old['system']['generation'] == generation and old['base']['artifact'] == identifier,'fresh image inputs differ')
    require(not (image/'OVMF_VARS.fd').exists(),'refuse an image whose firmware launcher was started')
    disk = image/'disk.img'
    # The parent remains private; a failure never produces the public launcher.
    with workspace(image.parent) as work:
        target = work/'target';target.mkdir()
        jail = work/'chroot';loop = None;mounted = [];clean = False
        def mount(*args, point):
            run('mount',*args,point);mounted.append(point)
        def bind(source, destination, *, readonly=False):
            destination.mkdir(parents=True,exist_ok=True)
            mount('--bind',source,point=destination)
            if readonly:run('mount','-o','remount,bind,ro',destination)
        try:
            loop = attach_root(disk,old['boot']['root_uuid'])
            mount(loop,point=target)
            require(not (target/'boot/mpm/format').exists() and not (target/'boot/mpm/grub.cfg').exists(), 'refuse an existing managed boot registry')
            require(not os.path.lexists(target/'artifacts') and not os.path.lexists(target/'realizations'),
                    'native construction already started; inspect its checkpoint instead of resuming this image')
            require(artifact.read_json(target/'boot/mojt'/generation/old['base']['release']/'deployment.json') == original,
                    'on-disk bootstrap deployment differs')
            import mojt_system
            profile = target/'system'/generation
            require(all(artifact.file_sha(profile/'tools'/name) == artifact.file_sha(REPO/'tools'/name)
                        for name in mojt_system.MPM_FILES),'bootstrap manager code differs from the current checkout; use a fresh image')
            # A disposable execution root, separate from every measured Base.
            shutil.copytree(target/'base'/old['base']['release'],jail,symlinks=True)
            prep = jail/'run/preparation';(prep/'tools').mkdir(parents=True)
            shutil.copyfile(package,prep/'base.tar.zst')
            shutil.copyfile(REPO/'tests/run-system-boot-acceptance.py',prep/'runner.py')
            shutil.copyfile(REPO/'tools/mojt_system_package.py',prep/'tools/mojt_system_package.py')
            for source,destination,readonly in ((target,jail/'run/mojt-disk',False),(target/'nix',jail/'nix',False),
                    (profile,jail/'run/mojt-system',True),(target/'state/etc',jail/'etc',True),(Path('/dev'),jail/'dev',False)):
                bind(source,destination,readonly=readonly)
            (jail/'proc').mkdir(exist_ok=True)
            env = dict(PATH='/run/mojt-system/libexec/mpm/bin:/run/mojt-system/bin:/usr/bin:/bin',
                       LC_ALL='C',HOME='/root',PYTHONDONTWRITEBYTECODE='1')
            chroot = shutil.which('chroot');require(chroot is not None,'host chroot unavailable')
            isolated([chroot,jail,'/run/mojt-system/bin/python3','-I','-B','/run/preparation/runner.py',
                      'construct','--base-artifact',identifier],jail/'proc',env=env)
            evidence = target/'state/var/lib/mojt/system-boot-acceptance/state.json'
            # External builder sidecars describe the v1 bootstrap assembly;
            # expose the actual A/B identities separately and remove the old
            # direct-boot launcher, which would bypass the new GRUB authority.
            shutil.copyfile(evidence,image/'native-v2-acceptance.json')
            (image/'native-v2-acceptance.json').chmod(0o644)
            direct = image/'run-qemu-direct.sh'
            require(direct.is_file() and not direct.is_symlink(),'unexpected bootstrap direct launcher')
            direct.unlink()
            clean = True
        finally:
            errors = []
            for point in reversed(mounted):
                try:run('umount',point)
                except subprocess.CalledProcessError:errors.append(str(point))
            if loop:
                try:detach_root(loop,disk)
                except (OSError,ValueError,subprocess.CalledProcessError) as error:errors.append(loop+': '+str(error))
            # Never recursively delete through a mount whose cleanup failed.
            if errors:
                raise RuntimeError('offline mount cleanup failed: '+', '.join(errors))
        require(clean, 'offline construction did not finish')



def main():
    if any(v == '--finalize' or v.startswith('--finalize=') for v in sys.argv[1:]):
        parser = argparse.ArgumentParser(description='Internal unpublished-image finalizer')
        parser.add_argument('--finalize',type=Path,required=True)
        parser.add_argument('--base-package',type=Path,required=True)
        parser.add_argument('--base-artifact',required=True);parser.add_argument('--generation',required=True)
        args = parser.parse_args()
        # This is a disposable helper process: do not inherit host sudo policy
        # when creating the new guest's public runtime and boot directories.
        os.umask(0o022)
        finalize(args.finalize,args.base_package,args.base_artifact,args.generation)
        return
    shared = runpy.run_path(str(REPO/'tests/prepare-kernel-source-boot.py'))
    def finish(*, image, base_package, base_artifact, generation):
        print('Constructing both native-v2 Systems on the unpublished disk (closure verification can take a while)...',flush=True)
        run('sudo','env','PATH='+shared['HOST_PATH'],'unshare','--mount','--propagation','private',sys.executable,'-I','-B',
            Path(__file__).resolve(),'--finalize',image,'--base-package',base_package,
            '--base-artifact',base_artifact,'--generation',generation)
    shared['main'](profile='system-v2',finish=finish)


if __name__ == '__main__':
    try:main()
    except (OSError,ValueError,KeyError,RuntimeError,subprocess.CalledProcessError) as error:
        print('System boot preparation:',error,file=sys.stderr)
        print('No READY launcher published. Failed preparations cannot resume; use a new output directory.',file=sys.stderr)
        sys.exit(1)
