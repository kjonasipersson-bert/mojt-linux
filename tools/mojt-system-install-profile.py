#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""One target-side install/preparation measurement; never select or reboot."""
import argparse
from collections import defaultdict
from contextlib import ExitStack, redirect_stdout, redirect_stderr
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
from unittest import mock

ROOT=Path('/run/mojt-disk')
RUNTIME=Path('/run/mojt-system')
WORK=Path('/var/lib/mojt/system-install-profile')
SUPPORT={'driver.py':'tools/mojt-system-install-profile.py','package.py':'tools/mojt_system_tooling.py',
         'profile.py':'tools/mojt-stage-profile.py','snapshot.py':'tools/mojt-system-firmware-test.py'}
FORMAT='mojt-system-install-profile-v1'


def require(ok,message):
    if not ok:raise ValueError(message)


def load(name,path):
    spec=importlib.util.spec_from_file_location('install_diagnostic_'+name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def protected(path):
    require(path == path.absolute() == path.resolve(),'linked diagnostic path: '+str(path))
    for point in (path,*path.parents):
        if not point.exists():continue
        info=point.lstat()
        require(info.st_uid == 0 and (not info.st_mode & 0o022 or stat.S_ISDIR(info.st_mode) and info.st_mode & stat.S_ISVTX),
                'unprotected diagnostic path: '+str(point))


def write(path,value):
    with path.open('xb') as stream:
        stream.write(json.dumps(value,sort_keys=True,indent=2).encode()+b'\n')
        os.fchmod(stream.fileno(),0o444);stream.flush();os.fsync(stream.fileno())


class IOCounts:
    """Python-process I/O only; provider/child fsyncs are not observed."""
    COARSE={'mpm_system._freeze','mpm_system.build_profile','mpm_system._retain','mpm_system.copy_profile','mpm_boot_update.stage'}
    def __init__(self,timings):self.timings=timings;self.rows=defaultdict(lambda:defaultdict(int))
    def row(self):
        name=next((f['name'] for f in reversed(self.timings.stack) if f['name'] in self.COARSE),'other')
        return self.rows[name]
    def observe(self,stack):
        import mpm_native_io as io
        copied=io.copy_regular;frozen=io.frozen_copy;unpack=io.unpack_regular;sync=os.fsync;rename=os.rename
        def copy_file(*args,**kwargs):
            result=copied(*args,**kwargs);row=self.row();row['copy_calls']+=1;row['copy_bytes']+=args[2];return result
        def freeze_file(*args,**kwargs):
            result=frozen(*args,**kwargs);row=self.row();row['frozen_calls']+=1;row['frozen_bytes']+=result[1];return result
        def extracted(*args,**kwargs):
            result=unpack(*args,**kwargs);row=self.row()
            row['unpacked_files']+=sum(r['type']=='file' for r in result['files'])
            row['unpacked_bytes']+=sum(r.get('size',0) for r in result['files']);return result
        def synced(fd):
            row=self.row();row['directory_fsync' if stat.S_ISDIR(os.fstat(fd).st_mode) else 'file_fsync']+=1
            start=time.perf_counter_ns()
            try:return sync(fd)
            except BaseException:row['fsync_failed']+=1;raise
            finally:row['fsync_wall_ns']+=time.perf_counter_ns()-start
        def moved(*args,**kwargs):
            try:result=rename(*args,**kwargs)
            except OSError as error:
                import errno
                if error.errno == errno.EXDEV:self.row()['cross_device_fallbacks']+=1
                raise
            self.row()['renames']+=1;return result
        for owner,name,value in ((io,'copy_regular',copy_file),(io,'frozen_copy',freeze_file),
                (io,'unpack_regular',extracted),(os,'fsync',synced),(os,'rename',moved)):
            stack.enter_context(mock.patch.object(owner,name,value))


def measure(folder,command,profiler,run):
    timings=profiler.Timings();timings.caption='Install profile';counts=IOCounts(timings)
    profiler.PHASES=dict(profiler.PHASES,mpm_system=('install','_freeze','build_profile','_retain','copy_profile'))
    started=profiler.clock()
    with (run/'mpm-result.json').open('x') as output,(run/'phases.log').open('x') as log,ExitStack() as stack:
        counts.observe(stack)
        with redirect_stderr(profiler.Tee(sys.stderr,log)):
            code=profiler.run_mpm(folder,command,timings,output)
    elapsed=[max(0,a-b) for a,b in zip(profiler.clock(),started)]
    try:result=json.loads((run/'mpm-result.json').read_text()) if (run/'mpm-result.json').stat().st_size else None
    except json.JSONDecodeError:result=None
    return dict(format=FORMAT,returncode=code,command=command,total=dict(zip(('wall_ns','python_cpu_ns','child_cpu_ns'),elapsed)),
        calls=timings.calls,phases=timings.phases,trees=timings.trees,processes=timings.processes,
        io={k:dict(v) for k,v in counts.rows.items()},result=result,
        scope='Public System install plus automatic boot preparation, using verified frozen checkout code. Interpreter startup, packaging and snapshot checks excluded; modules/content warmed by packaging. Python I/O counters exclude provider/child-process I/O.')


def child(run):
    protected(run)
    record=run/'context.json';require(record.stat().st_size <= 1024**2,'unbounded diagnostic context')
    saved=json.loads(record.read_text());require(saved['format'] == FORMAT,'unsupported diagnostic context')
    for name,digest in saved['support'].items():
        require(name in SUPPORT and hashlib.sha256((run/name).read_bytes()).hexdigest() == digest,'diagnostic support changed')
    require(set(saved['support']) == set(SUPPORT),'incomplete diagnostic support')
    code=Path(saved['code']);protected(code);sys.path.insert(0,str(code/'tools'));import mbt_runtime
    execution=mbt_runtime.verify(code);require(execution['id'] == saved['execution']['id'],'frozen diagnostic code changed')
    snapshot=load('snapshot',run/'snapshot.py');snapshot.unchanged(saved['baseline'])
    packager=load('package',run/'package.py');profiler=load('profile',run/'profile.py')
    data={name:mbt_runtime.read_file(code/name) for name in mbt_runtime.resources(code)}
    files={row['path']:row['sha256'] for row in execution['files']}
    print('Prepare a fresh tooling-only System package; packaging is outside the install measurement...',flush=True)
    started=time.monotonic()
    candidate=packager.package(ROOT,saved['baseline']['running'],data,run/'package',
        label='system-install-perf-'+run.name.removeprefix('run-'),expected_files=files,source_revision=execution['id'])
    write(run/'candidate.json',candidate);package_seconds=time.monotonic()-started
    snapshot.unchanged(saved['baseline'])
    command=['system','install','--from-file',str(run/'package'/candidate['generation']),
        '--expected-id',candidate['artifact'],'--dependency-file',str(run/'package'/candidate['component']),'-y','--json']
    print('Measure ordinary install and automatic boot preparation; next boot stays unchanged...',flush=True)
    report=measure(code/'tools',command,profiler,run)
    report.update(execution=execution,candidate=candidate,package_seconds=package_seconds,baseline=saved['baseline'])
    write(run/'profile.json',report)
    snapshot.unchanged(saved['baseline'])
    require(report['returncode'] == 0,'MPM failed; retain '+str(run)+' and inspect its reports')
    result=report['result']
    require(result and result.get('content_changed') is True and result.get('prepared') is True
        and result.get('preparation',{}).get('changed') is True
        and result.get('selection_changed') is False and result['artifact'] == candidate['artifact'],
        'incomplete/no-op measurement; preserve reports and inspect')
    with (run/'summary.txt').open('x') as summary,redirect_stdout(profiler.Tee(sys.stdout,summary)):
        print('TOTAL install + boot preparation: %.3f s wall / %.3f s CPU'%
            (report['total']['wall_ns']/1e9,(report['total']['python_cpu_ns']+report['total']['child_cpu_ns'])/1e9))
        print('Packaging (excluded): %.3f s'%package_seconds)
        print('Early-boot payload reused:',result['preparation']['initramfs_payload']['reused'])
        for name,row in sorted(report['io'].items()):
            print('%s: copy %d / %d bytes; unpacked %d files; file fsync %d; directory fsync %d; fsync %.3f s; moves %d; EXDEV %d'%
                (name,row.get('copy_calls',0),row.get('copy_bytes',0),row.get('unpacked_files',0),row.get('file_fsync',0),
                 row.get('directory_fsync',0),row.get('fsync_wall_ns',0)/1e9,row.get('renames',0),row.get('cross_device_fallbacks',0)))
        profiler.summary(report)
        print('PASS: fresh System installed and prepared; running/next boot and Base/Kernel preserved. Reports: '+str(run))
    return 0


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--child',type=Path,help=argparse.SUPPRESS)
    parser.add_argument('--samples',type=int,choices=(1,2),default=1,help='use two fresh installs to observe cold then warm boot-payload preparation')
    args=parser.parse_args(argv)
    require(os.geteuid() == 0 and os.path.ismount(ROOT) and os.path.ismount(RUNTIME),'run as root on installed native Mojt')
    if args.child is not None:
        require(args.samples == 1,'child execution accepts one frozen sample only')
        return child(args.child)
    for number in range(args.samples):
        print('Installation sample %d/%d'%(number+1,args.samples),flush=True)
        code=sample()
        if code:return code
    return 0


def sample():
    repo=Path(__file__).resolve().parents[1];sys.path.insert(0,str(repo/'tools'));import mbt_runtime
    protected(WORK);WORK.mkdir(mode=0o700,parents=True,exist_ok=True)
    run=Path(tempfile.mkdtemp(prefix='run-',dir=WORK));code=Path(tempfile.mkdtemp(prefix=mbt_runtime.PREFIX,dir=run))
    execution=mbt_runtime.freeze(repo,code);hashes={}
    for name,source in SUPPORT.items():
        data=mbt_runtime.read_file(repo/source);(run/name).write_bytes(data);(run/name).chmod(0o444)
        hashes[name]=hashlib.sha256(data).hexdigest()
    snapshot=load('snapshot',run/'snapshot.py');before=snapshot.snapshot()
    require(snapshot.mpm('system','status','--json')['running']['deployment'] == before['selected'],'resolve pending next boot first')
    write(run/'context.json',dict(format=FORMAT,baseline=before,code=str(code),execution=execution,support=hashes))
    (run/'tmp').mkdir(mode=0o700)
    environment={k:v for k,v in os.environ.items() if not k.startswith(('PYTHON','LD_'))}
    environment.update(PATH=str(RUNTIME/'libexec/mpm/bin')+':'+str(RUNTIME/'bin')+':/usr/sbin:/usr/bin:/sbin:/bin',TMPDIR=str(run/'tmp'))
    print('Evidence directory: '+str(run),flush=True)
    return subprocess.run([str(RUNTIME/'bin/python3'),'-I','-B',str(run/'driver.py'),'--child',str(run)],env=environment).returncode


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,KeyError,subprocess.CalledProcessError) as error:
        print('FAIL: '+str(error),file=sys.stderr);raise SystemExit(1)
