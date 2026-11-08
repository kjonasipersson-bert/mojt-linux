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

REPO = Path(__file__).resolve().parents[1]


def require(ok, message):
    if not ok:raise ValueError(message)


def run(*args, **kwargs):
    return subprocess.run([str(v) for v in args], check=True, **kwargs)


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
            loop = subprocess.check_output(['losetup','--find','--show','--partscan',str(image/'disk.img')],text=True).strip()
            require(loop.startswith('/dev/loop') and Path(loop+'p2').is_block_device(), 'partitioned loop device unavailable')
            mount(loop+'p2',point=target)
            old = json.loads((image/'selected-deployment.json').read_text())['description']
            require(old['system']['generation'] == generation and old['base']['artifact'] == identifier, 'fresh image inputs differ')
            require(not (target/'boot/mpm/format').exists() and not (target/'boot/mpm/grub.cfg').exists(), 'refuse an existing managed boot registry')
            # A disposable execution root, separate from every measured Base.
            shutil.copytree(target/'base'/old['base']['release'],jail,symlinks=True)
            prep = jail/'run/preparation';(prep/'tools').mkdir(parents=True)
            shutil.copyfile(package,prep/'base.tar.zst')
            shutil.copyfile(REPO/'tests/run-system-boot-acceptance.py',prep/'runner.py')
            shutil.copyfile(REPO/'tools/mojt_system_package.py',prep/'tools/mojt_system_package.py')
            profile = target/'system'/generation
            for source,destination,readonly in ((target,jail/'run/mojt-disk',False),(target/'nix',jail/'nix',False),
                    (profile,jail/'run/mojt-system',True),(target/'state/etc',jail/'etc',True),(Path('/dev'),jail/'dev',False)):
                bind(source,destination,readonly=readonly)
            (jail/'proc').mkdir(exist_ok=True);mount('-t','proc','proc',point=jail/'proc')
            env = dict(PATH='/run/mojt-system/libexec/mpm/bin:/run/mojt-system/bin:/usr/bin:/bin',
                       LC_ALL='C',HOME='/root',PYTHONDONTWRITEBYTECODE='1')
            chroot = shutil.which('chroot');require(chroot is not None,'host chroot unavailable')
            run(chroot,jail,'/run/mojt-system/bin/python3','-I','-B','/run/preparation/runner.py',
                'construct','--base-artifact',identifier,env=env)
            evidence = target/'state/var/lib/mojt/system-boot-acceptance/state.json'
            # External builder sidecars describe the v1 bootstrap assembly;
            # expose the actual A/B identities separately and remove the old
            # direct-boot launcher, which would bypass the new GRUB authority.
            shutil.copyfile(evidence,image/'native-v2-acceptance.json')
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
                try:run('losetup','--detach',loop)
                except subprocess.CalledProcessError:errors.append(loop)
            # Never recursively delete through a mount whose cleanup failed.
            if errors:
                raise RuntimeError('offline mount cleanup failed: '+', '.join(errors))
        require(clean, 'offline construction did not finish')


def main():
    if '--finalize' in sys.argv[1:]:
        parser = argparse.ArgumentParser(description='Internal unpublished-image finalizer')
        parser.add_argument('--finalize',type=Path,required=True)
        parser.add_argument('--base-package',type=Path,required=True)
        parser.add_argument('--base-artifact',required=True);parser.add_argument('--generation',required=True)
        args = parser.parse_args()
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
        print('No READY launcher published; inspect the private output before retrying.',file=sys.stderr)
        sys.exit(1)
