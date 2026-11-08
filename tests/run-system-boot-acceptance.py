#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""One owner native-v2 System A/B/A journey; construction runs only offline."""
import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path('/run/mojt-disk')
RUNTIME = Path('/run/mojt-system')
LAB = Path('/var/lib/mojt/system-boot-acceptance')
FORMAT = 'mojt-system-boot-acceptance-v1'


def require(ok,message):
    if not ok:raise ValueError(message)


def write(path,value):
    path.write_bytes(artifact.canonical(value)+b'\n')


def call(*args):
    result = subprocess.run([str(RUNTIME/'bin/mpm'),*args],text=True,capture_output=True)
    require(result.returncode == 0,result.stderr+result.stdout)
    return json.loads(result.stdout)


def checkpoint(path,value):
    temporary = path.with_name('.state-'+uuid.uuid4().hex)
    try:
        with temporary.open('xb') as stream:
            stream.write(artifact.canonical(value)+b'\n');stream.flush();os.fsync(stream.fileno())
        transaction.publish(temporary,path)
    finally:temporary.unlink(missing_ok=True)


def construct(base_id):
    """New-image test preparation only, not a live v1-to-v2 migration command."""
    require(not Path('/run/mojt/deployment.json').exists() and not Path('/run/mojt/native-v2.json').exists(),
            'construction is offline only; do not run in a booted Mojt VM')
    old_path = ROOT/'boot/mojt/system-v2-bootstrap'
    old_records = list(old_path.glob('*/deployment.json'))
    require(len(old_records) == 1,'one fresh bootstrap deployment required')
    old_record = base.read(old_records[0]);old = old_record['description']
    require(old['base']['artifact'] == base_id and not selection.present(ROOT),'unexpected Base or existing v2 authority')
    require(not (ROOT/'boot/mpm/format').exists(),'existing v1 managed installation is not an unpublished image')
    saved_lab = ROOT/'state'/LAB.relative_to('/')
    require(not saved_lab.exists(),'construction checkpoint exists; inspect the unpublished image')
    work = Path('/run/preparation/work');work.mkdir(mode=0o700)
    from mpm_nix_boot import NixBootAdapter
    sys.path.append('/run/preparation/tools')
    import mojt_system_package as packer
    import mojt_system as legacy
    import mojt_system_manifest as manifests
    import mpm_system as system
    import mpm_system_transition as transition
    import mpm_boot_constructor as constructor
    import mpm_boot_handover as handover
    import mpm_boot_v2 as model
    import mpm_deployment as deployment
    from mpm_request_plan import record
    adapter = NixBootAdapter(RUNTIME/'bin/nix-store');adapters = {'nix':adapter}
    # This fixed bootstrap operation loads the new disk's accepted registration;
    # no System setup script, package hook, evaluator or network build is run.
    with (RUNTIME/'registration').open('rb') as stream:
        subprocess.run([adapter.binary,'--load-db'],executable=adapter.executable,stdin=stream,check=True)
    base.install(ROOT,Path('/run/preparation/base.tar.zst'),base_id,yes=True)
    selected = manifests.validate(base.read(RUNTIME/'manifest.json'))
    require(selected['description']['label'] == 'system-v2-bootstrap','wrong bootstrap profile')
    manifest_inventory = copy.deepcopy(selected)
    before_menu = (ROOT/'boot/mojt/grub.cfg').read_bytes()
    python_output = selected['description']['artifacts']['nix']['packages']['python']['output']
    candidates = []
    for number,label in enumerate(('system-native-A','system-native-B'),1):
        print('Packaging and retaining '+label+' with unchanged startup dependencies...',flush=True)
        assembled = work/('assembled-'+str(number));profile = assembled/'system'/label
        profile.parent.mkdir(parents=True);shutil.copytree(RUNTIME,profile,symlinks=True)
        (profile/'version').write_text(label+'\n')
        (profile/'tools/native-system-acceptance.txt').write_text(label+'\n')
        d = copy.deepcopy(selected['description']);d['label'] = label;d['profile'] = system.inventory(profile)
        d['provenance'].update(acceptance_only=True,baseline_manifest=selected['id'])
        write(profile/'manifest.json',manifests.create(d))
        kit = work/('kit-'+str(number));packed = packer.package(assembled,label,'0.2.0',number,kit,adapter=adapter)
        generation = base.read(kit/'generation/archive.json');component = base.read(kit/'component/archive.json')
        identifier = packed['kit']['description']['generation']
        system.install(ROOT,kit/'generation'/generation['file'],identifier,
            dependency_files=[kit/'component'/component['file']],adapters=adapters,yes=True)
        candidates.append((label,identifier))
    refs = system.retained_providers(ROOT,candidates[0][1])
    ref = next(r for r in refs if r['provider'] == 'nix' and r['identity']['output'] == python_output)
    print('Freezing the explicitly accepted bootstrap Python closure...',flush=True)
    bundle = work/'python-runtime'
    runtime = constructor.freeze_runtime(ROOT,ref,python_output+'/bin/python3',bundle,adapters=adapters)
    bounds = base.read(old_records[0].parent/'base-context.json')
    body,receipt = base.object_record(ROOT,base_id)
    realized_base = base.realization(ROOT,base_id,receipt)
    kernel_body,unused = kernel.object_record(ROOT/'kernel/installed'/old['kernel']['artifact'][7:],old['kernel']['artifact'],verify=True)
    busybox = RUNTIME/'busybox';deployments = []
    for number,(label,identifier) in enumerate(candidates):
        print('Verifying and constructing '+label+' (complete closure scans can take a while)...',flush=True)
        plan = transition.prepare(ROOT,identifier,baseline=str(old_records[0].parent.relative_to(ROOT)),adapters=adapters)
        require(plan['description']['checks']['compatible'],str(plan['description']['checks']['errors']))
        realized = system.realization(ROOT,identifier)
        source = record(model.INPUTS,dict(installation=base.store_info(ROOT)['installation'],platform=old['platform'],layout='native-v2',
            base=dict(old['base'],rootfs_sha256=realized_base['description']['rootfs_sha256'],kernel_min=bounds['kernel_min'],
                      kernel_max=bounds['kernel_max'],bounds_evidence=artifact.digest(bounds)),
            system=dict(artifact=identifier,composition=realized['description']['composition'],manifest=realized['description']['manifest'],generation=label),
            kernel=dict(deployment.kernel_identity(kernel_body),upstream=kernel_body['version']['upstream']),
            firmware=[],boot=dict(root_uuid=old['boot']['root_uuid'],console='serial',profile=model.PROFILE,extra_args=['quiet']),
            constructor=constructor.constructor(runtime,busybox,handover=True),state_requirements=[],
            management_required=selection.MANAGEMENT_SUPPORT))
        contract = handover.prepare(ROOT,source,plan,adapters=adapters,
                                     tar=RUNTIME/'libexec/mpm/bin/tar')
        staged = selection.stage(ROOT,source,bundle,busybox,work/('construction-'+str(number)),
                                 bounds=bounds,adapters=adapters,contract=contract)
        deployments.append(dict(label=label,artifact=identifier,deployment=staged['deployment']))
    require((ROOT/'boot/mojt/grub.cfg').read_bytes() == before_menu,'staging changed the bootstrap menu')
    require(base.read(RUNTIME/'manifest.json') == manifest_inventory,'bootstrap profile changed')
    # This is the unpublished image's only initial authority switch, after both
    # complete constructors passed. The public launcher does not exist yet.
    hook = ROOT/'boot/mojt/grub.cfg';hook.chmod(0o644);hook.write_bytes(selection.HOOK);hook.chmod(0o444)
    with hook.open('rb') as stream:os.fsync(stream.fileno())
    selection.initialize(ROOT,deployments[0]['deployment'])
    saved_lab.mkdir(parents=True,mode=0o700)
    runner = saved_lab/'run.py';shutil.copyfile(Path(__file__),runner)
    checkpoint(saved_lab/'state.json',dict(format=FORMAT,phase='prepared',script_sha256=artifact.file_sha(runner),
        installation=base.store_info(ROOT)['installation'],base=old['base'],kernel=old['kernel'],systems=deployments))
    print('PASS: both exact native Systems admitted; initial A selected on the unpublished disk')


def boot_id():return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def retained():
    from mpm_ports_profile import current
    identities = {p:artifact.file_sha(Path(p)) for p in ('/etc/passwd','/etc/group','/etc/shadow','/etc/gshadow',
        '/etc/machine-id','/etc/timezone','/etc/localtime') if Path(p).is_file()}
    profile = current(Path('/var/lib/mojt/ports'))
    return dict(identities=identities,ports=profile['record']['id'] if profile else None)


def verify(value,index):
    from mpm_boot_status import read_running,description
    from mpm_cli import Runtime
    running = read_running(Runtime());require(running is not None,'missing exact v2 runtime record')
    d = description(running);expected = value['systems'][index]
    require(running['id'] == expected['deployment'] and d['system']['artifact'] == expected['artifact'],'wrong exact System deployment')
    require({k:d['base'][k] for k in value['base']} == value['base'] and
            {k:d['kernel'][k] for k in value['kernel']} == value['kernel'],'Base/Kernel changed')
    require(base.store_info(ROOT)['installation'] == value['installation'],'installation identity changed')
    status = call('system','status','--json')
    require(status['selected']['deployment'] == status['running']['deployment'] == running['id'],'System selected/running disagreement')
    require((RUNTIME/'tools/native-system-acceptance.txt').read_text() == expected['label']+'\n','wrong System payload')
    for name,fragment in (('/','/realizations/boot-base/'),('/run/mojt-system','/realizations/system/'+expected['artifact'][7:]+'/profile'),
                          ('/lib/modules','/kernel/installed/'+value['kernel']['artifact'][7:])):
        row = json.loads(subprocess.check_output(['findmnt','--json','-T',name,'-o','SOURCE,OPTIONS'],text=True))['filesystems']
        require(len(row) == 1 and fragment in row[0]['source'] and 'ro' in row[0]['options'].split(','),'wrong or writable mount: '+name)
    failed = subprocess.check_output(['systemctl','--failed','--no-legend','--no-pager'],text=True)
    require(not failed.strip(),'failed units: '+failed)
    if 'retained' in value:
        require(retained() == value['retained'],'account/machine/Ports state changed')
        for path,token in value['markers'].items():require(Path(path).read_text() == token+'\n','persistent marker missing: '+path)
        journal = subprocess.check_output(['journalctl','--boot='+value['initial_boot'].replace('-',''),
            '--identifier=mojt-system-acceptance','--output=cat','--no-pager'],text=True)
        require(value['journal_marker'] in journal.splitlines(),'journal from A was not retained')
        print('PASS: account/machine/Ports state, all four persistent mounts and A journal retained')
    print('PASS: exact '+expected['label']+' is running; selected/running IDs agree')
    print('PASS: Base/Kernel, read-only mounts and installation identity retained; no failed units')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('construct','baseline','select','check','rollback','check-old'))
    parser.add_argument('--base-artifact')
    args = parser.parse_args()
    require(os.geteuid() == 0 and os.path.ismount(ROOT),'root and the exact installation disk mount are required')
    sys.path.insert(0,str(RUNTIME/'tools'))
    global artifact,base,kernel,selection,transaction
    import mojt_artifact as artifact
    import mpm_base as base
    import mpm_kernel as kernel
    import mpm_boot_selection as selection
    import mpm_transaction as transaction
    os.environ['PATH'] = '/run/mojt-system/libexec/mpm/bin:/run/mojt-system/bin:/usr/bin:/bin'
    if args.action == 'construct':
        require(args.base_artifact is not None,'construction needs the exact Base');construct(args.base_artifact);return
    require(args.base_artifact is None,'Base argument is only for offline construction')
    with transaction.file_lock(LAB/'.acceptance-lock'):
        value = base.read(LAB/'state.json')
        require(value['format'] == FORMAT and value['script_sha256'] == artifact.file_sha(Path(__file__)),'checkpoint or test runner changed')
        if args.action == 'baseline':
            require(value['phase'] == 'prepared','baseline was already recorded; inspect its checkpoint')
            verify(value,0)
            token = 'system-boot-'+uuid.uuid4().hex
            markers = {p:token for p in ('/etc/mojt-system-acceptance','/var/lib/mojt/system-acceptance-marker',
                                       '/home/.mojt-system-acceptance','/root/.mojt-system-acceptance')}
            for name,content in markers.items():
                with Path(name).open('x') as stream:stream.write(content+'\n')
            subprocess.run(['systemd-cat','--identifier=mojt-system-acceptance'],input=token+'\n',text=True,check=True)
            value.update(phase='baseline',initial_boot=boot_id(),retained=retained(),markers=markers,journal_marker=token)
            print('PASS: A baseline and persistent-state checkpoint saved')
        elif args.action == 'select':
            require(value['phase'] == 'baseline','select requires the A baseline')
            request = ('system','select','--deployment',value['systems'][1]['deployment'],
                       '--expected-selected',value['systems'][0]['deployment'])
            preview = call(*request,'--dry-run');require(preview['dry_run'] and not preview['changed'],'invalid selection preview')
            call(*request,'-y')
            status = call('system','status','--json')
            require(status['running']['deployment'] == value['systems'][0]['deployment'] and
                    status['selected']['deployment'] == value['systems'][1]['deployment'] and
                    boot_id() == value['initial_boot'],'selection changed running identity')
            value['phase'] = 'selected'
            print('PASS: B selected through installed MPM; A is still running')
            print('READY: power off, restart the SAME VM, then run check')
        elif args.action == 'check':
            require(value['phase'] in ('selected','checked'),'check requires B selection')
            require(boot_id() != value['initial_boot'],'B requires a different real boot')
            verify(value,1);value.update(phase='checked',candidate_boot=boot_id())
        elif args.action == 'rollback':
            require(value['phase'] == 'checked','rollback requires accepted B')
            call('system','rollback','--expected-selected',value['systems'][1]['deployment'],'-y')
            value['phase'] = 'return-selected'
            print('READY: A selected through installed MPM; power off and restart the SAME VM, then run check-old')
        else:
            require(value['phase'] in ('return-selected','complete'),'check-old requires A return selection')
            require(boot_id() != value['candidate_boot'],'return requires a different real boot')
            verify(value,0);value['phase'] = 'complete'
            print('PASS: native-v2 System A/B/A boot and return acceptance')
        checkpoint(LAB/'state.json',value)


if __name__ == '__main__':
    try:main()
    except (OSError,ValueError,KeyError,StopIteration,subprocess.CalledProcessError) as error:
        print('System boot acceptance:',error,file=sys.stderr)
        print('Checkpoint and image retained; inspect the failed phase before retrying.',file=sys.stderr)
        sys.exit(1)
