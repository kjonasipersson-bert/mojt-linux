#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Compare private profile placement on synthetic files; never install or select."""
import argparse
from contextlib import ExitStack
import errno
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import time
from unittest import mock

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'tools'))
import mojt_artifact as artifact
import mpm_boot_inventory as inventory
import mpm_native_io as io
import mpm_system as system
import mpm_transaction as tx


def prepare(root,files,size,large_files,large_size):
    root.mkdir(mode=0o700)
    for directory,count,length in (('small',files,size),('large',large_files,large_size)):
        parent=root/directory;parent.mkdir(mode=0o700)
        block=b'x'*min(length,128*1024)
        for number in range(count):
            with (parent/('%05d.bin'%number)).open('xb') as stream:
                remaining=length
                while remaining:
                    chunk=block[:remaining];stream.write(chunk);remaining-=len(chunk)
                os.fchmod(stream.fileno(),0o444);stream.flush();os.fsync(stream.fileno())
        parent.chmod(0o555);io.sync_directory(parent)
    (root/'alias').symlink_to('small/00000.bin')
    root.chmod(0o555);io.sync_directory(root);io.sync_directory(root.parent)


def placement(source,target,*,copy):
    """Time the actual implementation, with EXDEV injected only for the copy case."""
    counters=dict(copy_calls=0,copy_bytes=0,file_fsync=0,directory_fsync=0,fsync_wall_ns=0)
    copied=io.copy_regular;synced=os.fsync;renamed=os.rename
    def copy_file(original,destination,size,mode):
        counters['copy_calls']+=1;counters['copy_bytes']+=size
        return copied(original,destination,size,mode)
    def sync(fd):
        counters['directory_fsync' if stat.S_ISDIR(os.fstat(fd).st_mode) else 'file_fsync']+=1
        start=time.perf_counter_ns()
        try:return synced(fd)
        finally:counters['fsync_wall_ns']+=time.perf_counter_ns()-start
    def rename(original,destination):
        if copy and original == source and destination == target:raise OSError(errno.EXDEV,'benchmark copy path')
        return renamed(original,destination)
    with ExitStack() as stack:
        stack.enter_context(mock.patch.object(io,'copy_regular',copy_file))
        stack.enter_context(mock.patch.object(os,'fsync',sync))
        stack.enter_context(mock.patch.object(os,'rename',rename))
        start=time.perf_counter_ns();cpu=time.process_time_ns()
        system.copy_profile(source,target)
        counters.update(wall_ns=time.perf_counter_ns()-start,python_cpu_ns=time.process_time_ns()-cpu)
    return counters


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,default=Path('/var/lib/mojt/system-profile-benchmark'))
    parser.add_argument('--files',type=int,default=2000)
    parser.add_argument('--file-size',type=int,default=4096)
    parser.add_argument('--large-files',type=int,default=2)
    parser.add_argument('--large-size-mib',type=int,default=16)
    args=parser.parse_args(argv)
    artifact.require(os.geteuid()==0,'run as root, like native System installation')
    artifact.require(1 <= args.files <= 20000 and 0 <= args.file_size <= 1024**2
        and 0 <= args.large_files <= 16 and 0 <= args.large_size_mib <= 128,'benchmark input bounds exceeded')
    total=args.files*args.file_size+args.large_files*args.large_size_mib*1024**2
    artifact.require(total <= 512*1024**2,'benchmark content exceeds 512 MiB')
    workspace=tx.protected_directory(args.workspace,write=True,label='benchmark workspace')
    workspace.mkdir(mode=0o700,parents=True,exist_ok=True)
    run=Path(tempfile.mkdtemp(prefix='run-',dir=workspace));scratch=run/'scratch';scratch.mkdir(mode=0o700)
    (scratch/'stage').mkdir(mode=0o700);source=scratch/'profile';copied=scratch/'stage/copied';moved=scratch/'stage/moved'
    try:
        print('Prepare and sync synthetic input (outside placement timings)...',flush=True)
        prepare(source,args.files,args.file_size,args.large_files,args.large_size_mib*1024**2)
        expected=inventory.snapshot(source);inode=(source/'small/00000.bin').stat().st_ino
        print('Measure durable profile copy...',flush=True);baseline=placement(source,copied,copy=True)
        print('Measure same-filesystem profile move...',flush=True);promoted=placement(source,moved,copy=False)
        artifact.require(inventory.snapshot(copied) == inventory.snapshot(moved) == expected,'benchmark profile differs')
        artifact.require(not source.exists() and (moved/'small/00000.bin').stat().st_ino == inode
            and (moved/'small/00000.bin').stat().st_nlink == 1,'profile move did not preserve an independent inode')
        artifact.require(baseline['copy_calls'] == baseline['file_fsync'] == args.files+args.large_files
            and promoted['copy_calls'] == promoted['file_fsync'] == 0 and promoted['directory_fsync'] == 2,
            'unexpected copy/sync counters: '+json.dumps(dict(copy=baseline,move=promoted),sort_keys=True))
        result=dict(format='mojt-system-profile-benchmark-v1',source_sha256=artifact.file_sha(REPO/'tools/mpm_system.py'),
            device=workspace.stat().st_dev,files=args.files+args.large_files,content_bytes=total,
            copy=baseline,move=promoted,contents_equal=True,
            scope='Synthetic profile placement only; preparation and comparison excluded. No install, boot change or full-install speedup claim.')
        io.write_json(run/'result.json',result)
        for label,row in (('Copy',baseline),('Move',promoted)):
            print('%s: %.6f s wall; %d copies / %d bytes; %d file + %d directory fsync; %.6f s in fsync'%
                (label,row['wall_ns']/1e9,row['copy_calls'],row['copy_bytes'],row['file_fsync'],row['directory_fsync'],row['fsync_wall_ns']/1e9))
        print('PASS: profile contents/modes/links match; no hardlink sharing. Report: '+str(run/'result.json'))
        return 0
    finally:io.clean_stage(scratch)


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError) as error:print('FAIL: '+str(error),file=sys.stderr);raise SystemExit(1)
