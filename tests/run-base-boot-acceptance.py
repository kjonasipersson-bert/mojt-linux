#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Owner-only disposable native VM: changed Base, same System/Kernel, then return."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

ROOT=Path('/run/mojt-disk')
RUNTIME=Path('/run/mojt-system')
LAB=Path('/var/lib/mojt/base-boot-acceptance')
FORMAT='mojt-base-boot-acceptance-v1'
MARKER=Path('/usr/lib/mojt-base-acceptance')


def require(ok,message):
    if not ok:raise ValueError(message)


def call(*args):
    result=subprocess.run([str(RUNTIME/'bin/mpm'),*args],text=True,capture_output=True)
    require(result.returncode==0,result.stderr+result.stdout)
    return json.loads(result.stdout)


def boot_id():return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def replace_field(text,section,key,value):
    # Acceptance fixture transformation only, not a general TOML serializer.
    pattern=r'(?ms)(^\['+re.escape(section)+r'\][^\n]*\n)(.*?)(?=^\[|\Z)'
    matches=list(re.finditer(pattern,text));require(len(matches)==1,'ambiguous release section: '+section)
    match=matches[0]
    body,count=re.subn(r'(?m)^'+re.escape(key)+r'\s*=.*$',key+' = '+json.dumps(value),match.group(2))
    require(count==1,'ambiguous release field: '+section+'.'+key)
    return text[:match.start(2)]+body+text[match.end(2):]


def runtime_record():
    record=deployment.read_json(Path('/run/mojt/deployment.json'))
    d=deployment.validate_deployment(record)
    require(d['kernel']['release']==os.uname().release,'running Kernel release differs from record')
    require(Path('/run/mojt/native-kernel-artifact').read_text().strip()==d['kernel']['artifact'],'native Kernel identity differs')
    return record


def retained_state():
    identities={str(p):artifact.file_sha(p) for p in map(Path,('/etc/passwd','/etc/group','/etc/shadow','/etc/gshadow',
        '/etc/machine-id','/etc/timezone','/etc/localtime')) if p.is_file()}
    profile=ports.current(Path('/var/lib/mojt/ports'))
    command=Path('/var/lib/mojt/ports/current/bin/hello')
    hello=str(command) if command.is_file() else None
    if hello:
        subprocess.run([hello],check=True)
        hello=str(Path(hello).resolve())
    return dict(identities=identities,ports=profile['record']['id'] if profile else None,hello=hello)


def checkpoint(value):
    path=LAB/('.state-'+uuid.uuid4().hex)
    try:
        kernel.write_json(path,value);transaction.publish(path,LAB/'state.json')
    finally:path.unlink(missing_ok=True)


def prepare():
    require(not os.path.lexists(LAB),'acceptance lab exists; inspect its checkpoint rather than replacing it')
    running=runtime_record();d=running['description']
    require(not os.path.lexists(MARKER),'acceptance marker already exists in baseline Base')
    status=call('base','status','--json')
    require(status['selected']['deployment']==running['id'] and status['running_is_selected'],
            'initial selected and running deployments must agree')
    state,entries,_=boot.current(ROOT,'boot/mojt/'+d['system']['generation']+'/'+d['base']['release'])
    entry=entries[state['selected']]
    _,_,receipt=boot.live_context(ROOT,entry)
    require(receipt['format']==native.INPUTS_FORMAT,'start this acceptance from a fresh native image, not a previous Base test')
    manager.management(ROOT/'system'/d['system']['generation'])
    original=ROOT/'base'/d['base']['release']
    before=native.base_inventory(original)
    LAB.mkdir(mode=0o700)
    tar=str(RUNTIME/'libexec/mpm/bin/tar')
    tree=LAB/'candidate-tree';tree.mkdir()
    archive=LAB/'baseline.tar'
    flags=[tar,'--numeric-owner','--acls','--xattrs','--xattrs-include=*']
    print('Copying and verifying the existing Base for a disposable test release...',flush=True)
    subprocess.run([*flags,'-cf',str(archive),'-C',str(original),'.'],check=True)
    base.extractor()['audit_tar'](archive)
    subprocess.run([*flags,'--same-owner','--same-permissions','-xf',str(archive),'-C',str(tree)],check=True)
    require(native.base_inventory(tree)==before,'test copy differs from original Base')
    release=d['base']['release']+'-boot-test'
    boot.boot.generation(release)
    osrel=tree/'usr/lib/os-release'
    require(osrel.is_file() and not osrel.is_symlink(),'regular candidate os-release required')
    text=osrel.read_text()
    for key in ('VERSION_ID','IMAGE_VERSION'):
        text,count=re.subn(r'(?m)^'+key+r'=.*$',key+'='+json.dumps(release),text)
        require(count==1,'missing/ambiguous Base identity: '+key)
    osrel.write_text(text)
    token='base-boot-'+uuid.uuid4().hex
    (tree/MARKER.relative_to('/')).write_text(token+'\n')
    payload=LAB/'release';payload.mkdir()
    raw=LAB/'candidate.tar'
    subprocess.run([*flags,'-cf',str(raw),'-C',str(tree),'.'],check=True)
    with (payload/'rootfs.tar.zst').open('xb') as stream:
        subprocess.run(['zstd','-q','-c','--',str(raw)],stdout=stream,check=True)
    manifest=(ROOT/'releases'/('base-'+d['base']['release']+'.toml')).read_text()
    manifest=re.sub(r'(?ms)^\[build\][^\n]*\n.*?(?=^\[|\Z)','',manifest)
    manifest += '\n[build]\nbackend = \"acceptance-base-copy\"\n'
    manifest=replace_field(manifest,'base','version',release)
    manifest=replace_field(manifest,'image','sha256',artifact.file_sha(payload/'rootfs.tar.zst'))
    (payload/'manifest.toml').write_text(manifest)
    spec,attachments=artifact.base_input(payload,1)
    spec['provenance'].update(acceptance_only=True,baseline_deployment=running['id'],source_base=d['base']['artifact'])
    package=artifact.pack(payload,spec,LAB/'package',attachments)
    candidate=package['artifact'];candidate_archive=LAB/'package'/package['archive']['file']
    request=('base','install','--from-file',str(candidate_archive),'--expected-id',candidate['id'])
    require(call(*request,'--dry-run')['dry_run'],'installation preview missing')
    require(call(*request,'-y')['changed'],'expected a newly installed Base')
    require(not call(*request,'-y')['changed'],'installation repeat changed content')
    kernel_body,_=kernel.object_record(ROOT/'kernel/installed'/kernel.identifier(d['kernel']['artifact']),d['kernel']['artifact'],verify=True)
    # A deliberately narrow acceptance declaration, never general published policy.
    bounds=dict(format=catalog.BASE_FORMAT,base=dict(artifact=candidate['id'],release=release),platform=d['platform'],
        kernel_min=kernel_body['version']['upstream'],kernel_max=kernel_body['version']['upstream'])
    kernel.write_json(LAB/'bounds.json',bounds)
    markers={str(p):token for p in map(Path,('/etc/mojt-base-acceptance','/var/lib/mojt/base-acceptance-marker',
                                             '/home/.mojt-base-acceptance','/root/.mojt-base-acceptance'))}
    for name,content in markers.items():
        with Path(name).open('x') as stream:stream.write(content+'\n')
    require(native.base_inventory(original)==before,'original Base changed during test preparation')
    require(call('base','status','--json')['selected']['deployment']==running['id'],'installation changed next boot')
    checkpoint(dict(format=FORMAT,script_sha256=artifact.file_sha(Path(__file__)),phase='prepared',old=running,
        initial_boot=boot_id(),new_base=candidate['id'],new_release=release,token=token,markers=markers,
        retained_state=retained_state()))
    print('PASS: distinct test Base installed; original Base/System/Kernel and next boot retained')
    print('Candidate:',candidate['id'])


def verify(value,old=False):
    running=runtime_record();status=call('base','status','--json');d=running['description']
    require(boot_id()!=value['initial_boot'],'a real different boot is required')
    expected=value['old']['id'] if old else value['new_deployment']
    require(running['id']==expected and status['selected']['deployment']==expected and status['running_is_selected'],
            'selected/running exact deployment IDs differ')
    require(all(d[k]==value['old']['description'][k] for k in ('kernel','system','platform')),'Base test changed System/Kernel')
    require(retained_state()==value['retained_state'],'account/machine/Ports/runtime state differs')
    for name,content in value['markers'].items():require(Path(name).read_text()==content+'\n','persistent marker missing: '+name)
    if old:
        require(not MARKER.exists(),'test Base marker remains after return')
    else:
        require(d['base']['artifact']==value['new_base'] and d['base']['release']==value['new_release'],'wrong candidate Base')
        require(MARKER.read_text()==value['token']+'\n','new Base content marker missing')
        mount=json.loads(subprocess.check_output(['findmnt','--json','-T','/','-o','SOURCE,OPTIONS'],text=True))['filesystems']
        require(len(mount)==1 and value['slot']+'/tree/rootfs' in mount[0]['source'] and
                'ro' in mount[0]['options'].split(','),'wrong or writable Base root')
    modules=json.loads(subprocess.check_output(['findmnt','--json','-T','/lib/modules','-o','SOURCE,OPTIONS'],text=True))['filesystems']
    require(len(modules)==1 and '/kernel/installed/'+kernel.identifier(d['kernel']['artifact']) in modules[0]['source'] and
            'ro' in modules[0]['options'].split(','),'wrong or writable native module tree')
    failed=subprocess.check_output(['systemctl','--failed','--no-legend','--no-pager'],text=True)
    require(not failed.strip(),'failed units: '+failed)
    print('PASS: '+('previous exact Base deployment restored' if old else 'changed exact Base deployment is running read-only'))
    print('PASS: exact System/Kernel, identities, account data, state markers and Ports baseline retained')
    print('PASS: read-only native modules, selected/running agreement and no failed units')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','stage','select','check','rollback','check-old'))
    args=parser.parse_args()
    require(os.geteuid()==0 and os.path.ismount(ROOT),'run as root in a disposable fresh native Mojt VM')
    require((RUNTIME/'tools/mpm_base_boot.py').is_file(),'updated delivered System MPM is required')
    sys.path.insert(0,str(RUNTIME/'tools'))
    global artifact,base,boot,manager,native,kernel,deployment,transaction,catalog,ports
    import mojt_artifact as artifact
    import mpm_base as base
    import mpm_kernel_boot as boot
    import mpm_base_boot as manager
    import mojt_native_image as native
    import mpm_kernel as kernel
    import mpm_deployment as deployment
    import mpm_transaction as transaction
    import mpm_catalog as catalog
    import mpm_ports_profile as ports
    from mpm_cli import Runtime
    runtime=Runtime();os.environ['PATH']=':'.join((str(runtime.helpers),str(runtime.system_bin),'/usr/bin','/bin'))
    if args.action=='prepare':prepare();return
    with transaction.file_lock(LAB/'.acceptance-lock'):
        value=deployment.read_json(LAB/'state.json')
        require(value['format']==FORMAT and value['script_sha256']==artifact.file_sha(Path(__file__)),'checkpoint/script differs')
        if args.action=='stage':
            require(value['phase']=='prepared','stage requires prepared candidate')
            menu=(ROOT/'boot/mojt/grub.cfg').read_bytes()
            command=('base','stage','--artifact',value['new_base'],'--base-context',str(LAB/'bounds.json'))
            print('Verifying and staging Base; retained System closure scans can take a while...',flush=True)
            call(*command,'--dry-run');result=call(*command,'-y');repeat=call(*command,'-y')
            require(not repeat['changed'] and repeat['deployment']==result['deployment'],'stage repeat differs')
            require((ROOT/'boot/mojt/grub.cfg').read_bytes()==menu,'staging changed next boot')
            value.update(phase='staged',new_deployment=result['deployment'],slot=result['slot'])
            print('PASS: changed Base staged; next boot unchanged; repeat is a no-op')
        elif args.action=='select':
            require(value['phase']=='staged','select requires staged candidate')
            command=('base','select','--deployment',value['new_deployment'],'--expected-selected',value['old']['id'])
            print('Rechecking both deployments and publishing the next-boot choice...',flush=True)
            call(*command,'--dry-run');call(*command,'-y')
            require(runtime_record()==value['old'] and boot_id()==value['initial_boot'],'selection changed running identity')
            status=call('base','status','--json')
            require(status['selected']['deployment']==value['new_deployment'] and not status['running_is_selected'],'next/running confused')
            value['phase']='selected'
            print('PASS: next Base selected; running deployment unchanged')
            print('READY: power off and restart the SAME VM disk, then run check')
        elif args.action=='check':
            require(value['phase'] in ('selected','checked'),'check requires candidate selection')
            verify(value);value.update(phase='checked',candidate_boot=boot_id())
        elif args.action=='rollback':
            require(value['phase']=='checked','rollback requires accepted candidate boot')
            call('base','rollback','--expected-selected',value['new_deployment'],'-y')
            value['phase']='return-selected'
            print('READY: previous Base selected; restart the SAME VM disk, then run check-old')
        else:
            require(value['phase'] in ('return-selected','complete'),'check-old requires return selection')
            require(boot_id()!=value['candidate_boot'],'return requires another real boot')
            verify(value,old=True);value['phase']='complete'
            print('PASS: changed-Base staging, selection, boot and return acceptance')
        checkpoint(value)


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,KeyError,subprocess.CalledProcessError) as error:
        print('Base boot acceptance:',error,file=sys.stderr)
        print('Data retained; inspect the existing VM checkpoint before retrying.',file=sys.stderr)
        sys.exit(1)
