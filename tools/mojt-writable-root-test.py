#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Pinned G/H boot and persistent-root test; no automatic reboot or in-place patch."""
import argparse
import ast
import errno
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import runpy
import secrets
import selectors
import stat
import subprocess
import sys

REVISION='0976c58d2202609ba1545739e5abd2c98b8794b1'
DRIVER_SHA256='3edf37cfe8e574ffacb09afabe1fa766aed9f7e024a396adc5320c09f82aadfa'
FILES={'tools/mojt_artifact.py': '006dae0b917d61ade8b52f80510bf334334e70e8aa93be51f474f8073d289dc1', 'tools/mpm_base.py': 'dd477271743b1771c9a0c28793c066d2e28f6d015dc7c1e39e84ecf4707a4403', 'tools/mpm_boot_base.py': '359043d0b43ece16674feb0880921d150ebaaa2eb55aa2938bbf6d593f248428', 'tools/mpm_boot_constructor.py': '6b716161948bca8644b019bb40457738def92f20af09f8ad814d0381ac5a076d', 'tools/mpm_boot_handover.py': '17bbb4194de2ed528108f1c8df70f8a227416cb5756b26879f35aef31a461eb7', 'tools/mpm_boot_selection.py': '60b489bf69f08db42c03807c4953966bc9edde09f82fa6e2f9ecf936e667dac7', 'tools/mpm_boot_update.py': '2cb3a95d5de05177047c8549d4daac12a40f40cbbf0b80f368960a9bb3305acc', 'tools/mpm_boot_v2_store.py': 'd7ed98a995b68bd746a0141b16d27571dc629cec9e5c3d72098f5c4084c4545a', 'tools/mpm_kernel.py': '888b5b20c3d44ddc6ec2d97307218da047986084da237dca89eeff63e1cb6f55', 'tools/mpm_management.py': '55da4c44ac6e22540395e2ea1c0fa5017124b59124aff316ef174d53931abac4', 'tools/mpm_native_io.py': '88168a9b468835a99bffb0b9e2ce70ccab54d1ed97d66c65838c32f9e02d6d7a', 'tools/mpm_nix_boot.py': 'c0faf2791c149c77474c1351841a0511f70fb90f32f73cc1326e04b8c2edb36e', 'tools/mpm_system.py': 'a54c6277aa7d26bba998a45545035e89d556d94cb7cd3ec2c37604614f47c879', 'tools/mpm_system_transition.py': 'b63a765492b69d13bd69af0f4d63d88f1f8109aa72b75b4c6fe47ea42afe7734', 'tools/mpm_base_boot.py': 'b0adf8d8cf870692e05c750bc06b1d32aa2706fb578680f77a5f292161e403ce', 'tools/mojt_native_image.py': 'd8833747e0a918120d4ebb1345ea910ca29e6bbb36ce1e65b8447fba1f18f9e9', 'man/mpm.1': 'c364d06133fd18265b0870c92bd78abb88a087cd3a878fcb8d30aa6b96e69676'}
ROOT=Path('/run/mojt-disk')
RUNTIME=Path('/run/mojt-system')
WORK=Path('/var/lib/mojt/writable-root-60')
FORMAT='mojt-writable-root-test-60-v1'


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
    """A fresh isolated process imports only installed G's checked code cohort.

    Runtime/provider defaults still refer to running F. No installed file is
    replaced, and no already-imported old manager modules can leak into G.
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


def stage_g(bridge):
    command=[sys.executable,'-I','-B',str(Path(__file__).resolve()),'_stage']
    print('+ reviewed installed G launcher: mpm system stage --artifact '+checked_state()['candidate']['artifact']+' -y --json',flush=True)
    output=[];size=0
    with (WORK/'stage-G.log').open('xb') as log:
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
    bridge.save('stage-G-command.json',dict(command=command,returncode=code,scope='installed G code, running F interpreter/runtime'))
    require(code==0,'private G stage failed; keep stage-G.log and inspect status')
    result=json.loads(b''.join(output));require(result['changed'] and result['deployment'],'G stage was not a fresh preparation')
    bridge.save('stage-G-result.json',result);return result['deployment']


def markers(token):
    require(type(token) is str and re.fullmatch('[0-9a-f]{32}',token),'invalid probe token')
    return [Path(prefix)/('mojt-root-test-'+token)/'marker' for prefix in ('/','/opt','/srv','/usr/local','/etc','/var/lib','/home','/root')]


def check_root(bridge,state,*,seed=False,rebooted=True):
    bridge.tools_match()
    require(os.path.samefile('/',ROOT/'state/rootfs') and os.path.samefile('/usr/local',ROOT/'state/local'),'boot did not enter the new writable-root layout')
    marker=plain(Path('/.mojt-root-layout.json'))
    require(marker['format']=='mojt-writable-root-v1' and marker['installation']==state['baseline']['installation'],'root marker differs')
    for path in (Path('/usr/lib/os-release'),RUNTIME/'version'):
        try:fd=os.open(path,os.O_WRONLY|os.O_APPEND)
        except OSError as error:require(error.errno==errno.EROFS,'expected read-only mount: '+str(path))
        else:os.close(fd);raise ValueError('release mount is writable: '+str(path))
    for path in markers(state['token']):
        protected(path.parent)
        if seed:
            require(not os.path.lexists(path.parent),'probe directory already exists: '+str(path.parent))
            path.parent.mkdir(mode=0o700)
            with path.open('x') as stream:stream.write(state['token']);stream.flush();os.fsync(stream.fileno())
        require(path.read_text()==state['token'],'persistent probe changed: '+str(path))
    temporary=Path('/tmp')/('mojt-root-test-'+state['token'])
    if seed:
        with temporary.open('x') as stream:stream.write(state['token'])
    elif rebooted:require(not temporary.exists(),'temporary probe survived reboot')
    subprocess.run([str(RUNTIME/'bin/mpm'),'ports','list'],check=True)
    subprocess.run(['/var/lib/mojt/ports/current/bin/nvim','--version'],check=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','enter','check','next','back','status','_stage'))
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
        require(not os.path.lexists(ROOT/'state/rootfs'),'this first-layout test requires no pre-existing persistent root; do not remove it to retry')
        WORK.mkdir(mode=0o700)
        path=WORK/'package-driver.py'
        subprocess.run([str(RUNTIME/'bin/curl'),'--fail','--show-error','--silent','--location','--proto','=https','--proto-redir','=https',
                        '--max-time','180','--max-filesize',str(4*1024**2),'--output',str(path),
                        'https://raw.githubusercontent.com/kjonasipersson-bert/mojt-linux/'+REVISION+'/tools/mojt-system-fast-test.py'],check=True)
        path.chmod(0o444)
    bridge=driver();sys.path.insert(0,str(RUNTIME/'tools'))
    import mpm_transaction as tx
    os.environ['PATH']=str(RUNTIME/'libexec/mpm/bin')+':'+str(RUNTIME/'bin')+':/usr/bin:/bin'
    with tx.file_lock(WORK/'.lock'):
        if args.action=='prepare':
            before=bridge.snapshot();old=plain(Path('/var/lib/mojt/initramfs-payload-55/state.json'))
            require(before['status']['running']['artifact']==before['status']['selected']['artifact']==old['probe']['artifact']
                    and before['status']['running']['deployment']==before['selected'],'start from accepted F running and selected')
            bridge.confirm('Package G/H with writable-root tooling, leaving running and next boot unchanged?')
            downloads=WORK/'downloads';downloads.mkdir();data=bridge.fetch(downloads)
            origin=before['status']['running']
            g=bridge.package(ROOT,origin['artifact'],data,WORK/'candidate',label='system-root-G',revision=1)
            h=bridge.package(ROOT,origin['artifact'],data,WORK/'probe',label='system-root-H',revision=2)
            code={name:hashlib.sha256(data.get('tools/'+name,(RUNTIME/'tools'/name).read_bytes())).hexdigest() for name in cohort(RUNTIME/'tools')}
            require(bridge.snapshot()==before,'baseline changed during preparation')
            bridge.save('state.json',dict(format=FORMAT,revision=REVISION,files=FILES,script=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                                         baseline=before,origin=origin,candidate=g,probe=h,code=code,token=secrets.token_hex(16)))
            print('READY: packages only. Next: enter.');return 0
        state=checked_state()
        if args.action=='status':print(json.dumps(bridge.snapshot(),indent=2));return 0
        if args.action=='enter':
            require(bridge.snapshot()==state['baseline'],'baseline changed after preparation')
            bridge.confirm('Install G, prepare with checked G code using F runtime, and select G for NEXT boot?')
            before=bridge.snapshot();bridge.run('install-G',*bridge.install_args(state['candidate'],'candidate'),before=before)
            bridge.unchanged(before,bridge.snapshot());deployment=stage_g(bridge)
            bridge.unchanged(before,bridge.snapshot())
            require(not os.path.lexists(ROOT/'state/rootfs'),'stage unexpectedly initialized writable root')
            bridge.run('select-G','system','select','--deployment',deployment,'--expected-selected',before['selected'],'-y','--json')
            bridge.check(state,'origin',selected='candidate')
            print('READY: G selected. Reboot deliberately, then run check.');return 0
        if args.action=='check':
            current=bridge.snapshot();who='candidate' if current['status']['running']['artifact']==state['candidate']['artifact'] else 'probe'
            current=bridge.check(state,who)
            deployment=bridge.read('stage-G-result.json' if who=='candidate' else 'stage-H-result.json')['deployment']
            require(current['selected']==deployment,'booted another deployment')
            seed=not (WORK/'seed.json').exists()
            require(not seed or who=='candidate','seed writable-root probes in G first')
            boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            rebooted=not seed and bridge.read('seed.json')['boot_id']!=boot_id
            check_root(bridge,state,seed=seed,rebooted=rebooted)
            if seed:bridge.save('seed.json',dict(token=state['token'],boot_id=boot_id))
            name='checked-H.json' if who=='probe' else 'checked-G-return.json' if (WORK/'checked-H.json').exists() else 'checked-G-first.json'
            if not (WORK/name).exists():bridge.save(name,current)
            print('PASS: '+name+'; writable root/local data, immutable release mounts and Ports verified. Evidence: '+str(WORK));return 0
        who='candidate' if args.action=='next' else 'probe';before=bridge.check(state,who);bridge.tools_match()
        if args.action=='next':
            require((WORK/'seed.json').exists(),'run check in G before switching')
            bridge.confirm('Install/prepare H and select H for NEXT boot, preserving G root data?')
            bridge.run('install-H',*bridge.install_args(state['probe'],'probe'),before=before)
            bridge.unchanged(before,bridge.snapshot())
            result=bridge.run('stage-H','system','stage','--artifact',state['probe']['artifact'],'-y','--json',before=before)['result']
            bridge.unchanged(before,bridge.snapshot());require(result['changed'] and result['deployment'],'H stage was a no-op')
            deployment=result['deployment'];target='probe'
        else:
            require((WORK/'checked-H.json').exists(),'run check in H before returning')
            bridge.confirm('Select the retained writable-root G deployment for NEXT boot?')
            deployment=bridge.read('stage-G-result.json')['deployment'];target='candidate'
        bridge.run('select-'+('H' if target=='probe' else 'G-return'),'system','select','--deployment',deployment,
                   '--expected-selected',before['selected'],'-y','--json')
        after=bridge.check(state,who,selected=target);require(after['selected']==deployment,'wrong selected deployment')
        print('READY: '+state[target]['label']+' selected. Reboot deliberately, then run check.')
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,KeyError,TypeError,EOFError,KeyboardInterrupt,subprocess.CalledProcessError) as error:
        print('Mojt writable-root test: '+str(error),file=sys.stderr);raise SystemExit(1)
