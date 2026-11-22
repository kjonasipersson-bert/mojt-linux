#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Real qemu-ga over VirtIO serial in a tiny guest, not full Mojt acceptance."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'tools'))
import mpm_kernel_boot as archive
import mojt_artifact as artifact


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel',type=Path,required=True)
    parser.add_argument('--modules-dir',type=Path,required=True)
    parser.add_argument('--busybox',type=Path,default=Path('/bin/busybox'))
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();artifact.require(os.geteuid()==0,'root required for initramfs nodes')
    artifact.require(not args.output.exists(),'use a new test output')
    args.output.mkdir(mode=0o700);work=args.output.resolve()
    binary=Path(shutil.which('qemu-ga') or '/usr/sbin/qemu-ga').resolve(strict=True)
    spec=importlib.util.spec_from_file_location('agent_guest_copy',REPO/'tests/run-shutdown-smoke.py')
    copier=importlib.util.module_from_spec(spec);spec.loader.exec_module(copier)
    vm=archive.vm_module();release=vm.kernel_release_from_path(args.kernel)
    modules=vm.module_paths(release,args.modules_dir,names=('virtio_pci','virtio_console'))
    init='''#!/bin/sh
set -eu
exec </dev/console >/dev/console 2>&1
export PATH=/bin
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
mkdir -p /run/qemu-guest-agent /dev/virtio-ports
while IFS= read -r module; do [ -z "$module" ] || insmod "$module"; done </modules.list
tries=0
while [ "$tries" -lt 30 ]; do
  for port in /sys/class/virtio-ports/*; do
    [ -f "$port/name" ] || continue
    if [ "$(cat "$port/name")" = org.qemu.guest_agent.0 ]; then
      ln -s "/dev/${port##*/}" /dev/virtio-ports/org.qemu.guest_agent.0
      export QGA_CONF=/etc/qemu/qemu-ga.conf
      exec AGENT --method=virtio-serial --path=/dev/virtio-ports/org.qemu.guest_agent.0 --statedir=/run/qemu-guest-agent --pidfile=/run/qemu-guest-agent/qemu-ga.pid
    fi
  done
  tries=$((tries+1)); sleep 1
done
echo MOJT_QGA_CHANNEL_MISSING
poweroff -f
'''.replace('AGENT',str(binary))
    def write(tree):
        copier.copy_binary(tree,binary)
        (tree/'etc').mkdir();(tree/'etc/os-release').write_text('ID=mojt-probe\nPRETTY_NAME="Mojt agent fixture"\n')
        return archive.write_initramfs(tree)
    data=vm.make_initramfs(work/'tree',args.busybox,modules,init,extra_applets=('cat','ln','poweroff'),archive_writer=write)
    image=work/'agent.cpio.gz';image.write_bytes(data);channel=work/'qga.sock'
    command=['qemu-system-x86_64','-machine','q35,accel=tcg','-m','512M','-display','none','-serial','stdio',
             '-monitor','none','-no-reboot','-nic','none','-kernel',str(args.kernel),'-initrd',str(image),
             '-append','console=ttyS0 rdinit=/init panic=5 quiet',
             '-chardev',f'socket,path={channel},server=on,wait=off,id=agent',
             '-device','virtio-serial-pci','-device','virtserialport,chardev=agent,name=org.qemu.guest_agent.0']
    with (work/'boot.log').open('wb') as log:
        process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
        try:
            deadline=time.monotonic()+90
            with socket.socket(socket.AF_UNIX) as client:
                while True:
                    artifact.require(process.poll() is None,'guest exited before agent connection; inspect boot.log')
                    try:client.connect(str(channel));break
                    except (FileNotFoundError,ConnectionRefusedError):
                        artifact.require(time.monotonic()<deadline,'agent socket timeout');time.sleep(0.1)
                client.settimeout(max(1,deadline-time.monotonic()))
                stream=client.makefile('rwb',buffering=0);responses={}
                for number,name in enumerate(('guest-ping','guest-info','guest-get-host-name'),1):
                    stream.write(json.dumps(dict(execute=name,id=number)).encode()+b'\n')
                    response=json.loads(stream.readline().lstrip(b'\xff'))
                    artifact.require('return' in response and response.get('id')==number,'guest-agent request failed: '+str(response))
                    responses[name]=response['return']
                (work/'responses.json').write_text(json.dumps(responses,indent=2)+'\n')
                artifact.require(responses['guest-info'].get('version'),'agent version absent')
            print('PASS: ordinary qemu-ga answered guest-ping, guest-info and guest-get-host-name over VirtIO serial.')
        finally:
            if process.poll() is None:process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait()


if __name__=='__main__':main()
