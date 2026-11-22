#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Prepare a retained firmware System generation; never patch a running release."""
import argparse
import ast
import copy
import hashlib
import importlib.util
import importlib.machinery
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import stat
import subprocess
import sys
import tempfile

ROOT=Path('/run/mojt-disk')
RUNTIME=Path('/run/mojt-system')
WORK=Path('/var/lib/mojt/firmware-system-test')
FORMAT='mojt-firmware-system-test-v1'
LABEL='system-firmware-1'


def require(ok,message):
    if not ok:raise ValueError(message)


def checked(path):
    require(path == path.absolute() == path.resolve(),'linked maintenance path: '+str(path))
    for point in (path,*path.parents):
        if not point.exists():continue
        info=point.lstat()
        require(info.st_uid == 0 and (not info.st_mode & 0o022 or stat.S_ISDIR(info.st_mode) and info.st_mode & stat.S_ISVTX),
                'unprotected maintenance path: '+str(point))


def state(*, allow_script_change=False):
    path=WORK/'state.json';checked(path);info=path.stat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= 1024**2,'unsafe maintenance state')
    value=json.loads(path.read_text())
    require(value['format'] == FORMAT and (allow_script_change or value['script'] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),
            'maintenance script/checkpoint differs')
    return value


def save(value):
    import mpm_native_io as io
    checked(WORK/'state.json')
    with tempfile.TemporaryDirectory(prefix='.checkpoint-',dir=WORK) as folder:
        pending=Path(folder)/'state.json';io.write_json(pending,value)
        os.replace(pending,WORK/'state.json');io.sync_directory(WORK)


def package_directory(value):
    path=Path(value.get('package',str(WORK/'package')))
    require(path.is_relative_to(WORK) and path != WORK,'package directory outside maintenance workspace')
    checked(path)
    return path


def mpm(*args):
    result=subprocess.run([str(RUNTIME/'bin/mpm'),*map(str,args)],check=True,stdout=subprocess.PIPE,text=True)
    return json.loads(result.stdout)


def snapshot():
    """Read exact live identities without enumerating installed/prepared history."""
    from mpm_cli import Runtime
    from mpm_boot_status import read_running,description
    from mpm_boot_selection import selected
    runtime=Runtime();active=read_running(runtime);state,entries,unused=selected(ROOT,receipt=False)
    require(active is not None and state is not None,'exact running/selected System required')
    source=entries[state['description']['selected']]['record']['description']['inputs']['description']
    running=description(active)['system']
    return dict(running=running['artifact'],label=running['generation'],running_deployment=active['id'],selected=state['description']['selected'],
        installation=source['installation'],base=source['base'],kernel=source['kernel'],boot=source['boot'])


def unchanged(before):
    require(snapshot() == before,'running System, next boot or retained Base/Kernel changed')


def import_binary(nix,output,root):
    subprocess.run([str(nix),'--realise',str(output),'--add-root',str(root),'--indirect',
                    '--option','max-jobs','0','--option','builders','','--option','require-sigs','true'],check=True)


def acquire(code,with_agent):
    """One pinned evaluation, binary substitution, and at most a fixed source fetch."""
    loader=importlib.machinery.SourceFileLoader('firmware_provider',str(code/'tools/mpm-nix-prototype'))
    spec=importlib.util.spec_from_loader(loader.name,loader);backend=importlib.util.module_from_spec(spec);loader.exec_module(backend)
    import tomllib
    source=backend.source_from_fields(tomllib.loads((RUNTIME/'ports.toml').read_text())['nixpkgs'],RUNTIME)
    expression='''{ requestJSON }:
let r = builtins.fromJSON requestJSON;
  pkgs = import (builtins.toPath r.source.path) {
    system=r.source.system; overlays=[];
    config.allowUnfreePredicate = p: (p.pname or "") == "linux-firmware";
  };
  fw = pkgs.linux-firmware;
  ga = pkgs.qemu_kvm.ga;
in {
  firmware = { version=fw.version; output=fw.outPath; source=fw.src.outPath;
               source_drv=fw.src.drvPath; fixed=fw.src.outputHash or ""; };
  agent = if r.with_agent then { version=ga.version; output=ga.outPath; } else null;
}
'''
    print('Resolve exact firmware and guest-agent inputs from the retained Nixpkgs source...',flush=True)
    values=backend.evaluate(expression,source=source,with_agent=with_agent);fw=values['firmware'];nix=RUNTIME/'bin/nix-store'
    for field in ('output','source'):backend.store_path(fw[field])
    require(fw['fixed'] and re.fullmatch('/nix/store/'+backend.STORE_NAME+r'\.drv',fw['source_drv']),
            'license source must be a pinned fixed-output fetch')
    print('Import firmware '+fw['version']+' (binary data only)...',flush=True)
    import_binary(nix,fw['output'],WORK/'firmware-root')
    if not Path(fw['source']).is_dir():
        print('Fetch exact upstream source for firmware attributions (no Kernel build)...',flush=True)
        args=[str(nix),'--realise',fw['source_drv'],'--option','builders','','--option','require-sigs','true','--option','fallback','false']
        planned=subprocess.run([*args,'--dry-run'],check=True,capture_output=True,text=True,env={**os.environ,'LC_ALL':'C'})
        builds=set(re.findall(r'(?m)^\s+(/nix/store/\S+\.drv)\s*$',planned.stderr))
        require(builds <= {fw['source_drv']},'license fetch would build dependencies; prepare the missing binary inputs on a builder first')
        subprocess.run([*args,'--option','max-jobs','1','--option','build-cores','1','--add-root',str(WORK/'license-root'),'--indirect'],check=True)
    else:import_binary(nix,fw['source'],WORK/'license-root')
    licenses=Path(fw['source']);require((licenses/'WHENCE').is_file(),'exact upstream WHENCE missing')
    agent=None
    if with_agent:
        row=values['agent'];backend.store_path(row['output'])
        print('Import ordinary qemu-guest-agent '+row['version']+'...',flush=True)
        import_binary(nix,row['output'],WORK/'agent-root')
        from mpm_nix_binary import NixBinaryAdapter
        adapter=NixBinaryAdapter(nix)
        paths=sorted(adapter.runner([adapter.binary,'--query','--requisites',row['output']]).splitlines())
        hashes=adapter.runner([adapter.binary,'--query','--hash',*paths]).splitlines()
        require(len(paths) == len(hashes),'incomplete QEMU guest-agent closure')
        agent=dict(provider='nix',identity=dict(format='mojt-nix-output-v1',output=row['output'],
                    closure=[dict(path=p,nar_hash=h) for p,h in zip(paths,hashes)],
                    commands=backend.discover_commands(dict(output=row['output'],attribute='qemu_kvm.ga'))))
        adapter.describe(agent,ROOT)
        require('qemu-ga' in agent['identity']['commands'],'QEMU guest-agent command missing')
    provenance=dict(provider='nix',nixpkgs=source,firmware=fw,agent=values['agent'])
    return Path(fw['output'])/'lib/firmware',licenses,agent,provenance


def write(path,data):
    require(not path.is_symlink(),'linked candidate path')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.unlink(missing_ok=True);path.write_bytes(data);path.chmod(0o644)


def overlay(source,target):
    """Merge data in a private copy without writing through old file symlinks."""
    require(target.is_dir() and not target.is_symlink(),'linked firmware destination')
    for original in source.iterdir():
        destination=target/original.name
        if original.is_dir() and not original.is_symlink():
            require(not destination.is_symlink() and (not destination.exists() or destination.is_dir()),'firmware directory type changed')
            destination.mkdir(mode=0o755,exist_ok=True);destination.chmod(0o755)
            overlay(original,destination)
        else:
            require(not destination.is_dir() or destination.is_symlink(),'firmware file replaces a directory')
            destination.unlink(missing_ok=True)
            if original.is_symlink():destination.symlink_to(os.readlink(original))
            else:shutil.copy2(original,destination)


def specification(body,version,provenance):
    return dict(format='mojt-artifact-spec-v1',**{k:copy.deepcopy(body[k]) for k in
        ('kind','name','platform','dependencies','requirements','provides','metadata')},
        version=version,provenance=dict(body['provenance'],firmware_update=provenance))


def license_texts(source):
    """Retain legacy root license files and the upstream LICENSES directory."""
    root=source.resolve(strict=True);texts={}
    def read(point):
        resolved=point.resolve(strict=True)
        require(resolved.is_relative_to(root) and resolved.is_file(), 'unsafe upstream license: '+str(point))
        texts[point.relative_to(source).as_posix()]=resolved.read_bytes()
    for point in sorted(source.iterdir()):
        if point.name == 'LICENSES' and point.is_dir() and not point.is_symlink():
            for directory,dirs,files in os.walk(point,followlinks=False):
                for name in dirs:
                    require(not (Path(directory)/name).is_symlink(),'linked upstream license directory: '+str(Path(directory)/name))
                for name in files:read(Path(directory)/name)
        elif point.name == 'WHENCE' or point.name.startswith(('LICENSE','LICENCE','COPYING')):
            read(point)
    require('WHENCE' in texts and len(texts)>1,'firmware license texts missing')
    return texts


def package(root,baseline,code,firmware,licenses,agent,provenance,output):
    """Copy owned System content only; retain all old provider references and startup."""
    import mojt_artifact as artifact
    import mojt_hardware as hardware
    import mojt_system as paths
    import mojt_system_manifest as manifests
    import mpm_base as base
    import mpm_system as system
    import mpm_system_model as model
    import mpm_system_transition as transition
    import mpm_management as management
    import mpm_transaction as tx
    hardware.checked_tree(firmware)
    texts=license_texts(licenses)
    body,_=system.object_record(root,baseline);composition,actions=system.composition(system.object_path(root,baseline),body)
    d=copy.deepcopy(composition['description'])
    require(len(d['components']) == 1 and d['components'][0]['role'] == 'runtime','single-runtime native System required')
    previous=d['components'][0]['reference']
    require(all(r['source']['reference'] == previous and r['path'] == r['source']['path'] and '/' not in r['path'] for r in d['profile']),
            'unsupported original profile mapping')
    component,_=system.object_record(root,previous['artifact']);old_manifest=base.read(system.realization_path(root,baseline)/'profile/manifest.json')
    require(not output.exists(),'package output already exists')
    version={k:body['version'][k] for k in ('upstream','scheme','revision')};version['revision']+=1
    source=system.object_path(root,previous['artifact'])/'payload'
    with tempfile.TemporaryDirectory(prefix='.firmware-package-',dir=output.parent) as folder:
        work=Path(folder);content=work/'content';shutil.copytree(source,content,symlinks=True)
        expected=copy.deepcopy(component['files'])
        for row in expected:
            if row['type'] != 'symlink':row['mode']=system.stored_mode(row)
        require(artifact.inventory(content)[0] == expected,'copied original component differs')
        for point in (content,*content.rglob('*')):
            if not point.is_symlink() and point.is_dir():point.chmod(0o755)
        before_raw=(content/'hardware.json').read_text();before=json.loads(before_raw)
        require(before.get('format') == 2 and before.get('modules_location') == 'native-kernel','native hardware System required')
        target=content/'kernel/lib/firmware'
        # Retain old firmware filenames for older Kernels, replacing collisions only in this new copy.
        overlay(firmware,target)
        hardware.checked_tree(target)
        attribution=content/'kernel/licenses/linux-firmware';attribution.mkdir(parents=True,exist_ok=True)
        for name,data in texts.items():write(attribution/name,data)
        for name in ('regulatory.db','regulatory.db.p7s'):
            require((target/name).is_file(),'preserved regulatory database missing')
        after=dict(before,firmware_tree_sha256=paths.tree_hash(target),licenses_tree_sha256=paths.tree_hash(content/'kernel/licenses'))
        after_raw=json.dumps(after,indent=2)+'\n';write(content/'hardware.json',after_raw.encode())
        import mbt_runtime
        for name in mbt_runtime.resources(code):write(content/name,(code/name).read_bytes())
        write(content/'share/man/man1/mpm.1',(code/'man/mpm.1').read_bytes())
        write(content/'share/man/man1/mbt.1',(code/'man/mbt.1').read_bytes())
        write(content/'version',(LABEL+'\n').encode())
        if (content/'libexec/mpm/bin/zstd').is_symlink() and not os.path.lexists(content/'bin/zstd'):
            (content/'bin/zstd').symlink_to(os.readlink(content/'libexec/mpm/bin/zstd'))
        if (content/'mbt-runtime.json').is_file():
            declared=json.loads((content/'mbt-runtime.json').read_text())
            declared.update(files=list(management.literal(content/'tools/mojt_system.py','MBT_FILES')),
                            source_files=list(management.literal(content/'tools/mojt_system.py','MBT_SOURCE_FILES')))
            write(content/'mbt-runtime.json',(json.dumps(declared,indent=2)+'\n').encode())
        if agent:
            executable=Path(agent['identity']['output'])/'bin/qemu-ga'
            require(executable.is_file() and os.access(executable,os.X_OK),'qemu-ga binary missing')
            require(not os.path.lexists(content/'bin/qemu-ga'),'candidate already exports qemu-ga')
            (content/'bin/qemu-ga').symlink_to(str(executable))
            write(content/'units/qemu-guest-agent.service',transition.QEMU_AGENT_UNIT.encode())
            (content/'units/mojt.target.wants/qemu-guest-agent.service').symlink_to('../qemu-guest-agent.service')
        names=management.literal(content/'tools/mojt_system.py','MPM_FILES');support=management.produce(content/'tools',names)
        require(support['description']['state'] == d['state'],'System state schemas must remain exact')
        # The reviewed data proof binds the retained baseline and sealed profile inventories.
        proof=dict(format=transition.FIRMWARE_FORMAT,baseline=old_manifest['id'],hardware_before=before_raw,hardware_after=after_raw,
            inventory_before=artifact.digest(transition.firmware_inventory(old_manifest['description']['profile'])),
            inventory_after=artifact.digest(transition.firmware_inventory(system.inventory(content))),source=provenance)
        write(content/transition.FIRMWARE_PROOF,artifact.canonical(proof)+b'\n')
        stage=work/'kit';stage.mkdir();part_spec=specification(component,version,provenance)
        if agent:part_spec['dependencies'].append(agent)
        part=artifact.pack(content,part_spec,stage/'component',numeric_owner=(0,0));reference=dict(provider='native',artifact=part['artifact']['id'])
        d['label']=LABEL;d['components'][0]['reference']=reference
        for mapping in d['profile']:mapping['source']['reference']=reference
        mapped={r['path'] for r in d['profile']}
        required={p.split('/')[0] for p in mbt_runtime.resources(code)} | {'share','version','kernel',transition.FIRMWARE_PROOF}
        for name in sorted(required-mapped):
            d['profile'].append(dict(path=name,source=dict(reference=reference,path=name)))
        d['profile'].sort(key=lambda r:r['path']);d['management']=support['description']['management']
        proposed=copy.deepcopy(old_manifest['description']);proposed['label']=LABEL
        roots={row['path'] for row in d['profile']}
        proposed['profile']={p:r for p,r in system.inventory(content).items() if p.split('/')[0] in roots}
        review=transition.tooling_review(old_manifest,manifests.create(proposed),firmware=proof)
        require(review['description']['compatible'],'candidate changes unrelated startup: '+', '.join(review['description']['blockers']))
        from mpm_boot_v2 import canonical as boot_canonical
        boot_canonical(review)  # Refuse oversized handover evidence before installation.
        comp=base.record(model.FORMAT,d);model.supported(comp,actions)
        generation=work/'generation';generation.mkdir()
        write(generation/'composition.json',artifact.canonical(comp)+b'\n');write(generation/'lifecycle.json',artifact.canonical(actions)+b'\n')
        gen_spec=specification(body,version,provenance);gen_spec['dependencies']=[reference];gen_spec['metadata']['composition']['id']=comp['id']
        result=artifact.pack(generation,gen_spec,stage/'generation',numeric_owner=(0,0));tx.publish(stage,output)
    return dict(artifact=result['artifact']['id'],label=LABEL,generation='generation/'+result['archive']['file'],
                component='component/'+part['archive']['file'],code={n:artifact.file_sha(code/'tools'/n) for n in names})


def private_stage(value):
    candidate=value['candidate'];folder=ROOT/'realizations/system'/candidate['artifact'][7:]/'profile/tools'
    for name,digest in candidate['code'].items():
        path=folder/name;checked(path)
        require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == digest,'candidate manager changed')
    names=None
    for node in ast.parse((folder/'mojt_system.py').read_text()).body:
        if isinstance(node,ast.Assign) and any(isinstance(n,ast.Name) and n.id=='MPM_FILES' for n in node.targets):
            names=ast.literal_eval(node.value)
    require(type(names) is tuple and set(names) == set(candidate['code']) and all('/' not in n and n not in ('.','..') for n in names),
            'candidate manager cohort is incomplete')
    sys.path.insert(0,str(folder))
    sys.argv=[str(folder/'mpm-system'),'system','stage','--artifact',candidate['artifact'],'-y','--json']
    runpy.run_path(str(folder/'mpm-system'),run_name='__main__')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','install','activate','check','back','status','_prepare','_stage'))
    parser.add_argument('--refresh-code',action='store_true',help='refresh preparation before completed installation, retaining prior packages and inputs')
    args=parser.parse_args(argv)
    require(not args.refresh_code or args.action == 'prepare','--refresh-code requires prepare')
    require(os.geteuid() == 0 and os.path.ismount(ROOT) and os.path.ismount(RUNTIME),'run as root on installed native Mojt')
    os.environ['PATH']=str(RUNTIME/'libexec/mpm/bin')+':'+str(RUNTIME/'bin')+':/usr/sbin:/usr/bin:/sbin:/bin'
    checked(WORK)
    if args.action == 'prepare':
        if (WORK/'state.json').exists():
            previous=state(allow_script_change=args.refresh_code)
            prepared=previous['phase'] == 'prepared' and args.refresh_code
            require((previous['phase'] == 'preparing' or prepared) and 'deployment' not in previous,
                    'preparation already complete; use status/install')
            old_package=package_directory(previous)
            if prepared:
                require(old_package.is_dir() and 'candidate' in previous,'prepared package/checkpoint missing; retain and inspect')
            else:require(not old_package.exists(),'preparation package already exists; retain and inspect')
            if args.refresh_code:
                unchanged(previous['baseline'])
                repo=Path(__file__).resolve().parents[1];sys.path.insert(0,str(repo/'tools'));import mbt_runtime
                old=Path(previous['code'])
                require(mbt_runtime.verify(old)['id'] == previous['execution']['id'],'prepared source cohort changed')
                code=Path(tempfile.mkdtemp(prefix=mbt_runtime.PREFIX,dir=WORK));execution=mbt_runtime.freeze(repo,code)
                if prepared:
                    import mpm_native_io as io
                    replacement=Path(tempfile.mkdtemp(prefix='repackage-',dir=WORK))
                    io.write_json(replacement/'previous-state.json',previous)
                    previous.update(package=str(replacement/'package'),phase='preparing')
                    previous.pop('candidate')
                previous.update(code=str(code),execution=execution,script=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
                save(previous)
                print('Refreshed preparation code; retained baseline, prior packages and downloaded inputs.',flush=True)
            os.execv(sys.executable,[sys.executable,'-I','-B',str(Path(__file__).resolve()),'_prepare'])
        require(not args.refresh_code,'no preparation checkpoint to refresh')
        require(not WORK.exists(),'incomplete preparation without checkpoint; retain it and inspect before retrying')
        before=snapshot();require(mpm('system','status','--json')['running']['deployment'] == before['selected'],'resolve pending next boot first')
        WORK.mkdir(mode=0o700)
        repo=Path(__file__).resolve().parents[1];sys.path.insert(0,str(repo/'tools'));import mbt_runtime
        code=Path(tempfile.mkdtemp(prefix=mbt_runtime.PREFIX,dir=WORK));execution=mbt_runtime.freeze(repo,code)
        value=dict(format=FORMAT,script=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),phase='preparing',baseline=before,
                   code=str(code),execution=execution,with_agent=True)
        (WORK/'state.json').write_text(json.dumps(value,indent=2)+'\n');(WORK/'state.json').chmod(0o600)
        os.execv(sys.executable,[sys.executable,'-I','-B',str(Path(__file__).resolve()),'_prepare'])
    value=state()
    if args.action == '_stage':return private_stage(value)
    code=Path(value['code']);sys.path.insert(0,str(code/'tools'));import mbt_runtime
    require(mbt_runtime.verify(code)['id'] == value['execution']['id'],'prepared source cohort changed')
    if args.action == 'status':
        print(json.dumps(dict(phase=value['phase'],baseline=value['baseline']['label'],
            candidate={k:v for k,v in value.get('candidate',{}).items() if k != 'code'},
            package=str(package_directory(value)),deployment=value.get('deployment')),indent=2));return 0
    if args.action == '_prepare':
        unchanged(value['baseline']);firmware,licenses,agent,provenance=acquire(code,value['with_agent'])
        print('Package new firmware System generation on the target...',flush=True)
        value['candidate']=package(ROOT,value['baseline']['running'],code,firmware,licenses,agent,provenance,package_directory(value))
        unchanged(value['baseline']);value['phase']='prepared';save(value)
        print('READY: packages only. Next: install. Boot choice unchanged.');return 0
    candidate=value['candidate'];before=value['baseline']
    if args.action == 'install':
        unchanged(before)
        if 'TMPDIR' not in os.environ:
            temporary=WORK/'tmp';checked(temporary);temporary.mkdir(mode=0o700,exist_ok=True)
            os.environ['TMPDIR']=str(temporary)
        directory=package_directory(value)
        mpm('system','install','--from-file',directory/candidate['generation'],'--expected-id',candidate['artifact'],
            '--dependency-file',directory/candidate['component'],'--content-only','-y','--json')
        unchanged(before)
        result=subprocess.run([sys.executable,'-I','-B',str(Path(__file__).resolve()),'_stage'],check=True,stdout=subprocess.PIPE,text=True)
        staged=json.loads(result.stdout);unchanged(before)
        value['deployment']=staged['deployment'];value['phase']='installed';save(value)
        print('READY: installed and prepared, not selected. Next: activate.');return 0
    if args.action == 'activate':
        unchanged(before)
        print('Change next boot: '+before['label']+' -> '+candidate['label']+'. Base, Kernel and boot policy retained. Reboot required.',flush=True)
        mpm('system','select','--deployment',value['deployment'],'--expected-selected',before['selected'],'-y','--json')
        value['phase']='selected';save(value);print('READY: reboot deliberately, then run check.');return 0
    current=snapshot()
    require(all(current[k] == before[k] for k in ('installation','base','kernel','boot')),'Base/Kernel/boot policy changed')
    require(current['running'] == candidate['artifact'] and current['selected'] == value['deployment'],'boot the firmware generation first')
    if args.action == 'check':
        require((RUNTIME/'kernel/lib/firmware').is_dir() and (RUNTIME/'kernel/licenses/linux-firmware/WHENCE').is_file(),'firmware/attribution paths missing')
        require(os.path.samefile('/lib/firmware',RUNTIME/'kernel/lib/firmware'),'running firmware mount is not the selected System')
        require(os.statvfs('/lib/firmware').f_flag & os.ST_RDONLY,'running firmware mount is not read-only')
        subprocess.run([str(RUNTIME/'bin/qemu-ga'),'--version'],check=True)
        print('PASS: new System running; original Base/Kernel/boot policy retained. Check real devices and guest-agent status separately.');return 0
    if args.action == 'back':
        mpm('system','select','--deployment',before['selected'],'--expected-selected',current['selected'],'-y','--json')
        print('READY: original deployment selected; reboot deliberately.');return 0
    return 0


if __name__ == '__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,KeyError,subprocess.CalledProcessError) as error:
        print('FAIL: '+str(error),file=sys.stderr)
        if isinstance(error,subprocess.CalledProcessError) and error.stdout:
            print(str(error.stdout)[:8192],file=sys.stderr)
        raise SystemExit(1)
