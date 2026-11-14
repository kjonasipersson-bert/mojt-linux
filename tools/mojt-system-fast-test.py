#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Pinned successor hardware test: old MPM enters C; new MPM measures D.

One USB-delivered file supplies long exact arguments and records evidence.
Every install/stage/selection runs the public installed MPM, shown before use.
No in-place tooling patch, automatic reboot, provider rebuild or disk formatting.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import resource
import selectors
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

REVISION = '991714acfab88676521599ca8f303cd24b09590f'
ORIGIN = 'https://raw.githubusercontent.com/kjonasipersson-bert/mojt-linux/' + REVISION + '/'
FILES = {'tools/mpm_boot_update.py': '91d5bd4be75ca583c1282f65fdfa86ad7a006d6f239de2acb0dc4a7fef11b320', 'tools/mpm_boot_selection.py': '3f1fc453c3316475ca3bce2d8d66d655785b1b0857f91dfe298540c3a368933f', 'tools/mpm_cli.py': 'c5e229ae2e4b748eb9b3409a73a6acda58ca9e57cc55be2af1a0362ffbed1b3b', 'tools/mpm_native_io.py': '73ca7279541119c0ad2171d69184fbc1a54e983e06bebce47de3cb7b855c39da', 'tools/mpm_nix_boot.py': '341a0a31af58f93d2c45b81d8c6942ba160f91fc2973a08040d21c13dc2d7e91', 'tools/mpm_system.py': '3984e6d6bb5101d8ff6e41c7e6a7e263465abc2c9c7ff95af20c038002d286bd', 'tools/mpm_system_cli.py': 'b437b965d25f3d4c9a85356ad6667f4ce5f3fc67682b459f9ab348b63e713bea', 'tools/mpm_system_source.py': 'e13c7750f3f7bdcccbc0b0465b282b06a6c3bd3708068eaa02538eb2008ec70d', 'man/mpm.1': '5e75761605284b87f602e294ab02ef270934afcb9e79fc61807c2bbf7796de1d'}
ROOT = Path('/run/mojt-disk')
RUNTIME = Path('/run/mojt-system')
WORK = Path('/var/lib/mojt/activation-fast-54')
LABEL = 'system-activation-C'
PROBE_LABEL = 'system-activation-D'
FORMAT = 'mojt-fast-activation-test-54-v1'
AREAS = ('base','kernel','platform','boot','firmware','state_requirements')


def require(ok, message):
    if not ok:raise ValueError(message)


def fetch(directory):
    """Data only. The USB-delivered script pins commit and every file hash."""
    result = {}
    for name, expected in FILES.items():
        print('Downloading ' + name + '...', flush=True)
        target = directory / Path(name).name
        subprocess.run([str(RUNTIME / 'bin/curl'), '--fail', '--show-error', '--silent',
            '--location', '--proto', '=https', '--proto-redir', '=https',
            '--connect-timeout', '15', '--max-time', '180', '--max-filesize', str(4 * 1024**2),
            '--output', str(target), ORIGIN + name], check=True)
        data = target.read_bytes()
        require(len(data) <= 4 * 1024**2 and hashlib.sha256(data).hexdigest() == expected,
                'download checksum differs: ' + name)
        result[name] = data
    return result


def write_data(path, data):
    require(not path.is_symlink(), 'linked candidate file: ' + str(path))
    for parent in path.parents:
        require(not parent.is_symlink(), 'linked candidate ancestor: ' + str(parent))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    with path.open('xb') as stream:
        stream.write(data); stream.flush(); os.fchmod(stream.fileno(), 0o444); os.fsync(stream.fileno())


def specification(body, version, provenance):
    return dict(format='mojt-artifact-spec-v1',
        **{k:copy.deepcopy(body[k]) for k in ('kind', 'name', 'platform', 'dependencies', 'requirements', 'provides', 'metadata')},
        version=version, provenance=dict(body['provenance'], activation_test=provenance))


def package(root, baseline, downloads, output, *, label=LABEL, revision=1):
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
            write_data(content / name, data)
        write_data(content / 'share/man/man1/mpm.1', downloads['man/mpm.1'])
        write_data(content / 'version', (label + '\n').encode())
        names = management.literal(content / 'tools/mojt_system.py', 'MPM_FILES')
        require(all((content / 'tools' / n).is_file() for n in names), 'incomplete candidate MPM')
        support = management.produce(content / 'tools', names)
        require(support['description']['state'] == d['state'], 'delivery cannot change state schemas')
        stage = work / 'kit'; stage.mkdir()
        part = artifact.pack(content, specification(component, version, provenance), stage / 'component', numeric_owner=(0, 0))
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
        write_data(gen / 'composition.json', artifact.canonical(composition) + b'\n')
        write_data(gen / 'lifecycle.json', artifact.canonical(actions) + b'\n')
        spec = specification(body, version, provenance); spec['dependencies'] = [new_ref]
        spec['metadata']['composition']['id'] = composition['id']
        generation = artifact.pack(gen, spec, stage / 'generation', numeric_owner=(0, 0))
        # Publish only complete, independently verified native package archives.
        tx.publish(stage, output)
    return dict(artifact=generation['artifact']['id'], version=generation['artifact']['version']['release_id'],
        label=label, generation='generation/' + generation['archive']['file'],
        component='component/' + part['archive']['file'], providers_unchanged=True)


def save(name, value):
    import mpm_native_io as native
    import mpm_transaction as tx
    native.write_json(WORK/name,value);tx.sync_directory(WORK)


def read(name):
    import mpm_base as base
    return base.read(WORK/name)


def mpm(*args):
    result = subprocess.run([str(RUNTIME/'bin/mpm'),*args],check=True,text=True,stdout=subprocess.PIPE)
    return json.loads(result.stdout)


def snapshot():
    import mpm_boot_selection as selection
    status = mpm('system','status','--json')
    require(status['running']['state'] == status['selected']['state'] == 'known','exact installed/running System identities required')
    value,entries,_ = selection.current(ROOT)
    require(value is not None,'native-v2 boot selection required')
    selected = value['description']['selected']
    require(status['selected']['deployment'] == selected,'status/menu selection differs')
    inputs = entries[selected]['record']['description']['inputs']['description']
    return dict(status=status,selection=value['id'],selected=selected,installation=inputs['installation'],
                preserved={key:inputs[key] for key in AREAS})


def baseline():
    before = snapshot();status = before['status']
    require(status['running']['label'] in ('system-ports-fix-1','system-activation-A','system-activation-B'),
            'start from the accepted SSD System (Ports fix or original activation A/B), not installer media or another test')
    require(status['running']['deployment'] == before['selected'],'resolve the pending boot choice before preparation')
    return before


def check(state, running, *, selected=None):
    current = snapshot()
    require(current['installation'] == state['baseline']['installation'] and current['preserved'] == state['baseline']['preserved'],
            'installation/Base/Kernel/boot policy differs from baseline')
    require(current['status']['running']['artifact'] == state[running]['artifact'],'boot '+state[running]['label']+' first')
    if selected is None:
        require(current['status']['running']['deployment'] == current['selected'],'resolve the pending boot choice first')
    else:
        require(current['status']['selected']['artifact'] == state[selected]['artifact'],'selected System differs from '+state[selected]['label'])
    return current


def unchanged(before, after):
    require(before['selection'] == after['selection'] and before['status']['running'] == after['status']['running'],
            'operation unexpectedly changed next boot or running System')
    require(before['installation'] == after['installation'] and before['preserved'] == after['preserved'],
            'operation changed installation/Base/Kernel/boot policy')


def tools_match():
    for name,expected in FILES.items():
        path = RUNTIME/name if name.startswith('tools/') else RUNTIME/'share/man/man1/mpm.1'
        require(hashlib.sha256(path.read_bytes()).hexdigest() == expected,'running test tooling differs: '+name)


def confirm(message):
    require(input(message+' [y/N] ').strip().lower() in ('y','yes'),'cancelled before running MPM')


def emit(data):
    if hasattr(sys.stdout,'buffer'):sys.stdout.buffer.write(data);sys.stdout.buffer.flush()
    else:sys.stdout.write(data.decode(errors='replace'));sys.stdout.flush()


def run(name, *args, check_code=True, before=None):
    """Show public MPM; time only its process, outside this helper's own checks."""
    log = WORK/(name+'.log');evidence = WORK/(name+'.json')
    require(not log.exists() and not evidence.exists(),'evidence already exists for '+name+'; inspect status/logs before repeating')
    command = [str(RUNTIME/'bin/mpm'),*args]
    print('+ '+shlex.join(['mpm',*args]),flush=True)
    output = [];size = 0
    with log.open('xb') as stream:
        stream.write((shlex.join(command)+'\n').encode());stream.flush()
        cpu = resource.getrusage(resource.RUSAGE_CHILDREN);started = time.monotonic_ns()
        child = subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            with selectors.DefaultSelector() as events:
                events.register(child.stdout,selectors.EVENT_READ,'stdout')
                events.register(child.stderr,selectors.EVENT_READ,'stderr')
                while events.get_map():
                    for key,_ in events.select():
                        data = key.fileobj.read1(4096)
                        if not data:events.unregister(key.fileobj);continue
                        stream.write(data);stream.flush()
                        if key.data == 'stdout':
                            size += len(data);require(size <= 16*1024**2,'MPM JSON output exceeds evidence limit')
                            output.append(data)
                        if key.data == 'stderr' or '--json' not in args:emit(data)
            code = child.wait()
            elapsed = time.monotonic_ns()-started;after_cpu = resource.getrusage(resource.RUSAGE_CHILDREN)
        except BaseException:
            if child.poll() is None:child.terminate()
            child.wait();raise
        finally:child.stdout.close();child.stderr.close()
        stream.flush();os.fsync(stream.fileno())
    stdout = b''.join(output).decode()
    report = dict(command=command,returncode=code,elapsed_ns=elapsed,before=before,
                  user_us=round((after_cpu.ru_utime-cpu.ru_utime)*1000000),system_us=round((after_cpu.ru_stime-cpu.ru_stime)*1000000))
    save(name+'.json',report)
    print(name+': %.3f s wall, %.3f s CPU; exit %d' % (elapsed/1000000000,(report['user_us']+report['system_us'])/1000000,code),flush=True)
    if check_code:require(code == 0,'MPM failed; preserve '+str(log)+' and inspect status before retrying')
    if '--json' in args and code == 0:
        report['result'] = json.loads(stdout)
        save(name+'-result.json',report['result'])
    return report


def install_args(row, directory):
    return ('system','install','--from-file',str(WORK/directory/row['generation']),
            '--expected-id',row['artifact'],'--dependency-file',str(WORK/directory/row['component']),'-y','--json')


def enter(state):
    require(baseline() == state['baseline'],'running/selected baseline changed after preparation')
    confirm('Install C through OLD MPM, prepare it and select C for NEXT boot? This is bootstrap, not a performance sample.')
    before = snapshot()
    run('bootstrap-install',*install_args(state['candidate'],'candidate'),before=before)
    unchanged(before,snapshot())
    staged = run('bootstrap-stage','system','stage','--artifact',state['candidate']['artifact'],'-y','--json',before=before)['result']['deployment']
    unchanged(before,snapshot())
    run('bootstrap-select','system','select','--deployment',staged,'--expected-selected',before['selected'],'-y','--json',before=before)
    after = check(state,'origin',selected='candidate')
    require(after['selected'] == staged,'bootstrap selected another deployment')
    save('entered.json',after)
    print('READY: C selected. Reboot deliberately, then run install. Bootstrap timings do not measure the new MPM.')


def exercise(action, state):
    before = check(state,'candidate');tools_match()
    if action == 'install':
        require(not any(row['artifact'] == state['probe']['artifact'] for row in before['status']['installed']),
                'D is already installed; a repeat is not a fresh installation sample')
        confirm('Install D with NEW MPM, without --verify, keeping next boot unchanged?')
        result = run('install',*install_args(state['probe'],'probe'),before=before)
        require(result['result']['changed'],'D installation was a no-op, not a fresh installation sample')
        unchanged(before,check(state,'candidate'))
        require(any(row['artifact'] == state['probe']['artifact'] for row in snapshot()['status']['installed']), 'D was not installed')
    elif action == 'stage':
        require(not any(row['artifact'] == state['probe']['artifact'] for row in before['status']['staged_deployments']),
                'D is already prepared; a repeat is not a fresh preparation sample')
        confirm('Prepare D for boot without selecting it? Construction may still take time.')
        report = run('stage','system','stage','--artifact',state['probe']['artifact'],'-y','--json',before=before)
        unchanged(before,check(state,'candidate'))
        require(report['result']['changed'] and report['result']['deployment'] is not None,'expected newly prepared D deployment')
    elif action == 'cancel':
        require(sys.stdin.isatty(),'cancellation test needs a terminal')
        print('In the real MPM chooser, enter 0, then q.',flush=True)
        report = run('cancel','system','activate',check_code=False,before=before)
        unchanged(before,check(state,'candidate'))
        text = (WORK/'cancel.log').read_text()
        require(report['returncode'] != 0 and 'Choose a listed number, or q.' in text and 'candidate selection cancelled' in text,
                'expected invalid-number reprompt followed by q cancellation')
    elif action == 'activate':
        staged = read('stage-result.json')['deployment']
        confirm('Select prepared D ('+state['probe']['artifact']+') for NEXT boot?')
        report = run('activate','system','activate','--artifact',state['probe']['artifact'],
                     '--expected-selected',before['selected'],'-y','--json',before=before)
        after = check(state,'candidate',selected='probe')
        require(after['selected'] == staged and report['result']['selected'] == staged,'expected exact staged D selection')
        require(after['status']['running'] == before['status']['running'],'running System changed during selection')
        print('PASS: D selected; C still running. Reboot deliberately, then run after.')
    save(action+'-after.json',snapshot())
    print('PASS: '+action+'; original Base/Kernel/boot policy retained. Evidence: '+str(WORK))


def after(state):
    current = check(state,'probe');tools_match()
    require(current['selected'] == read('stage-result.json')['deployment'],'booted deployment differs from measured D')
    subprocess.run([str(RUNTIME/'bin/mpm'),'ports','list'],check=True)
    subprocess.run(['/var/lib/mojt/ports/current/bin/nvim','--version'],check=True)
    save('after.json',current)
    print('PASS: D running and selected; original Base/Kernel retained; Ports and Neovim work.')


def back(state):
    before = check(state,'probe');tools_match()
    candidate = read('bootstrap-stage-result.json')['deployment']
    confirm('Select retained C for NEXT boot?')
    run('back','system','select','--deployment',candidate,'--expected-selected',before['selected'],'-y','--json',before=before)
    current = check(state,'probe',selected='candidate')
    require(current['selected'] == candidate,'expected original C return deployment')
    save('back-after.json',current)
    print('C selected for NEXT boot. Reboot deliberately if returning; running D is unchanged.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','enter','status','install','stage','cancel','activate','after','back'))
    args = parser.parse_args(argv)
    require(os.geteuid() == 0 and os.path.ismount(ROOT) and os.path.ismount(RUNTIME),
            'run as root on the installed Mojt SSD, not Debian or installer media')
    sys.path.insert(0,str(RUNTIME/'tools'))
    import mpm_transaction as tx
    os.environ['PATH'] = str(RUNTIME/'libexec/mpm/bin')+':'+str(RUNTIME/'bin')+':/usr/bin:/bin'
    require(WORK.resolve() == WORK,'linked evidence directory')
    tx.protected_directory(WORK,write=True,label='hardware test evidence');WORK.mkdir(mode=0o700,exist_ok=True)
    with tx.file_lock(WORK/'.lock'):
        if args.action == 'status':
            print(json.dumps(dict(checkpoint=read('state.json') if (WORK/'state.json').exists() else None,
                                  current=snapshot()),indent=2));return 0
        if args.action == 'prepare':
            require(not any((WORK/name).exists() for name in ('state.json','candidate','probe','downloads')),
                    'preparation evidence already exists; inspect status before repeating')
            before = baseline();downloads = WORK/'downloads';downloads.mkdir(mode=0o700)
            data = fetch(downloads)
            print('Packaging C and D on the SSD. This preparation is outside the MPM performance samples.',flush=True)
            origin = before['status']['running']
            candidate = package(ROOT,origin['artifact'],data,WORK/'candidate',label=LABEL,revision=1)
            probe = package(ROOT,origin['artifact'],data,WORK/'probe',label=PROBE_LABEL,revision=2)
            require(baseline() == before,'baseline changed during preparation')
            save('state.json',dict(format=FORMAT,revision=REVISION,files=FILES,bridge_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                                   baseline=before,origin=origin,candidate=candidate,probe=probe))
            print('READY: packages C and D only. Next: enter. No boot choice changed.');return 0
        state = read('state.json')
        require(state['format'] == FORMAT and state['revision'] == REVISION and state['files'] == FILES
                and state['bridge_sha256'] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'test checkpoint or script revision differs; preserve evidence')
        if args.action == 'enter':enter(state)
        elif args.action == 'after':after(state)
        elif args.action == 'back':back(state)
        else:exercise(args.action,state)
    return 0


if __name__ == '__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,KeyError,TypeError,subprocess.CalledProcessError,EOFError,KeyboardInterrupt) as error:
        print('Mojt fast activation test: '+str(error),file=sys.stderr);raise SystemExit(1)
