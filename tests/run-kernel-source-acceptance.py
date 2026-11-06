#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""One real package on a disposable Mojt VM copy; installation, never selection."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def prepare_repository(archive, lab, name, *, artifact, cache):
    body = artifact.verify(archive)
    repo = lab / 'repository'; repo.mkdir()
    shutil.copyfile(archive, repo / 'kernel.tar.zst')
    descriptor = artifact.canonical(body) + b'\n'
    (repo / 'artifact.json').write_bytes(descriptor)
    def encoded(value):return artifact.canonical(value) + b'\n'
    def evidence(raw):return dict(sha256=hashlib.sha256(raw).hexdigest(), size=len(raw))
    checksum = artifact.file_sha(repo / 'kernel.tar.zst')
    policy = cache.record(cache.POLICY, dict(name=name, provider='native', channel='stable',
        root=str(repo), max_archive=(repo/'kernel.tar.zst').stat().st_size, max_expanded=8*1024**3))
    source = cache.record('mojt-source-v1', dict(name=name, provider='native', channel='stable',
        location=dict(kind='local-directory', path=str(repo)), trust=dict(kind='explicit-local', policy=policy['id'])))
    version = body['version']
    candidate = dict(name=body['name'], release_id=version['release_id'], upstream_version=version['upstream'],
        version_scheme=version['scheme'], source=name, artifact=body['id'], integrity=dict(sha256=checksum),
        stability='stable', compatibility='unknown')
    if version['revision'] is not None:
        candidate.update(package_revision=version['revision'], revision_scheme='mojt-r-v1')
    catalog = encoded(dict(format='mpm-release-catalog-v1', area='kernel', name=body['name'],
        platform=body['platform'], channel='stable', sources={name:dict(backend='native',
        identity=dict(repository='owner-trusted VM acceptance fixture'))}, candidates=[candidate]))
    mapping = cache.record('mojt-acquisition-map-v1', dict(catalog_sha256=evidence(catalog)['sha256'],
        offers=[dict(reference=dict(provider='native', artifact=body['id']),
        descriptor=dict(path='artifact.json', **evidence(descriptor)),
        archives=[dict(sha256=checksum, size=(repo/'kernel.tar.zst').stat().st_size, paths=['kernel.tar.zst'])])]))
    mapping_raw = encoded(mapping)
    snapshot = cache.record('mojt-source-snapshot-v1', dict(source=source['id'],
        catalog=dict(format='mpm-release-catalog-v1', **evidence(catalog)),
        acquisition=dict(id=mapping['id'], **evidence(mapping_raw)),
        provider_snapshot=None, trust_policy=policy['id']))
    for path, raw in ((lab/'policy.json', encoded(policy)), (lab/'source.json', encoded(source)),
        (repo/'snapshot.json', encoded(snapshot)), (repo/'catalog.json', catalog),
        (repo/'acquisition-map.json', mapping_raw)):
        path.write_bytes(raw)
    return body, checksum


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive', type=Path, required=True)
    args = p.parse_args()
    runtime = Path('/run/mojt-system'); disk = Path('/run/mojt-disk')
    if os.geteuid() != 0 or not (runtime/'version').is_file() or not os.path.ismount(disk):
        raise ValueError('run as root inside a disposable Mojt VM copy with its disk mounted')
    if not (runtime/'tools/mpm_kernel_source.py').is_file():
        raise ValueError('the selected System must deliver the new source-install MPM runtime')
    sys.path.insert(0, str(runtime/'tools'))
    import mojt_artifact as artifact
    import mpm_kernel as kernel
    import mpm_native_cache as cache
    from mpm_cli import Runtime
    paths = Runtime()
    os.environ['PATH'] = ':'.join((str(paths.helpers), str(paths.system_bin), '/usr/bin', '/bin'))
    body = artifact.verify(args.archive); kernel.acceptable(body)
    if any(row['artifact'] == body['id'] for row in kernel.status(disk/'kernel')['installed']):
        raise ValueError('artifact already installed: use another package revision with retained build provenance')
    tracked = [Path('/etc/machine-id'), Path('/usr/lib/os-release'), runtime/'version', Path('/run/mojt/deployment.json'),
               Path('/run/mojt/native-kernel-artifact'), Path('/proc/sys/kernel/random/boot_id')]
    tracked += sorted((disk/'boot').rglob('*.cfg')) + sorted((disk/'boot').rglob('*.json'))
    before = {str(path):path.read_bytes() for path in tracked if path.is_file()}
    release = os.uname().release
    lab = Path(tempfile.mkdtemp(prefix='kernel-source-acceptance.', dir='/var/lib/mojt'))
    name = 'kernel-acceptance-' + lab.name.split('.')[-1]
    body, checksum = prepare_repository(args.archive, lab, name, artifact=artifact, cache=cache)
    def call(*command):
        result = subprocess.run([str(runtime/'bin/mpm'), *command], text=True, capture_output=True)
        if result.returncode:
            raise ValueError(result.stderr + result.stdout)
        return json.loads(result.stdout)
    call('source', 'add', name, '--from-file', str(lab/'source.json'), '--policy-file', str(lab/'policy.json'), '-y')
    call('source', 'update', name, '-y')
    command = ('kernel', 'install', '--source', name, '--expected-id', body['id'], '--archive-sha256', checksum)
    preview = call(*command, '--dry-run')
    assert preview['dry_run'] and not preview['changed']
    assert not (disk/'kernel/installed'/body['id'].split(':')[1]).exists()
    result = call(*command, '-y'); assert result['changed']
    target = Path(result['installation']['installed_path'])
    recorded = (target/'installed.json').read_bytes()
    (lab/'repository/kernel.tar.zst').unlink()
    repeat = call(*command, '-y'); assert not repeat['changed'] and repeat['acquisition'] is None
    assert (target/'installed.json').read_bytes() == recorded
    row = next(row for row in kernel.status(disk/'kernel', verify=True)['installed'] if row['artifact'] == body['id'])
    assert row['trust']['kind'] == 'registered-native-source'
    assert row['acquisition']['verification'] == result['acquisition']['record']
    assert os.uname().release == release
    assert all(Path(path).read_bytes() == raw for path,raw in before.items())
    (lab/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print('PASS: installed System MPM joined named source, cache and exact Kernel installation')
    print('PASS: retained source provenance, archive and module tree verified; repeat was a no-op')
    print('PASS: running Kernel, machine identity, Base/System and existing boot records unchanged')
    print('No boot selection or reboot performed. Lab retained:', lab)


if __name__ == '__main__':
    try:main()
    except (OSError, ValueError, KeyError, AssertionError) as error:
        print('Kernel source acceptance:', error, file=sys.stderr)
        sys.exit(1)
