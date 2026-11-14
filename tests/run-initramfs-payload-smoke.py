#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Boot two small overlays over one cached payload with a real Linux Kernel.

This checks Linux's concatenated gzip/newc loading, not a complete Mojt System,
firmware matrix, storage drivers or owner-machine performance.
"""
import argparse
from pathlib import Path
import os
import subprocess
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import mojt_artifact as artifact
import mpm_boot_constructor as constructor
import mpm_boot_v2 as model
import mpm_kernel_boot as archive


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel',type=Path,required=True)
    parser.add_argument('--busybox',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    artifact.require(os.geteuid()==0,'real initramfs device nodes require root')
    # RUNNER_TEMP is below an unprivileged home on GitHub. The cache must
    # obey the same protected-ancestor contract as a real installed disk.
    with tempfile.TemporaryDirectory(prefix='mojt-payload-smoke-',dir='/var/tmp') as private:
        probe(args,Path(private)/'disk')


def probe(args,root):
    kernel=args.kernel.resolve(strict=True);busybox=args.busybox.resolve(strict=True)
    artifact.require(not args.output.exists(),'use a new disposable smoke output')
    args.output.mkdir(parents=True,mode=0o700);work=args.output.resolve()
    (root/'boot/mpm').mkdir(parents=True)
    vm=archive.vm_module();artifact.require(vm.static_x86_64_elf(busybox),'static BusyBox required')
    key=model.record(constructor.PAYLOAD_KEY,dict(probe=1,kernel_sha256=artifact.file_sha(kernel),busybox_sha256=artifact.file_sha(busybox)))
    def create():
        def write(tree):
            (tree/'payload-marker').write_text('preserved-heavy-payload\n')
            return archive.write_initramfs(tree)
        return vm.make_initramfs(work/'payload-tree',busybox,[],constructor.PAYLOAD_INIT,archive_writer=write)
    first=None
    for number,label in enumerate(('system-one','system-two')):
        def forbidden():raise AssertionError('warm payload was rebuilt')
        payload,reused=constructor.cached_payload(root,key,create if number==0 else forbidden)
        artifact.require(reused==(number==1),'unexpected payload reuse state')
        if first is None:first=payload
        else:artifact.require(payload==first,'reused compressed payload changed')
        overlay=work/label;overlay.mkdir()
        (overlay/'mojt').mkdir();(overlay/'mojt/selected').write_text(label+'\n')
        script='''#!/bin/sh
exec </dev/console >/dev/console 2>&1
if [ "$(/bin/busybox cat /payload-marker)" = preserved-heavy-payload ] &&
   [ "$(/bin/busybox cat /mojt/selected)" = LABEL ]; then
    /bin/busybox echo 'MOJT_PAYLOAD_OVERLAY_BOOT: LABEL'
fi
/bin/busybox poweroff -f
'''.replace('LABEL',label)
        (overlay/'init').write_text(script);(overlay/'init').chmod(0o755)
        path=work/(label+'.cpio.gz');path.write_bytes(payload+archive.write_initramfs(overlay))
        try:
            result=subprocess.run(['qemu-system-x86_64','-machine','q35,accel=tcg','-m','512M','-nographic',
                '-monitor','none','-no-reboot','-nic','none','-kernel',str(kernel),'-initrd',str(path),
                '-append','console=ttyS0 rdinit=/init panic=5 quiet'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
        except subprocess.TimeoutExpired as error:
            (work/(label+'.log')).write_bytes(error.stdout or b'')
            raise ValueError('payload/overlay Kernel boot timed out; inspect '+str(work/(label+'.log'))) from error
        (work/(label+'.log')).write_bytes(result.stdout)
        artifact.require(result.returncode==0 and ('MOJT_PAYLOAD_OVERLAY_BOOT: '+label).encode() in result.stdout,
                         'payload/overlay Kernel boot failed; inspect '+str(work/(label+'.log')))
        print('PASS: real Kernel booted '+label+'; payload '+('reused' if reused else 'built'))


if __name__=='__main__':main()
