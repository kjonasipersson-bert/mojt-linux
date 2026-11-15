#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Pinned I/J usability and Ports manual test; no automatic reboot or in-place patch."""
import argparse
import copy
import shutil
import tempfile
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import runpy
import selectors
import stat
import subprocess
import sys

REVISION='8c3b4e1d5cd6c001aecad59a2a9efd76fdb82ebb'
DRIVER_SHA256='3edf37cfe8e574ffacb09afabe1fa766aed9f7e024a396adc5320c09f82aadfa'
FILES={'man/mpm.1': '6fc1a1264581660de503069ac58a299b565699c3ad5d30536c768c403826bb28', 'tools/mojt_system.py': '18c3c4b6e6eec19aa2eb71f9e4751f2e249f23ddb8fc9edd083207f229061e04', 'tools/mpm-nix-catalog.py': '7aae8a2b54eaf2a3492e7eeafc54bfe5cd35af2e20266235a6b0e4b6245c3d55', 'tools/mpm-nix-prototype': '3abd589bfee13d9a7b91f03f7a0502aadb7a9ddf90a817c93f1b029af533d4bd', 'tools/mpm_base_cli.py': '5d6e224f9d4f48f791f1e41a3983a083b2e27d8ea300b2452cc7115ad170c89b', 'tools/mpm_boot_constructor.py': 'a03d2284a1a3760e01c73f79826ab45496a65ebe22641eadab1a15b3c535117f', 'tools/mpm_boot_selection.py': 'ad4979e0cee61e890c677609785c6193077ecbc59ae9fbb4514a8ef5b9d233b2', 'tools/mpm_boot_update.py': '38db573b53b0d6ea35dc5e26c36ac4c86db588644b17570ae80631741054215b', 'tools/mpm_kernel_boot.py': 'da18db7fa1c05899243b33a747a21045625a09b8f23cc521b33401959e3782ec', 'tools/mpm_man.py': 'e524dfec92b424c41c479808f300506345dd9c6cb350b32e53b50f19b7a63f4f', 'tools/mpm_ports_cli.py': '1ff282885602437c7aeb9a278008301047c584a6b1be6db0989c7326df7889e7', 'tools/mpm_ports_nix_source.py': 'f97ba12c7f9c5044b405d65f68e3a5cd821bb6705d0b3f1cdbeca4b7a41d270f', 'tools/mpm_ports_profile.py': 'b5bf161ebfafaabec7e6c7f4c95f1b2c85653f6722770693d46bfe8cb6678ce6', 'tools/mpm_system.py': 'c73c190de7f554c18d18b568ff685b6b86abb06513858732f17b821436564452', 'tools/mpm_system_cli.py': 'b78523e0886cb94518745b427fc3c37e77add1a094f3188df805952e66142250', 'tools/mpm_system_transition.py': '25511c3d03affc587d7c45220823afcb83294852024dc9f952cf5e6c8c6a96d8', 'tools/mpm_ui.py': 'e2b46d9b7aa7dbd079e9a0eb70591bd87c5ca84c5ccc87a71f0350baa67c85c1'}
ROOT=Path('/run/mojt-disk')
RUNTIME=Path('/run/mojt-system')
WORK=Path('/var/lib/mojt/usability-61')
FORMAT='mojt-usability-test-61-v1'


def require(ok,message):
    if not ok:raise ValueError(message)


def protected(path):
    require(path==path.absolute()==path.resolve(),'linked maintenance path: '+str(path))
    for parent in (path,*path.parents):
        if not parent.exists():continue
        info=parent.lstat()
        require(info.st_uid==0 and (not info.st_mode & 0o022 or stat.S_ISDIR(info.st_mode) and info.st_mode & stat.S_ISVTX),
                'unprotected maintenance path: '+str(parent))


def plain(path):
    protected(path);info=path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_size<=16*1024**2,'unsafe maintenance JSON')
    return json.loads(path.read_text())


def cohort(folder):
    for node in ast.parse((folder/'mojt_system.py').read_text()).body:
        if isinstance(node,ast.Assign) and any(isinstance(n,ast.Name) and n.id=='MPM_FILES' for n in node.targets):
            names=ast.literal_eval(node.value)
            require(type(names) is tuple and 0<len(names)<256 and len(set(names))==len(names)
                    and all(type(n) is str and '/' not in n and n not in ('.','..') for n in names),'invalid closed MPM cohort')
            return names
    raise ValueError('missing closed MPM cohort')


def checked_state():
    state=plain(WORK/'state.json')
    require(state['format']==FORMAT and state['revision']==REVISION and state['files']==FILES
            and state['script']==hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'test checkpoint/script differs')
    return state


def private_stage():
    """A fresh isolated process imports only installed I's checked code cohort.

    Runtime/provider defaults still refer to running G/H. No installed file is
    replaced, and no already-imported old manager modules can leak into I.
    """
    state=checked_state();identifier=state['candidate']['artifact']
    require(re.fullmatch(r'sha256:[0-9a-f]{64}',identifier),'invalid candidate artifact')
    folder=ROOT/'realizations/system'/identifier[7:]/'profile/tools'
    names=cohort(folder);require(set(names)==set(state['code']),'private code cohort differs')
    for name,expected in state['code'].items():
        path=folder/name;protected(path)
        require(stat.S_ISREG(path.lstat().st_mode) and hashlib.sha256(path.read_bytes()).hexdigest()==expected,'candidate code changed: '+name)
    require(all(state['code'].get(name[6:])==digest for name,digest in FILES.items() if name.startswith('tools/')),'candidate replacements differ')
    sys.path.insert(0,str(folder));sys.argv=[str(folder/'mpm-system'),'system','stage','--artifact',identifier,'-y','--json']
    runpy.run_path(str(folder/'mpm-system'),run_name='__main__')


def driver():
    path=WORK/'package-driver.py';protected(path)
    require(hashlib.sha256(path.read_bytes()).hexdigest()==DRIVER_SHA256,'package driver checksum differs')
    spec=importlib.util.spec_from_file_location('root_test_package_driver',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.WORK=WORK;module.REVISION=REVISION;module.FILES=FILES
    module.ORIGIN='https://raw.githubusercontent.com/kjonasipersson-bert/mojt-linux/'+REVISION+'/'
    return module


def stage_i(bridge):
    command=[sys.executable,'-I','-B',str(Path(__file__).resolve()),'_stage']
    print('+ reviewed installed I launcher: mpm system stage --artifact '+checked_state()['candidate']['artifact']+' -y --json',flush=True)
    output=[];size=0
    with (WORK/'stage-I.log').open('xb') as log:
        with subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE) as child:
            try:
                with selectors.DefaultSelector() as events:
                    events.register(child.stdout,selectors.EVENT_READ,'stdout');events.register(child.stderr,selectors.EVENT_READ,'stderr')
                    while events.get_map():
                        for key,unused in events.select():
                            data=key.fileobj.read1(4096)
                            if not data:events.unregister(key.fileobj);continue
                            log.write(data);log.flush()
                            if key.data=='stdout':
                                size+=len(data);require(size<=16*1024**2,'stage JSON limit');output.append(data)
                            else:bridge.emit(data)
                code=child.wait()
            except BaseException:
                if child.poll() is None:child.terminate()
                child.wait();raise
        os.fsync(log.fileno())
    bridge.save('stage-I-command.json',dict(command=command,returncode=code,scope='installed I code, running G/H interpreter/runtime'))
    require(code==0,'private I stage failed; keep stage-I.log and inspect status')
    result=json.loads(b''.join(output));require(result['changed'] and result['deployment'],'I stage was not a fresh preparation')
    bridge.save('stage-I-result.json',result);return result['deployment']



def package(bridge, root, baseline, downloads, output, *, label, revision=1):
    """Copy and verify owned component bytes, never copy/evaluate the Nix store."""
    import mojt_artifact as artifact
    import mpm_base as base
    import mpm_management as management
    import mpm_system as system
    import mpm_system_model as model
    import mpm_system_transition as transition
    import mpm_transaction as tx
    import mojt_system_manifest as manifests
    require(set(downloads) == set(FILES) and all(hashlib.sha256(v).hexdigest() == FILES[k]
            for k,v in downloads.items()), 'delivery inputs differ from pinned data')
    body, unused = system.object_record(root, baseline)
    comp, actions = system.composition(system.object_path(root, baseline), body)
    d = copy.deepcopy(comp['description'])
    require(len(d['components']) == 1 and d['components'][0]['role'] == 'runtime',
            'delivery supports only the existing single-runtime System composition')
    old_ref = d['components'][0]['reference']
    require(all(row['source']['reference'] == old_ref and row['path'] == row['source']['path']
            and '/' not in row['path'] for row in d['profile']), 'unsupported runtime profile mapping')
    component, unused = system.object_record(root, old_ref['artifact'])
    require(all(r['path'] == 'payload' or r['path'].startswith('payload/') for r in component['files']),
            'component attachments need a separate packaging implementation')
    require(all(r['provider'] != 'native' for r in component['dependencies']), 'nested native dependencies unsupported')
    source = system.object_path(root, old_ref['artifact']) / 'payload'
    require(not output.exists(), 'prepared package directory already exists')
    version = {k:body['version'][k] for k in ('upstream', 'scheme', 'revision')}
    require(type(version['revision']) is int, 'delivery requires a numeric System package revision')
    version['revision'] += revision
    provenance = dict(source_revision=REVISION, files=FILES, baseline=baseline,
        baseline_component=old_ref['artifact'], bridge_sha256=artifact.file_sha(__file__))
    with tempfile.TemporaryDirectory(prefix='.package-', dir=output.parent) as temporary:
        work = Path(temporary); content = work / 'content'
        shutil.copytree(source, content, symlinks=True)
        # Read only owned System files once here; do not rescan provider closures.
        expected = copy.deepcopy(component['files'])
        for row in expected:
            if row['type'] != 'symlink': row['mode'] = system.stored_mode(row)
        require(artifact.inventory(content)[0] == expected, 'copied installed component differs from its descriptor')
        for path in [content, *content.rglob('*')]:
            if not path.is_symlink() and path.is_dir(): path.chmod(0o755)
        require((content / 'version').is_file() and not (content / 'version').is_symlink(),
                'installed runtime lacks a regular version marker')
        from mpm_man import wrapper
        for name in ('man','manpath'):
            target=content/'bin'/name
            require(target.is_symlink(),'expected original retained man-db link: '+name)
            program=os.readlink(target);data=wrapper(program).encode();target.unlink()
            bridge.write_data(target,data);target.chmod(0o555)
        for name, data in downloads.items():
            bridge.write_data(content / name, data)
        bridge.write_data(content / 'share/man/man1/mpm.1', downloads['man/mpm.1'])
        bridge.write_data(content / 'version', (label + '\n').encode())
        names = management.literal(content / 'tools/mojt_system.py', 'MPM_FILES')
        require(all((content / 'tools' / n).is_file() for n in names), 'incomplete candidate MPM')
        support = management.produce(content / 'tools', names)
        require(support['description']['state'] == d['state'], 'delivery cannot change state schemas')
        stage = work / 'kit'; stage.mkdir()
        part = artifact.pack(content, bridge.specification(component, version, provenance), stage / 'component', numeric_owner=(0, 0))
        new_ref = dict(provider='native', artifact=part['artifact']['id'])
        d['label'] = label; d['components'][0]['reference'] = new_ref
        for row in d['profile']: row['source']['reference'] = new_ref
        # The bootstrap composition maps whole top-level directories.
        mapped = {r['path'] for r in d['profile']}
        required = {p.split('/')[0] for p in downloads} | {'share', 'version'}
        for name in sorted(required - mapped):
            d['profile'].append(dict(path=name, source=dict(reference=new_ref, path=name)))
        d['profile'].sort(key=lambda r:r['path'])
        d['management'] = support['description']['management']
        old_manifest = base.read(system.realization_path(root, baseline) / 'profile/manifest.json')
        proposed = copy.deepcopy(old_manifest['description']); proposed['label'] = label
        roots = {r['path'] for r in d['profile']}
        proposed['profile'] = {p:r for p,r in system.inventory(content).items()
            if p.split('/')[0] in roots}
        review = transition.tooling_review(old_manifest, manifests.create(proposed))
        require(review['description']['compatible'],
                'delivery changes startup content: ' + ', '.join(review['description']['blockers']))
        composition = base.record(model.FORMAT, d); model.supported(composition, actions)
        gen = work / 'generation'; gen.mkdir()
        bridge.write_data(gen / 'composition.json', artifact.canonical(composition) + b'\n')
        bridge.write_data(gen / 'lifecycle.json', artifact.canonical(actions) + b'\n')
        spec = bridge.specification(body, version, provenance); spec['dependencies'] = [new_ref]
        spec['metadata']['composition']['id'] = composition['id']
        generation = artifact.pack(gen, spec, stage / 'generation', numeric_owner=(0, 0))
        # Publish only complete, independently verified native package archives.
        tx.publish(stage, output)
    return dict(artifact=generation['artifact']['id'], version=generation['artifact']['version']['release_id'],
        label=label, generation='generation/' + generation['archive']['file'],
        component='component/' + part['archive']['file'], providers_unchanged=True)


def code_cohort(downloads):
    """Pin a complete cohort before importing any new management code."""
    folder=WORK/'code';folder.mkdir(mode=0o700)
    # The NEW manifest includes new modules absent from the old runtime.
    (folder/'mojt_system.py').write_bytes(downloads['tools/mojt_system.py'])
    names=cohort(folder);code={}
    for name in names:
        key='tools/'+name
        data=downloads[key] if key in downloads else (RUNTIME/'tools'/name).read_bytes()
        (folder/name).write_bytes(data);(folder/name).chmod(0o444)
        code[name]=hashlib.sha256(data).hexdigest()
    require(all(code.get(name[6:])==digest for name,digest in FILES.items() if name.startswith('tools/')),'incomplete new code cohort')
    return folder,code


def install_probe(bridge,state):
    before=bridge.check(state,'candidate');bridge.tools_match()
    bridge.confirm('Install J with normal NEW System install, including boot preparation, leaving next boot unchanged?')
    result=bridge.run('install-J',*bridge.install_args(state['probe'],'probe'),before=before)['result']
    bridge.unchanged(before,bridge.snapshot())
    require(result.get('prepared') is True and result['preparation']['deployment'] and not result['selection_changed'],
            'normal install did not finish boot preparation')
    deployment=result['preparation']['deployment'];bridge.save('stage-J-result.json',dict(deployment=deployment))
    require(any(r['deployment']==deployment for r in bridge.snapshot()['status']['staged_deployments']),'prepared J absent from status')
    subprocess.run([str(RUNTIME/'bin/mpm'),'system','status'],check=True)
    print('PASS: normal install prepared J; running and next boot remain I. Next: manuals, then choose.')


def repair_manuals(bridge,state):
    bridge.check(state,'candidate');bridge.tools_match()
    import mpm_ports_profile as profiles
    root=Path('/var/lib/mojt/ports');old=profiles.current(root)
    require(old is not None,'install Ports before this test')
    before=old['record']['description']
    roles={'neovim','git','ncdu','mdbook'} & set(before['active'])
    claims=[c for c in before['requests']['description']['claims'] if c['role'] in roles]
    require(roles and all(any(c['role']==role and c['origin']['kind']=='interactive' and c['source']=='nixpkgs' for c in claims) for role in roles),
            'test requires existing interactive pinned-provider wishes for the active probe packages')
    selectors=sorted({c['policy']['selector'] for c in claims if c['origin']['kind']=='interactive' and c['source']=='nixpkgs'})
    bridge.confirm('Complete manuals for the existing wishes '+', '.join(selectors)+' without changing exact binaries or activation?')
    bridge.run('manuals-install','ports','install',*selectors,'-y')
    after=profiles.current(root)['record']['description']
    for name in ('active','requests'):require(after[name]==before[name],'manual repair changed '+name)
    for package in before['packages']:
        match=next(p for p in after['packages'] if p['reference']==package['reference'])
        for name in ('reference','release_id','commands','installed','activated'):
            require(package[name]==match[name],'manual repair changed accepted package '+name)
    bridge.save('manuals-expected.json',dict(active=after['active'],requests=after['requests'],roles=sorted(roles)))
    check_manuals(bridge)
    print('PASS: manual acquisition retained exact versions, wishes and active choices. No new login required.')


def check_manuals(bridge):
    import mpm_ports_profile as profiles
    expected=bridge.read('manuals-expected.json');d=profiles.current(Path('/var/lib/mojt/ports'))['record']['description']
    require(d['active']==expected['active'] and d['requests']==expected['requests'],'Ports choice changed')
    for role in expected['roles']:
        if role=='mdbook':continue  # Upstream may provide only --help/HTML.
        page='nvim' if role=='neovim' else role
        command=[str(RUNTIME/'bin/man'),'-w',page]
        result=subprocess.run(command,check=True,text=True,capture_output=True)
        require(result.stdout.strip(),'no manual path: '+page);print(result.stdout.strip())
        rendered=subprocess.run([str(RUNTIME/'bin/man'),'-P','cat',page],check=True,text=True,capture_output=True,
            env=dict(os.environ,MANWIDTH='80',PAGER='cat',MANPAGER='cat'))
        require(rendered.stdout.strip(),'manual did not render: '+page)
        if role=='neovim':subprocess.run([str(RUNTIME/'bin/man'),'-w','neovim'],check=True)
    subprocess.run([str(RUNTIME/'bin/manpath')],check=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','enter','check','install','manuals','choose','status','_stage'))
    args=parser.parse_args(argv)
    require(os.geteuid()==0 and os.path.ismount(ROOT) and os.path.ismount(RUNTIME),'run as root on the installed Mojt SSD')
    python=(RUNTIME/'bin/python3').resolve(strict=True)
    if Path(sys.executable).resolve()!=python or not sys.flags.isolated or not sys.dont_write_bytecode:
        os.execv(str(python),[str(python),'-I','-B',str(Path(__file__).resolve()),*(sys.argv[1:] if argv is None else argv)])
    os.umask(0o077)
    if args.action=='_stage':return private_stage()
    protected(WORK)
    if args.action=='prepare':
        require(not os.path.lexists(WORK),'test evidence exists; preserve it and inspect status')
        require(os.path.samefile('/',ROOT/'state/rootfs'),'start from accepted writable-root G/H')
        WORK.mkdir(mode=0o700);path=WORK/'package-driver.py'
        subprocess.run([str(RUNTIME/'bin/curl'),'--fail','--show-error','--silent','--location','--proto','=https','--proto-redir','=https',
            '--max-time','180','--max-filesize',str(4*1024**2),'--output',str(path),
            'https://raw.githubusercontent.com/kjonasipersson-bert/mojt-linux/'+REVISION+'/tools/mojt-system-fast-test.py'],check=True)
        path.chmod(0o444)
        bridge=driver();downloads=WORK/'downloads';downloads.mkdir();data=bridge.fetch(downloads)
        folder,code=code_cohort(data);sys.path.insert(0,str(folder))
    else:
        bridge=driver();sys.path.insert(0,str(RUNTIME/'tools'))
    import mpm_transaction as tx
    os.environ['PATH']=str(RUNTIME/'libexec/mpm/bin')+':'+str(RUNTIME/'bin')+':/usr/bin:/bin'
    with tx.file_lock(WORK/'.lock'):
        if args.action=='prepare':
            before=bridge.snapshot();old=plain(Path('/var/lib/mojt/writable-root-60/state.json'))
            require(before['status']['running']['artifact'] in (old['candidate']['artifact'],old['probe']['artifact'])
                    and before['status']['running']['deployment']==before['selected'],'start from accepted G/H running and selected')
            bridge.confirm('Package I/J with reviewed management/manual wrappers, leaving all boot choices unchanged?')
            origin=before['status']['running']
            first=package(bridge,ROOT,origin['artifact'],data,WORK/'candidate',label='system-ux-I',revision=1)
            probe=package(bridge,ROOT,origin['artifact'],data,WORK/'probe',label='system-ux-J',revision=2)
            require(bridge.snapshot()==before,'baseline changed during packaging')
            bridge.save('state.json',dict(format=FORMAT,revision=REVISION,files=FILES,script=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                baseline=before,origin=origin,candidate=first,probe=probe,code=code))
            print('READY: packages only. Next: enter.');return 0
        state=checked_state()
        if args.action=='status':print(json.dumps(bridge.snapshot(),indent=2));return 0
        if args.action=='enter':
            require(bridge.snapshot()==state['baseline'],'baseline changed after packaging')
            bridge.confirm('Bootstrap I through old MPM, prepare with checked installed I code, and select I for NEXT boot?')
            before=bridge.snapshot();bridge.run('install-I',*bridge.install_args(state['candidate'],'candidate'),before=before)
            bridge.unchanged(before,bridge.snapshot());deployment=stage_i(bridge);bridge.unchanged(before,bridge.snapshot())
            bridge.run('select-I','system','select','--deployment',deployment,'--expected-selected',before['selected'],'-y','--json')
            bridge.check(state,'origin',selected='candidate')
            print('READY: I selected. Reboot deliberately, then run check and install.');return 0
        if args.action=='install':install_probe(bridge,state);return 0
        if args.action=='manuals':repair_manuals(bridge,state);return 0
        if args.action=='choose':
            bridge.check(state,'candidate');bridge.tools_match();deployment=bridge.read('stage-J-result.json')['deployment']
            # Real public terminal UI: the user can cancel and inspect status first.
            subprocess.run([str(RUNTIME/'bin/mpm'),'system','activate'],check=True)
            require(bridge.snapshot()['selected']==deployment,'J was not selected; inspect status before continuing')
            bridge.check(state,'candidate',selected='probe')
            print('READY: J selected. Reboot deliberately, then run check.');return 0
        current=bridge.snapshot();who='candidate' if current['status']['running']['artifact']==state['candidate']['artifact'] else 'probe'
        bridge.check(state,who);bridge.tools_match()
        deployment=bridge.read('stage-I-result.json' if who=='candidate' else 'stage-J-result.json')['deployment']
        require(current['selected']==deployment,'booted another exact deployment')
        require(os.path.samefile('/',ROOT/'state/rootfs') and os.path.samefile('/usr/local',ROOT/'state/local'),'writable-root backing differs')
        subprocess.run([str(RUNTIME/'bin/mpm'),'system','status'],check=True)
        subprocess.run([str(RUNTIME/'bin/mpm'),'base','status'],check=True)
        subprocess.run([str(RUNTIME/'bin/mpm'),'kernel','status'],check=True)
        if (WORK/'manuals-expected.json').exists():check_manuals(bridge)
        bridge.save('checked-'+('I' if who=='candidate' else 'J')+'.json',current)
        print('PASS: '+state[who]['label']+' exact boot, writable root and status'+(' / manuals' if (WORK/'manuals-expected.json').exists() else '')+'. Evidence: '+str(WORK))
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,KeyError,TypeError,EOFError,KeyboardInterrupt,subprocess.CalledProcessError) as error:
        print('Mojt usability test: '+str(error),file=sys.stderr);raise SystemExit(1)
