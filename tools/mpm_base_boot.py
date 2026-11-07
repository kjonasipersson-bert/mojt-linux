# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Exact Base-only boot staging; no boot selection or persistent state changes."""
from contextlib import contextmanager
import copy
import hashlib
import os
import re
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import tomllib
import uuid

import mojt_artifact as artifact
import mojt_native_image as native
import mojt_system as system
import mojt_system_manifest as manifests
import mpm_base as base
import mpm_base_transition as transition
import mpm_deployment as deployment
import mpm_kernel as kernel
import mpm_kernel_boot as boot
import mpm_transaction as tx

INPUTS = 'mojt-base-boot-inputs-v1'
CODE = ('mpm_cli.py', 'mpm_base_cli.py', 'mpm_base_status.py', 'mpm_base_boot.py', 'mpm_base_transition.py', 'mpm_base.py', 'mpm_native_io.py',
        'mojt-base-install', 'mpm_kernel_boot.py', 'mpm_deployment.py', 'mojt-vm-build.py',
        'mojt_native_image.py', 'mojt_system.py', 'mojt_boot.py', 'mpm_transaction.py', 'mpm_defaults.py', 'mpm_management.py')
require = base.require


def defaults_check(root, tree):
    """The first deployment subset requires defaults to be present already.

    Preserve all existing local files/conflicts. Never follow a state symlink.
    Adding defaults needs a separately durable lifecycle action, not a hidden
    side effect of constructing an immutable boot slot.
    """
    source = tree / 'usr/etc'
    require(source.is_dir() and not source.is_symlink(), 'Base defaults directory missing')
    missing = []
    def visit(src, dst):
        for child in sorted(src.iterdir()):
            if child.name == 'os-release' and src == source:
                continue
            target = dst / child.name
            require(child.is_symlink() or child.is_dir() or child.is_file(), 'unsupported Base default')
            if not os.path.lexists(target):
                missing.append(str(target.relative_to(root / 'state/etc')))
            elif child.is_dir() and not child.is_symlink() and target.is_dir() and not target.is_symlink():
                visit(child, target)
    visit(source, root / 'state/etc')
    return dict(policy='existing-defaults-only-v1', missing=missing)


def management(profile):
    # The retained System must itself carry these readers. Running an inspector
    # from a checkout cannot confer capabilities on the booted System.
    for name in CODE:
        source = Path(__file__).with_name(name)
        retained = profile / 'tools' / name
        require(retained.is_file() and not retained.is_symlink() and
                artifact.file_sha(retained) == artifact.file_sha(source),
                'retained System management code differs or is missing: ' + name)


def producer(profile, tar):
    management(profile)
    tool = shutil.which(str(tar))
    require(tool is not None, 'retained GNU tar helper is unavailable')
    tool = Path(tool).resolve()
    require('GNU tar' in subprocess.check_output([str(tool), '--version'], text=True), 'Base boot tree requires GNU tar')
    busybox = profile / 'busybox'
    return dict(code={n: artifact.file_sha(Path(__file__).with_name(n)) for n in CODE},
                busybox=artifact.file_sha(busybox), tar=dict(program=str(tool), sha256=artifact.file_sha(tool)))


@contextmanager
def locked(root):
    boot.disk_root(root, write=True)
    base.target(root, write=True)
    # Base installation must have initialized its store before staging.
    require(base.store_info(root) is not None, 'installed Base store required')
    for name in ('boot/mpm', 'state/var/lib/mojt/ports'):
        path = root / name
        tx.protected_directory(path, write=True)
        path.mkdir(parents=True, exist_ok=True, mode=0o755)
    paths = {root / '.artifact-store.lock', root / 'artifacts/.lock', *tx.boot_lock_paths(root)}
    with tx.resource_locks(paths, modes={root / '.install-lock': 0o644}):
        boot.initialize_boot_registry(root / 'boot/mpm')
        yield


def boot_tree(root, identifier, stage, tool):
    body, receipt = base.object_record(root, identifier, verify=True)
    original = base.realization_path(root, identifier) / 'tree/rootfs'
    source_inventory = native.base_inventory(original)
    private = stage / 'tree'
    private.mkdir(mode=0o700)
    target = private / 'rootfs'
    target.mkdir()
    inner, unused, old = base.inner_tar(base.object_path(root, identifier), body, stage)
    flags = [tool, '--numeric-owner', '--acls', '--xattrs', '--xattrs-include=*', '--same-owner', '--same-permissions']
    subprocess.run([*flags, '-xf', str(inner), '-C', str(target)], check=True)
    subprocess.run([*flags, '--compare', '-f', str(inner), '-C', str(target)], check=True)
    require(native.base_inventory(target) == source_inventory, 'Base boot copy differs from installed rootfs')
    inner.unlink()
    # Only the already reviewed additive mountpoint policy is accepted.
    for name in ('dev', 'proc', 'sys', 'etc', 'var', 'home', 'root'):
        point = system.virtual_file(target, '/' + name)
        require(point.is_dir(), 'Base lacks required mountpoint: /' + name)
    for name, mode in (('run', 0o755), ('tmp', 0o1777), ('nix', 0o755), ('lib/modules', 0o755)):
        point = system.virtual_file(target, '/' + name)
        require(point == target or target in point.parents, 'boot mountpoint escapes Base')
        if not point.exists():
            point.mkdir(parents=True, mode=mode)
        require(point.is_dir() and not any(point.iterdir()), 'Base boot mountpoint is not an empty directory: /' + name)
    evidence = native.check_base_copy(target, source_inventory)
    old['sync_tree'](target)
    private.chmod(0o500)
    kernel.sync_directory(private)
    return evidence


def init_transform(identifier, relative):
    key = kernel.identifier(identifier)
    require(isinstance(relative, str) and re.fullmatch(r'boot/mpm/slots/[0-9a-f]{32}/tree/rootfs', relative),
            'invalid exact Base boot tree reference')
    def transform(script):
        old_root = 'root="/sysroot/base/$version"'
        old_manifest = '[ -f "/sysroot/releases/base-$version.toml" ] || panic "Base metadata missing"'
        bind = 'mount --bind "$root" /newroot || panic "cannot bind Base root"'
        require(script.count(old_root) == script.count(old_manifest) == script.count(bind) == 1,
                'Base initramfs hooks changed; review required')
        script = script.replace(old_root, 'root="/sysroot/' + relative + '"')
        script = script.replace(old_manifest, '[ -f /sysroot/artifacts/base/installed/' + key +
            '/payload/manifest.toml ] || panic "Base metadata missing"')
        return script.replace(bind, bind + '\nmount -o remount,bind,ro "$root" /newroot || panic "cannot protect Base root"')
    return transform


def build_initramfs(root, body, candidate, slot, busybox, work):
    transform = init_transform(candidate['record']['description']['base']['artifact'],
                               'boot/mpm/slots/' + slot + '/tree/rootfs')
    return boot.build_initramfs(root, body, candidate, slot, busybox, work, transform=transform)


def context(root, entry, manifest, receipt, *, constructing=False):
    """Validate a staged Base receipt and derive facts from its candidate root."""
    d = entry['record']['description']
    require(receipt.get('format') == INPUTS and receipt['base_artifact'] == d['base']['artifact'], 'Base boot receipt identity differs')
    require(receipt['system_manifest'] == manifest['id'], 'Base boot receipt System differs')
    identifier = d['base']['artifact']
    body, installed = base.object_record(root, identifier, verify=True)
    realized = base.realization(root, identifier, installed, verify=True)
    require(realized is not None and receipt['base_receipt'] == installed['id'] and
            receipt['base_realization'] == realized['id'], 'Base boot receipt differs from installation')
    relative = receipt['base_tree']
    require(isinstance(relative, str) and re.fullmatch(r'boot/mpm/slots/[0-9a-f]{32}/tree/rootfs', relative),
            'invalid Base boot tree reference')
    if constructing:
        private = entry['path'] / 'tree'
    else:
        owner = boot.entry_path(root, relative.removesuffix('/tree/rootfs'))
        private = owner / 'tree'

    require(private == private.resolve() and stat.S_IMODE(private.stat().st_mode) == 0o500 and
            private.stat().st_uid == 0 and {p.name for p in private.iterdir()} == {'rootfs'}, 'unprotected Base boot tree')
    tree = private / 'rootfs'
    require(tree == tree.resolve(), 'linked Base boot root')
    expected = native.check_base_copy(tree, native.base_inventory(base.realization_path(root, identifier) / 'tree/rootfs'))
    require(receipt['base_copy'] == expected, 'staged Base content/metadata differs')
    release = tomllib.loads(transition.checked_bytes(base.object_path(root, identifier) / 'payload/manifest.toml').decode())
    state = transition.state_inputs(root)
    facts = dict(format=manifests.CONTEXT, architecture=release['base']['architecture'], base_abi=release['abi'],
        state_layout=state['layout'], ports=state['ports'], required_system_paths=state['system_shells'])
    bounds = boot.read(entry['path'] / 'base-context.json')
    report = transition.candidate_checks(body, release, entry['record'], manifest, entry['body'], bounds, facts)
    account_shells = transition.account_shell_check(root, tree, state, manifest)
    report['errors'].extend(account_shells['errors'])
    require(not report['errors'], 'Base declaration check failed: ' + '; '.join(report['errors']))
    require(not defaults_check(root, tree)['missing'], 'Base requires missing-default preparation before boot')
    return dict(format=deployment.CONTEXT, selected=entry['record']['id'], base=d['base'],
                root_uuid=d['boot']['root_uuid'], facts=facts)


def existing(root, state, entries, p, made_by, bounds):
    retained, unused = boot.available(root, state, entries)
    for entry in retained.values():
        receipt = boot.read(entry['path'] / 'native-build-inputs.json')
        d = entry['record']['description']
        if (receipt.get('format') == INPUTS and receipt.get('base_boot_producer') == made_by and
                d['base'] == p['checks']['candidate_base'] and d['system'] == p['retained_system'] and
                d['kernel'] == p['retained_kernel'] and boot.read(entry['path'] / 'base-context.json') == bounds):
            boot.live_context(root, entry)
            return entry
    return None


def unchanged(plan, entry, dry_run):
    return dict(plan=dict(plan, action='no-change'), changed=False, dry_run=dry_run,
                deployment=entry['record']['id'], slot=entry['relative'], boot_ready=False)


def stage(root, identifier, bounds, *, baseline=None, dry_run=False, yes=False, tar='tar', builder=build_initramfs):
    root = boot.disk_root(base.target(root), write=not dry_run)
    preflight = transition.prepare(root, identifier, bounds, baseline=baseline)
    p = preflight['description']
    require(p['checks']['declared_compatible'], 'Base declaration check failed: ' + '; '.join(p['checks']['errors']))
    state, entries, old_menu = boot.current(root, baseline)
    require(state['selected'] == p['selected'], 'selection changed during preview')
    selected = entries[state['selected']]
    manifest, unused, unused_receipt = boot.live_context(root, selected)
    profile = root / 'system' / p['retained_system']['generation']
    made_by = producer(profile, tar)
    tree = base.realization_path(root, identifier) / 'tree/rootfs'
    defaults = defaults_check(root, tree)
    plan = dict(action='stage', base=p['candidate_base']['artifact'], selected=p['selected'],
        retained_system=p['retained_system'], retained_kernel=p['retained_kernel'],
        defaults=defaults, selection_changes=False, persistent_state_changes=False, running_changes=False)
    require(not defaults['missing'], 'Base needs explicit missing-default preparation: ' + ', '.join(defaults['missing']))
    entry = existing(root, state, entries, p, made_by, bounds)
    if entry is not None:
        return unchanged(plan, entry, dry_run)
    if dry_run:
        return dict(plan=plan, changed=False, dry_run=True, boot_ready=False)
    if not yes:
        require(input('Stage this exact Base without changing state or next boot? [y/N] ').lower() == 'y', 'staging cancelled')
    with locked(root):
        require(transition._prepare(root, identifier, bounds, baseline) == preflight, 'Base staging inputs changed; repeat preview')
        require(defaults_check(root, tree) == defaults and producer(profile, tar) == made_by, 'Base construction inputs changed')
        entry = existing(root, state, entries, p, made_by, bounds)
        if entry is not None:
            return unchanged(plan, entry, False)
        slot = uuid.uuid4().hex
        slots = root / 'boot/mpm/slots'
        staging = Path(tempfile.mkdtemp(prefix='.stage-', dir=slots))
        try:
            base_copy = boot_tree(root, identifier, staging, made_by['tar']['program'])
            d = copy.deepcopy(selected['record']['description'])
            d['base'] = p['checks']['candidate_base']
            d['boot']['cmdline'] = boot.boot.cmdline(d['boot']['root_uuid'], d['system']['generation'], d['base']['release'], d['boot']['console'])
            candidate = dict(record=deployment.create(d))
            with tempfile.TemporaryDirectory(prefix='mojt-base-init-') as temporary:
                frozen = Path(temporary) / 'busybox'
                shutil.copyfile(profile / 'busybox', frozen);frozen.chmod(0o755)
                raw, evidence = builder(root, selected['body'], candidate, slot, frozen, Path(temporary))
            archive = dict(sha256=hashlib.sha256(raw).hexdigest(), size=len(raw))
            binding = deployment.create(dict(platform=d['platform'], base=d['base'], system=d['system'],
                kernel=d['kernel'], boot=d['boot'], archive=archive), deployment.BINDING)
            d['initramfs'] = dict(archive=archive, binding=binding['id'])
            record = deployment.create(d)
            deployment.validate_deployment(record)
            _, kernel_receipt = kernel.object_record(root / 'kernel/installed' / kernel.identifier(d['kernel']['artifact']), d['kernel']['artifact'], verify=True)
            receipt = dict(format=INPUTS, selection_origin='existing-disk-base-stage', base_artifact=identifier,
                base_receipt=p['candidate_base']['receipt'], base_realization=p['candidate_base']['realization'],
                base_copy=base_copy, base_tree='boot/mpm/slots/' + slot + '/tree/rootfs',
                base_boot_producer=made_by, preflight=preflight,
                kernel_artifact=d['kernel']['artifact'], kernel_installation_digest=artifact.digest(kernel_receipt),
                kernel_acquisition=kernel_receipt.get('acquisition'), system_manifest=manifest['id'], **evidence)
            for name, value in {'deployment.json':record, 'base-context.json':bounds, 'system-manifest.json':manifest,
                               'initramfs-binding.json':binding, 'native-build-inputs.json':receipt}.items():
                kernel.write_json(staging / name, value)
            image = boot.checked_file(selected['path'] / 'vmlinuz', native.MAX_INITRAMFS)
            for name, content in (('vmlinuz', image), ('initramfs.cpio.gz', raw)):
                with (staging / name).open('xb') as stream:
                    stream.write(content);os.fchmod(stream.fileno(), 0o444);os.fsync(stream.fileno())
            # All expensive construction is finished. Revalidate inputs and the
            # copied root once at the publication boundary under the same locks.
            require(transition._prepare(root, identifier, bounds, baseline) == preflight, 'Base staging inputs changed during construction')
            require(producer(profile, tar) == made_by, 'Base constructor changed during staging')
            require(boot.checked_file(root / 'boot/mojt/grub.cfg') == old_menu, 'selection changed during Base staging')
            transient = dict(record=record, path=staging, body=selected['body'])
            context(root, transient, manifest, receipt, constructing=True)
            require(hashlib.sha256(image).hexdigest() == d['kernel']['image_sha256'], 'retained Kernel image changed')
            kernel.sync_directory(staging);staging.chmod(0o555)
            tx.publish(staging, slots / slot, sync=kernel.sync_directory)
        finally:
            base.io.clean_stage(staging)
        published = boot.inspect_entry(root, 'boot/mpm/slots/' + slot)
        require(published['record'] == record, 'published Base deployment differs')
    return dict(plan=plan, changed=True, deployment=record['id'], slot='boot/mpm/slots/' + slot,
                selected=state['selected'], running='unchanged', persistent_state='unchanged',
                stage_ready=True, boot_ready=False)


def selection_context(root, entry):
    """Recheck both the candidate and the retained recovery deployment."""
    manifest, facts, receipt = boot.live_context(root, entry)
    state = transition.state_inputs(root)
    require(facts['facts']['state_layout'] == state['layout'] and
            facts['facts']['ports'] == state['ports'] and
            facts['facts']['required_system_paths'] == state['system_shells'],
            'observed persistent state differs from deployment compatibility facts')
    d = entry['record']['description']
    if receipt.get('format') == INPUTS:
        tree = root / receipt['base_tree']
    else:
        tree = root / 'base' / d['base']['release']
    account_shells = transition.account_shell_check(root, tree, state, manifest)
    require(account_shells['compatible'], 'deployment account shells differ: ' + '; '.join(account_shells['errors']))
    require(not defaults_check(root, tree)['missing'], 'deployment needs missing-default preparation')
    management(root / 'system' / d['system']['generation'])
    return dict(manifest=manifest, facts=facts, receipt=receipt, state=state, account_shells=account_shells)


def selection_scope(selected, candidate):
    old = deployment.validate_deployment(selected)
    new = deployment.validate_deployment(candidate)
    require(all(old[k] == new[k] for k in ('system', 'kernel', 'platform')) and
            all(old['boot'][k] == new['boot'][k] for k in ('root_uuid', 'console')),
            'Base selection must preserve exact System/Kernel/platform/root/console')


def select(root, identifier, *, expected_selected, baseline=None, dry_run=False, yes=False, rollback=False):
    root = boot.disk_root(base.target(root), write=not dry_run)
    state, selected_entries, old_menu = boot.current(root, baseline)
    require(state['selected'] == expected_selected, 'selected deployment changed; repeat preview')
    if rollback:
        identifier = state['previous']
        require(identifier is not None, 'no previous selected deployment')
    kernel.identifier(identifier)
    entries, unused = boot.available(root, state, selected_entries)
    require(identifier in entries, 'deployment is not completely staged')
    selected, candidate = selected_entries[state['selected']], entries[identifier]
    selection_scope(selected['record'], candidate['record'])
    old_context = selection_context(root, selected)
    new_context = old_context if identifier == state['selected'] else selection_context(root, candidate)
    d = candidate['record']['description']
    plan = dict(action='no-change' if identifier == state['selected'] else 'select',
        before=state['selected'], after=identifier, base=d['base'], retained_system=d['system'], retained_kernel=d['kernel'],
        persistent_state_changes=False, running='unchanged until boot')
    if dry_run or identifier == state['selected']:
        return dict(plan=plan, changed=False, dry_run=dry_run)
    if not yes:
        require(input('Select this exact Base deployment for next boot? [y/N] ').lower() == 'y', 'selection cancelled')
    with locked(root):
        require(boot.checked_file(root / 'boot/mojt/grub.cfg') == old_menu, 'boot selection changed; repeat preview')
        new = dict(state, format=boot.BASE_MENU_FORMAT, selected=identifier, previous=state['selected'], entries=dict(state['entries']))
        new['entries'][identifier] = candidate['relative']
        raw = boot.menu(new, {i: entries[i] for i in new['entries']})
        target = root / 'boot/mojt/grub.cfg'
        fd, temporary = tempfile.mkstemp(prefix='.grub-', dir=target.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw);os.fchmod(stream.fileno(), 0o644);os.fsync(stream.fileno())
            # One menu is the commit point for both metadata and loader entries.
            # Do not trust a previous preview or only recheck the menu's bytes.
            fresh_selected = boot.inspect_entry(root, selected['relative'])
            fresh_candidate = boot.inspect_entry(root, candidate['relative'])
            require(fresh_selected['record'] == selected['record'] and fresh_candidate['record'] == candidate['record'],
                    'deployment changed during Base selection')
            require(selection_context(root, fresh_selected) == old_context and
                    selection_context(root, fresh_candidate) == new_context,
                    'deployment or persistent state changed during Base selection')
            selection_scope(fresh_selected['record'], fresh_candidate['record'])
            require(boot.checked_file(target) == old_menu, 'boot menu changed before publication')
            tx.publish(temporary, target, sync=kernel.sync_directory)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return dict(plan=plan, changed=True, selected=identifier, previous=state['selected'], running='unchanged until boot')
