#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Fixed PR #54 hardware test delivery as two native System generations.

This maintenance bridge downloads pinned Python/manual data, packages it using
the installed manager, and invokes installed MPM. It is not a remote catalog,
an in-place patcher, a service migration or a general release updater.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

REVISION = 'cecbb47f4eaa6a3485249ecc0ee5bf036911f5cd'
ORIGIN = 'https://raw.githubusercontent.com/kjonasipersson-bert/mojt-linux/' + REVISION + '/'
FILES = {'tools/mpm_boot_update.py': '304cdc02a91f2075895206e24ac3d37ebce9f880d82232efd9d35094b2223187', 'tools/mpm_boot_selection.py': '4ffb756dd366a0ea618e0c3382f069e2e0f028ae3093916fcf1f7a265cbdfe90', 'man/mpm.1': '4bf5256aadd96f88761d2fa449f5d5ec74754a8857d5ffdef96a1b2c2d987683'}

ROOT = Path('/run/mojt-disk')
RUNTIME = Path('/run/mojt-system')
WORK = Path('/var/lib/mojt/activation-test-54')
LABEL = 'system-activation-A'
FORMAT = 'mojt-activation-test-54-v1'


def require(ok, message):
    if not ok:
        raise ValueError(message)


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
            for k,v in downloads.items()), 'repair inputs differ from pinned data')
    body, unused = system.object_record(root, baseline)
    comp, actions = system.composition(system.object_path(root, baseline), body)
    d = copy.deepcopy(comp['description'])
    require(len(d['components']) == 1 and d['components'][0]['role'] == 'runtime',
            'repair supports only the existing single-runtime System composition')
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
    require(type(version['revision']) is int, 'repair requires a numeric System package revision')
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
        require(support['description']['state'] == d['state'], 'repair cannot change state schemas')
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
                'repair changes startup content: ' + ', '.join(review['description']['blockers']))
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


def mpm(*args):
    result = subprocess.run([str(RUNTIME / 'bin/mpm'), *args], text=True, stdout=subprocess.PIPE)
    require(result.returncode == 0, 'installed MPM failed; retained work can be inspected before retrying')
    return json.loads(result.stdout)


def baseline():
    status = mpm('system', 'status', '--json')
    require(status['running']['state'] == status['selected']['state'] == 'known', 'exact native-v2 System status required')
    require(status['running']['label'] == 'system-ports-fix-1',
            'boot the installed system-ports-fix-1 on the SSD before running this fixed repair')
    require(status['running']['deployment'] == status['selected']['deployment'],
            'another deployment is already selected; resolve that choice first')
    return dict(artifact=status['running']['artifact'], deployment=status['running']['deployment'])


def exercise(action, value):
    import time
    import mpm_boot_selection as selection
    status = mpm('system', 'status', '--json')
    candidate, probe = value['candidate'], value['probe']
    wanted = probe if action == 'after' else candidate
    require(status['running']['artifact'] == wanted['artifact'], 'boot '+wanted['label']+' first')
    require(status['running']['deployment'] == status['selected']['deployment'], 'resolve pending boot choice first')
    baseline_entry = selection.ready(ROOT, value['baseline']['deployment'])['record']['description']['inputs']['description']
    def unchanged_areas():
        current = selection.current(ROOT)
        selected = current[0]['description']['selected']
        inputs = current[1][selected]['record']['description']['inputs']['description']
        require(all(inputs[k] == baseline_entry[k] for k in ('base','kernel','platform','boot','firmware','state_requirements')),
                'selected Base/Kernel/boot policy differs from baseline')
    unchanged_areas()
    if action == 'after':
        result = subprocess.run([str(RUNTIME/'bin/mpm'), 'ports', 'list'], check=True)
        subprocess.run(['/var/lib/mojt/ports/current/bin/nvim', '--version'], check=True)
        write_data(WORK/'after.json', json.dumps(status,indent=2).encode())
        print('PASS: B running and selected; exact Base/Kernel/boot policy preserved; Ports and nvim inspected.')
        return 0
    for name, expected in FILES.items():
        require(hashlib.sha256((RUNTIME/name if name.startswith('tools/') else RUNTIME/'share/man/man1/mpm.1').read_bytes()).hexdigest() == expected,
                'running test tooling differs: '+name)
    require(sys.stdin.isatty(), 'interactive test needs a terminal')
    print('Enter an invalid number, then q.' if action == 'cancel' else
          'Choose B: '+probe['version']+' / '+probe['artifact']+', then confirm NEXT boot.', flush=True)
    log = WORK/(action+'.log')
    require(not log.exists(), 'test log already exists; keep evidence before repeating this step')
    started = time.monotonic()
    # Inherit the terminal on stdin; relay stdout/stderr without piping input.
    with log.open('xb') as output:
        output.write((json.dumps(dict(before=status, baseline=value['baseline'], candidate=candidate, probe=probe))+'\n').encode());output.flush()
        child = subprocess.Popen([str(RUNTIME/'bin/mpm'), 'system', 'activate'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            while data := child.stdout.read1(4096):
                sys.stdout.buffer.write(data);sys.stdout.buffer.flush();output.write(data);output.flush()
            code = child.wait()
        except BaseException:
            child.terminate();child.wait();raise
        after = mpm('system', 'status', '--json')
        output.write(('\n'+json.dumps(dict(returncode=code, elapsed_seconds=time.monotonic()-started, after=after))+'\n').encode())
    require(after['running'] == status['running'], 'running System identity changed')
    unchanged_areas()
    if action == 'cancel':
        require(code != 0 and after['selected'] == status['selected'], 'cancellation did not preserve next boot')
        print('PASS: invalid choice/cancellation left next boot unchanged.')
    else:
        require(code == 0 and after['selected']['artifact'] == probe['artifact'], 'expected B for next boot')
        require(after['selected']['deployment'] != status['selected']['deployment'], 'no changed boot selection')
        print('PASS: B selected; A still running. Logs: '+str(log)+'; reboot deliberately when ready.')
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('prepare', 'install', 'activate', 'status', 'cancel', 'test', 'after'))
    args = p.parse_args(argv)
    require(os.geteuid() == 0 and os.path.ismount(ROOT) and os.path.ismount(RUNTIME),
            'run as root on the installed native Mojt, not on the Debian host')
    sys.path.insert(0, str(RUNTIME / 'tools'))
    import mpm_base as base
    import mpm_transaction as tx
    os.environ['PATH'] = str(RUNTIME / 'libexec/mpm/bin') + ':' + str(RUNTIME / 'bin') + ':/usr/bin:/bin'
    require(WORK.resolve() == WORK, 'linked work directory')
    tx.protected_directory(WORK, write=True, label='repair workspace')
    WORK.mkdir(mode=0o700, exist_ok=True)
    with tx.file_lock(WORK / '.lock'):
        state = WORK / 'state.json'
        if args.action == 'status':
            print(json.dumps(base.read(state) if state.exists() else dict(format=FORMAT, phase='not-prepared'), indent=2))
            return 0
        if args.action == 'prepare':
            require(not state.exists() and not (WORK / 'package').exists(), 'repair already prepared; use status/install')
            before = baseline()
            downloads = WORK / 'downloads'; downloads.mkdir(mode=0o700, exist_ok=True)
            data = fetch(downloads)
            print('Packaging native System generation on the SSD...', flush=True)
            result = package(ROOT, before['artifact'], data, WORK / 'package')
            probe = package(ROOT, before['artifact'], data, WORK / 'probe', label='system-activation-B', revision=2)
            require(baseline() == before, 'boot selection changed during preparation')
            base.io.write_json(state, dict(format=FORMAT, baseline=before, candidate=result, probe=probe, source_revision=REVISION))
            tx.sync_directory(WORK)
            print('READY: ' + result['label'] + ' / ' + result['version'])
            print('Packages prepared only. Running System and next boot unchanged.')
            return 0
        value = base.read(state)
        require(value['format'] == FORMAT and value['source_revision'] == REVISION, 'unsupported repair checkpoint')
        candidate = value['candidate']; before = value['baseline']
        if args.action in ('cancel', 'test', 'after'):
            return exercise(args.action, value)
        require(baseline() == before, 'running or selected deployment differs from the preparation baseline')
        print(candidate['label'] + ' / ' + candidate['version'] + ' / ' + candidate['artifact'], flush=True)
        if args.action == 'install':
            if input('Install test generations A and B and keep next boot unchanged? [y/N] ').strip().lower() != 'y':
                print('Cancelled.'); return 0
            print('Installing A and B through the running System MPM...', flush=True)
            mpm('system', 'install', '--from-file', str(WORK / 'package' / candidate['generation']),
                '--expected-id', candidate['artifact'], '--dependency-file', str(WORK / 'package' / candidate['component']), '-y')
            mpm('system', 'install', '--from-file', str(WORK / 'probe' / value['probe']['generation']),
                '--expected-id', value['probe']['artifact'], '--dependency-file', str(WORK / 'probe' / value['probe']['component']), '-y')
            require(baseline() == before, 'unexpected boot selection change')
            print('READY: generation installed. Use activate to select it for next boot.')
        else:
            if input('Prepare and select this generation for next boot? [y/N] ').strip().lower() != 'y':
                print('Cancelled.'); return 0
            print('Preparing boot deployment through installed MPM...', flush=True)
            mpm('system', 'upgrade', '--artifact', candidate['artifact'], '-y')
            print('READY: new System selected for next boot; previous deployment retained.')
            print('Reboot when ready. The script does not reboot automatically.')
        return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError, EOFError, KeyboardInterrupt) as error:
        print('Mojt activation test: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
