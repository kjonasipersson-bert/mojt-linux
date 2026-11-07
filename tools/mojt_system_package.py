# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Package an already assembled System profile, never build or activate it."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import mojt_artifact as artifact
import mojt_system_manifest as manifests
import mpm_base as base
import mpm_management as management
import mpm_native_cache as cache
import mpm_system as system
import mpm_system_model as model
import mpm_transaction as tx

FORMAT = 'mojt-system-package-kit-v1'


def nix_references(manifest, adapter):
    """Read the explicit helper's existing store; no realise, build, root or profile writes."""
    data = manifest['description']['artifacts'].get('nix')
    artifact.require(type(data) is dict, 'assembled profile needs Nix provenance')
    rows = data['objects'];artifact.require(type(rows) is list and 0 < len(rows) <= 4096, 'unbounded System closure')
    expected = {r['path']:r['nar_hash'] for r in rows}
    artifact.require(len(expected) == len(rows), 'duplicate System store object')
    from mpm_nix_binary import store_path
    for path in expected:store_path(path)
    outputs = sorted({r['output'] for r in data['packages'].values()} | {data['source']['store']})
    artifact.require(0 < len(outputs) <= model.MAX_ROWS, 'too many System outputs')
    actual = sorted(adapter.runner([adapter.binary, '--query', '--requisites', *outputs]).splitlines())
    artifact.require(actual == sorted(expected), 'live System closure differs from assembled provenance')
    hashes = adapter.runner([adapter.binary, '--query', '--hash', *actual]).splitlines()
    artifact.require(hashes == [expected[p] for p in actual], 'System NAR hashes differ')
    adapter.runner([adapter.binary, '--verify-path', *actual])
    refs = []
    for output in outputs:
        store_path(output)
        paths = sorted(adapter.runner([adapter.binary, '--query', '--requisites', output]).splitlines())
        artifact.require(set(paths) <= set(expected) and output in paths, 'unbound System output closure')
        directory = Path(output) / 'bin'
        commands = sorted(p.name for p in directory.iterdir() if p.is_file() and os.access(p, os.X_OK)) if directory.is_dir() else []
        ref = dict(provider='nix', identity=dict(format='mojt-nix-output-v1', output=output,
            closure=[dict(path=p, nar_hash=expected[p]) for p in paths], commands=commands))
        adapter.describe(ref, None)
        for name in commands:adapter.verify_path(ref, str(directory / name))
        refs.append(ref)
    return sorted(refs, key=artifact.canonical)


def raw(value):return artifact.canonical(value) + b'\n'


def evidence(value):return dict(sha256=hashlib.sha256(value).hexdigest(), size=len(value))


def expanded_size(path):
    """Bound the entire tar stream, including headers/PAX metadata and padding."""
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(['zstd', '-q', '-d', '-c', '--', str(path)], stdout=subprocess.PIPE, stderr=errors)
        try:
            length = 0
            while chunk := process.stdout.read(128 * 1024):
                length += len(chunk)
                artifact.require(length <= 2 * artifact.MAX_CONTENT, 'System archive expansion exceeds limit')
            artifact.require(process.wait() == 0, 'cannot measure System archive expansion')
            return length
        finally:
            process.stdout.close()
            if process.poll() is None:process.terminate();process.wait()


def source_metadata(stage, destination, results):
    """An ordinary owner-authorized local kit, using existing source/cache wires."""
    name = 'system-kit';channel = 'local'
    maximum = max(r['archive']['size'] for r in results.values())
    expanded = max(expanded_size(stage / role / r['archive']['file']) for role, r in results.items())
    policy = base.record(cache.POLICY, dict(name=name, provider='native', channel=channel,
        root=str(destination), max_archive=max(1, maximum), max_expanded=max(1, expanded)))
    source = base.record('mojt-source-v1', dict(name=name, provider='native', channel=channel,
        location=dict(kind='local-directory', path=str(destination)), trust=dict(kind='explicit-local', policy=policy['id'])))
    offers, candidates = [], []
    for role, result in results.items():
        body = result['artifact'];archive = result['archive'];v = body['version']
        descriptor = (stage / role / 'artifact.json').read_bytes()
        candidates.append(dict(name=body['name'], release_id=v['release_id'], upstream_version=v['upstream'],
            version_scheme=v['scheme'], package_revision=v['revision'], revision_scheme='mojt-r-v1', source='local', artifact=body['id'],
            integrity=dict(sha256=archive['sha256']), stability='stable', compatibility='unknown'))
        offers.append(dict(reference=dict(provider='native', artifact=body['id']),
            descriptor=dict(path=role + '/artifact.json', **evidence(descriptor)),
            archives=[dict(sha256=archive['sha256'], size=archive['size'], paths=[role + '/' + archive['file']])]))
    catalog = dict(format='mpm-release-catalog-v1', area='system', name=name, platform=results['generation']['artifact']['platform'],
        channel=channel, sources=dict(local=dict(backend='native', identity=dict(format=FORMAT))), candidates=candidates)
    catalog_raw = raw(catalog)
    mapping = base.record('mojt-acquisition-map-v1', dict(catalog_sha256=evidence(catalog_raw)['sha256'],
        offers=sorted(offers, key=lambda row:artifact.canonical(row['reference']))))
    snapshot = base.record('mojt-source-snapshot-v1', dict(source=source['id'],
        catalog=dict(format=catalog['format'], **evidence(catalog_raw)),
        acquisition=dict(id=mapping['id'], **evidence(raw(mapping))), provider_snapshot=None, trust_policy=policy['id']))
    for name, value in (('policy', policy), ('source', source), ('catalog', catalog), ('acquisition-map', mapping), ('snapshot', snapshot)):
        (stage / (name + '.json')).write_bytes(raw(value))
    cache.metadata(policy_file=stage / 'policy.json', source=source, snapshot=snapshot,
        catalog_bytes=catalog_raw, acquisition_bytes=raw(mapping))
    return dict(source=source['id'], snapshot=snapshot['id'])


def package(tree, generation, upstream, revision, output, *, adapter):
    tree = Path(tree).absolute();output = Path(output).absolute()
    artifact.require(type(generation) is str and generation not in ('.', '..', 'current') and '/' not in generation, 'require an exact generation label')
    profile = tx.protected_directory(tree / 'system' / generation, label='assembled System')
    tx.protected_directory(output.parent, write=True, label='System package output')
    artifact.require(not os.path.lexists(output), 'System kit output already exists')
    artifact.require(not output.is_relative_to(tree) and not tree.is_relative_to(output), 'System inputs and output must be disjoint')
    base.io.regular(profile / 'manifest.json')
    manifest = manifests.validate(artifact.read_json(profile / 'manifest.json'));d = manifest['description']
    artifact.require(d['label'] == generation and system.inventory(profile) == d['profile'], 'assembled System profile differs from manifest')
    support = management.retained(profile, manifest)
    artifact.require(support is not None, 'assembled System lacks measured management support')
    refs = nix_references(manifest, adapter)
    outputs = sorted({os.readlink(p) for p in profile.rglob('*') if p.is_symlink()
        and os.readlink(p) in ('/run/mojt-privileged/passwd', '/run/mojt-privileged/sudo')})
    system.verify_links(profile, refs, {'nix':adapter}, outputs)
    artifact.require(type(revision) is int and revision >= 0, 'System packaging requires an explicit numeric revision')
    version = dict(upstream=upstream, scheme='dotted-v1', revision=revision)
    artifact.version(version)
    provenance = dict(assembled_manifest=manifest['id'], packer_sha256=artifact.file_sha(__file__))
    with tempfile.TemporaryDirectory(prefix='.mojt-system-package-', dir=output.parent) as temporary:
        work = Path(temporary);stage = work / 'kit';stage.mkdir();content = work / 'component'
        shutil.copytree(profile, content, symlinks=True,
            ignore=lambda directory, names:{'manifest.json', management.FILENAME} if Path(directory) == profile else set())
        artifact.require(system.inventory(content) == {p:r for p,r in d['profile'].items() if p != management.FILENAME},
                         'copied System profile differs from measured input')
        spec = dict(format=artifact.SPEC_FORMAT, kind='system', name='mojt-system-runtime', platform=d['architecture'] + '-linux',
            version=version, dependencies=refs, requirements={}, provides={}, provenance=provenance, metadata=dict(system_role='component',
                **({'runtime_outputs':dict(format='mojt-profile-runtime-outputs-v1', producer='mojt-privileged-v1', paths=outputs)} if outputs else {})))
        component = artifact.pack(content, spec, stage / 'component', numeric_owner=(0, 0))
        ref = dict(provider='native', artifact=component['artifact']['id'])
        actions = base.record(model.LIFECYCLE, dict(platform=spec['platform'], actions=[]))
        mappings = [dict(path=p.name, source=dict(reference=ref, path=p.name)) for p in sorted(content.iterdir())]
        units = content / 'units';enabled = set()
        for directory in units.glob('*.wants'):
            enabled.update(p.name for p in directory.iterdir())
        target = units / 'mojt.target'
        if target.is_file() and not target.is_symlink():
            for line in target.read_text().splitlines():
                if line.startswith(('Wants=', 'Requires=')):enabled.update(line.split('=', 1)[1].split())
        composition = base.record(model.FORMAT, dict(label=generation, platform=spec['platform'], components=[dict(role='runtime', reference=ref)],
            requirements=dict(base_abi=[dict(name=k, value=v) for k,v in sorted(d['requirements']['base_abi'].items())],
                state_layout=d['requirements']['state_layout'], kernel_capabilities=[], host_capabilities=[]),
            management=support['description']['management'], state=support['description']['state'], profile=mappings,
            services=[dict(unit=name, enabled=True) for name in sorted(enabled) if name.endswith('.service')],
            runtime=dict(interpreter='bin/python3', frontend='bin/mpm', module_root='tools'),
            lifecycle=dict(format=model.LIFECYCLE, id=actions['id'], path='payload/lifecycle.json')))
        model.supported(composition, actions)
        generation_source = work / 'generation';generation_source.mkdir()
        (generation_source / 'composition.json').write_bytes(raw(composition));(generation_source / 'lifecycle.json').write_bytes(raw(actions))
        spec = dict(spec, name='mojt-system', dependencies=[ref], metadata=dict(system_role='generation',
            composition=dict(format=model.FORMAT, id=composition['id'], path='payload/composition.json'),
            deployment_contract=dict(format='mojt-system-content-only-v1', initialization='profile-services-not-reviewed')))
        generation_result = artifact.pack(generation_source, spec, stage / 'generation',
            attachments={'assembled-manifest.json':profile / 'manifest.json'}, numeric_owner=(0, 0))
        archive = stage / 'generation' / generation_result['archive']['file']
        # Validate the real archives, mappings and links without target writes.
        system.install(work, archive, generation_result['artifact']['id'],
            dependency_files=[stage / 'component' / component['archive']['file']], dry_run=True, adapters={'nix':adapter})
        source = source_metadata(stage, output, dict(component=component, generation=generation_result))
        kit = base.record(FORMAT, dict(generation=generation_result['artifact']['id'], component=ref['artifact'],
            assembled_manifest=manifest['id'], source=source, version=artifact.version(version), runtime_outputs=outputs, deployment_ready=False))
        (stage / 'kit.json').write_bytes(raw(kit))
        artifact.require(system.inventory(profile) == d['profile'] and artifact.read_json(profile / 'manifest.json') == manifest, 'System inputs changed during packaging')
        for p in stage.rglob('*'):
            if p.is_file():
                with p.open('rb') as stream:os.fsync(stream.fileno())
        for p in sorted((p for p in stage.rglob('*') if p.is_dir()), key=lambda p:len(p.parts), reverse=True):tx.sync_directory(p)
        tx.sync_directory(stage);tx.publish(stage, output)
    return dict(kit=kit, output=str(output), changed=True, activation=False)
