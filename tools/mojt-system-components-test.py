#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Build/install two component generations, then explicitly boot and return."""
import time
STARTED=time.monotonic()
import argparse
import builtins
from contextlib import ExitStack
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest import mock

ROOT=Path('/run/mojt-disk')
RUNTIME=Path('/run/mojt-system')
WORK=Path('/var/lib/mojt/system-components-test')
SUPPORT={'driver.py':'tools/mojt-system-components-test.py','measure.py':'tools/mojt-system-install-profile.py',
         'profile.py':'tools/mojt-stage-profile.py','snapshot.py':'tools/mojt-system-firmware-test.py'}
FORMAT='mojt-system-components-test-v1'


def require(ok,message):
    if not ok:raise ValueError(message)


def load(name,path):
    spec=importlib.util.spec_from_file_location('component_test_'+name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def save(path,value):
    with path.open('xb') as stream:
        stream.write(json.dumps(value,sort_keys=True,indent=2).encode()+b'\n')
        stream.flush();os.fchmod(stream.fileno(),0o444);os.fsync(stream.fileno())


def context(run):
    measure=load('measure',run/'measure.py');measure.protected(run)
    require((run/'context.json').stat().st_size <= 1024**2,'unbounded test context')
    saved=json.loads((run/'context.json').read_text());require(saved['format']==FORMAT,'unsupported component test context')
    require(set(saved['support'])==set(SUPPORT),'incomplete reviewed test support')
    for name,digest in saved['support'].items():
        require(hashlib.sha256((run/name).read_bytes()).hexdigest()==digest,'test support changed')
    code=Path(saved['code']);measure.protected(code);sys.path.insert(0,str(code/'tools'));import mbt_runtime
    require(mbt_runtime.verify(code)['id']==saved['execution']['id'],'reviewed code changed')
    return saved,code,measure,load('snapshot',run/'snapshot.py')


class FirmwareIO:
    """Refuse Python file access to retained firmware bytes and containing archives."""
    def __init__(self,roots,archives):self.roots=roots;self.archives=archives
    def check(self,path):
        if isinstance(path,int):return
        path=Path(os.fsdecode(path)).absolute()
        require(path not in self.archives and not any(path==r or r in path.parents for r in self.roots),
                'unchanged firmware data accessed: '+str(path))
    def observe(self,stack):
        path_open=Path.open;native_open=os.open;plain_open=builtins.open
        def opened(path,*args,**kwargs):self.check(path);return path_open(path,*args,**kwargs)
        def native(path,*args,**kwargs):self.check(path);return native_open(path,*args,**kwargs)
        def plain(path,*args,**kwargs):self.check(path);return plain_open(path,*args,**kwargs)
        stack.enter_context(mock.patch.object(Path,'open',opened));stack.enter_context(mock.patch.object(os,'open',native))
        stack.enter_context(mock.patch.object(builtins,'open',plain))


def prepare_child(run):
    saved,code,measure,snapshot=context(run)
    import mpm_base as base
    import mpm_system as system
    import mojt_system_package as package
    import mbt_runtime
    import mpm_base_transition as common
    state=common.state_inputs(ROOT)['evidence']
    marker=hashlib.sha256(os.urandom(32)).hexdigest();(run/'persistent-marker').write_text(marker)
    snapshot.unchanged(saved['baseline'])
    baseline=saved['baseline']['running'];profile=system.realization_path(ROOT,baseline)/'profile'
    old=base.read(profile/'manifest.json');composition,_=system.composition(system.object_path(ROOT,baseline),system.object_record(ROOT,baseline)[0])
    roots=[RUNTIME/'kernel/lib/firmware',RUNTIME/'kernel/licenses',Path('/lib/firmware')];archives=set()
    for name in ('kernel/lib/firmware','kernel/licenses'):
        row=next((r for r in composition['description']['profile'] if name==r['path'] or name.startswith(r['path']+'/')),None)
        if row is None:continue
        identifier=row['source']['reference']['artifact'];folder=system.object_path(ROOT,identifier)
        roots.extend([folder/'payload'/row['source']['path']/name[len(row['path']):].lstrip('/'),profile/name])
        archives.add(folder/'archive.tar.zst')
    guard=FirmwareIO(roots,archives)
    resources={name:mbt_runtime.read_file(code/name) for name in mbt_runtime.resources(code)}
    reports=[];baseline_for_build=baseline;first_firmware=None
    with ExitStack() as stack:
        guard.observe(stack)
        for number in (1,2):
            directory=run/('sample-'+str(number));directory.mkdir()
            label='system-components-'+run.name.removeprefix('run-')+'-'+str(number)
            print('Build Runtime and reference retained firmware: '+label,flush=True)
            started=time.monotonic()
            candidate=package.package_installed(ROOT,baseline_for_build,directory/'package',label=label,firmware='keep',resources=resources)
            build_seconds=time.monotonic()-started;save(directory/'candidate.json',candidate)
            command=['system','install','--from-file',str(directory/'package'/candidate['generation']),
                '--expected-id',candidate['artifact'],'-y','--json']
            for file in candidate['dependency_files']:command.extend(['--dependency-file',str(directory/'package'/file)])
            profiler=load('profile'+str(number),run/'profile.py')
            report=measure.measure(code/'tools',command,profiler,directory)
            report.update(candidate=candidate,build_seconds=build_seconds)
            save(directory/'profile.json',report)
            result=report['result']
            require(report['returncode']==0 and result and result.get('content_changed') is True and result.get('prepared') is True
                    and result.get('selection_changed') is False,'incomplete component installation; preserve '+str(run))
            if number==1:first_firmware=candidate['firmware']
            require(candidate['firmware']==first_firmware,'Runtime update changed the firmware reference')
            require(report['io'].get('mpm_system.build_profile',{}).get('copy_calls',0)==0,'thin profile copied component data')
            reports.append(report);baseline_for_build=candidate['artifact']
            print('BUILD %.3f s; INSTALL + PREPARE %.3f s; early-boot payload reused: %s'%
                (build_seconds,report['total']['wall_ns']/1e9,result['preparation']['initramfs_payload']['reused']),flush=True)
            for name,row in sorted(report['io'].items()):
                print('%s: copies %d; bytes %d; file fsync %d; directory fsync %d; EXDEV %d'%
                    (name,row.get('copy_calls',0),row.get('copy_bytes',0),row.get('file_fsync',0),row.get('directory_fsync',0),row.get('cross_device_fallbacks',0)))
            snapshot.unchanged(saved['baseline'])
    require(reports[1]['result']['preparation']['initramfs_payload']['reused'] is True,'second Runtime update rebuilt the unchanged heavy payload')
    require(common.state_inputs(ROOT)['evidence']==state,'persistent state changed during preparation')
    completed=dict(format=FORMAT,state=state,marker=marker,baseline=saved['baseline'],first=reports[0]['candidate'],candidate=reports[1]['candidate'],
        deployment=reports[1]['result']['preparation']['deployment'],firmware=first_firmware,
        firmware_data_accesses=0,build_seconds=sum(r['build_seconds'] for r in reports),
        install_seconds=sum(r['total']['wall_ns']/1e9 for r in reports))
    save(run/'completed.json',completed)
    print('PASS: two fresh component generations prepared; unchanged firmware never opened or repacked; zero profile file copies.',flush=True)
    print('Next: activate, reboot, after, back, reboot, check-back. Reports: '+str(run),flush=True)
    return 0


def current_run():
    pointer=WORK/'current';require(pointer.is_symlink(),'run prepare first')
    run=pointer.resolve();require(run.parent==WORK and run.name.startswith('run-'),'linked component test workspace')
    return run


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','activate','after','back','check-back'))
    parser.add_argument('--child',type=Path,help=argparse.SUPPRESS)
    args=parser.parse_args(argv)
    require(os.geteuid()==0 and os.path.ismount(ROOT) and os.path.ismount(RUNTIME),'run as root on native installed Mojt')
    if args.child is not None:
        require(args.action=='prepare','child execution only prepares packages')
        return prepare_child(args.child)
    if args.action=='prepare':
        repo=Path(__file__).resolve().parents[1];sys.path.insert(0,str(repo/'tools'));import mbt_runtime
        measure=load('measure',repo/SUPPORT['measure.py']);measure.protected(WORK);WORK.mkdir(mode=0o700,parents=True,exist_ok=True)
        run=Path(tempfile.mkdtemp(prefix='run-',dir=WORK));code=Path(tempfile.mkdtemp(prefix=mbt_runtime.PREFIX,dir=run))
        print('Component test workspace: '+str(run),flush=True)
        execution=mbt_runtime.freeze(repo,code);hashes={}
        for name,source in SUPPORT.items():
            data=mbt_runtime.read_file(repo/source);(run/name).write_bytes(data);(run/name).chmod(0o444)
            hashes[name]=hashlib.sha256(data).hexdigest()
        snapshot=load('snapshot',run/'snapshot.py');before=snapshot.snapshot()
        require(snapshot.mpm('system','status','--json')['running']['deployment']==before['selected'],'resolve pending next boot first')
        save(run/'context.json',dict(format=FORMAT,baseline=before,code=str(code),execution=execution,support=hashes))
        temporary=WORK/('.current-'+run.name);temporary.symlink_to(run.name);os.replace(temporary,WORK/'current')
        (run/'tmp').mkdir(mode=0o700)
        environment={k:v for k,v in os.environ.items() if not k.startswith(('PYTHON','LD_'))}
        environment.update(PATH=str(RUNTIME/'libexec/mpm/bin')+':'+str(RUNTIME/'bin')+':/usr/sbin:/usr/bin:/sbin:/bin',TMPDIR=str(run/'tmp'))
        result=subprocess.run([str(RUNTIME/'bin/python3'),'-I','-B',str(run/'driver.py'),'prepare','--child',str(run)],env=environment)
        elapsed=time.monotonic()-STARTED
        save(run/'command.json',dict(wall_seconds=elapsed,returncode=result.returncode,scope='Whole prepare command from script entry, including freezing, both builds, installs, preparation and status checks.'))
        print('WHOLE COMMAND: %.3f s wall (both builds/installations and all setup/checks included)'%elapsed,flush=True)
        return result.returncode
    run=current_run();saved,code,measure,snapshot=context(run)
    complete=json.loads((run/'completed.json').read_text());before=saved['baseline']
    import mpm_base_transition as common
    require(common.state_inputs(ROOT)['evidence']==complete['state'],'persistent state differs from the test baseline')
    require((run/'persistent-marker').read_text()==complete['marker'],'persistent marker was lost')
    selected=complete['deployment'];baseline=before['selected']
    if args.action=='activate':
        snapshot.unchanged(before)
        snapshot.mpm('system','select','--deployment',selected,'--expected-selected',baseline,'-y','--json')
        print('Selected component generation. Reboot deliberately, then run after.')
    elif args.action=='after':
        now=snapshot.snapshot();require(now['running']==complete['candidate']['artifact'] and now['selected']==selected,'boot the component generation first')
        for area in ('base','kernel','boot'):
            require(now[area]==before[area],'unrelated boot scope changed: '+area)
        subprocess.run([str(RUNTIME/'bin/mpm'),'system','status'],check=True)
        subprocess.run([str(RUNTIME/'bin/mbt'),'package','system','--help'],check=True)
        require((RUNTIME/'tools').is_symlink(),'running profile is not thin')
        require(complete['firmware'] is None or os.statvfs('/lib/firmware').f_flag & os.ST_RDONLY,'firmware is not read-only')
        print('PASS: component System running; MPM/MBT available; Base/Kernel/boot policy retained. Next: back, then reboot.')
    elif args.action=='back':
        now=snapshot.snapshot();require(now['running']==complete['candidate']['artifact'] and now['selected']==selected,'boot and check the component generation first')
        snapshot.mpm('system','select','--deployment',baseline,'--expected-selected',selected,'-y','--json')
        print('Selected original generation. Reboot deliberately, then run check-back.')
    else:
        snapshot.unchanged(before)
        print('PASS: original generation running/selected again with Base/Kernel/state preserved.')
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,KeyError,subprocess.CalledProcessError) as error:
        print('FAIL: '+str(error),file=sys.stderr);raise SystemExit(1)
