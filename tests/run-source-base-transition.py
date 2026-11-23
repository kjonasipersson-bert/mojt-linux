#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""One copied source Base VM: marked successor, reboot, original Base, reboot."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

INPUTS=Path('/mnt/mojt-base-transition')
LAB=Path('/var/lib/mojt/source-base-transition')
FORMAT='mojt-source-base-transition-test-v1'
RUNTIME=Path('/run/mojt-system')


def require(ok,message):
    if not ok:raise ValueError(message)


def call(*args):
    result=subprocess.run([str(RUNTIME/'bin/mpm'),*args,'--json'],text=True,stdout=subprocess.PIPE)
    require(result.returncode==0,'MPM operation failed: '+result.stdout)
    return json.loads(result.stdout)


def running():
    result=status.read_running(cli.Runtime())
    require(result is not None and result['format']==model.DEPLOYMENT,'running native-v2 record required')
    return result


def boot_id():return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def fingerprint():
    return {str(p):artifact.file_sha(p) for p in map(Path,('/etc/passwd','/etc/group','/etc/shadow',
        '/etc/gshadow','/etc/machine-id','/run/mojt-disk/state/rootfs/.mojt-root-layout.json')) if p.is_file()}


def checkpoint(state):
    path=LAB/('.state-'+uuid.uuid4().hex)
    try:
        io_native.write_json(path,state);transaction.publish(path,LAB/'state.json')
    finally:path.unlink(missing_ok=True)


def check(state,plan,*,candidate):
    current=running();d=status.description(current);old=status.description(state['original'])
    for name in ('installation','platform','system','kernel','boot','firmware','state_requirements'):
        require(d[name]==old[name],'preserved boot input changed: '+name)
    expected=state['candidate'] if candidate else old['base']['artifact']
    require(d['base']['artifact']==expected,'unexpected running Base')
    chosen=status.selected(cli.Runtime().disk,current)
    require(chosen['state']=='known' and chosen['record']['id']==current['id'],'running and next boot differ')
    require(fingerprint()==state['fingerprint'],'account/machine identity or root layout changed')
    for name in state['markers']:
        require(Path(name).read_text()==state['token'],'persistent marker changed: '+name)
    marker=Path(plan['marker'])
    require(marker.read_text()==plan['release']+'\n' if candidate else not os.path.lexists(marker),
            'Base content marker does not match the running generation')
    release=Path('/usr/lib/os-release').read_text()
    require('VERSION_ID="'+d['base']['release']+'"' in release,'visible Base release differs')
    require(subprocess.check_output(['/usr/bin/getconf','GNU_LIBC_VERSION'],text=True).strip()=='glibc 2.44',
            'expected our glibc 2.44 on both sides')
    subprocess.run([sys.executable,'-I','-B','-c',
        "import pwd,socket; pwd.getpwnam('root'); socket.getaddrinfo('localhost',None)"],check=True)
    subprocess.run([str(RUNTIME/'bin/mpm'),'system','status'],check=True)
    failed=subprocess.check_output([str(RUNTIME/'bin/systemctl'),'--failed','--no-legend','--no-pager'],text=True)
    require(not failed.strip(),'failed systemd units:\n'+failed)


def select(deployment,expected):
    before=running();boot=boot_id()
    call('base','select','--deployment',deployment,'--expected-selected',expected,'-y')
    require(running()==before and boot_id()==boot,'selection changed running identity')
    chosen=status.selected(cli.Runtime().disk,before)
    require(chosen['state']=='known' and chosen['record']['id']==deployment,'next boot was not selected')


def start(plan):
    require(not LAB.exists(),'test already started; preserve its checkpoint')
    current=running();old=status.description(current)
    require(current==plan['original'] and old['base']['release']=='0.2.0','start from the copied source Base 0.2.0 VM')
    require(not os.path.lexists(plan['marker']),'Base test marker already exists')
    archive=INPUTS/plan['archive']
    require(archive.resolve().is_relative_to(INPUTS) and artifact.file_sha(archive)==plan['archive_sha256'],
            'candidate archive differs')
    LAB.mkdir(mode=0o700);token=uuid.uuid4().hex
    markers=['/etc/mojt-base-transition-'+token,'/var/lib/mojt/base-transition-'+token]
    for name in markers:
        with Path(name).open('x') as stream:stream.write(token)
    state=dict(format=FORMAT,phase='started',original=current,candidate=plan['candidate'],token=token,
        markers=markers,fingerprint=fingerprint(),initial_boot=boot_id())
    checkpoint(state);check(state,plan,candidate=False)
    call('base','install','--from-file',str(archive),'--expected-id',plan['candidate'],'-y')
    bounds=dict(format=catalog.BASE_FORMAT,base=dict(artifact=plan['candidate'],release=plan['release']),
        platform=old['platform'],kernel_min=old['kernel']['upstream'],kernel_max=old['kernel']['upstream'])
    catalog.base_context(bounds);io_native.write_json(LAB/'bounds.json',bounds)
    staged=call('base','stage','--artifact',plan['candidate'],'--base-context',str(LAB/'bounds.json'),'-y')
    require(staged['selected']==current['id'] and running()==current,'installation/staging changed selection or running')
    check(state,plan,candidate=False)
    state.update(phase='staged',deployment=staged['deployment']);checkpoint(state)
    select(state['deployment'],current['id']);state['phase']='selected';checkpoint(state)
    print('PASS: marked Base prepared; only next boot changed. Reboot, then run: python3 /root/bt.py after')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('start','after','check-back'))
    args=parser.parse_args(argv);require(os.geteuid()==0,'run as root inside the disposable copied Mojt VM')
    if not os.path.ismount(INPUTS):
        INPUTS.mkdir(parents=True,exist_ok=True)
        subprocess.run(['mount','-o','ro','LABEL=MOJT_BASE_SWAP',str(INPUTS)],check=True)
    sys.path.insert(0,str(RUNTIME/'tools'))
    global cli,status,model,artifact,io_native,catalog,transaction
    import mpm_cli as cli, mpm_boot_status as status, mpm_boot_v2 as model
    import mojt_artifact as artifact, mpm_native_io as io_native, mpm_catalog as catalog, mpm_transaction as transaction
    plan=artifact.read_json(INPUTS/'plan.json')
    require(plan['format']=='mojt-source-base-transition-inputs-v1','unsupported input disk')
    if args.action=='start':start(plan);return
    require(LAB.is_dir(),'run start first')
    with transaction.file_lock(LAB/'.lock'):
        state=artifact.read_json(LAB/'state.json')
        require(state['format']==FORMAT and state['candidate']==plan['candidate']
                and state['original']==plan['original'],'test checkpoint/input disk differs')
        if args.action=='after':
            require(state['phase']=='selected' and boot_id()!=state['initial_boot'],'after requires a real candidate boot')
            check(state,plan,candidate=True)
            state['candidate_boot']=boot_id();checkpoint(state)
            select(state['original']['id'],state['deployment']);state['phase']='return-selected';checkpoint(state)
            print('PASS: marked Base running; same System/Kernel and state. Original Base now selected.')
            print('Reboot, then run: python3 /root/bt.py check-back')
        else:
            require(state['phase'] in ('return-selected','complete') and boot_id()!=state['candidate_boot'],
                    'check-back requires a real return boot')
            check(state,plan,candidate=False);state['phase']='complete';checkpoint(state)
            print('PASS: own Base switched in and out; System/Kernel and persistent state preserved.')


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,KeyError,TypeError,subprocess.CalledProcessError) as error:
        raise SystemExit('Source Base transition: '+str(error)+'\nCheckpoint retained; no automatic reboot or cleanup.')
