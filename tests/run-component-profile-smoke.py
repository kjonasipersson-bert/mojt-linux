#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Boot actual component projections and read-only payloads with a real Kernel.

Synthetic Runtime/start and firmware data; this is a path/mount/return probe,
not full Mojt systemd, hardware-firmware loading or owner-machine acceptance.
"""
import argparse
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile

REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'tools'),str(REPO/'tests')]
import mojt_artifact as artifact
import mpm_base as base
import mpm_system as system
import mpm_kernel_boot as archive
from test_system_components import Components


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel',type=Path,required=True);parser.add_argument('--busybox',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    artifact.require(os.geteuid()==0,'run the disposable component probe as root')
    artifact.require(not args.output.exists(),'use a new component smoke output')
    args.output.mkdir(parents=True,mode=0o700)
    with tempfile.TemporaryDirectory(prefix='mojt-component-smoke-',dir='/var/tmp') as temporary:
        old_temp=tempfile.tempdir;tempfile.tempdir=temporary
        fixture=Components();fixture.setUp()
        try:
            a=fixture.build(label='component-a');fixture.import_package(a)
            b=fixture.build(a['artifact'],'component-b');fixture.import_package(b)
            artifact.require(a['firmware']==b['firmware'],'Runtime update changed firmware')
            vm=archive.vm_module()
            for label,identifier in (('component-a',a['artifact']),('component-b',b['artifact']),('system-native-test',fixture.body['id'])):
                profile=system.realization_path(fixture.root,identifier)/'profile'
                components=system.native_components(fixture.root,identifier)
                mounts=''
                for row in components:
                    point='/run/mojt-disk/'+row['path']
                    mounts+='mount --bind '+point+' '+point+' || fail component-bind\n'
                    mounts+='mount -o remount,bind,ro '+point+' '+point+' || fail component-readonly\n'
                    mounts+='if /bin/busybox touch '+point+'/.unexpected-write 2>/dev/null; then fail component-writable; fi\n'
                script='''#!/bin/sh
exec </dev/console >/dev/console 2>&1
export PATH=/bin
fail() { echo "MOJT_COMPONENT_FAILURE: $*"; /bin/busybox poweroff -f; }
mount -t proc proc /proc || fail proc
mkdir -p /run/mojt-disk /run/mojt-system
mount --bind /disk /run/mojt-disk || fail backing
'''+mounts+'''mount --bind /run/mojt-disk/PROFILE /run/mojt-system || fail profile
mount -o remount,bind,ro /run/mojt-system || fail profile-readonly
if /bin/busybox touch /run/mojt-system/.unexpected-write 2>/dev/null; then fail profile-writable; fi
/bin/busybox sha256sum /run/mojt-system/kernel/lib/firmware/fixture.bin || fail firmware-path
/run/mojt-system/start || fail start
echo MOJT_COMPONENT_BOOT_OK:LABEL
/bin/busybox poweroff -f
'''.replace('PROFILE',profile.relative_to(fixture.root).as_posix()).replace('LABEL',label)
                directory=args.output/label
                def writer(tree):
                    shutil.copytree(fixture.root,tree/'disk',symlinks=True)
                    return archive.write_initramfs(tree)
                raw=vm.make_initramfs(directory,args.busybox,[],script,archive_writer=writer)
                initrd=args.output/(label+'.cpio.gz');initrd.write_bytes(raw)
                try:
                    result=subprocess.run(['qemu-system-x86_64','-machine','q35,accel=tcg','-m','512M','-nographic',
                        '-monitor','none','-no-reboot','-nic','none','-kernel',str(args.kernel),'-initrd',str(initrd),
                        '-append','console=ttyS0 rdinit=/init panic=5 quiet'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
                except subprocess.TimeoutExpired as error:
                    (args.output/(label+'.log')).write_bytes(error.stdout or b'');raise ValueError('component boot timed out: '+label) from error
                (args.output/(label+'.log')).write_bytes(result.stdout)
                artifact.require(result.returncode==0 and ('MOJT_COMPONENT_SYSTEM:'+label).encode() in result.stdout
                    and ('MOJT_COMPONENT_BOOT_OK:'+label).encode() in result.stdout
                    and b'MOJT_COMPONENT_FAILURE' not in result.stdout,'component projection boot failed: '+label)
                print('PASS: real Kernel started '+label+' with protected profile/component paths')
            print('PASS: Runtime A/B and return to legacy profile; shared firmware reference retained')
        finally:
            fixture.doCleanups();tempfile.tempdir=old_temp


if __name__=='__main__':main()
