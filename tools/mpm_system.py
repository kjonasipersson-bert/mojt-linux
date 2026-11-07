# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Content-only native System composition install. No state effects or selection."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile

import mojt_artifact as artifact
import mojt_system_manifest as manifests
import mpm_base as base
import mpm_management as management
import mpm_native_io as io
import mpm_system_model as model
import mpm_transaction as tx

REGISTRY = 'mojt-system-registry-v1'
REALIZATION = 'mojt-system-realization-v1'
PLAN = 'mojt-system-install-plan-v1'
MANAGEMENT_SUPPORT = [{'family': 'mpm-system', 'read': [1], 'write': [1], 'capabilities': []}]
CODE = ('mpm_system.py', 'mpm_system_model.py', 'mpm_native_io.py', 'mpm_base.py',
        'mojt_artifact.py', 'mojt_system_manifest.py', 'mpm_management.py', 'mpm_transaction.py')
require = base.require


def target(value, *, write=False):
    root = base.target(value, write=write)
    for name in ('artifacts/system', 'artifacts/system/installed', 'realizations/system'):
        tx.protected_directory(root / name, write=write, label='System storage')
    return root


def registry(root):
    directory = root / 'artifacts/system'
    if not management.present(directory):return None
    io.directory(directory)
    require({p.name for p in directory.iterdir()} == {'registry.json', 'installed'}, 'incomplete/unmanaged System registry')
    info = base.store_info(root);require(info is not None, 'System registry lacks installation identity')
    value = base.read(directory / 'registry.json');d = base.envelope(value, REGISTRY)
    artifact.fields(d, ('installation', 'layout'))
    require(d == dict(installation=info['installation'], layout='system-objects-v1'), 'unsupported System registry layout/installation')
    io.directory(directory / 'installed')
    return value


def object_path(root, identifier):return root / 'artifacts/system/installed' / io.identifier(identifier)

def realization_path(root, identifier):return root / 'realizations/system' / io.identifier(identifier)


def stored_mode(row):return row['mode'] & 0o555


def acceptable(body, role=None):
    artifact.validate_descriptor(body)
    require(body['kind'] == 'system' and body['platform'] == os.uname().machine + '-linux', 'System kind/platform differs')
    require(role is None or body['metadata']['system_role'] == role, 'System component/generation role differs')
    require(not body['requirements'], 'unsupported outer System requirements')
    require(all(row['type'] in ('file', 'directory') and row['uid'] == row['gid'] == 0
                and not row['mode'] & 0o7022 and row['mode'] & 0o400 and (row['type'] != 'directory' or row['mode'] & 0o100) for row in body['files']),
            'System install requires protected root-owned ordinary files/directories; links need a supported adapter')
    if body['metadata']['system_role'] == 'component':require(not body['dependencies'], 'System component transitive dependencies are not supported yet')


def manager():
    return dict(provider='mojt-manager-code', identity=dict(files={n:artifact.file_sha(Path(__file__).with_name(n)) for n in CODE}))


def object_record(root, identifier, *, verify=False):
    marker = registry(root);require(marker is not None, 'missing System registry')
    path = object_path(root, identifier);require(stat.S_IMODE(io.directory(path).st_mode) == 0o555, 'unsealed System object')
    body = base.read(path / 'artifact.json');acceptable(body)
    require(body['id'] == identifier, 'System object identity differs')
    receipt = base.read(path / 'installed.json');d = base.envelope(receipt, base.RECEIPT)
    artifact.fields(d, ('installation', 'kind', 'artifact', 'archive', 'representation', 'dependencies', 'trust', 'installed_utc', 'uid', 'manager'), ('acquisition',))
    require(d['installation'] == marker['description']['installation'] and d['kind'] == 'system' and d['artifact'] == identifier
            and d['representation'] == 'system-object-v1' and d['dependencies'] == body['dependencies'], 'System receipt binding differs')
    artifact.fields(d['archive'], ('sha256', 'size'))
    require(type(d['archive']['sha256']) is str and re.fullmatch('[0-9a-f]{64}', d['archive']['sha256'])
            and type(d['archive']['size']) is int and 0 <= d['archive']['size'] <= io.MAX_ARCHIVE, 'invalid System encoding evidence')
    require(type(d['uid']) is int and d['uid'] == path.stat().st_uid
            and type(d['installed_utc']) is str and datetime.fromisoformat(d['installed_utc'].replace('Z', '+00:00')).utcoffset() == timezone.utc.utcoffset(None), 'invalid System installer/time')
    artifact.fields(d['manager'], ('provider', 'identity'));artifact.fields(d['manager']['identity'], ('files',))
    require(d['manager']['provider'] == 'mojt-manager-code' and set(d['manager']['identity']['files']) == set(CODE)
            and all(type(v) is str and re.fullmatch('[0-9a-f]{64}', v) for v in d['manager']['identity']['files'].values()), 'invalid System installer identity')
    require(d['trust'] == io.acquisition_trust(d.get('acquisition'), identifier, **dict(checksum=d['archive']['sha256'], size=d['archive']['size'])), 'System origin differs')
    for name in ('artifact.json', 'installed.json', 'archive.tar.zst'):
        item = io.regular(path / name)
        require(item.st_uid == path.stat().st_uid and stat.S_IMODE(item.st_mode) == 0o444, 'unsafe System object metadata')
    if verify:
        require((path / 'archive.tar.zst').stat().st_size == d['archive']['size'] and artifact.file_sha(path / 'archive.tar.zst') == d['archive']['sha256'], 'retained System archive damaged')
        require(artifact.verify(path / 'archive.tar.zst', identifier) == body, 'retained System descriptor damaged')
        expected = {'artifact.json', 'installed.json', 'archive.tar.zst', *(r['path'] for r in body['files'])}
        require({p.relative_to(path).as_posix() for p in path.rglob('*')} == expected, 'System object inventory differs')
        for row in body['files']:
            file = path / row['path'];info = io.directory(file) if row['type'] == 'directory' else io.regular(file)
            require(info.st_uid == info.st_gid == 0 and stat.S_IMODE(info.st_mode) == stored_mode(row), 'System object mode/owner differs')
            if row['type'] == 'file':require(info.st_size == row['size'] and artifact.file_sha(file) == row['sha256'], 'System object bytes differ')
    return body, receipt


def composition(path, body):
    acceptable(body, 'generation')
    binding = body['metadata'].get('composition');artifact.fields(binding, ('format', 'id', 'path'))
    require(binding['format'] == model.FORMAT and binding['path'] == 'payload/composition.json', 'unsupported System composition binding')
    value = base.read(path / binding['path']);actions = base.read(path / 'payload/lifecycle.json')
    d = model.supported(value, actions)
    require(value['id'] == binding['id'] and d['platform'] == body['platform'], 'System composition identity/platform differs')
    expected = sorted({artifact.canonical(r['reference']) for r in d['components']})
    require(sorted(artifact.canonical(r) for r in body['dependencies']) == expected, 'System descriptor/composition dependencies differ')
    require(all(r['path'] in ('payload', 'payload/composition.json', 'payload/lifecycle.json') or r['path'].startswith('provenance/') or r['path'] == 'provenance' for r in body['files']), 'unmapped generation payload; use a component')
    return value, actions


def inventory(profile):
    result = {}
    for path in sorted(profile.rglob('*')):
        name = path.relative_to(profile).as_posix()
        if name == 'manifest.json':continue
        info = path.lstat()
        require(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'non-regular System profile')
        result[name] = dict(directory=True, mode=stat.S_IMODE(info.st_mode)) if path.is_dir() else dict(sha256=artifact.file_sha(path), mode=stat.S_IMODE(info.st_mode))
    return result


def build_profile(profile, body, value, parts):
    d = value['description'];planned = {};total = 0
    for mapping in d['profile']:
        identifier = model.reference(mapping['source']['reference']);component, source = parts[identifier]
        prefix = 'payload/' + mapping['source']['path']
        selected = [r for r in component['files'] if r['path'] == prefix or r['path'].startswith(prefix + '/')]
        require(selected and selected[0]['path'] == prefix, 'missing native component source: ' + prefix)
        for row in selected:
            name = mapping['path'] + row['path'][len(prefix):]
            require(name not in planned, 'duplicate materialized System path')
            planned[name] = (row, source / row['path']);total += row.get('size', 0)
    require(len(planned) <= artifact.MAX_ENTRIES and total <= artifact.MAX_CONTENT, 'materialized System exceeds content limits')
    profile.mkdir();modes = {profile:0o555}
    for name in sorted(planned, key=lambda p:(len(p.split('/')), p)):
        row, source = planned[name];destination = profile / name
        for parent in reversed(destination.parents):
            if parent == profile or profile in parent.parents:
                parent.mkdir(exist_ok=True);modes.setdefault(parent, 0o555)
        if row['type'] == 'directory':destination.mkdir(exist_ok=True)
        else:
            require(artifact.file_sha(source) == row['sha256'], 'System source component changed')
            with source.open('rb') as origin, destination.open('xb') as output:
                shutil.copyfileobj(origin, output, 128 * 1024);output.flush();os.fchmod(output.fileno(), stored_mode(row));os.fsync(output.fileno())
        modes[destination] = stored_mode(row)
    runtime = d['runtime']
    for name in ('interpreter', 'frontend'):
        path = profile / runtime[name]
        require(path.is_file() and path.stat().st_mode & 0o001, 'System runtime must be a public executable: ' + runtime[name])
    tools = profile / runtime['module_root'];require(tools.is_dir() and modes.get(tools, 0o555) & 0o005 == 0o005, 'missing/private System management modules')
    for name in ('interpreter', 'frontend', 'module_root'):
        for parent in (profile / runtime[name]).parents:
            if parent == profile or profile in parent.parents:
                require(modes.get(parent, 0o555) & 0o001, 'private System runtime ancestor')
    names = management.literal(tools / 'mojt_system.py', 'MPM_FILES')
    for name in names:
        management.path(name);require('/' not in name and (tools / name).is_file() and (tools / name).stat().st_mode & 0o004, 'incomplete/unreadable delivered MPM: ' + str(name))
    support = management.produce(tools, names)
    require(support['description']['management'] == d['management'] and support['description']['state'] == d['state'], 'System composition overstates bundled management/schema support')
    own = management.context(registries=[dict(family='mpm-system', version=1, capabilities=[], evidence=body['id'])])
    checked = management.check_transition(management.current(), support, own)
    require(checked['compatible'], 'System cannot manage its installed representation: ' + '; '.join(checked['errors']))
    for service in d['services']:require((profile / 'units' / service['unit']).is_file(), 'missing declared System unit')
    io.write_json(profile / management.FILENAME, support)
    if os.geteuid() == 0:
        for path in [*profile.rglob('*'), profile]:os.chown(path, 0, 0)
    for path, mode in sorted(modes.items(), key=lambda r:len(r[0].parts), reverse=True):path.chmod(mode)
    ports = dict(read=list(management.literal(tools / 'mpm_ports_cli.py', 'SUPPORTED_STATE_FORMATS')),
                 write=list(management.literal(tools / 'mpm_ports_cli.py', 'SUPPORTED_STATE_FORMATS')),
                 capabilities=list(management.literal(tools / 'mpm_ports_cli.py', 'SUPPORTED_CAPABILITIES')))
    measured = manifests.create(dict(label=d['label'], architecture=d['platform'].removesuffix('-linux'),
        requirements=dict(base_abi={r['name']:r['value'] for r in d['requirements']['base_abi']}, state_layout=d['requirements']['state_layout']),
        support=dict(ports=ports),
        provides=sorted('/run/mojt-system/' + p.relative_to(profile).as_posix() for p in (profile / 'bin').iterdir() if p.is_file() and p.stat().st_mode & 0o111),
        artifacts=dict(native=dict(components=d['components'])), provenance=dict(artifact=body['id'], composition=value['id'], assembler=manager()), profile=inventory(profile)))
    require(len(artifact.canonical(measured)) <= artifact.MAX_METADATA, 'System profile manifest exceeds metadata limit')
    # The root is private and read-only only after both generated files exist.
    profile.chmod(0o755);io.write_json(profile / 'manifest.json', measured);profile.chmod(0o555)
    for directory in [p for p in profile.rglob('*') if p.is_dir()] + [profile]:io.sync_directory(directory)
    return measured


def realization(root, identifier, *, verify=False):
    path = realization_path(root, identifier)
    if not management.present(path):return None
    require(stat.S_IMODE(io.directory(path).st_mode) == 0o555 and {p.name for p in path.iterdir()} == {'profile', 'realization.json'}, 'incomplete/unsealed System realization')
    value = base.read(path / 'realization.json');d = base.envelope(value, REALIZATION)
    artifact.fields(d, ('installation', 'artifact', 'receipt', 'composition', 'manifest', 'dependencies'))
    body, receipt = object_record(root, identifier, verify=verify);require(body['metadata']['system_role'] == 'generation', 'component cannot be a System generation')
    comp, unused = composition(object_path(root, identifier), body)
    require(d['installation'] == receipt['description']['installation'] and d['artifact'] == identifier and d['receipt'] == receipt['id']
            and d['composition'] == comp['id'], 'System realization binding differs')
    require(set(d['dependencies']) == {r['artifact'] for r in body['dependencies']}, 'System realization dependencies differ')
    for dependency, identity in d['dependencies'].items():
        dependency_body, dependency_receipt = object_record(root, dependency, verify=verify)
        acceptable(dependency_body, 'component');require(dependency_receipt['id'] == identity, 'retained System component receipt differs')
    measured = manifests.validate(base.read(path / 'profile/manifest.json'))
    require(d['manifest'] == measured['id'] and measured['description']['provenance']['artifact'] == identifier
            and measured['description']['provenance']['composition'] == comp['id'], 'System profile manifest binding differs')
    if verify:require(inventory(path / 'profile') == measured['description']['profile'], 'System profile content/modes damaged')
    return value


def _initialize(root, info):
    directory = root / 'artifacts/system'
    if management.present(directory):registry(root)
    else:
        stage = Path(tempfile.mkdtemp(prefix='.system-registry-', dir=root / 'artifacts'))
        try:
            (stage / 'installed').mkdir(mode=0o755)
            io.write_json(stage / 'registry.json', base.record(REGISTRY, dict(installation=info['installation'], layout='system-objects-v1')))
            io.sync_directory(stage / 'installed');stage.chmod(0o755);io.sync_directory(stage);tx.publish(stage, directory)
        finally:io.clean_stage(stage)
    (root / 'realizations/system').mkdir(mode=0o755, exist_ok=True);io.sync_directory(root / 'realizations')


def _retain(root, info, body, source, encoding, acquisition=None):
    dest = object_path(root, body['id'])
    if management.present(dest):return object_record(root, body['id'], verify=True)[1]
    stage = Path(tempfile.mkdtemp(prefix='.install-', dir=dest.parent))
    try:
        checksum, size = io.frozen_copy(source / 'archive.tar.zst', stage / 'archive.tar.zst')
        require(dict(sha256=checksum, size=size) == encoding and artifact.verify(stage / 'archive.tar.zst', body['id']) == body, 'System import changed after preview')
        io.unpack_regular(stage / 'archive.tar.zst', body, stage)
        for row in reversed(body['files']):
            os.chown(stage / row['path'], 0, 0);(stage / row['path']).chmod(stored_mode(row))
        receipt = base.record(base.RECEIPT, dict(installation=info['installation'], kind='system', artifact=body['id'], archive=encoding,
            representation='system-object-v1', dependencies=body['dependencies'], trust=io.acquisition_trust(acquisition, body['id'], checksum, size),
            installed_utc=datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'), uid=os.geteuid(), manager=manager(),
            **({'acquisition':acquisition} if acquisition else {})))
        io.write_json(stage / 'artifact.json', body);io.write_json(stage / 'installed.json', receipt)
        for row in body['files']:
            if row['type'] == 'directory':io.sync_directory(stage / row['path'])
        os.chown(stage, 0, 0);stage.chmod(0o555);io.sync_directory(stage);tx.publish(stage, dest)
    finally:io.clean_stage(stage)
    return receipt


def _freeze(archive, work, expected=None, *, budget=artifact.MAX_CONTENT):
    work.mkdir();checksum, size = io.frozen_copy(archive, work / 'archive.tar.zst')
    body = artifact.verify(work / 'archive.tar.zst', expected);acceptable(body)
    require(sum(r.get('size', 0) for r in body['files']) <= budget, 'System dependency bundle exceeds content budget')
    io.unpack_regular(work / 'archive.tar.zst', body, work)
    for row in reversed(body['files']):(work / row['path']).chmod(stored_mode(row))
    return body, dict(sha256=checksum, size=size)


def target_identity(root):
    if not management.present(root):return None
    info = io.directory(root)
    return dict(device=info.st_dev, inode=info.st_ino)


def install(root, archive, identifier, *, dependency_files=(), dry_run=False, yes=False, acquisition=None):
    io.identifier(identifier);root = target(root, write=not dry_run)
    physical = target_identity(root)
    require(dry_run or os.geteuid() == 0, 'System realization requires an administrator')
    require(type(dependency_files) in (list, tuple) and len(dependency_files) <= 64, 'too many System dependency archives')
    marker = registry(root)
    if marker and management.present(object_path(root, identifier)):
        body, receipt = object_record(root, identifier, verify=True)
        completed = realization(root, identifier, verify=True)
        if completed:
            if not dry_run:
                io.sync_directory(realization_path(root, identifier));io.sync_directory(realization_path(root, identifier).parent)
            return dict(changed=False, dry_run=dry_run, action='no-change', artifact=identifier, realization=completed['id'], selected='unchanged', running='unchanged')
        archive = object_path(root, identifier) / 'archive.tar.zst';acquisition = receipt['description'].get('acquisition')
    require(archive is not None, 'missing exact System archive')
    with tempfile.TemporaryDirectory(prefix='mojt-system-preview-') as temp:
        work = Path(temp);body, encoding = _freeze(archive, work / 'generation', identifier)
        comp, actions = composition(work / 'generation', body)
        io.acquisition_trust(acquisition, identifier, encoding['sha256'], encoding['size'])
        parts, frozen, encodings = {}, {}, {}
        remaining = artifact.MAX_CONTENT - sum(r.get('size', 0) for r in body['files'])
        required = {r['artifact'] for r in body['dependencies']}
        for n, file in enumerate(dependency_files):
            component, encoded = _freeze(file, work / ('part-' + str(n)), budget=remaining)
            remaining -= sum(r.get('size', 0) for r in component['files'])
            acceptable(component, 'component');dep = component['id']
            require(dep in required and dep not in frozen, 'unexpected/duplicate System dependency archive')
            frozen[dep] = work / ('part-' + str(n));encodings[dep] = encoded;parts[dep] = (component, frozen[dep])
        for dep in required - set(parts):
            require(marker is not None and management.present(object_path(root, dep)), 'missing exact System component: ' + dep + '; supply --dependency-file')
            component, unused = object_record(root, dep, verify=True);acceptable(component, 'component');parts[dep] = (component, object_path(root, dep))
        measured = build_profile(work / 'profile', body, comp, parts)
        require(target_identity(root) == physical, 'System target changed during preview')
        plan = base.record(PLAN, dict(target=str(root), target_identity=physical, installation=base.store_info(root)['installation'] if base.store_info(root) else None,
            artifact=identifier, composition=comp['id'], dependencies=sorted(required), manifest=measured['id'],
            archive=encoding, configuration_changes=False, service_changes=False, selection_changes=False, running_changes=False))
        if dry_run:return dict(plan=plan, changed=False, dry_run=True, archive_verified=True, profile_validated=True)
        if not yes:
            print(json.dumps(plan, indent=2), file=__import__('sys').stderr)
            if input('Install this exact System without changing state or boot? [y/N] ').strip().lower() not in ('y', 'yes'):
                return dict(plan=plan, changed=False, cancelled=True)
        require(target_identity(root) == physical, 'System target changed after preview')
        with base.locked(root, installation_lock=True) as info:
            require(target_identity(root) == physical, 'System target changed while acquiring locks')
            require(plan['description']['installation'] in (None, info['installation']), 'System installation identity changed after preview')
            _initialize(root, info)
            existing = realization(root, identifier, verify=True) if management.present(object_path(root, identifier)) else None
            if existing:return dict(plan=plan, changed=False, realization=existing['id'])
            for dep in sorted(required):
                if dep in frozen:_retain(root, info, parts[dep][0], frozen[dep], encodings[dep])
                else:object_record(root, dep, verify=True)
            receipt = _retain(root, info, body, work / 'generation', encoding, acquisition)
            destination = realization_path(root, identifier)
            require(not management.present(destination), 'refuse to replace a System realization')
            stage = Path(tempfile.mkdtemp(prefix='.install-', dir=destination.parent))
            try:
                retained = {dep:(object_record(root, dep, verify=True)[0], object_path(root, dep)) for dep in required}
                actual = build_profile(stage / 'profile', body, comp, retained)
                require(actual == measured, 'System profile changed after preview')
                dependencies = {dep:object_record(root, dep, verify=True)[1]['id'] for dep in sorted(required)}
                proof = base.record(REALIZATION, dict(installation=info['installation'], artifact=identifier, receipt=receipt['id'], composition=comp['id'], manifest=actual['id'], dependencies=dependencies))
                io.write_json(stage / 'realization.json', proof);stage.chmod(0o555);io.sync_directory(stage)
                tx.publish(stage, destination)
            finally:io.clean_stage(stage)
        return dict(plan=plan, changed=True, artifact=identifier, realization=proof['id'], profile=str(destination / 'profile'),
                    selected='unchanged', running='unchanged', compatibility='not evaluated for a deployment; not boot readiness')


def object_names(root):
    names = []
    with os.scandir(root / 'artifacts/system/installed') as entries:
        for entry in entries:
            require(len(names) < 256, 'System registry exceeds object observation limit')
            names.append(entry.name)
    return sorted(names)


def registry_observation(root):
    root = target(root);marker = registry(root)
    if marker is None:return None
    identities = [marker['id']]
    for name in object_names(root):
        path = root / 'artifacts/system/installed' / name
        require(re.fullmatch('[0-9a-f]{64}', path.name), 'incomplete/unknown System object; inspect before transition')
        body, receipt = object_record(root, 'sha256:' + path.name);identities.extend((body['id'], receipt['id']))
        if body['metadata']['system_role'] == 'generation':
            value = realization(root, body['id'])
            require(value is not None, 'System generation retained without completed realization')
            identities.append(value['id'])
    folder = root / 'realizations/system'
    if management.present(folder):
        with os.scandir(folder) as entries:
            count = 0
            for entry in entries:
                count += 1;require(count <= 256, 'unbounded System realization observation')
                require(re.fullmatch('[0-9a-f]{64}', entry.name) and management.present(object_path(root, 'sha256:' + entry.name)),
                        'incomplete/orphan System realization; inspect before transition')
    return base.record('mojt-system-observation-v1', dict(installation=marker['description']['installation'], records=sorted(identities)))


def status(root, *, verify=False, running_record=None):
    root = target(root)
    from mpm_boot_status import selected
    from mpm_deployment import validate_deployment
    observed = selected(root, running_record) if root.exists() else dict(state='unknown', record=None, reason='target does not exist')
    info = base.store_info(root);marker = registry(root);installed, components, retained, incomplete = [], [], [], []
    if marker:
        for name in object_names(root):
            if name.startswith('.install-'):
                io.directory(root / 'artifacts/system/installed' / name);incomplete.append('artifacts/system/installed/' + name);continue
            require(re.fullmatch('[0-9a-f]{64}', name), 'unknown System object entry')
            identifier = 'sha256:' + name;body, receipt = object_record(root, identifier, verify=verify)
            row = dict(artifact=identifier, version=body['version'], role=body['metadata']['system_role'],
                       dependencies=body['dependencies'], trust=receipt['description']['trust'], acquisition=receipt['description'].get('acquisition'))
            if row['role'] == 'component':components.append(row);continue
            value = realization(root, identifier, verify=verify)
            if value:
                measured = manifests.validate(base.read(realization_path(root, identifier) / 'profile/manifest.json'))
                row.update(label=measured['description']['label'], composition=value['description']['composition'],
                           manifest=measured['id'], realization=value['id'], profile=str(realization_path(root, identifier) / 'profile'))
                installed.append(row)
            else:retained.append(row)
    folder = root / 'realizations/system'
    if management.present(folder):
        for path in folder.iterdir():
            if path.name.startswith('.install-'):io.directory(path);incomplete.append(str(path.relative_to(root)));continue
            require(re.fullmatch('[0-9a-f]{64}', path.name) and any(r['artifact'] == 'sha256:' + path.name for r in installed), 'orphan/unknown System realization')
    def observation(record, reason):
        if record is None:return dict(state='unknown', artifact=None, manifest=None, label=None, deployment=None, reason=reason)
        d = validate_deployment(record)['system']
        matched = [row for row in installed if row['manifest'] == d['manifest']]
        require(len(matched) <= 1, 'ambiguous exact System identity')
        return dict(state='known', artifact=matched[0]['artifact'] if matched else None, manifest=d['manifest'], label=d['generation'],
                    deployment=record['id'], artifact_evidence='exact installed manifest' if matched else 'native artifact unknown; label is not identity')
    return dict(format='mpm-system-status-v1', target=str(root), installation=info['installation'] if info else None,
        installed=installed, components=components, retained=retained, incomplete=sorted(incomplete),
        selected=observation(observed['record'], observed['reason']),
        running=observation(running_record, 'offline target or no authoritative running record'),
        compatibility='installed content is not deployment compatibility, activation or boot readiness')
