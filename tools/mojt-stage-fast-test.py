#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Pinned private-code stage test using the accepted installed F runtime.

Run once: prepare E with new code, then D using its warm payload. No System
package installation, menu selection, file replacement in F or reboot.
"""
import argparse
import ast
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile

REVISION='8b5c22b98f53587f79fbece136899b417343b3bb'
PROFILER_REVISION='1b825382610660fbfc2920b977963b7f7b454a57'
FILES={'mojt_artifact.py': '006dae0b917d61ade8b52f80510bf334334e70e8aa93be51f474f8073d289dc1', 'mpm_base.py': 'dd477271743b1771c9a0c28793c066d2e28f6d015dc7c1e39e84ecf4707a4403', 'mpm_boot_base.py': '359043d0b43ece16674feb0880921d150ebaaa2eb55aa2938bbf6d593f248428', 'mpm_boot_constructor.py': '6b716161948bca8644b019bb40457738def92f20af09f8ad814d0381ac5a076d', 'mpm_boot_handover.py': 'c6024b3ebd45a6b9f1c58523d94ecbfc0792b85909bc5efb1a84ea5699243d1c', 'mpm_boot_selection.py': '60b489bf69f08db42c03807c4953966bc9edde09f82fa6e2f9ecf936e667dac7', 'mpm_boot_update.py': '2cb3a95d5de05177047c8549d4daac12a40f40cbbf0b80f368960a9bb3305acc', 'mpm_boot_v2_store.py': 'd7ed98a995b68bd746a0141b16d27571dc629cec9e5c3d72098f5c4084c4545a', 'mpm_kernel.py': '888b5b20c3d44ddc6ec2d97307218da047986084da237dca89eeff63e1cb6f55', 'mpm_management.py': '55da4c44ac6e22540395e2ea1c0fa5017124b59124aff316ef174d53931abac4', 'mpm_native_io.py': '1473ada63fb3c35a5ad12e3aaf396384cb836359f1037df2497d1d4706136647', 'mpm_nix_boot.py': '6ac8c1c49d56edfc37d02973a7f23e32f1af246b619fd687324980d76a74dd96', 'mpm_system.py': 'a54c6277aa7d26bba998a45545035e89d556d94cb7cd3ec2c37604614f47c879', 'mpm_system_transition.py': 'b63a765492b69d13bd69af0f4d63d88f1f8109aa72b75b4c6fe47ea42afe7734'}
PROFILER_SHA256='4cbc8dc3315f49d21bd8c5d2220200b5d1747c051fadf05a8c2a9db8dfdba980'
ORIGIN='https://raw.githubusercontent.com/kjonasipersson-bert/mojt-linux/'
SYSTEM=Path('/run/mojt-system')
CHECKPOINT=Path('/var/lib/mojt/initramfs-payload-55')
WORK=Path('/var/lib/mojt/stage-fast-57')


def require(ok,message):
    if not ok:raise ValueError(message)


def protected(path):
    """Run before importing either the installed or delivered manager."""
    require(path==path.absolute()==path.resolve(),'linked/nonabsolute maintenance path: '+str(path))
    for parent in (path,*path.parents):
        if not parent.exists():continue
        info=parent.lstat()
        require(info.st_uid==0 and not info.st_mode & 0o022 or
                info.st_uid==0 and stat.S_ISDIR(info.st_mode) and info.st_mode & stat.S_ISVTX,
                'unprotected maintenance path: '+str(parent))


def read(path):
    protected(path);info=path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_size<=16*1024**2,'unsafe maintenance JSON')
    return json.loads(path.read_text())


def names(folder):
    protected(folder/'mojt_system.py')
    for node in ast.parse((folder/'mojt_system.py').read_text()).body:
        if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='MPM_FILES' for target in node.targets):
            value=ast.literal_eval(node.value)
            require(type(value) is tuple and 0<len(value)<256 and len(set(value))==len(value)
                    and all(type(name) is str and name not in ('.','..') and '/' not in name for name in value),'invalid installed code cohort')
            return value
    raise ValueError('installed manager lacks its closed file list')


def fetch(name,revision,expected,destination):
    subprocess.run([str(SYSTEM/'bin/curl'),'--fail','--show-error','--silent','--location',
        '--proto','=https','--proto-redir','=https','--connect-timeout','15','--max-time','180',
        '--max-filesize',str(4*1024**2),'--output',str(destination),ORIGIN+revision+'/tools/'+name],check=True)
    require(destination.stat().st_size<=4*1024**2 and hashlib.sha256(destination.read_bytes()).hexdigest()==expected,
            'download checksum differs: '+name)


def seal(folder,downloads,destination):
    """Publish a complete cohort after checking all reviewed replacements."""
    members=names(folder);require(set(downloads)==set(FILES) and set(FILES)<=set(members),'incomplete delivery inputs')
    require(not destination.exists(),'private code cohort already exists')
    for name,source in downloads.items():
        require(hashlib.sha256(source.read_bytes()).hexdigest()==FILES[name],'delivery checksum differs: '+name)
    with tempfile.TemporaryDirectory(prefix='.code-',dir=destination.parent) as temporary:
        private=Path(temporary);code=private/'tools';code.mkdir();hashes={}
        for name in members:
            source=downloads.get(name,folder/name);protected(source)
            require(stat.S_ISREG(source.lstat().st_mode),'nonregular source code: '+name)
            target=code/name;shutil.copyfile(source,target);target.chmod(0o444)
            hashes[name]=hashlib.sha256(target.read_bytes()).hexdigest()
            require(hashes[name]==hashlib.sha256(source.read_bytes()).hexdigest(),'source changed while copying: '+name)
        for target in code.iterdir():
            with target.open('rb') as stream:os.fsync(stream.fileno())
        code.chmod(0o555)
        descriptor=os.open(code,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(descriptor)
        finally:os.close(descriptor)
        os.rename(code,destination)
        descriptor=os.open(destination.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(descriptor)
        finally:os.close(descriptor)
    return hashes


def check_bundle():
    state=read(WORK/'state.json');require(state['revision']==REVISION,'maintenance revision differs')
    folder=WORK/'code';members=names(folder)
    require(set(state['files'])==set(members)=={file.name for file in folder.iterdir()},'private cohort file list differs')
    for name,expected in state['files'].items():
        file=folder/name;protected(file)
        require(stat.S_ISREG(file.lstat().st_mode) and hashlib.sha256(file.read_bytes()).hexdigest()==expected,'private code changed: '+name)
    require(all(state['files'].get(name)==expected for name,expected in FILES.items()),'private replacements differ from delivery')
    profiler=WORK/'stage-profile.py';protected(profiler)
    require(hashlib.sha256(profiler.read_bytes()).hexdigest()==PROFILER_SHA256,'profiler checksum differs')
    return state


def installed_status():
    data=subprocess.check_output([str(SYSTEM/'bin/mpm'),'system','status','--json'],text=True)
    value=json.loads(data);saved=read(CHECKPOINT/'state.json')
    require(saved['format']=='mojt-initramfs-payload-test-55-v1','wrong E/F checkpoint')
    require(value['running']['state']==value['selected']['state']=='known'
            and value['running']['artifact']==value['selected']['artifact']==saved['probe']['artifact']
            and value['running']['deployment']==value['selected']['deployment'],
            'accepted F must be running and selected; resolve any pending boot choice first')
    return saved


def probe(label):
    state=check_bundle();installed_status()
    folder=WORK/'code';sys.path.insert(0,str(folder))
    spec=importlib.util.spec_from_file_location('reviewed_stage_profiler',WORK/'stage-profile.py')
    profiler=importlib.util.module_from_spec(spec);spec.loader.exec_module(profiler)
    from mpm_cli import Runtime
    runtime=Runtime();before=profiler.current(runtime);timings=profiler.Timings()
    destination=WORK/label;destination.mkdir(mode=0o700)
    command=['system','stage','--artifact',state[label],'-y','--json']
    print('+ mpm '+' '.join(command)+' (reviewed private launcher; installed F interpreter/runtime)',flush=True)
    report=dict(format=profiler.FORMAT,ok=False,returncode=None,command=command,artifact=state[label],
        revision=REVISION,profiler_revision=PROFILER_REVISION,tools=str(folder),interpreter=sys.executable,
        scope='private reviewed MPM stage using installed F; setup/imports/prompt excluded; observer overhead included')
    try:
        with (destination/'mpm-result.json').open('x') as output,(destination/'stage.log').open('x') as log, \
             redirect_stderr(profiler.Tee(sys.stderr,log)):
            report['returncode']=profiler.run_mpm(folder,command,timings,output)
        require(report['returncode']==0,'new MPM failed; preserve evidence and inspect status')
        report['result']=read(destination/'mpm-result.json')
        require(profiler.current(runtime)==before,'running deployment or boot menu changed')
        require(report['result']['changed'] and report['result']['deployment'] is not None,'stage was a no-op, not a complete sample')
        report['ok']=True
    finally:
        report.update(calls=timings.calls,phases=timings.phases,trees=timings.trees,processes=timings.processes)
        with (destination/'profile.json').open('x') as output:json.dump(report,output,indent=2,sort_keys=True)
        with (destination/'summary.txt').open('x') as output,redirect_stdout(profiler.Tee(sys.stdout,output)):profiler.summary(report)
    return 0


def validate_result(report,*,warm=None):
    require(report.get('ok') is True and report['returncode']==0 and report['result']['changed'],
            'incomplete stage sample; preserve the report and inspect status')
    require(report['result']['verification_requested'] is False,'unexpected full audit policy')
    require(not report['processes'].get('--verify-path',{}).get('calls',0),'normal stage ran a full Nix path audit')
    payload=report['result']['initramfs_payload']
    require(payload['reused'] is (warm is not None),'unexpected cold/warm payload state')
    if warm is not None:require(payload['inputs']==warm['inputs'],'warm stage used a different payload')
    return payload


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe',choices=('cold','warm'),help=argparse.SUPPRESS)
    args=parser.parse_args(argv)
    require(os.geteuid()==0 and os.path.ismount(SYSTEM) and os.path.ismount('/run/mojt-disk'),'run as root on the installed Mojt SSD')
    python=(SYSTEM/'bin/python3').resolve(strict=True)
    require(python.is_file() and python.stat().st_uid==0 and not python.stat().st_mode & 0o022,'unprotected installed Python')
    if Path(sys.executable).resolve()!=python or not sys.flags.isolated or not sys.dont_write_bytecode:
        os.execv(str(python),[str(python),'-I','-B',str(Path(__file__).resolve()),*(sys.argv[1:] if argv is None else argv)])
    os.umask(0o077)
    if args.probe:return probe(args.probe)
    saved=installed_status();protected(WORK)
    require(not os.path.lexists(WORK),'test evidence already exists; preserve it and inspect status before retrying')
    print('New MPM code in a private reviewed bundle; installed F remains running and selected.',flush=True)
    print('Prepare retained E once, then retained D using the new warm payload. No reboot.',flush=True)
    require(input('Prepare the code bundle and run both measured stages? [y/N] ').strip().lower() in ('y','yes'),'cancelled')
    WORK.mkdir(mode=0o700);downloads=WORK/'downloads';downloads.mkdir()
    for name,expected in FILES.items():
        print('Downloading '+name+'...',flush=True);fetch(name,REVISION,expected,downloads/name)
    fetch('mojt-stage-profile.py',PROFILER_REVISION,PROFILER_SHA256,WORK/'stage-profile.py')
    for file in [*downloads.iterdir(),WORK/'stage-profile.py']:file.chmod(0o444)
    hashes=seal(SYSTEM/'tools',{name:downloads/name for name in FILES},WORK/'code')
    with (WORK/'state.json').open('x') as stream:
        json.dump(dict(revision=REVISION,files=hashes,cold=saved['candidate']['artifact'],warm=saved['origin']['artifact']),stream,sort_keys=True)
        stream.flush();os.fchmod(stream.fileno(),0o444);os.fsync(stream.fileno())
    previous=None
    for label in ('cold','warm'):
        print('\nMEASURE: '+label+' stage through the new private MPM launcher',flush=True)
        subprocess.run([str(python),'-I','-B',str(Path(__file__).resolve()),'--probe',label],check=True)
        report=read(WORK/label/'profile.json');previous=validate_result(report,warm=previous)
    installed_status()
    with (WORK/'summary.txt').open('x') as stream:
        for label in ('cold','warm'):
            stream.write(label.upper()+' STAGE\n'+(WORK/label/'summary.txt').read_text()+'\n')
    print('\nPASS: new ordinary stage; exact warm payload reused; zero Nix --verify-path calls; F running/selected.',flush=True)
    print('Send:',WORK/'summary.txt',flush=True)
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,KeyError,TypeError,EOFError,KeyboardInterrupt,subprocess.CalledProcessError) as error:
        print('Mojt stage fast test: '+str(error),file=sys.stderr);raise SystemExit(1)
