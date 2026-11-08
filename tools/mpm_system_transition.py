# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Read-only exact System transition planning and bounded unchanged-startup review."""
import copy
import hashlib
import os
import stat
import tomllib

import mojt_artifact as artifact
import mojt_system as paths
import mojt_system_manifest as manifests
import mpm_base as base
import mpm_base_transition as common
import mpm_catalog as catalog
import mpm_deployment as deployment
import mpm_kernel_boot as boot
import mpm_management as management
import mpm_system as system

FORMAT = 'mojt-system-transition-preflight-v1'
REVIEW = 'mojt-system-startup-review-v1'
require = base.require


def normalized(row):
    if set(row) == {'link'}:
        require(type(row['link']) is str, 'invalid profile link evidence');return copy.deepcopy(row)
    require(set(row) in ({'directory', 'mode'}, {'sha256', 'mode'}) and type(row['mode']) is int, 'unsupported profile evidence')
    return dict(row, mode=row['mode'] & ~0o222)


def tooling_review(selected, candidate):
    """Allow management tooling changes; do not infer service/schema migrations."""
    old = manifests.validate(selected)['description'];new = manifests.validate(candidate)['description']
    before = {p:normalized(r) for p,r in old['profile'].items() if p != management.FILENAME}
    after = {p:normalized(r) for p,r in new['profile'].items() if p != management.FILENAME}
    changed = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))
    blocked = []
    for path in changed:
        allowed = (path.startswith(('tools/', 'tests/')) or path in ('tools', 'tests', 'bin/mpm', 'bin/mojt-system-inspect', 'share/man/man1/mpm.1')
                   or path.startswith('bin/') and path not in before and path in after
                   or path in ('share', 'share/man', 'share/man/man1') and path not in before and after.get(path, {}).get('directory') is True)
        if path == 'version':
            allowed = after.get(path, {}).get('sha256') == hashlib.sha256((new['label'] + '\n').encode()).hexdigest()
        if not allowed:blocked.append(path)
    previous_outputs = sorted({r['link'] for r in before.values() if r.get('link') in
        ('/run/mojt-privileged/passwd', '/run/mojt-privileged/sudo')})
    outputs = new['provenance'].get('runtime_outputs', [])
    if outputs != previous_outputs:blocked.append('runtime-output-contract')
    stable = {p:r for p,r in before.items() if p not in changed}
    return base.record(REVIEW, dict(policy='unchanged-startup-only-v1', selected=selected['id'], candidate=candidate['id'],
        changed=changed, blockers=sorted(blocked), preserved_inventory=artifact.digest(stable),
        runtime_outputs=outputs, compatible=not blocked, effects=False,
        limitation='No service upgrade, new initializer, state-schema migration or runtime health is authorized.'))


def defaults(root, profile):
    """Only observe missing profile defaults; preserve local files and symlinks."""
    source = profile / 'defaults';missing = [];observed = []
    if not source.exists():return dict(policy='existing-defaults-only-v1', missing=[], observed=artifact.digest([]))
    require(source.is_dir() and not source.is_symlink(), 'unsupported System defaults root')
    def visit(src, dst):
        for file in sorted(src.iterdir()):
            target = dst / file.name;relative = target.relative_to(root / 'state/etc').as_posix()
            try:info = target.lstat()
            except FileNotFoundError:missing.append(relative);continue
            require(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode), 'unsupported existing default target')
            observed.append(dict(path=relative, mode=info.st_mode, device=info.st_dev, inode=info.st_ino,
                                 link=os.readlink(target) if stat.S_ISLNK(info.st_mode) else None))
            if file.is_dir() and not file.is_symlink() and stat.S_ISDIR(info.st_mode):visit(file, target)
    visit(source, root / 'state/etc')
    return dict(policy='existing-defaults-only-v1', missing=missing, observed=artifact.digest(observed))


def providers(manifest, candidate, refs, adapters):
    """Provider-specific preservation facts stay in the manager-owned adapter."""
    reports = [];errors = []
    for name, record in sorted(manifest['description']['artifacts'].items()):
        if name == 'native':continue
        try:
            require(adapters is not None, 'provider adapter required for startup preservation: ' + name)
            adapter = adapters[name]
            require(hasattr(adapter, 'preserves'), 'provider cannot prove unchanged startup dependencies: ' + name)
            report = adapter.preserves([copy.deepcopy(r) for r in refs if r['provider'] == name], copy.deepcopy(record))
            require(type(report) is dict and type(report.get('compatible')) is bool, 'invalid provider preservation report')
            reports.append(dict(provider=name, evidence=report))
            if not report['compatible']:errors.append('selected startup provider closure is not preserved: ' + name)
            files = report.get('runtime_files', [])
            require(type(files) is list and len(files) <= 128, 'invalid provider runtime evidence')
            for path in files:
                management.path(path)
                old = manifest['description']['profile'].get(path);new = candidate['description']['profile'].get(path)
                if old is None or new is None or normalized(old) != normalized(new):
                    errors.append('provider runtime change requires an explicit upgrade contract: ' + path)
        except (KeyError, ValueError) as error:errors.append(str(error))
    return dict(compatible=not errors, errors=errors, reports=reports)


def shells(root, tree, state, candidate, refs, adapters):
    errors = []
    for shell in state['base_shells']:
        owners = [] if adapters is None else [r for r in refs if hasattr(adapters[r['provider']], 'contains') and adapters[r['provider']].contains(r, shell)]
        try:
            if owners:
                ref = owners[0];require(hasattr(adapters[ref['provider']], 'verify_path'), 'provider cannot verify persistent account shell')
                adapters[ref['provider']].verify_path(ref, shell, executable=True)
            else:
                file = paths.virtual_file(tree, shell)
                require(file.is_file() and file.stat().st_mode & 0o001, 'selected Base/candidate System lacks public account shell: ' + shell)
        except (OSError, ValueError) as error:errors.append(str(error))
    return dict(compatible=not errors, errors=errors)


def _prepare(root, identifier, baseline, adapters):
    require(os.geteuid() == 0, 'verified System planning requires administrator access to retained content')
    physical = system.target_identity(root)
    state, entries, menu = boot.current(root, baseline);entry = entries[state['selected']]
    old = deployment.validate_deployment(entry['record'])
    selected, _, _ = boot.live_context(root, entry)
    persistent = common.state_inputs(root)
    info = base.store_info(root);require(info is not None, 'native installation store required')
    body, receipt = system.object_record(root, identifier)
    require(body['metadata']['system_role'] == 'generation', 'candidate must be an installed System generation')
    realized = system.realization(root, identifier, verify=True)
    require(realized is not None, 'System is retained but not installed; finish realization first')
    profile = system.realization_path(root, identifier) / 'profile'
    candidate = manifests.validate(base.read(profile / 'manifest.json'))
    refs = system.retained_providers(root, identifier)
    system.providers(root, refs, adapters, effect='verify')
    outputs = candidate['description']['provenance'].get('runtime_outputs', [])
    system.verify_links(profile, refs, adapters, outputs)
    base_body, base_receipt = base.object_record(root, old['base']['artifact'], verify=True)
    require(base_body['version']['upstream'] == old['base']['release'], 'installed Base differs from selected exact Base')
    base_realized = base.realization(root, base_body['id'], base_receipt, verify=True)
    require(base_realized is not None, 'selected Base needs an installed native realization')
    release = tomllib.loads(common.checked_bytes(base.object_path(root, base_body['id']) / 'payload/manifest.toml').decode())
    require(type(release.get('abi')) is dict and release['abi'], 'selected Base needs explicit ABI facts')
    facts = dict(format=manifests.CONTEXT, architecture=release['base']['architecture'], base_abi=release['abi'],
        state_layout=persistent['layout'], ports=persistent['ports'], required_system_paths=persistent['system_shells'])
    compatibility = manifests.check(candidate, facts)
    require(base_body['platform'] == body['platform'] == old['platform'], 'System/Base/deployment platform differs')
    bounds = catalog.base_context(boot.read(entry['path'] / 'base-context.json'))
    require(bounds['base'] == old['base'] and bounds['platform'] == old['platform'], 'retained Kernel bounds do not bind selected Base')
    upstream = entry['body']['version']
    require(upstream['scheme'] == 'dotted-v1' and catalog.compare_versions(bounds['kernel_min'], upstream['upstream']) <= 0
            and catalog.compare_versions(upstream['upstream'], bounds['kernel_max']) <= 0, 'preserved Kernel is outside selected Base bounds')
    reviewed = tooling_review(selected, candidate)
    requirements = providers(selected, candidate, refs, adapters)
    management_report = management.check_target(root, profile, candidate)
    tree = base.realization_path(root, base_body['id']) / 'tree/rootfs'
    shell_report = shells(root, tree, persistent, candidate, refs, adapters)
    observed_defaults = defaults(root, profile)
    errors = list(compatibility['errors']) + list(requirements['errors']) + list(shell_report['errors'])
    if body['metadata'].get('deployment_contract') != dict(format='mojt-system-content-only-v1', initialization='profile-services-not-reviewed'):
        errors.append('candidate has no supported System initialization review contract')
    if not reviewed['description']['compatible']:errors.append('startup/service changes require a supported initialization contract: ' + ', '.join(reviewed['description']['blockers']))
    if not management_report['compatible']:errors.extend(management_report['errors'])
    if observed_defaults['missing']:errors.append('missing System defaults need explicit preparation: ' + ', '.join(observed_defaults['missing']))
    # Bind actual persistent/selection facts, not the running System label.
    require(boot.checked_file(root / 'boot/mojt/grub.cfg') == menu and system.target_identity(root) == physical, 'selection or target changed during System planning')
    require(common.state_inputs(root) == persistent and defaults(root, profile) == observed_defaults, 'persistent state changed during System planning')
    result = base.record(FORMAT, dict(target=str(root), target_identity=physical, installation=info['installation'], baseline=baseline,
        selected=state['selected'], selection_sha256=hashlib.sha256(menu).hexdigest(), root_uuid=old['boot']['root_uuid'],
        operation='system', retained_base=dict(old['base'], receipt=base_receipt['id'], realization=base_realized['id']),
        retained_kernel=copy.deepcopy(old['kernel']), kernel_bounds=bounds,
        candidate_system=dict(artifact=identifier, receipt=receipt['id'], realization=realized['id'], composition=realized['description']['composition'],
            manifest=candidate['id'], generation=candidate['description']['label'], runtime_outputs=outputs),
        state=persistent['evidence'], checks=dict(compatible=not errors, errors=errors, base=compatibility, management=management_report,
            providers=requirements, startup=reviewed, account_shells=shell_report, defaults=observed_defaults),
        writes=False, effects=False, stage_ready=False, boot_ready=False,
        remaining_gates=['native-v2 input/initramfs binding and early-boot reader', 'complete native-v2 slot publication',
                         'atomic next-boot selection and focused owner System boot/return acceptance']))
    require(len(artifact.canonical(result)) <= artifact.MAX_METADATA, 'System plan exceeds metadata limit')
    return result


def prepare(root, identifier, *, baseline=None, adapters=None):
    root = system.target(root);boot.disk_root(root);base.io.identifier(identifier)
    with common.read_locks(root):return _prepare(root, identifier, baseline, adapters)


def recheck(root, plan, *, adapters=None):
    d = base.envelope(plan, FORMAT)
    require(str(system.target(root)) == d['target'], 'System plan belongs to another target')
    actual = prepare(root, d['candidate_system']['artifact'], baseline=d['baseline'], adapters=adapters)
    require(actual == plan, 'System transition inputs changed; prepare a fresh plan')
    return actual
