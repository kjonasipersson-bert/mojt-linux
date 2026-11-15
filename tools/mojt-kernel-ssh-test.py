#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Pinned System/Kernels/SSH delivery; no in-place patch or automatic reboot."""
import argparse
import copy
import shutil
import tempfile
import ast
import pwd
import time
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

REVISION='8e5b39c0ab0f8da7b601d0d16ceaa15740f41285'
DRIVER_SHA256='3edf37cfe8e574ffacb09afabe1fa766aed9f7e024a396adc5320c09f82aadfa'
FILES={'man/mbt.1': '341aa51b4af634daea0ebc18a31bddc4dd1f5c49bdcb01ada37884826f64e9ff', 'man/mpm.1': '6fc1a1264581660de503069ac58a299b565699c3ad5d30536c768c403826bb28', 'manifests/kernel-first-build.json': 'c8862e291c1ffa1553f5d5a01935bd89f89cfd1407e3d78050e6dc8bd60fe7bb', 'manifests/kernel-lts.json': '415d5fde68e4527770531248b43522b3d5e4280ec83888435d5078010d463eb7', 'manifests/kernel-stable.json': '21111a5c79b2a8283e5572b83522664536589c4d9c1ea3779aae2e91d68f348d', 'manifests/mpm-release-example.json': 'd6104468e5c8a6e24b362d176d1127f680dcdcc3c51b1b4e5c0169a9e5434a18', 'tests/check-mojt-system.sh': 'ad4ff9836cd6639d428b84d98b17e310cc7b8e70c3952c6548868d21783549ac', 'tests/run-mpm-nix-ports.py': '16f230c8fe410232a51e5dd6f1a930c3ad30ce003c7570fbd13c51a5990fa2fb', 'tests/run-mpm-nix-python.py': '9a0ec75d5b7f4e264f3be230beac6befb63c74ee0581b5602c984f2a6d4bf5fa', 'tests/run-mpm-nix-upgrade.py': 'b97ff5cf12f111cad486505185c2d73c3995f4a93afd2eceb2710fd7da3b400d', 'tests/run-mpm-selectors.py': '548f6abb31337ff746a4012ee305f6e81b237c25d14fb6bc8cad889f6a9a2c17', 'tools/mbt': '872ae877137546c9755055fa77fb5337bbdfd2a2d9a7a09c6617edc953df802e', 'tools/mbt_cli.py': '3fdc05b4e1de2a7c27e159c2a363b183f20bc03f6cfa1b9d6bece282eb215f42', 'tools/mbt_runtime.py': 'e7e764de220aef9b5d6989eca69cf7872bb712a8e9d195d7aa0dc159f449c126', 'tools/mojt-artifact-pack.py': '536f2587fc864c0e6f2c5cf59a1b9484027a2c4f8659870552df380b3a7d5178', 'tools/mojt-base-install': '2c3b9f7038ffedbc5199abba474230e526d25ecfdfb985d9fc52d6e6fd786d1a', 'tools/mojt-build-env.py': '9e385ce1d0aa2e4c5418146b5655ee8d69deb889e04fd5f1e49fcc37782948cc', 'tools/mojt-console-size.py': '92320de91da14f36523eca8eebb45acfd7a0ef20e054d00c59d835b210ff904a', 'tools/mojt-kernel-build.py': '420fb32eec949d8980c3f41c5a27906f1d2b096873af35e0f672da6c116dec48', 'tools/mojt-privileged-setup.py': '4fa83da72f8aaf2dd4cd1dd2805215ef8c2665e3ebb4d924f471c1c8f08dd623', 'tools/mojt-system-inspect.py': 'a5b4320460e4c8aae6a1b84f8acf12e8f361d5366220babd58ead35eb04f45a8', 'tools/mojt-vm-build.py': '7b2fe1088adb49d9c59b9c89d1f7078cfed7aa91d8231b28500db64d04b84893', 'tools/mojt_accounts.py': '2a9404dbe278ae52936911b5ec57060dece5a2c5ac5af1803d077b3b05a56085', 'tools/mojt_artifact.py': '7ab012a3ebe416153c6e80e14c7e496408215cf9e5f13e3bae982b9d1a87dcf6', 'tools/mojt_boot.py': '7ffc799dcd802924d39bca0aa890c734ad919567292213616904388ef47b63d9', 'tools/mojt_bootstrap.py': 'f8cc2d19579e922783a481ec8fa2404ed7a5375d878ddd30a068bd9cb08a2a92', 'tools/mojt_bootstrap_inputs.py': '1e89ebe4b947ff7f4fb9e9b185606ccba12d9caffdf999bfd619c172cc46b434', 'tools/mojt_generations.py': 'a53acba12de372f58d5b550f2994c87e5204710274bfd91d900cb9946585e893', 'tools/mojt_hardware.py': 'b9dee62177cbf51c4a5d84ef2048084a4ab45c827bf32a02f80ab5b23dfdf18d', 'tools/mojt_mounted_install.py': 'd02f075688b6a58521f7488c7fa5b14b3da57af0f100ec44c42a76990e4ae5e7', 'tools/mojt_native_image.py': 'd8833747e0a918120d4ebb1345ea910ca29e6bbb36ce1e65b8447fba1f18f9e9', 'tools/mojt_sshd.py': '2eae8007b449f290353fe8e31996d27695a93ec1bb8fba977f086493c3ac6a68', 'tools/mojt_system.py': '598def25ceb3406ededad90db56f9c7434c3c563755eb9828e48a2d38754690c', 'tools/mojt_system_manifest.py': '78b96796236568b23f209f18efc6c13312c258e6794a4690097523677e974b5c', 'tools/mojt_system_package.py': '8636f6b548d8ecc4540bb0c28fca49f7c5813f523a186c9f41efa0858a065008', 'tools/mpm': 'e95b021064ef359007163fb07ff8d16044031b6f6413a4b69e8fe8eea3db098b', 'tools/mpm-nix-catalog.py': '7aae8a2b54eaf2a3492e7eeafc54bfe5cd35af2e20266235a6b0e4b6245c3d55', 'tools/mpm-nix-prototype': '3abd589bfee13d9a7b91f03f7a0502aadb7a9ddf90a817c93f1b029af533d4bd', 'tools/mpm-system': 'a720625d186044a7de24ca89ff1ddec16b1f4ae50cfc2f80f3bcdb229bb74ee0', 'tools/mpm_base.py': 'dd477271743b1771c9a0c28793c066d2e28f6d015dc7c1e39e84ecf4707a4403', 'tools/mpm_base_boot.py': 'b0adf8d8cf870692e05c750bc06b1d32aa2706fb578680f77a5f292161e403ce', 'tools/mpm_base_cli.py': '5d6e224f9d4f48f791f1e41a3983a083b2e27d8ea300b2452cc7115ad170c89b', 'tools/mpm_base_source.py': 'fb2859a553f9ba8c933c1d75c6e4ba6f38fd532ce617eb758e5f6a47eb191c6a', 'tools/mpm_base_status.py': '9ed7ec132cecfc3456ef4afd19d5032c280c90d695afc03cdb191ad0f9e1870b', 'tools/mpm_base_transition.py': '2c7fb2d00f83154a42acd7e682c4ae619f52fb5f95155a44e327bf96ad1fd9c2', 'tools/mpm_boot_base.py': '359043d0b43ece16674feb0880921d150ebaaa2eb55aa2938bbf6d593f248428', 'tools/mpm_boot_constructor.py': 'a03d2284a1a3760e01c73f79826ab45496a65ebe22641eadab1a15b3c535117f', 'tools/mpm_boot_early.py': '332bdd1e9f905759a12c567076da2acb293995efb680a5f47282e8c1058a85f7', 'tools/mpm_boot_handover.py': '17bbb4194de2ed528108f1c8df70f8a227416cb5756b26879f35aef31a461eb7', 'tools/mpm_boot_inventory.py': '9598da63ad89a82bf45b7156f9a3789fd98da9a0fde1f16a0e9334246e529c8e', 'tools/mpm_boot_selection.py': 'ad4979e0cee61e890c677609785c6193077ecbc59ae9fbb4514a8ef5b9d233b2', 'tools/mpm_boot_status.py': 'bc5fa38c01ac53b63351ec499923aeefdc7d8357c772a1feaa74eb010a950510', 'tools/mpm_boot_update.py': '1aacf090ba1a85e069cb5b0ef56da6aa2c3719662a2c3a22bb2fcca895a92466', 'tools/mpm_boot_v2.py': 'ab1f448d90dae9c46eb090f79ed12239e8ae7c2c2bcdf44076df4dc92322e4ce', 'tools/mpm_boot_v2_store.py': 'd7ed98a995b68bd746a0141b16d27571dc629cec9e5c3d72098f5c4084c4545a', 'tools/mpm_catalog.py': '5045d2b449e8c30d7cbe16072e86366c130c68e39189b1ba8492da803c55ae19', 'tools/mpm_cli.py': 'c5e229ae2e4b748eb9b3409a73a6acda58ca9e57cc55be2af1a0362ffbed1b3b', 'tools/mpm_defaults.py': '3343f32328719fbd45683a81e94c3b263890f96abd7e4a09e97f9c4686a0ed95', 'tools/mpm_deployment.py': '2545c643ed7e285b29012e125ba55703e9ab7f219d7bad0df977cd055774b774', 'tools/mpm_kernel.py': 'eb9893b93ed3ff95dba0b95f07b9478ed2c6f367ca08a482cb23cec6331d031a', 'tools/mpm_kernel_boot.py': '991b821797dc0275a338ca20d5d1204a55eea35f4505e1908895eb36195b680c', 'tools/mpm_kernel_source.py': '4d93d200bc7fb1a2b19d9ba9226e1c0e629f882955af2d06c46525ef42d36111', 'tools/mpm_man.py': 'e524dfec92b424c41c479808f300506345dd9c6cb350b32e53b50f19b7a63f4f', 'tools/mpm_management.py': '55da4c44ac6e22540395e2ea1c0fa5017124b59124aff316ef174d53931abac4', 'tools/mpm_native_cache.py': '047a4e7f331e8170154b41f7e83628840fa7eb5f7450a32f0de76fd4e74e15e7', 'tools/mpm_native_io.py': '88168a9b468835a99bffb0b9e2ce70ccab54d1ed97d66c65838c32f9e02d6d7a', 'tools/mpm_nix_binary.py': 'f05169d5ca796b9150f40dbefbbd8d5b66cf55376116e4a356365431a9118d99', 'tools/mpm_nix_boot.py': 'c0faf2791c149c77474c1351841a0511f70fb90f32f73cc1326e04b8c2edb36e', 'tools/mpm_ports_cli.py': '1ff282885602437c7aeb9a278008301047c584a6b1be6db0989c7326df7889e7', 'tools/mpm_ports_nix_source.py': 'f97ba12c7f9c5044b405d65f68e3a5cd821bb6705d0b3f1cdbeca4b7a41d270f', 'tools/mpm_ports_profile.py': 'b5bf161ebfafaabec7e6c7f4c95f1b2c85653f6722770693d46bfe8cb6678ce6', 'tools/mpm_request_plan.py': '9fe41e419e021621006ac813db3325489b190025ea9119817020f53bf1d4d538', 'tools/mpm_requests.py': '172197d896610bbf2962acb476ff5e6b82c96ac1dbf8907a8e18fb2bf22b0afa', 'tools/mpm_selection.py': '5f0977db6d051c67ca61fcf1804e3ebe18fa67966ba8babd6bf43f62c9ea0769', 'tools/mpm_selector_ports.py': '12c868e8601cc3a00135670f7b64d6418795c76ec5c8a70ff15c4103f80c9146', 'tools/mpm_sources.py': '284af164d7e345669b84bf6d20bda0d3486f3b7a93c2ca78ffc9f671809b9391', 'tools/mpm_sources_cli.py': '4527b61f4f64ca4edd24e66514ae2dbbd04c950afc81e54abfec42d821b57aad', 'tools/mpm_system.py': 'c73c190de7f554c18d18b568ff685b6b86abb06513858732f17b821436564452', 'tools/mpm_system_cli.py': 'b78523e0886cb94518745b427fc3c37e77add1a094f3188df805952e66142250', 'tools/mpm_system_model.py': '346c0cd4e91135f3da26636c2f6828c2689da556643c6ad1fbc3f9b7aa4c2296', 'tools/mpm_system_source.py': 'e13c7750f3f7bdcccbc0b0465b282b06a6c3bd3708068eaa02538eb2008ec70d', 'tools/mpm_system_transition.py': '25511c3d03affc587d7c45220823afcb83294852024dc9f952cf5e6c8c6a96d8', 'tools/mpm_transaction.py': '24be957e8e0264a0dac31d45d5143b984eeffe5151cdda3b99ef8f053e5a8f5c', 'tools/mpm_ui.py': '46a9fc23884c9890d3b13c8f0df2bc823a16d8bccf24494f5d3c052145e17ad0'}
ROOT=Path('/run/mojt-disk')
RUNTIME=Path('/run/mojt-system')
WORK=Path('/var/lib/mojt/kernel-ssh-63')
FORMAT='mojt-kernel-ssh-test-63-v1'


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
    """A fresh isolated process imports only installed K's checked code cohort.

    Runtime/provider defaults still refer to running I/J. No installed file is
    replaced, and no already-imported old manager modules can leak into K.
    """
    state=checked_state();identifier=state['candidate']['artifact']
    require(re.fullmatch(r'sha256:[0-9a-f]{64}',identifier),'invalid candidate artifact')
    folder=ROOT/'realizations/system'/identifier[7:]/'profile/tools'
    names=cohort(folder);require(set(names)==set(state['code']),'private code cohort differs')
    for name,expected in state['code'].items():
        path=folder/name;protected(path)
        require(stat.S_ISREG(path.lstat().st_mode) and hashlib.sha256(path.read_bytes()).hexdigest()==expected,'candidate code changed: '+name)
    for name,digest in FILES.items():
        path=folder.parent/name;protected(path)
        require(hashlib.sha256(path.read_bytes()).hexdigest()==digest,'candidate resource changed: '+name)
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


def stage_k(bridge):
    command=[sys.executable,'-I','-B',str(Path(__file__).resolve()),'_stage']
    print('+ reviewed installed K launcher: mpm system stage --artifact '+checked_state()['candidate']['artifact']+' -y --json',flush=True)
    output=[];size=0
    with (WORK/'stage-K.log').open('xb') as log:
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
    bridge.save('stage-K-command.json',dict(command=command,returncode=code,scope='installed K code, running I/J interpreter/runtime'))
    require(code==0,'private K stage failed; keep stage-K.log and inspect status')
    result=json.loads(b''.join(output));require(result['changed'] and result['deployment'],'K stage was not a fresh preparation')
    bridge.save('stage-K-result.json',result);return result['deployment']



def package(bridge, root, baseline, downloads, output, extra_reference, *, label="system-build-K", revision=1):
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
        for name, data in downloads.items():
            bridge.write_data(content / name, data)
        bridge.write_data(content / 'share/man/man1/mpm.1', downloads['man/mpm.1'])
        bridge.write_data(content / 'share/man/man1/mbt.1', downloads['man/mbt.1'])
        bridge.write_data(content / 'version', (label + '\n').encode())
        # Optional server tools are retained content; no server unit or keys are activated.
        ssh=Path(extra_reference['identity']['output'])
        for name in ('sshd','ssh-keygen'):
            target=content/'bin'/name
            require(not os.path.lexists(target),'candidate already exports '+name)
            target.symlink_to(str(ssh/'bin'/name))
        runner=(RUNTIME/'bin/systemctl').resolve().with_name('systemd-run')
        require(runner.is_file() and os.access(runner,os.X_OK),'retained systemd has no systemd-run')
        (content/'bin/systemd-run').symlink_to(str(runner))
        bridge.write_data(content/'bin/mojt-sshd',b'#!/bin/sh\nexec /run/mojt-system/bin/python3 -I -B /run/mojt-system/tools/mojt_sshd.py "$@"\n')
        (content/'bin/mojt-sshd').chmod(0o555)
        bridge.write_data(content/'bin/mbt',b'#!/bin/sh\nexec /run/mojt-system/bin/python3 -I -B /run/mojt-system/tools/mbt "$@"\n')
        (content/'bin/mbt').chmod(0o555)
        metadata=dict(format='mojt-mbt-runtime-v1',python=str((RUNTIME/'bin/python3').resolve()),
            files=list(management.literal(content/'tools/mojt_system.py','MBT_FILES')),
            source_files=list(management.literal(content/'tools/mojt_system.py','MBT_SOURCE_FILES')),
            syntax='experimental',scope='environment, Kernel build, packaging and native-v2 bootstrap')
        bridge.write_data(content/'mbt-runtime.json',(json.dumps(metadata,indent=2)+'\n').encode())
        bridge.write_data(content/'share/mbt/kernel-first-build.json',downloads['manifests/kernel-first-build.json'])
        names = management.literal(content / 'tools/mojt_system.py', 'MPM_FILES')
        require(all((content / 'tools' / n).is_file() for n in names), 'incomplete candidate MPM')
        support = management.produce(content / 'tools', names)
        require(support['description']['state'] == d['state'], 'delivery cannot change state schemas')
        stage = work / 'kit'; stage.mkdir()
        part_spec=bridge.specification(component,version,provenance)
        if extra_reference not in part_spec['dependencies']:part_spec['dependencies'].append(extra_reference)
        part=artifact.pack(content,part_spec,stage/'component',numeric_owner=(0,0))
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
        component='component/' + part['archive']['file'], startup_providers_preserved=True)


def fetch():
    data={};inputs=WORK/'inputs';inputs.mkdir(mode=0o700)
    for name,expected in FILES.items():
        local=RUNTIME/name
        if local.is_file() and not local.is_symlink() and hashlib.sha256(local.read_bytes()).hexdigest()==expected:
            value=local.read_bytes()
        else:
            print('Downloading '+name+'...',flush=True)
            target=inputs/Path(name).name
            subprocess.run([str(RUNTIME/'bin/curl'),'--fail','--show-error','--silent','--location','--proto','=https','--proto-redir','=https',
                '--connect-timeout','15','--max-time','180','--max-filesize',str(4*1024**2),'--output',str(target),
                'https://raw.githubusercontent.com/kjonasipersson-bert/mojt-linux/'+REVISION+'/'+name],check=True)
            value=target.read_bytes()
        require(hashlib.sha256(value).hexdigest()==expected,'pinned input differs: '+name);data[name]=value
    code=WORK/'code';code.mkdir(mode=0o700)
    for name,value in data.items():
        if name.startswith('tools/'):(code/Path(name).name).write_bytes(value);(code/Path(name).name).chmod(0o444)
    names=cohort(code);hashes={n:hashlib.sha256((code/n).read_bytes()).hexdigest() for n in names}
    return data,code,hashes


def acquire_ssh(bridge):
    # Extensionless provider requires its explicit source loader.
    import importlib.machinery
    loader=importlib.machinery.SourceFileLoader('kernel_ssh_provider',str(WORK/'code/mpm-nix-prototype'))
    spec=importlib.util.spec_from_loader(loader.name,loader);backend=importlib.util.module_from_spec(spec);loader.exec_module(backend)
    source=backend.catalog_from_manifest(RUNTIME/'ports.toml')['source']
    row=backend.resolve_package(source,'openssh','openssh');print('OpenSSH '+row['version']+': '+row['output'],flush=True)
    bridge.confirm('Import this exact OpenSSH binary and package new System tooling, preserving the current boot choice?')
    from mpm_nix_binary import NixBinaryAdapter
    adapter=NixBinaryAdapter(RUNTIME/'bin/nix-store')
    adapter.runner([adapter.binary,'--realise',row['output'],'--add-root',str(WORK/'openssh-root'),'--indirect',
        '--option','max-jobs','0','--option','builders','','--option','require-sigs','true'])
    paths=sorted(adapter.runner([adapter.binary,'--query','--requisites',row['output']]).splitlines())
    hashes=adapter.runner([adapter.binary,'--query','--hash',*paths]).splitlines()
    require(len(paths)==len(hashes),'incomplete OpenSSH closure')
    reference=dict(provider='nix',identity=dict(format='mojt-nix-output-v1',output=row['output'],
        closure=[dict(path=p,nar_hash=h) for p,h in zip(paths,hashes)],commands=backend.discover_commands(dict(output=row['output'],attribute='openssh'))))
    adapter.describe(reference,ROOT)
    for name in ('sshd','ssh-keygen'):adapter.verify_path(reference,str(Path(row['output'])/'bin'/name),executable=True)
    bridge.save('openssh.json',dict(source=source,package=row,reference=reference));return reference


def tools_match():
    for name,expected in FILES.items():
        path=RUNTIME/name;protected(path)
        require(stat.S_ISREG(path.lstat().st_mode) and hashlib.sha256(path.read_bytes()).hexdigest()==expected,'running resource differs: '+name)


def running_system(bridge,state):
    current=bridge.snapshot();require(current['installation']==state['baseline']['installation'],'another installation')
    require(current['status']['running']['artifact']==current['status']['selected']['artifact']==state['candidate']['artifact'],'boot the delivered System first')
    require(current['status']['running']['deployment']==current['selected'],'resolve the pending boot choice first')
    for area in ('platform','boot','firmware','state_requirements'):
        require(current['preserved'][area]==state['baseline']['preserved'][area],'boot policy changed: '+area)
    for key in ('artifact','release','rootfs_sha256','kernel_min'):
        require(current['preserved']['base'][key]==state['baseline']['preserved']['base'][key],'selected Base changed: '+key)
    require(current['preserved']['base']['kernel_max'] in (state['baseline']['preserved']['base']['kernel_max'],'7.3.999'),'unreviewed Kernel range')
    return current


def seed_config(bridge,state,args):
    """Freeze an explicit seed, preferring the original retained Debian config."""
    import mpm_kernel
    from mpm_boot_status import description,read_running
    from mpm_cli import Runtime
    record=read_running(Runtime());kernel=description(record)['kernel']['artifact']
    source=args.config or (ROOT/'kernel/installed'/mpm_kernel.identifier(kernel)/'provenance/debian.config')
    require(source.is_file() and not source.is_symlink(),'provide --config FILE containing the frozen Debian starting config')
    data=source.read_bytes();require(b'CONFIG_X86_64=y' in data,'need an x86_64 Debian seed')
    home=Path('/var/lib/mojt/kernel-build');protected(home);home.mkdir(mode=0o755,exist_ok=True);home.chmod(0o755)
    frozen=home/'debian.config'
    if frozen.exists():require(frozen.read_bytes()==data,'existing frozen build config differs')
    else:bridge.write_data(frozen,data)
    settings=dict(path=str(frozen),sha256=hashlib.sha256(data).hexdigest(),origin=str(source))
    bridge.save('seed.json',settings);return settings


def build_user(name):
    user=pwd.getpwnam(name)
    require(user.pw_uid>=1000 and user.pw_uid!=65534 and Path(user.pw_dir).is_dir() and Path(user.pw_dir)==Path(user.pw_dir).resolve(),'use an existing ordinary build user with a home')
    return user


def share_environment(environment):
    """Expose root-owned build inputs read-only without following store links."""
    for path in [environment,*environment.rglob('*')]:
        if path.is_symlink():continue
        require(path.lstat().st_uid==0,'compiler input is not root-owned')
        if path.is_dir():path.chmod(0o755)
        elif path.is_file():path.chmod(0o555 if path.stat().st_mode&0o111 else 0o444)
        else:require(False,'unsupported compiler environment entry')


def build(bridge,args):
    state=checked_state();current=running_system(bridge,state);tools_match()
    user=build_user(args.user);seed=bridge.read('seed.json');env=Path('/var/lib/mojt/kernel-build/environment')
    require((env/'environment.json').is_file(),'run environment first')
    workspace=Path(user.pw_dir)/'mojt-kernel-build'
    if not workspace.exists():
        subprocess.run([str(RUNTIME/'bin/systemd-run'),'--wait','--pipe','--collect','--uid',str(user.pw_uid),'--gid',str(user.pw_gid),
            '/usr/bin/mkdir','-m','0700','-p','--',str(workspace)],check=True)
    # The parent is user-owned by design; do not pass it through root-only protected().
    require(workspace==workspace.resolve() and workspace.stat().st_uid==user.pw_uid and not workspace.stat().st_mode&0o077,'unsafe build workspace')
    label='lts' if args.track=='linux-kernel-lts' else 'stable';output=workspace/label
    recipe=RUNTIME/'manifests'/('kernel-lts.json' if label=='lts' else 'kernel-stable.json')
    plan=json.loads(recipe.read_text());require(plan['track']==args.track,'recipe changed')
    command=[str(RUNTIME/'bin/mbt'),'build','kernel','--track',args.track,'--config',seed['path'],'--config-sha256',seed['sha256'],
        '--environment',str(env),'--output',str(output),'--jobs',str(args.jobs),'-y']
    if args.resume:command+=['--resume','--source',str(output/'source')]
    else:require(not output.exists(),'build output already exists; inspect it before explicit resume')
    unit='mojt-kernel-'+label+'-build'
    bridge.confirm('Run '+args.track+' '+plan['version']+' as '+args.user+' in a detached system service?')
    subprocess.run([str(RUNTIME/'bin/systemd-run'),'--unit',unit,'--uid',str(user.pw_uid),'--gid',str(user.pw_gid),
        '--property','WorkingDirectory='+str(workspace),'--property','UMask=0022','--setenv','HOME='+user.pw_dir,
        '--setenv','PATH=/run/mojt-system/bin:/usr/bin:/bin',*command],check=True)
    bridge.save('build-'+label+'.json',dict(track=args.track,unit=unit,output=str(output),recipe=plan,uid=user.pw_uid,command=command))
    bridge.unchanged(current,bridge.snapshot())
    print('STARTED: journalctl -fu '+unit+'; SSH disconnect does not cancel the build. Next: result --track '+args.track)


def result(bridge,args):
    label='lts' if args.track=='linux-kernel-lts' else 'stable';job=bridge.read('build-'+label+'.json');output=Path(job['output'])
    require((output/'kernel.json').is_file() and not (output/'.building').exists(),'build incomplete; inspect journalctl -u '+job['unit'])
    from mojt_artifact import kernel_input
    spec,unused=kernel_input(output,1);require(spec['metadata']['kernel_name']==args.track,'built another track')
    print('PASS: build evidence and staged Kernel/modules checked: '+spec['metadata']['kernel_release'])
    print('Next: install --track '+args.track+' (retains current Kernel and next-boot choice)')


def install_kernel(bridge,args):
    result(bridge,args)
    label='lts' if args.track=='linux-kernel-lts' else 'stable';job=bridge.read('build-'+label+'.json')
    kit=WORK/('package-'+label);require(not kit.exists(),'package evidence exists; inspect status before repeating')
    before=bridge.snapshot();bridge.confirm('Package and install this built Kernel, keeping next boot unchanged?')
    process=subprocess.run([str(RUNTIME/'bin/mbt'),'package','kernel','--build',job['output'],'--revision','1','--output',str(kit)],check=True,text=True,capture_output=True)
    record=json.loads(process.stdout);bridge.save('package-'+label+'.json',record)
    archive=kit/record['archive']['file'];identifier=record['artifact']['id']
    bridge.run('install-'+label,'kernel','install','--from-file',str(archive),'--expected-id',identifier,'-y','--json',before=before)
    bridge.unchanged(before,bridge.snapshot());print('PASS: Kernel installed, next boot unchanged. Next: choose --track '+args.track)


def choose_kernel(bridge,args):
    from mpm_boot_status import description
    import mpm_boot_selection as selection
    import mpm_catalog as catalog
    label='lts' if args.track=='linux-kernel-lts' else 'stable';package=bridge.read('package-'+label+'.json');identifier=package['artifact']['id']
    before=bridge.snapshot();value,entries,unused=selection.current(ROOT);inputs=description(entries[before['selected']]['record'])
    version=package['artifact']['version']['upstream']
    if catalog.compare_versions(inputs['base']['kernel_max'],version)<0:
        maximum='7.3.999';require(catalog.compare_versions(version,maximum)<=0,'track exceeds reviewed local range')
        context=dict(format=catalog.BASE_FORMAT,platform=inputs['platform'],base={k:inputs['base'][k] for k in ('artifact','release')},
            kernel_min=inputs['base']['kernel_min'],kernel_max=maximum)
        print('Selected Base is unchanged. Local declared Kernel range: '+inputs['base']['kernel_min']+'..'+inputs['base']['kernel_max']+' -> '+context['kernel_min']+'..'+maximum)
        bridge.confirm('Authorize this explicit local compatibility range for the requested Kernel test (not a completed runtime verification)?')
        path=WORK/('base-context-'+label+'.json');bridge.save(path.name,context)
        bridge.run('bounds-'+label,'base','upgrade','--artifact',inputs['base']['artifact'],'--base-context',str(path),'-y','--json',before=before)
        before=bridge.snapshot()
    bridge.confirm('Prepare and select '+args.track+' for NEXT boot, retaining the previous Kernel?')
    bridge.run('choose-'+label,'kernel','upgrade','--artifact',identifier,'-y','--json',before=before)
    after=bridge.snapshot()
    for area in ('base','platform','boot','firmware','state_requirements'):require(after['preserved'][area]==before['preserved'][area],'unrelated boot area changed: '+area)
    require(after['status']['running']==before['status']['running'],'running System changed')
    bridge.save('selected-'+label+'.json',after)
    print('READY: Kernel selected. Reboot deliberately, then run check --track '+args.track)


def activate_kernel(bridge,args):
    label='lts' if args.track=='linux-kernel-lts' else 'stable'
    package=bridge.read('package-'+label+'.json');before=bridge.snapshot()
    bridge.confirm('Select the retained prepared '+args.track+' Kernel for NEXT boot without rebuilding?')
    bridge.run('activate-'+label,'kernel','activate','--artifact',package['artifact']['id'],'-y','--json',before=before)
    bridge.save('selected-'+label+'.json',bridge.snapshot())
    print('READY: retained Kernel selected. Reboot deliberately, then run check --track '+args.track)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','enter','check','environment','build','result','install','choose','activate','status','_stage'))
    p.add_argument('--track',choices=('linux-kernel-lts','linux-kernel'),default='linux-kernel-lts')
    p.add_argument('--user',default='mojtbuild');p.add_argument('--config',type=Path);p.add_argument('--jobs',type=int,choices=range(1,5),default=2)
    p.add_argument('--resume',action='store_true');args=p.parse_args(argv)
    require(os.geteuid()==0 and os.path.ismount(ROOT) and os.path.ismount(RUNTIME),'run as root on the installed Mojt target')
    python=(RUNTIME/'bin/python3').resolve(strict=True)
    if Path(sys.executable).resolve()!=python or not sys.flags.isolated or not sys.dont_write_bytecode:
        os.execv(str(python),[str(python),'-I','-B',str(Path(__file__).resolve()),*(sys.argv[1:] if argv is None else argv)])
    os.umask(0o077)
    if args.action=='_stage':return private_stage()
    protected(WORK)
    if args.action=='prepare':
        require(not os.path.lexists(WORK),'test evidence exists; preserve it and inspect status')
        WORK.mkdir(mode=0o700);target=WORK/'package-driver.py'
        subprocess.run([str(RUNTIME/'bin/curl'),'--fail','--show-error','--silent','--location','--proto','=https','--proto-redir','=https',
            '--max-time','180','--max-filesize',str(4*1024**2),'--output',str(target),
            'https://raw.githubusercontent.com/kjonasipersson-bert/mojt-linux/'+REVISION+'/tools/mojt-system-fast-test.py'],check=True)
        target.chmod(0o444);data,code,hashes=fetch();sys.path.insert(0,str(code))
    else:sys.path.insert(0,str(RUNTIME/'tools'))
    bridge=driver()
    import mpm_transaction as tx
    os.environ['PATH']=str(RUNTIME/'libexec/mpm/bin')+':'+str(RUNTIME/'bin')+':/usr/bin:/bin'
    with tx.file_lock(WORK/'.lock'):
        if args.action=='prepare':
            before=bridge.snapshot();old=plain(Path('/var/lib/mojt/usability-61/state.json'))
            require(before['status']['running']['artifact'] in (old['candidate']['artifact'],old['probe']['artifact']) and before['status']['running']['deployment']==before['selected'],'start from accepted I/J running and selected')
            reference=acquire_ssh(bridge)
            candidate=package(bridge,ROOT,before['status']['running']['artifact'],data,WORK/'candidate',reference)
            require(bridge.snapshot()==before,'baseline changed during packaging')
            bridge.save('state.json',dict(format=FORMAT,revision=REVISION,files=FILES,script=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                baseline=before,origin=before['status']['running'],candidate=candidate,code=hashes))
            print('READY: package only. Next: enter.');return 0
        state=checked_state()
        if args.action=='status':print(json.dumps(bridge.snapshot(),indent=2));return 0
        if args.action=='enter':
            require(bridge.snapshot()==state['baseline'],'baseline changed after preparation')
            bridge.confirm('Install new tooling content, prepare with checked installed code and select it for NEXT boot?')
            before=bridge.snapshot();bridge.run('install-K',*bridge.install_args(state['candidate'],'candidate'),'--content-only',before=before)
            bridge.unchanged(before,bridge.snapshot());deployment=stage_k(bridge);bridge.unchanged(before,bridge.snapshot())
            bridge.run('select-K','system','select','--deployment',deployment,'--expected-selected',before['selected'],'-y','--json')
            bridge.check(state,'origin',selected='candidate');print('READY: new System selected. Reboot deliberately, then run check.');return 0
        if args.action=='environment':
            running_system(bridge,state);tools_match();build_user(args.user)
            seed_config(bridge,state,args);env=Path('/var/lib/mojt/kernel-build/environment')
            bridge.confirm('Acquire the pinned private compiler environment, leaving Ports and next boot unchanged?')
            subprocess.run([str(RUNTIME/'bin/mbt'),'env','--profile','kernel','--source-manifest',str(RUNTIME/'ports.toml'),'--output',str(env),'-y'],check=True)
            share_environment(env)
            print('READY: private compiler environment. Next: build --track '+args.track);return 0
        running_system(bridge,state);tools_match()
        if args.action=='build':build(bridge,args);return 0
        if args.action=='result':result(bridge,args);return 0
        if args.action=='install':install_kernel(bridge,args);return 0
        if args.action=='choose':choose_kernel(bridge,args);return 0
        if args.action=='activate':activate_kernel(bridge,args);return 0
        snapshot=bridge.snapshot();require(snapshot['status']['running']['artifact']==state['candidate']['artifact'],'boot the delivered System first')
        tools_match();subprocess.run([str(RUNTIME/'bin/mpm'),'system','status'],check=True);subprocess.run([str(RUNTIME/'bin/mpm'),'kernel','status'],check=True)
        label='lts' if args.track=='linux-kernel-lts' else 'stable'
        if (WORK/('selected-'+label+'.json')).exists():
            package=bridge.read('package-'+label+'.json');from mpm_boot_status import description,read_running
            from mpm_cli import Runtime
            running=description(read_running(Runtime()));require(running['kernel']['artifact']==package['artifact']['id'],'boot the selected exact Kernel first')
            require(running['kernel']['release']==os.uname().release==package['artifact']['metadata']['kernel_release'],'Kernel/module release differs')
            require((Path('/lib/modules')/os.uname().release/'modules.dep').is_file(),'matching modules unavailable')
        require(os.path.samefile('/',ROOT/'state/rootfs'),'writable-root mapping differs')
        bridge.save('checked-'+label+'.json',snapshot);print('PASS: exact System/Kernel, writable root and status. Check the SSH reconnect and Ports manually.')
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,KeyError,TypeError,EOFError,KeyboardInterrupt,subprocess.CalledProcessError) as error:
        print('Mojt Kernel/SSH test: '+str(error),file=sys.stderr);raise SystemExit(1)
