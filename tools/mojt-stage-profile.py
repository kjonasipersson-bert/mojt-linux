#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Time the unchanged installed MPM stage path; retain content, never select.

Default: after the accepted E/F test, prepare E using running F and its warm
payload cache. No replacement manager, new System package or reboot is needed.
"""
import argparse
from contextlib import contextmanager, ExitStack, redirect_stdout, redirect_stderr
import functools
import hashlib
import importlib
import json
import os
from pathlib import Path
import resource
import runpy
import shlex
import stat
import sys
import time

FORMAT = 'mojt-stage-profile-v1'
SYSTEM = Path('/run/mojt-system')
CHECKPOINT = Path('/var/lib/mojt/initramfs-payload-55')
OUTPUT = Path('/var/lib/mojt/stage-profile')
AREAS = ('base','kernel','platform','boot','firmware','state_requirements')


def require(ok,message):
    if not ok:raise ValueError(message)


def clock():
    child = resource.getrusage(resource.RUSAGE_CHILDREN)
    return (time.perf_counter_ns(),time.process_time_ns(),round((child.ru_utime+child.ru_stime)*1e9))


class Timings:
    """Inclusive and own time for nested calls; never add inclusive totals."""
    def __init__(self):
        self.stack=[];self.calls={};self.phases=[];self.trees=[];self.processes={};self.sequence=0

    @contextmanager
    def observe(self,module,name,*,phase=False,tree=False):
        original=getattr(module,name)
        prefix=module.__module__+'.'+module.__name__ if isinstance(module,type) else module.__name__
        key=prefix+'.'+name
        @functools.wraps(original)
        def wrapped(*args,**kwargs):
            self.sequence+=1
            frame=dict(id=self.sequence,parent=self.stack[-1]['id'] if self.stack else None,
                       name=key,children=[0,0,0])
            if phase:print(getattr(self,'caption','Stage profile')+': '+key+'...',file=sys.stderr,flush=True)
            self.stack.append(frame);start=clock();ok=False;result=None
            try:
                result=original(*args,**kwargs);ok=True
                return result
            finally:
                elapsed=[max(0,end-begin) for end,begin in zip(clock(),start)]
                self.stack.pop()
                if self.stack:
                    for i,value in enumerate(elapsed):self.stack[-1]['children'][i]+=value
                own=[max(0,value-child) for value,child in zip(elapsed,frame['children'])]
                row=self.calls.setdefault(key,dict(calls=0,failed=0,wall_ns=0,python_cpu_ns=0,child_cpu_ns=0,
                                                   own_wall_ns=0,own_python_cpu_ns=0,own_child_cpu_ns=0))
                row['calls']+=1;row['failed']+=not ok
                metrics=dict(zip(('wall_ns','python_cpu_ns','child_cpu_ns'),elapsed))
                metrics.update(zip(('own_wall_ns','own_python_cpu_ns','own_child_cpu_ns'),own))
                for field,value in metrics.items():row[field]+=value
                if phase:
                    self.phases.append(dict(id=frame['id'],parent=frame['parent'],
                        caller=self.stack[-1]['name'] if self.stack else None,name=key,ok=ok,**metrics))
                    print((getattr(self,'caption','Stage profile')+': %.3f s wall / %.3f s CPU  %s%s') %
                          (elapsed[0]/1e9,(elapsed[1]+elapsed[2])/1e9,key,'' if ok else ' FAILED'),file=sys.stderr,flush=True)
                if tree:
                    detail=dict(parent=frame['parent'],caller=self.stack[-1]['name'] if self.stack else None,
                                operation=key,path=str(args[0]),ok=ok,**metrics)
                    if ok and name=='measure':detail.update(nodes=result['nodes'],content_bytes=result['content_bytes'])
                    self.trees.append(detail)
                if key=='mpm_nix_binary.NixBinaryAdapter._run':
                    command=args[1] if len(args)>1 else kwargs['args']
                    verb=' '.join(command[1:3] if command[1]=='--query' else command[1:2])
                    row=self.processes.setdefault(verb,dict(calls=0,wall_ns=0,python_cpu_ns=0,child_cpu_ns=0))
                    row['calls']+=1
                    for field,value in zip(('wall_ns','python_cpu_ns','child_cpu_ns'),elapsed):row[field]+=value
        setattr(module,name,wrapped)
        try:yield
        finally:setattr(module,name,original)


# Coarse phases plus the expensive nested work. No per-file/hash-byte observer.
PHASES = {
    'mpm_cli':('main',),
    'mpm_boot_update':('stage','prepare','runtime_reference','source_for'),
    'mpm_boot_constructor':('describe_runtime','freeze_runtime','build','_build_locked','capture','cached_payload','decode_modules'),
    'mpm_boot_handover':('prepare','prepare_locked'),
    'mpm_boot_selection':('stage','_stage_locked','_admit','_admit_locked'),
    'mpm_boot_v2_store':('retain','_retain_locked'),
}
DETAILS = {
    'mpm_system_transition':('_prepare','repeat','recheck','selected_context','providers','shells','tooling_review','defaults'),
    'mpm_boot_handover':('recheck_locked','check','validate'),
    'mpm_boot_v2_store':('audit_inputs','inspect','freeze'),
    'mpm_boot_base':('prepare_locked','inspect'),
    'mpm_boot_early':('verify_content',),
    'mpm_base':('object_record','realization'),
    'mpm_system':('object_record','realization','providers','verify_links'),
    'mpm_kernel':('object_record',),
    'mpm_management':('current','retained'),
    'mpm_native_io':('frozen_copy','sync_directory','clean_stage'),
    'mpm_kernel_boot':('write_initramfs',),
    'mojt_native_image':('inspect_initramfs',),
    'mojt_artifact':('canonical','file_sha'),
    'gzip':('compress',),
}


def installed_tools():
    folder=SYSTEM/'tools'
    require(folder==folder.resolve() and folder.is_dir(),'installed System tools unavailable')
    for path in (folder,folder/'mpm-system',*folder.glob('*.py')):
        info=path.lstat()
        require(info.st_uid==0 and not info.st_mode & 0o022 and not stat.S_ISLNK(info.st_mode),
                'unprotected installed tools: '+str(path))
        require(stat.S_ISDIR(info.st_mode) if path==folder else stat.S_ISREG(info.st_mode),
                'unexpected installed tool type: '+str(path))
    return folder


def run_mpm(folder,command,timings,output):
    """Run the real installed launcher with unchanged argv/defaults in this process."""
    previous_argv=sys.argv;previous_path=sys.path[:]
    try:
        with ExitStack() as stack:
            for table,is_phase in ((PHASES,True),(DETAILS,False)):
                for module,names in table.items():
                    loaded=importlib.import_module(module)
                    for name in names:stack.enter_context(timings.observe(loaded,name,phase=is_phase))
            inventory=importlib.import_module('mpm_boot_inventory')
            for name in ('measure','snapshot','clone_runtime'):
                stack.enter_context(timings.observe(inventory,name,tree=name!='clone_runtime'))
            adapter=importlib.import_module('mpm_nix_binary').NixBinaryAdapter
            for name in ('verify','_run'):
                stack.enter_context(timings.observe(adapter,name))
            sys.argv=[str(folder/'mpm-system'),*command]
            with redirect_stdout(output):
                try:runpy.run_path(str(folder/'mpm-system'),run_name='__main__')
                except SystemExit as error:return error.code if isinstance(error.code,int) else 0 if error.code is None else 1
            return 0
    finally:
        sys.argv=previous_argv;sys.path[:]=previous_path


class Tee:
    def __init__(self,*streams):self.streams=streams
    def write(self,text):
        for stream in self.streams:stream.write(text)
        return len(text)
    def flush(self):
        for stream in self.streams:stream.flush()


def summary(report):
    print('MPM exit:',report['returncode'])
    print('Seconds: wall / total CPU (Python + completed child processes)')
    total=report['calls'].get('mpm_cli.main')
    if total:print('Total CPU: %.3f s Python + %.3f s children' % (total['python_cpu_ns']/1e9,total['child_cpu_ns']/1e9))
    print('Phases include nested work; DO NOT add their totals:')
    for row in sorted(report['phases'],key=lambda row:row['id']):
        print('%8.3f / %8.3f  %s%s' % (row['wall_ns']/1e9,(row['python_cpu_ns']+row['child_cpu_ns'])/1e9,
                                             row['name'],'' if row['ok'] else ' FAILED'))
    print('\nLargest own times (observed children subtracted; includes unobserved work/waits):')
    for name,row in sorted(report['calls'].items(),key=lambda item:item[1]['own_wall_ns'],reverse=True)[:12]:
        print('%8.3f / %8.3f  %5d calls  %s' % (row['own_wall_ns']/1e9,
              (row['own_python_cpu_ns']+row['own_child_cpu_ns'])/1e9,row['calls'],name))
    print('\nSlowest tree scans (overlap with the phases above):')
    for row in sorted(report['trees'],key=lambda row:row['wall_ns'],reverse=True)[:8]:
        print('%8.3f s  %s  %s' % (row['wall_ns']/1e9,row['operation'],row['path']))
    if report['processes']:
        print('\nNix subprocesses (already included above; not additional time):')
        for name,row in sorted(report['processes'].items(),key=lambda item:item[1]['wall_ns'],reverse=True):
            print('%8.3f / %8.3f  %5d calls  %s' %
                  (row['wall_ns']/1e9,(row['python_cpu_ns']+row['child_cpu_ns'])/1e9,row['calls'],name))


def current(runtime):
    import mpm_boot_selection as selection
    from mpm_boot_status import read_running
    value,entries,raw=selection.current(runtime.disk)
    running=read_running(runtime)
    require(value is not None and running is not None,'exact running and selected native-v2 deployment required')
    chosen=value['description']['selected']
    require(running['id']==chosen,'resolve pending boot selection first')
    return dict(menu=raw,running=running,inputs=entries[chosen]['record']['description']['inputs']['description'])


def candidate(before,explicit):
    import mpm_base as base
    import mpm_boot_v2 as model
    import mpm_transaction as tx
    if explicit is not None:return model.identity(explicit),None
    tx.protected_directory(CHECKPOINT,label='E/F test checkpoint')
    saved=base.read(CHECKPOINT/'state.json');warm=base.read(CHECKPOINT/'stage-result.json')
    require(saved['format']=='mojt-initramfs-payload-test-55-v1'
            and before['inputs']['system']['artifact']==saved['probe']['artifact'],
            'default probe requires the accepted F running; otherwise specify --artifact')
    require(all(before['inputs'][key]==saved['baseline']['preserved'][key] for key in AREAS),
            'Base/Kernel/boot context differs from the E/F test')
    require(warm['changed'] and warm['initramfs_payload']['reused'] is True,'missing accepted warm F result')
    return model.identity(saved['candidate']['artifact']),warm['initramfs_payload']['inputs']


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact',help='optional exact installed System; default is E from the accepted E/F checkpoint')
    parser.add_argument('--output',type=Path,default=OUTPUT,help='new evidence directory; never overwrite previous results')
    parser.add_argument('-y','--yes',action='store_true')
    args=parser.parse_args(argv)
    require(os.geteuid()==0 and os.path.ismount(SYSTEM) and os.path.ismount('/run/mojt-disk'),
            'run as root on installed Mojt, not Debian or installer media')
    folder=installed_tools()
    python=(SYSTEM/'bin/python3').resolve(strict=True)
    require(python.is_file() and python.stat().st_uid==0 and not python.stat().st_mode & 0o022,'unprotected installed Python')
    if Path(sys.executable).resolve()!=python or not sys.flags.isolated or not sys.dont_write_bytecode:
        os.execv(str(python),[str(python),'-I','-B',str(Path(__file__).resolve()),*(sys.argv[1:] if argv is None else argv)])
    sys.path.insert(0,str(folder))
    from mpm_cli import Runtime
    import mpm_transaction as tx
    runtime=Runtime();before=current(runtime);identifier,expected_payload=candidate(before,args.artifact)
    require(identifier!=before['inputs']['system']['artifact'],'choose another System to measure preparation')
    work=tx.protected_directory(args.output,write=True,label='stage profile evidence')
    require(not os.path.lexists(work),'evidence already exists; inspect it and MPM status before choosing a new output directory')
    command=['system','stage','--artifact',identifier,'-y','--json']
    print('+ '+shlex.join(['mpm',*command])+' (installed launcher, observed in this process)',flush=True)
    print('This retains a prepared deployment. Running System and next boot stay unchanged.',flush=True)
    if not args.yes:require(input('Run one measured stage? [y/N] ').strip().lower() in ('y','yes'),'cancelled')
    work.mkdir(mode=0o700);timings=Timings();code=None
    report=dict(format=FORMAT,ok=False,command=command,artifact=identifier,selected_before=before['running']['id'],
        tools=str(folder),interpreter=str(python),script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='installed stage only; setup/imports/prompt/summary excluded; observers add overhead')
    try:
        with (work/'mpm-result.json').open('x') as output,(work/'stage.log').open('x') as log,redirect_stderr(Tee(sys.stderr,log)):
            code=run_mpm(folder,command,timings,output)
        report['returncode']=code
        require(code==0,'MPM failed; keep evidence and inspect status')
        require((work/'mpm-result.json').stat().st_size<=16*1024**2,'MPM JSON result exceeds limit')
        result=json.loads((work/'mpm-result.json').read_text());report['result']=result
        after=current(runtime)
        require(after==before,'running deployment or next-boot selection changed during measurement')
        require(result['changed'] and result['deployment'] is not None,'stage was a no-op; this is not a complete preparation sample')
        if expected_payload is not None:
            require(result['initramfs_payload']==dict(inputs=expected_payload,reused=True),
                    'expected the accepted warm payload; inspect evidence before interpreting this comparison')
        report['ok']=True
    finally:
        report.update(returncode=code,calls=timings.calls,phases=timings.phases,trees=timings.trees,processes=timings.processes)
        with (work/'profile.json').open('x') as output:json.dump(report,output,indent=2,sort_keys=True);output.write('\n')
        with (work/'summary.txt').open('x') as output,redirect_stdout(Tee(sys.stdout,output)):summary(report)
        print('Evidence:',work,flush=True)
    print('PASS: complete stage; running System and next boot unchanged.',flush=True)
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,KeyError,TypeError,EOFError,KeyboardInterrupt) as error:
        print('Mojt stage profile: '+str(error),file=sys.stderr);raise SystemExit(1)
