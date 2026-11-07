# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Internal, explicitly authorized missing-default preparation; no install hooks.

This narrow protocol precedes the general saved-plan/lifecycle executor. It is
not called by install, stage, select, login or a package-supplied executable.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import stat
import uuid

import mojt_artifact as artifact
import mpm_base as base
import mpm_transaction as tx

PLAN = 'mojt-defaults-preparation-v1'
APPROVAL = 'mojt-defaults-approval-v1'
RESULT = 'mojt-defaults-result-v1'
REGISTRY = 'state/var/lib/mojt/lifecycle/defaults-v1'
MAX_FILE = 1024 * 1024
MAX_RECORD = 64 * 1024
MAX_ACTIONS = 64
MAX_RUNS = 128
# Literal, measured support for this bounded protocol; not the generic action wire.
MANAGEMENT_SUPPORT = [{'family': 'mpm-defaults', 'read': [1], 'write': [1], 'capabilities': []}]
HANDLER_SUPPORT = [{'type': 'missing-default', 'version': 1, 'phase': 'initialize', 'contract': 'mojt-defaults-preparation-v1'}]
PROTECTED = {'passwd', 'group', 'shadow', 'gshadow', 'machine-id', 'os-release'}
require = base.require


def relative(path):
    require(type(path) is str and 0 < len(os.fsencode(path)) <= 4096,
            'invalid default path')
    parts = path.split('/')
    require(len(parts) <= 64 and all(p not in ('', '.', '..') for p in parts)
            and not any(ord(c) < 32 or ord(c) == 127 or c in '\\:' for c in path),
            'unsafe default path')
    require(parts[0] not in PROTECTED, 'default belongs to a dedicated state handler')
    return parts


def _directory(fd):
    info = os.fstat(fd)
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022,
            'default directory must be root-owned and protected')
    return info


@contextmanager
def directory(path):
    """Walk every component with no-follow dirfds, including the absolute root."""
    path = tx.protected_directory(path, label='defaults/evidence')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = new
        _directory(fd)
        yield fd
    finally:
        os.close(fd)


@contextmanager
def parent(root, path):
    parts = relative(path)
    with directory(root) as top:
        fd = os.dup(top)
        try:
            for part in parts[:-1]:
                new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = new
                _directory(fd)
            yield fd, parts[-1]
        finally:
            os.close(fd)


def identity(path):
    with directory(path) as fd:
        info = os.fstat(fd)
        return dict(device=info.st_dev, inode=info.st_ino)


def _bytes(fd, *, metadata=False):
    info = os.fstat(fd)
    limit = MAX_RECORD if metadata else MAX_FILE
    require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_gid == 0
            and info.st_nlink == 1 and not info.st_mode & 0o7022 and info.st_size <= limit,
            'unsafe/unbounded default or evidence file')
    data = b''
    while len(data) <= limit:
        chunk = os.read(fd, min(65536, limit + 1 - len(data)))
        if not chunk:break
        data += chunk
    after = os.fstat(fd)
    stable = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_uid', 'st_gid', 'st_mode', 'st_nlink')
    require(len(data) <= limit and all(getattr(after, k) == getattr(info, k) for k in stable),
            'file changed during default observation')
    return data, info


def observe(root, path):
    with parent(root, path) as (fd, name):
        try:file = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        except FileNotFoundError:return None
        try:data, info = _bytes(file)
        finally:os.close(file)
    return dict(namespace='etc', path=path, sha256=hashlib.sha256(data).hexdigest(),
                uid=info.st_uid, gid=info.st_gid, mode=stat.S_IMODE(info.st_mode))


def handler():
    # Exact executing manager code, never a path supplied by a package.
    names = sorted({'mpm_defaults.py', *base.MANAGER_FILES})
    return dict(type='missing-default', version=1,
                implementation=dict(provider='mojt-manager-code', identity=dict(
                    files={name: artifact.file_sha(Path(__file__).with_name(name)) for name in names})))


def prepare(root, identifier, paths):
    """Read-only exact plan. Parents must exist; no locks, registry or state writes."""
    root = base.target(root)
    info = base.store_info(root)
    require(info is not None, 'installed Base store required for defaults')
    body, receipt = base.object_record(root, identifier, verify=True)
    realization = base.realization(root, identifier, receipt, verify=True)
    require(realization is not None, 'verified Base realization required')
    tree = base.realization_path(root, identifier) / 'tree/rootfs'
    require(type(paths) in (list, tuple) and 0 < len(paths) <= MAX_ACTIONS
            and all(type(p) is str for p in paths) and len(set(paths)) == len(paths),
            'bounded unique explicit default paths required')
    actions = []
    for path in sorted(paths):
        relative(path)
        # Validate target type/parents now, without opening an existing file for write.
        observe(root / 'state/etc', path)
        with parent(tree / 'usr/etc', path) as (fd, name):
            file = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            try:data, source = _bytes(file)
            finally:os.close(file)
        actions.append(dict(path=path, source=dict(reference=dict(provider='native', artifact=identifier),
                        path='usr/etc/' + path, sha256=hashlib.sha256(data).hexdigest()),
                        uid=0, gid=0, mode=stat.S_IMODE(source.st_mode)))
    d = dict(installation=info['installation'], owner=body['id'], realization=realization['id'],
             target=dict(root=str(root), root_identity=identity(root),
                         etc=identity(root / 'state/etc'), state=identity(root / 'state/var/lib/mojt')),
             handler=handler(), actions=actions)
    result = base.record(PLAN, d)
    require(len(artifact.canonical(result)) <= MAX_RECORD, 'default plan exceeds evidence limit')
    return result


def validate_plan(plan):
    """Read known records across manager revisions without granting authority."""
    d = base.envelope(plan, PLAN)
    require(len(artifact.canonical(plan)) <= MAX_RECORD, 'unbounded default plan')
    artifact.fields(d, ('installation', 'owner', 'realization', 'target', 'handler', 'actions'))
    require(type(d['installation']) is str and re.fullmatch('[0-9a-f]{32}', d['installation']), 'invalid default installation')
    base.io.identifier(d['owner']);base.io.identifier(d['realization'])
    artifact.fields(d['target'], ('root', 'root_identity', 'etc', 'state'))
    target = d['target']['root']
    require(type(target) is str and target.startswith('/') and 0 < len(os.fsencode(target)) <= 4096
            and os.path.normpath(target) == target and not any(ord(c) < 32 or ord(c) == 127 for c in target), 'invalid stored default target')
    for key in ('root_identity', 'etc', 'state'):
        value = d['target'][key];artifact.fields(value, ('device', 'inode'))
        require(all(type(n) is int and 0 <= n < 2**64 for n in value.values()), 'invalid default target identity')
    artifact.fields(d['handler'], ('type', 'version', 'implementation'))
    require(d['handler']['type'] == 'missing-default' and type(d['handler']['version']) is int
            and d['handler']['version'] == 1, 'unsupported stored default handler')
    implementation = d['handler']['implementation'];artifact.fields(implementation, ('provider', 'identity'))
    require(implementation['provider'] == 'mojt-manager-code', 'unsupported stored default implementation')
    artifact.fields(implementation['identity'], ('files',));files = implementation['identity']['files']
    require(type(files) is dict and 'mpm_defaults.py' in files and 0 < len(files) <= 128, 'invalid default manager evidence')
    for name, checksum in files.items():
        require(type(name) is str and re.fullmatch('[A-Za-z0-9_.-]{1,128}', name)
                and name not in ('.', '..') and type(checksum) is str and re.fullmatch('[0-9a-f]{64}', checksum), 'invalid default code identity')
    require(type(d['actions']) is list and 0 < len(d['actions']) <= MAX_ACTIONS, 'invalid default actions')
    paths = []
    for action in d['actions']:
        artifact.fields(action, ('path', 'source', 'uid', 'gid', 'mode'))
        relative(action['path']);paths.append(action['path'])
        source = action['source'];artifact.fields(source, ('reference', 'path', 'sha256'))
        require(source['reference'] == dict(provider='native', artifact=d['owner'])
                and source['path'] == 'usr/etc/' + action['path'] and type(source['sha256']) is str
                and re.fullmatch('[0-9a-f]{64}', source['sha256']), 'invalid default source binding')
        require(type(action['uid']) is type(action['gid']) is type(action['mode']) is int
                and action['uid'] == action['gid'] == 0 and 0 <= action['mode'] <= 0o777
                and not action['mode'] & 0o022, 'unsupported default ownership/mode')
    require(paths == sorted(set(paths)), 'default paths must be sorted and unique')
    return d


def _validated(root, plan):
    d = validate_plan(plan)
    require(prepare(root, d['owner'], [a['path'] for a in d['actions']]) == plan,
            'default plan or target changed; prepare again')
    return d


def invocation(plan):
    base.envelope(plan, PLAN)
    return artifact.digest(dict(format='mojt-defaults-invocation-v1', plan=plan['id']))


def location(root, plan):
    return Path(root) / REGISTRY / plan['description']['installation'] / invocation(plan)[7:]


def _read(path, fmt):
    with directory(path.parent) as fd:
        file = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:data, unused = _bytes(file, metadata=True)
        finally:os.close(file)
    value = artifact.parse_json(data)
    base.envelope(value, fmt)
    return value


def _mkdir(path):
    """Only caller-enumerated registry directories, never configuration parents."""
    with directory(path.parent) as fd:
        try:
            os.mkdir(path.name, 0o700, dir_fd=fd)
        except FileExistsError:pass
        child = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
        try:_directory(child);os.fsync(child)
        finally:os.close(child)
        os.fsync(fd)


def publish(fd, name, data, *, mode=0o600, prefix='.result-'):
    """Complete file then atomic no-overwrite link. Never replace a destination.

    A crash can leave a temp/hardlink requiring diagnosis. Any error after link
    is uncertainty; retain visible content and never undo an observed effect.
    """
    temp = prefix + uuid.uuid4().hex
    file = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
    linked = False
    prepared = None
    try:
        with os.fdopen(file, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fchown(stream.fileno(), 0, 0)
            os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
            prepared = os.fstat(stream.fileno())
        try:os.link(temp, name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
        except FileExistsError:
            os.unlink(temp, dir_fd=fd)
            os.fsync(fd)
            raise
        linked = True
        os.unlink(temp, dir_fd=fd)
        os.fsync(fd)
    except BaseException as error:
        # An asynchronous interruption can land just after the link syscall.
        try:
            visible = os.stat(name, dir_fd=fd, follow_symlinks=False)
            linked = linked or (prepared is not None and
                (visible.st_dev, visible.st_ino) == (prepared.st_dev, prepared.st_ino))
        except OSError:pass
        if linked:
            raise tx.PublicationUncertain('default/evidence publication uncertain; retain and inspect') from error
        # Keep incomplete temp as evidence; do not mistake it for a final record.
        raise


def _write(path, value):
    data = artifact.canonical(value)
    require(len(data) <= MAX_RECORD, 'default result exceeds evidence limit')
    with directory(path.parent) as fd:publish(fd, path.name, data)


def _approval(plan):
    return base.record(APPROVAL, dict(plan=plan['id'], installation=plan['description']['installation'],
        invocation=invocation(plan), authority='administrator', uid=0,
        scope='missing-default-preparation', target=plan['description']['target']))


def _check(facts, outcome):
    facts = dict(facts, outcome=outcome)
    body = dict(format='mojt-action-check-v1', name='default-state', result='passed', facts=facts)
    return dict(name=body['name'], result=body['result'], facts=facts, evidence=artifact.digest(body))


def _result(plan, approval, run, *, previous=None, checks=None):
    return base.record(RESULT, dict(invocation=invocation(plan), plan=plan['id'], approval=approval['id'],
        run=run, sequence=2 if previous else 1, previous=previous,
        status='completed' if previous else 'started',
        recorded_utc=datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'), checks=checks or []))


def _validate_result(value, plan, approval, run, sequence, previous):
    d = base.envelope(value, RESULT)
    artifact.fields(d, ('invocation', 'plan', 'approval', 'run', 'sequence', 'previous',
                        'status', 'recorded_utc', 'checks'))
    require(d['invocation'] == invocation(plan) and d['plan'] == plan['id'] and d['approval'] == approval['id']
            and d['run'] == run and type(d['sequence']) is int and d['sequence'] == sequence
            and d['previous'] == previous and d['status'] == ('started' if sequence == 1 else 'completed'),
            'default result chain or binding differs')
    require(type(d['recorded_utc']) is str and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?Z', d['recorded_utc']),
            'invalid default result timestamp')
    datetime.fromisoformat(d['recorded_utc'].replace('Z', '+00:00'))
    require(type(d['checks']) is list and len(d['checks']) == (len(plan['description']['actions']) if sequence == 2 else 0),
            'incomplete default postconditions')
    for check, action in zip(d['checks'], plan['description']['actions']):
        artifact.fields(check, ('name', 'result', 'facts', 'evidence'))
        facts = check['facts']
        artifact.fields(facts, ('namespace', 'path', 'outcome', 'sha256', 'uid', 'gid', 'mode'))
        require(check == _check({k:v for k,v in facts.items() if k != 'outcome'}, facts['outcome'])
                and facts['namespace'] == 'etc' and facts['path'] == action['path']
                and facts['outcome'] in ('created', 'preserved')
                and type(facts['sha256']) is str and re.fullmatch('[0-9a-f]{64}', facts['sha256'])
                and type(facts['uid']) is int and facts['uid'] == 0 and type(facts['gid']) is int and facts['gid'] == 0
                and type(facts['mode']) is int and 0 <= facts['mode'] <= 0o777 and not facts['mode'] & 0o022,
                'invalid default postcondition evidence')
        if facts['outcome'] == 'created':
            require(facts['sha256'] == action['source']['sha256'] and facts['mode'] == action['mode'],
                    'created default differs from declaration')


def _names(path, limit):
    names = []
    with os.scandir(path) as entries:
        for entry in entries:
            require(len(names) < limit, 'unbounded default registry directory')
            names.append(entry.name)
    return sorted(names)


def _scan(root, plan, *, read_record=None):
    validate_plan(plan)
    read_record = read_record or _read
    path = location(root, plan)
    if not os.path.lexists(path):return dict(attempts=[], incomplete=[])
    with directory(path):pass
    names = _names(path, MAX_RUNS + 3)
    require(len(names) <= MAX_RUNS + 3 and set(names) >= {'plan.json', 'approval.json', '.lock'},
            'incomplete/unbounded default registry')
    require(read_record(path / 'plan.json', PLAN) == plan and read_record(path / 'approval.json', APPROVAL) == _approval(plan),
            'default registry plan/approval differs')
    tx.check_lock_file(path / '.lock', shared=True)
    attempts, incomplete = [], []
    for name in names:
        if name in ('plan.json', 'approval.json', '.lock'):continue
        require(re.fullmatch('[0-9a-f]{32}', name), 'unknown default registry entry')
        run = path / name
        with directory(run):pass
        files = _names(run, 4)
        require(len(files) <= 4 and all(n in ('000001.json', '000002.json') or re.fullmatch(r'\.result-[0-9a-f]{32}', n) for n in files),
                'invalid default result sequence')
        temps = [n for n in files if n.startswith('.result-')]
        incomplete.extend(name + '/' + n for n in temps)
        if '000001.json' not in files:
            require('000002.json' not in files, 'orphan default terminal result')
            attempts.append(dict(run=name, state='interrupted', checks=[]))
            continue
        started = read_record(run / '000001.json', RESULT)
        _validate_result(started, plan, _approval(plan), name, 1, None)
        if '000002.json' in files:
            end = read_record(run / '000002.json', RESULT)
            _validate_result(end, plan, _approval(plan), name, 2, started['id'])
            attempts.append(dict(run=name, state='completed', checks=end['description']['checks']))
        else:attempts.append(dict(run=name, state='interrupted', checks=[]))
    return dict(attempts=attempts, incomplete=incomplete)


def inspect_registry(root):
    """Bounded format/integrity observation, independent of current handler hash."""
    root = tx.protected_directory(root, label='lifecycle target')
    lifecycle = root / 'state/var/lib/mojt/lifecycle'
    tx.protected_directory(lifecycle, label='lifecycle registry')
    try:lifecycle.lstat()
    except FileNotFoundError:return None
    with directory(lifecycle):pass
    names = _names(lifecycle, 16)
    require(set(names) <= {'defaults-v1'}, 'unsupported lifecycle registry: ' + ', '.join(names))
    if not names:return None
    version = root / REGISTRY
    with directory(version):pass
    info = base.store_info(root)
    require(info is not None, 'lifecycle registry lacks an installation identity')
    installations = _names(version, 1)
    require(set(installations) <= {info['installation']}, 'lifecycle registry belongs to another installation')
    objects, interrupted, incomplete = {}, [], []
    read_count = total_bytes = 0
    def read_record(path, fmt):
        nonlocal read_count, total_bytes
        read_count += 1
        require(read_count <= 4096, 'lifecycle observation record budget exceeded')
        value = _read(path, fmt)
        total_bytes += len(artifact.canonical(value))
        require(total_bytes <= 32 * 1024 * 1024, 'lifecycle observation byte budget exceeded')
        objects[str(path.relative_to(version))] = value['id']
        return value
    if installations:
        installation = version / info['installation']
        with directory(installation):pass
        for name in _names(installation, 128):
            require(re.fullmatch('[0-9a-f]{64}', name), 'invalid lifecycle invocation directory')
            scope = installation / name
            with directory(scope):pass
            lock = scope / '.lock'
            require(lock.lstat().st_uid == lock.lstat().st_gid == 0, 'unprotected lifecycle lock owner')
            with tx.file_lock(lock, shared=True, create=False):
                plan = read_record(scope / 'plan.json', PLAN)
                validate_plan(plan)
                require(plan['description']['installation'] == info['installation']
                        and invocation(plan)[7:] == name, 'lifecycle invocation/installation differs')
                observed = _scan(root, plan, read_record=read_record)
            interrupted.extend(name + '/' + a['run'] for a in observed['attempts'] if a['state'] == 'interrupted')
            incomplete.extend(name + '/' + p for p in observed['incomplete'])
    return base.record('mojt-defaults-observation-v1', dict(installation=info['installation'],
        objects=dict(sorted(objects.items())), interrupted=sorted(interrupted), incomplete=sorted(incomplete)))


def status(root, plan):
    """Observe evidence and actual files. Never create a lock/registry or readiness."""
    _validated(root, plan)
    path = location(root, plan)
    if os.path.lexists(path):
        with tx.file_lock(path / '.lock', shared=True, create=False):state = _scan(root, plan)
    else:state = dict(attempts=[], incomplete=[])
    state['observed'] = [observe(Path(root) / 'state/etc', a['path']) for a in plan['description']['actions']]
    state['invocation'] = invocation(plan)
    return state


def _apply(root, plan):
    source = base.realization_path(Path(root), plan['description']['owner']) / 'tree/rootfs/usr/etc'
    checks = []
    for action in plan['description']['actions']:
        path = action['path']
        facts = observe(Path(root) / 'state/etc', path)
        outcome = 'preserved'
        if facts is None:
            with parent(source, path) as (fd, name):
                file = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                try:data, unused = _bytes(file)
                finally:os.close(file)
            require(hashlib.sha256(data).hexdigest() == action['source']['sha256'], 'default source changed')
            with parent(Path(root) / 'state/etc', path) as (fd, name):
                try:publish(fd, name, data, mode=action['mode'], prefix='.mpm-default-')
                except FileExistsError:pass  # Concurrent local writer wins; inspect it below.
                else:outcome = 'created'
            facts = observe(Path(root) / 'state/etc', path)
            require(facts is not None, 'default disappeared during preparation')
        if outcome == 'created':
            require(facts['sha256'] == action['source']['sha256'] and facts['mode'] == action['mode'],
                    'default changed after creation')
        with parent(Path(root) / 'state/etc', path) as (fd, name):
            file = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            try:os.fsync(file)
            finally:os.close(file)
            os.fsync(fd)
        require(observe(Path(root) / 'state/etc', path) == facts, 'default changed before evidence publication')
        checks.append(_check(facts, outcome))
    return checks


def initialize(root, plan, *, yes=False, reconcile=False):
    """Trusted root caller explicitly approves this exact bounded preparation.

    The incoming JSON is never authority: rederive it from retained verified Base
    content and actual protected target, then retain local approval under lock.
    There is deliberately no public CLI or implicit boot hook in this increment.
    """
    require(type(reconcile) is bool, 'invalid default reconciliation option')
    require(os.geteuid() == 0, 'default preparation requires an administrator')
    require(yes is True, 'explicit default preparation approval required')
    root = base.target(root, write=True)
    _validated(root, plan)
    # Global order shared with Base/boot writers. No initialization of content store.
    with tx.resource_locks((root / '.artifact-store.lock', root / 'artifacts/.lock', root / '.install-lock'),
                           modes={root / '.install-lock': 0o644}):
        _validated(root, plan)
        state = root / 'state/var/lib/mojt'
        for name in ('lifecycle', 'lifecycle/defaults-v1', 'lifecycle/defaults-v1/' + plan['description']['installation']):
            _mkdir(state / name)
        scope = location(root, plan)
        _mkdir(scope)
        with tx.file_lock(scope / '.lock'):
            for name, value in (('plan.json', plan), ('approval.json', _approval(plan))):
                dest = scope / name
                if os.path.lexists(dest):require(_read(dest, value['format']) == value, 'retained default authorization differs')
                else:_write(dest, value)
            prior = _scan(root, plan)
            require(not prior['incomplete'], 'incomplete default evidence; inspect before retry')
            unresolved = [a for a in prior['attempts'] if a['state'] == 'interrupted']
            require(not unresolved or (reconcile and len(unresolved) == 1),
                    'interrupted default preparation; explicit reconciliation required')
            observed = [observe(root / 'state/etc', a['path']) for a in plan['description']['actions']]
            facts = [{k:v for k,v in c['facts'].items() if k != 'outcome'} for a in prior['attempts'] for c in a['checks']]
            if not unresolved and prior['attempts'] and all(o is not None and o in facts for o in observed):
                # Retry can make previously uncertain terminal names durable.
                for attempt in prior['attempts']:
                    tx.sync_directory(scope / attempt['run'])
                return dict(changed=False, evidence_written=False, invocation=invocation(plan))
            if unresolved:
                # The only resumable operation is this idempotent ensure-file.
                # Existing bytes are observed/preserved, never attributed to us.
                run = unresolved[0]['run']
                destination = scope / run
                started = _read(destination / '000001.json', RESULT)
                tx.sync_directory(destination)  # Re-establish durable intent before resumed effects.
            else:
                require(len(prior['attempts']) < MAX_RUNS, 'default attempt limit reached')
                run = uuid.uuid4().hex
                destination = scope / run
                require(not os.path.lexists(destination), 'default attempt already exists')
                _mkdir(destination)
                started = _result(plan, _approval(plan), run)
                _write(destination / '000001.json', started)  # Durable before effects.
            checks = _apply(root, plan)
            completed = _result(plan, _approval(plan), run, previous=started['id'], checks=checks)
            _validate_result(completed, plan, _approval(plan), run, 2, started['id'])
            _write(destination / '000002.json', completed)
            return dict(changed=any(c['facts']['outcome'] == 'created' for c in checks),
                        evidence_written=True, invocation=invocation(plan), result=completed['id'])
