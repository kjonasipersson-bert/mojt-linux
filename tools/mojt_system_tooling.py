#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Package reviewed tooling against an installed native System without selecting it."""
import copy
import hashlib
import os
from pathlib import Path
import shutil
import tempfile


def require(ok, message):
    if not ok:raise ValueError(message)


# These private temporary inputs are consumed by artifact.pack, which syncs the
# verified final archives. They need no per-file durability of their own.
def write_data(path, data):
    require(not path.is_symlink(), 'linked candidate file: ' + str(path))
    for parent in path.parents:
        require(not parent.is_symlink(), 'linked candidate ancestor: ' + str(parent))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    with path.open('xb') as stream:
        stream.write(data); os.fchmod(stream.fileno(), 0o444)


def specification(body, version, provenance):
    return dict(format='mojt-artifact-spec-v1',
        **{k:copy.deepcopy(body[k]) for k in ('kind', 'name', 'platform', 'dependencies', 'requirements', 'provides', 'metadata')},
        version=version, provenance=dict(body['provenance'], activation_test=provenance))


def package(root, baseline, downloads, output, *, label, expected_files, source_revision, revision=1):
    """Copy and verify owned component bytes, never copy/evaluate the Nix store."""
    import mojt_artifact as artifact
    import mpm_base as base
    import mpm_management as management
    import mpm_system as system
    import mpm_system_model as model
    import mpm_system_transition as transition
    import mpm_transaction as tx
    import mojt_system_manifest as manifests
    files=expected_files
    require(set(downloads) == set(files) and all(hashlib.sha256(v).hexdigest() == files[k]
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
    provenance = dict(source_revision=source_revision, files=files, baseline=baseline,
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

