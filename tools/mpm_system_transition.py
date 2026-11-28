# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Read-only exact System transition planning and bounded unchanged-startup review."""
import copy
import hashlib
import json
import os
import posixpath
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
import mpm_kernel as kernel
import mpm_system as system

FORMAT = 'mojt-system-transition-preflight-v1'
NATIVE_FORMAT = 'mojt-system-transition-preflight-v2'
BOOT_FORMAT = 'mojt-boot-transition-preflight-v1'
REVIEW = 'mojt-system-startup-review-v1'
FIRMWARE_REVIEW = 'mojt-system-startup-review-v2'
FIRMWARE_FORMAT = 'mojt-system-firmware-data-v1'
FIRMWARE_PROOF = 'firmware-update.json'
QEMU_AGENT_UNIT = '''[Unit]
Description=QEMU Guest Agent
After=mojt-hardware.service systemd-udev-trigger.service

[Service]
Type=simple
Environment=QGA_CONF=/etc/qemu/qemu-ga.conf
Environment=PATH=/run/mojt-system/bin:/usr/sbin:/usr/bin:/sbin:/bin
RuntimeDirectory=qemu-guest-agent
ExecCondition=/run/mojt-system/bin/udevadm trigger --action=add --settle --subsystem-match=virtio
ExecCondition=/run/mojt-system/bin/udevadm trigger --action=add --settle --subsystem-match=virtio-ports
ExecCondition=/run/mojt-system/busybox test -e /dev/virtio-ports/org.qemu.guest_agent.0
ExecStart=/run/mojt-system/bin/qemu-ga --method=virtio-serial --path=/dev/virtio-ports/org.qemu.guest_agent.0 --statedir=/run/qemu-guest-agent --pidfile=/run/qemu-guest-agent/qemu-ga.pid
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=mojt.target
'''
require = base.require


def normalized(row):
    if set(row) == {'component'}:
        artifact.fields(row['component'],('artifact','path'));base.io.identifier(row['component']['artifact']);management.path(row['component']['path'])
        return copy.deepcopy(row)
    if set(row) == {'link'}:
        require(type(row['link']) is str, 'invalid profile link evidence');return copy.deepcopy(row)
    require(set(row) in ({'directory', 'mode'}, {'sha256', 'mode'}) and type(row['mode']) is int, 'unsupported profile evidence')
    return dict(row, mode=row['mode'] & ~0o222)


def firmware_inventory(profile):
    """Firmware data and its attributions, not Kernel modules or service code."""
    return {p:normalized(r) for p,r in profile.items()
            if p == 'kernel/lib/firmware' or p.startswith('kernel/lib/firmware/')
            or p == 'kernel/licenses' or p.startswith('kernel/licenses/')}


def firmware_review(selected, candidate, proof):
    """A bounded data-only exception; the selected machine/startup policy stays exact."""
    artifact.fields(proof, ('format','baseline','hardware_before','hardware_after',
                            'inventory_before','inventory_after','source'))
    require(proof['format'] == FIRMWARE_FORMAT and proof['baseline'] == selected['id'],
            'firmware review does not bind the selected System manifest')
    require(type(proof['source']) is dict and proof['source'], 'firmware source provenance required')
    before=selected['description']['profile'];after=candidate['description']['profile']
    hardware=[]
    for profile,key in ((before,'hardware_before'),(after,'hardware_after')):
        raw=proof[key]
        require(type(raw) is str and len(raw.encode()) <= 65536, 'bounded hardware evidence required')
        row=normalized(profile.get('hardware.json',{}))
        require(row.get('sha256') == hashlib.sha256(raw.encode()).hexdigest() and not row['mode'] & 0o111,
                'firmware hardware evidence differs from profile')
        value=artifact.parse_json(raw.encode())
        require(type(value) is dict and value.get('format') == 2 and value.get('modules_location') == 'native-kernel',
                'firmware update needs native Kernel hardware metadata')
        hardware.append(value)
    mutable={'firmware_tree_sha256','licenses_tree_sha256'}
    require(all(mutable <= set(row) for row in hardware) and
            {k:v for k,v in hardware[0].items() if k not in mutable} ==
            {k:v for k,v in hardware[1].items() if k not in mutable},
            'firmware update changes hardware/Kernel/module startup policy')
    for row in hardware:
        for key in mutable:
            require(type(row[key]) is str and len(row[key]) == 64 and all(c in '0123456789abcdef' for c in row[key]),
                    'invalid firmware tree provenance hash')
    inventories=(firmware_inventory(before),firmware_inventory(after))
    require(all(artifact.digest(rows) == proof[key] for rows,key in zip(inventories,('inventory_before','inventory_after'))),
            'firmware inventory proof differs')
    changed={p for p in set(inventories[0])|set(inventories[1]) if inventories[0].get(p) != inventories[1].get(p)}
    require(changed,'firmware update has no data changes')
    for path in changed:
        if path.startswith('kernel/licenses/'):
            package=path.split('/')[2]
            import mojt_hardware as hardware_model
            require(package in (*hardware_model.license_packages(hardware_model.PC_PROFILE),'linux-firmware'),
                    'firmware update changes unrelated Kernel licenses')
    for path,row in inventories[1].items():
        if 'sha256' in row:require(not row['mode'] & 0o111,'executable firmware/license data refused')
        if 'link' in row:
            target=posixpath.normpath(posixpath.join(posixpath.dirname(path),row['link']))
            boundary='kernel/lib/firmware/' if path.startswith('kernel/lib/firmware/') else 'kernel/licenses/'
            require(not row['link'].startswith('/') and target.startswith(boundary) and target in inventories[1],
                    'firmware/license link escapes its data tree')
    for name in ('regulatory.db','regulatory.db.p7s'):
        require('sha256' in after.get('kernel/lib/firmware/'+name,{}),'firmware update lacks regulatory data/signature')
    # One of the supported input layouts must retain its complete attributions.
    import mojt_hardware as hardware_model
    debian=all('sha256' in after.get('kernel/licenses/'+p+'/copyright',{})
               for p in hardware_model.license_packages(hardware_model.PC_PROFILE))
    upstream=('sha256' in after.get('kernel/licenses/linux-firmware/WHENCE',{}) and
              any(p.startswith('kernel/licenses/linux-firmware/') and
                  (p.startswith('kernel/licenses/linux-firmware/LICENSES/') or p.rsplit('/',1)[-1].startswith(('LICENSE','LICENCE','COPYING')))
                  and 'sha256' in r for p,r in after.items()))
    require(debian or upstream,'firmware update lacks complete input licenses')
    allowed=changed | {'hardware.json',FIRMWARE_PROOF}
    unit='units/qemu-guest-agent.service';wanted='units/mojt.target.wants/qemu-guest-agent.service'
    if before.get(unit) != after.get(unit) or before.get(wanted) != after.get(wanted):
        require(unit not in before and wanted not in before and
                normalized(after.get(unit,{})) == dict(sha256=hashlib.sha256(QEMU_AGENT_UNIT.encode()).hexdigest(),mode=0o444)
                and after.get(wanted) == dict(link='../qemu-guest-agent.service')
                and 'link' in after.get('bin/qemu-ga',{}), 'unsupported QEMU guest service transition')
        allowed.update((unit,wanted))
    return allowed


def profile_review(selected, candidate, profile, *, selected_system=None, candidate_system=None):
    """Read only the small, inventoried contract when firmware data actually changes."""
    previous_layout=system.component_profile(selected);layout=system.component_profile(candidate)
    one_legacy=(previous_layout is None) != (layout is None)
    changed_firmware=(firmware_inventory(selected['description']['profile']) != firmware_inventory(candidate['description']['profile']))
    expand=one_legacy or changed_firmware
    before=(selected_system.inventory if selected_system is not None and not expand else
        system.logical_inventory(profile,selected,parts=selected_system.parts if selected_system is not None else None,firmware=expand))
    after=(candidate_system.inventory if candidate_system is not None and not expand else
        system.logical_inventory(profile,candidate,parts=candidate_system.parts if candidate_system is not None else None,firmware=expand))
    allowed=set()
    if layout is not None and not any(r['role']=='firmware' for r in layout['components']) and 'hardware.json' not in before and 'hardware.json' not in after:
        allowed=set(firmware_inventory(before)) | {FIRMWARE_PROOF}
    if layout is not None and not any(r['role']=='firmware' for r in layout['components']) and 'hardware.json' in after:
        following=artifact.parse_json(common.checked_bytes(system.profile_file(profile,'hardware.json',manifest=candidate)))
        if following.get('format') == 3 and following.get('firmware_mode') == 'none':
            root=system.profile_root(profile)
            previous_profile=(system.realization_path(root,selected['description']['provenance']['artifact'])/'profile'
                if 'artifact' in selected['description']['provenance'] else root/'system'/selected['description']['label'])
            raw=common.checked_bytes(system.profile_file(previous_profile,'hardware.json',manifest=selected))
            require(before['hardware.json']['sha256'] == hashlib.sha256(raw).hexdigest(),'baseline hardware metadata changed')
            previous=artifact.parse_json(raw)
            mutable={'format','firmware_mode','firmware_tree_sha256','licenses_tree_sha256'}
            require({k:v for k,v in previous.items() if k not in mutable} == {k:v for k,v in following.items() if k not in mutable}
                    and following['firmware_tree_sha256'] is None and following['licenses_tree_sha256'] is None
                    and not firmware_inventory(after),'minimal System changes non-firmware hardware policy')
            allowed=set(firmware_inventory(before)) | {'hardware.json',FIRMWARE_PROOF}
            if 'kernel/lib' not in after:allowed.add('kernel/lib')
    if allowed:
        for name,row in sorted(before.items(),key=lambda pair:len(pair[0].split('/')),reverse=True):
            if row.get('directory') and name not in after and all(p in allowed for p in before if p.startswith(name+'/')):
                allowed.add(name)
    needed=(firmware_inventory(before) != firmware_inventory(after) or before.get(FIRMWARE_PROOF) != after.get(FIRMWARE_PROOF)) and not allowed
    proof=None
    if needed and FIRMWARE_PROOF in after:
        raw=common.checked_bytes(system.profile_file(profile,FIRMWARE_PROOF,manifest=candidate))
        require(len(raw) <= 65536 and after[FIRMWARE_PROOF].get('sha256') == hashlib.sha256(raw).hexdigest(),
                'firmware contract differs from profile')
        proof=artifact.parse_json(raw)
    return tooling_review(selected,candidate,firmware=proof,inventories=(before,after),allowed_data=allowed)


def user_bus_paths(before, after):
    accounts = paths.accounts
    expected = {
        "user-units/" + name: dict(sha256=hashlib.sha256(text.encode()).hexdigest(), mode=0o444)
        for name, text in accounts.USER_BUS_UNITS.items()
    }
    socket = "user-units/dbus.socket"
    if socket in before and socket not in after:
        before, after = after, before
    if any(after.get(name) != row for name, row in expected.items()):
        return set()
    default = "user-units/default.target"
    legacy = dict(sha256=hashlib.sha256(accounts.USER_SESSION_TARGET.encode()).hexdigest(), mode=0o444)
    if before.get(default) != legacy or any(name in before for name in expected if name != default):
        return set()
    daemon = before.get("bin/dbus-daemon", {})
    config = accounts.user_bus_config(daemon.get("link"))
    if not config or after.get("bin/dbus-daemon") != daemon:
        return set()
    config_path = accounts.USER_BUS_CONFIG
    link = dict(link=config)
    if after.get(config_path) != link or before.get(config_path) not in (None, link):
        return set()
    return {*expected, config_path}


def tooling_review(selected, candidate, *, firmware=None, inventories=None, allowed_data=()):
    """Allow management tooling changes; do not infer service/schema migrations."""
    old = manifests.validate(selected)['description'];new = manifests.validate(candidate)['description']
    previous,following = inventories if inventories is not None else (old['profile'],new['profile'])
    before = {p:normalized(r) for p,r in previous.items() if p != management.FILENAME}
    after = {p:normalized(r) for p,r in following.items() if p != management.FILENAME}
    changed = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))
    firmware_paths=firmware_review(selected,candidate,firmware) if firmware is not None else set()
    bus_paths = user_bus_paths(before, after)
    blocked = []
    for path in changed:
        allowed = (path.startswith(('tools/', 'tests/')) or path in ('tools', 'tests', 'bin/mpm', 'bin/man', 'bin/manpath', 'bin/mojt-system-inspect', 'bin/mbt', 'share/man/man1/mpm.1',
                   'share/man/man1/mbt.1','mbt-runtime.json','mpm-runtime.json','share/mbt/kernel-first-build.json') + paths.MBT_SOURCE_FILES
                   or path.startswith('bin/') and path not in before and path in after
                   or path in ('share', 'share/man', 'share/man/man1') and path not in before and after.get(path, {}).get('directory') is True
                   or path in ('share/mbt','man','manifests','bootstrap','bootstrap/licenses') and all(row is None or row.get('directory') is True for row in (before.get(path),after.get(path))))
        if path=='libexec/mpm/bin/openssl' and path not in before:
            # The public and private aliases must name the same exact provider
            # executable. Installation separately checks their retained closure.
            allowed=(after.get(path,{}).get('link') is not None and
                     after[path]['link']==after.get('bin/openssl',{}).get('link'))
        if path == 'version':
            allowed = after.get(path, {}).get('sha256') == hashlib.sha256((new['label'] + '\n').encode()).hexdigest()
        if not allowed and path not in firmware_paths and path not in bus_paths and path not in allowed_data:blocked.append(path)
    previous_outputs = sorted({r['link'] for r in before.values() if r.get('link') in
        ('/run/mojt-privileged/passwd', '/run/mojt-privileged/sudo')})
    outputs = new['provenance'].get('runtime_outputs', [])
    if outputs != previous_outputs:blocked.append('runtime-output-contract')
    stable = {p:r for p,r in before.items() if p not in changed}
    policy=('firmware-data-and-guest-agent-v1' if firmware is not None and 'units/qemu-guest-agent.service' in firmware_paths
            else 'firmware-data-only-v1' if firmware is not None
            else 'dbus-user-bus-v1' if bus_paths else 'unchanged-startup-only-v1')
    description=dict(policy=policy, selected=selected['id'], candidate=candidate['id'],
        changed=changed, blockers=sorted(blocked), preserved_inventory=artifact.digest(stable),
        runtime_outputs=outputs, compatible=not blocked, effects=False,
        limitation=('Firmware data and the fixed optional QEMU guest service only; no other service or state-schema migration.'
                    if firmware is not None else 'Fixed D-Bus user units only; no state-schema migration or runtime health is authorized.'
                    if bus_paths else 'No service upgrade, new initializer, state-schema migration or runtime health is authorized.'))
    if firmware is not None:
        data_paths=set(firmware_inventory(before)) | set(firmware_inventory(after))
        data_changes=[p for p in changed if p in data_paths]
        description['changed']=[p for p in changed if p not in data_paths]
        # Complete inventories remain bound by the manifests/proof. Boot handover
        # needs their exact change-set identity, not another unbounded path list.
        description['firmware_changes']=dict(count=len(data_changes),digest=artifact.digest(data_changes),
            inventory_before=firmware['inventory_before'],inventory_after=firmware['inventory_after'])
    return base.record(FIRMWARE_REVIEW if firmware is not None else REVIEW,description)


def defaults(root, profile):
    """Only observe missing profile defaults; preserve local files and symlinks."""
    source = system.profile_file(profile,'defaults');missing = [];observed = []
    if not source.exists():return dict(policy='existing-defaults-only-v1', missing=[], observed=artifact.digest([]))
    require(source.is_dir() and not source.is_symlink(), 'unsupported System defaults root')
    def visit(src, dst):
        for file in sorted(src.iterdir()):
            # The assembled System's flat defaults directory also contains
            # these two private resources, linked from /etc/systemd. They are
            # not requests to create unused /etc/journald.conf or timesyncd.conf.
            directory = dst
            if src == source and file.name in ('journald.conf','timesyncd.conf'):
                directory = dst / 'systemd'
                try:parent = directory.lstat()
                except FileNotFoundError:
                    missing.append('systemd/'+file.name);continue
                require(stat.S_ISDIR(parent.st_mode),'unsupported System defaults parent')
            target = directory / file.name;relative = target.relative_to(root / 'state/etc').as_posix()
            try:info = target.lstat()
            except FileNotFoundError:missing.append(relative);continue
            require(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode), 'unsupported existing default target')
            observed.append(dict(path=relative, mode=info.st_mode, device=info.st_dev, inode=info.st_ino,
                                 link=os.readlink(target) if stat.S_ISLNK(info.st_mode) else None))
            if file.is_dir() and not file.is_symlink() and stat.S_ISDIR(info.st_mode):visit(file, target)
    visit(source, root / 'state/etc')
    return dict(policy='existing-defaults-only-v1', missing=missing, observed=artifact.digest(observed))


def providers(manifest, candidate, refs, adapters, *, baseline_refs=None, inventories=None):
    """Provider-specific preservation facts stay in the manager-owned adapter."""
    reports = [];errors = []
    baselines = manifest['description']['artifacts'] if baseline_refs is None else {
        name:dict(format='mojt-system-provider-baseline-v1',references=[copy.deepcopy(r) for r in baseline_refs if r['provider'] == name])
        for name in sorted({r['provider'] for r in baseline_refs})}
    for name, record in sorted(baselines.items()):
        if baseline_refs is None and name == 'native':continue
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
                previous,following = inventories if inventories is not None else (manifest['description']['profile'],candidate['description']['profile'])
                old = previous.get(path);new = following.get(path)
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


def selected_context(root, baseline):
    """Read the actual selection format; never cast a native-v2 record to v1."""
    import mpm_boot_selection as selection
    if not selection.present(root):
        state,entries,menu = boot.current(root,baseline);entry = entries[state['selected']]
        old = deployment.validate_deployment(entry['record'])
        selected,_,_ = boot.live_context(root,entry)
        return dict(native=False,selected=state['selected'],old=old,manifest=selected,menu=menu,
                    bounds=catalog.base_context(boot.read(entry['path']/'base-context.json')),kernel=entry['body'])
    require(baseline is None,'native-v2 selection is authoritative; --baseline is only for a fresh v1 image')
    from mpm_boot_v2 import inputs, slot, DEPLOYMENT
    from mpm_boot_v2_store import inspect
    state,entries,menu = selection.selected(root)
    require(state is not None,'native-v2 initial selection is incomplete')
    selected_id = state['description']['selected'];value = entries[selected_id]['record']
    if base.io.preparation_verify():
        require(inspect(root,selected_id,verify=True) == value,'selected native-v2 slot changed')
    source = value['description']['inputs'];old = inputs(source)
    checked=system.CheckedSystem(root,old['system']['artifact'],verify=base.io.preparation_verify())
    body,receipt,realized,profile,manifest=checked.body,checked.receipt,checked.realization,checked.profile,checked.manifest
    require(all(realized['description'][key] == old['system'][key] for key in ('composition','manifest'))
            and manifest['id']==old['system']['manifest'] and manifest['description']['label']==old['system']['generation']
            and body['platform']==old['platform'],'selected native System identity differs')
    kernel_body,_ = kernel.object_record(root/'kernel/installed'/kernel.identifier(old['kernel']['artifact']),old['kernel']['artifact'],verify=base.io.preparation_verify())
    require(dict(deployment.kernel_identity(kernel_body),upstream=kernel_body['version']['upstream']) == old['kernel'],
            'selected native Kernel identity differs')
    bounds = catalog.base_context(dict(format=catalog.BASE_FORMAT,platform=old['platform'],
        base={key:old['base'][key] for key in ('artifact','release')},
        kernel_min=old['base']['kernel_min'],kernel_max=old['base']['kernel_max']))
    require(artifact.digest(bounds) == old['base']['bounds_evidence'],'selected native Base bounds differ')
    return dict(native=True,selected=selected_id,old=old,manifest=manifest,menu=menu,bounds=bounds,kernel=kernel_body,
                baseline_format=DEPLOYMENT,baseline_entry=slot(selected_id),selected_inputs=source['id'],baseline_inputs=source,
                entries=entries,selection=state,systems={body['id']:checked},objects=checked.loaded,provider_references=checked.references,
                selected_system=dict(old['system'],receipt=receipt['id'],realization=realized['id']))


def _prepare(root, identifier, baseline, adapters, *, area='system', bounds=None, joined=False, context=None):
    require(os.geteuid() == 0, 'verified System planning requires administrator access to retained content')
    physical = system.target_identity(root)
    context = selected_context(root,baseline) if context is None else context
    old,selected,menu = context['old'],context['manifest'],context['menu']
    if joined:
        require(context['native'] and area in ('base','system','kernel'), 'joined updates require native-v2 selection')
        old = copy.deepcopy(old)
        if area == 'base':
            body,receipt = base.object_record(root,identifier,verify=base.io.preparation_verify())
            realized = base.realization(root,identifier,receipt,verify=base.io.preparation_verify())
            require(realized is not None,'candidate Base is not installed')
            if bounds is None:
                if identifier == context['old']['base']['artifact']:bounds = context['bounds']
                else:
                    # Scope this local request to the exact selected Kernel.
                    # This is not inherited release support or a broader range
                    # claim by the Base producer; explicit bounds remain accepted.
                    upstream = context['kernel']['version']
                    require(upstream['scheme'] == 'dotted-v1','explicit Base Kernel bounds required for an opaque Kernel version')
                    bounds = dict(format=catalog.BASE_FORMAT,platform=body['platform'],
                        base=dict(artifact=identifier,release=body['version']['upstream']),
                        kernel_min=upstream['upstream'],kernel_max=upstream['upstream'])
            bounds = catalog.base_context(bounds)
            require(bounds['base'] == dict(artifact=identifier,release=body['version']['upstream'])
                    and bounds['platform'] == body['platform'], 'Kernel bounds do not bind candidate Base')
            old['base'] = dict(bounds['base'],rootfs_sha256=realized['description']['rootfs_sha256'],
                kernel_min=bounds['kernel_min'],kernel_max=bounds['kernel_max'],bounds_evidence=artifact.digest(bounds))
            context['bounds'] = bounds
        elif area == 'kernel':
            body,_ = kernel.object_record(root/'kernel/installed'/kernel.identifier(identifier),identifier,verify=base.io.preparation_verify())
            require(body['platform'] == old['platform'] and not body['requirements'] and not body['dependencies'],
                    'unsupported candidate Kernel platform/requirements')
            old['kernel'] = dict(deployment.kernel_identity(body),upstream=body['version']['upstream'])
            context['kernel'] = body
        if area != 'system':identifier = old['system']['artifact']
    persistent = common.state_inputs(root)
    info = base.store_info(root);require(info is not None, 'native installation store required')
    systems=context.setdefault('systems',{})
    checked=systems.get(identifier)
    if checked is None:
        checked=system.CheckedSystem(root,identifier,verify=base.io.preparation_verify(),loaded=context.setdefault('objects',{}));systems[identifier]=checked
    body,receipt,realized,profile,candidate=checked.body,checked.receipt,checked.realization,checked.profile,checked.manifest
    refs=checked.references
    system.providers(root,refs,adapters,effect='verify' if base.io.preparation_verify() else 'inspect')
    outputs=candidate['description']['provenance'].get('runtime_outputs',[])
    system.verify_links(profile,refs,adapters,outputs,manifest=candidate,inventory=checked.inventory)
    context['candidate']=checked
    base_body, base_receipt = base.object_record(root, old['base']['artifact'], verify=base.io.preparation_verify())
    require(base_body['version']['upstream'] == old['base']['release'], 'installed Base differs from selected exact Base')
    base_realized = base.realization(root, base_body['id'], base_receipt, verify=base.io.preparation_verify())
    require(base_realized is not None, 'selected Base needs an installed native realization')
    if context['native']:
        require(base_realized['description']['rootfs_sha256'] == old['base']['rootfs_sha256'],
                'selected native Base realization differs from deployment')
    release = tomllib.loads(common.checked_bytes(base.object_path(root, base_body['id']) / 'payload/manifest.toml').decode())
    require(type(release.get('abi')) is dict and release['abi'], 'selected Base needs explicit ABI facts')
    require(release['base']['version'] == old['base']['release'] and release['state']['layout_version'] == persistent['layout'],
            'candidate Base release/state layout differs')
    facts = dict(format=manifests.CONTEXT, architecture=release['base']['architecture'], base_abi=release['abi'],
        state_layout=persistent['layout'], ports=persistent['ports'], required_system_paths=persistent['system_shells'])
    compatibility = manifests.check(candidate, facts)
    require(base_body['platform'] == body['platform'] == old['platform'], 'System/Base/deployment platform differs')
    bounds = context['bounds']
    require(bounds['base'] == {key:old['base'][key] for key in ('artifact','release')} and bounds['platform'] == old['platform'], 'retained Kernel bounds do not bind selected Base')
    upstream = context['kernel']['version']
    require(upstream['scheme'] == 'dotted-v1' and catalog.compare_versions(bounds['kernel_min'], upstream['upstream']) <= 0
            and catalog.compare_versions(upstream['upstream'], bounds['kernel_max']) <= 0, 'preserved Kernel is outside selected Base bounds')
    previous=context.get('systems',{}).get(context['old']['system'].get('artifact'))
    reviewed = profile_review(selected,candidate,profile,selected_system=previous,candidate_system=checked)
    requirements = providers(selected,candidate,refs,adapters,baseline_refs=context.get('provider_references'),
        inventories=(previous.inventory if previous is not None else system.logical_inventory(profile,selected),checked.inventory))
    if base.io.preparation_verify():management_report=management.check_target(root,profile,candidate)
    else:
        observed=management.schemas(root,systems=tuple(systems.values()),selection=context.get('selection'))
        preparing=context.setdefault('preparing_support',management.current())
        management_report=dict(management.check_transition(preparing,checked.support,observed),observed=observed,
            candidate=checked.support['id'] if checked.support else None,preparing=preparing['id'])
    tree = base.realization_path(root, base_body['id']) / 'tree/rootfs'
    shell_report = shells(root, tree, persistent, candidate, refs, adapters)
    observed_defaults = defaults(root, profile)
    from mpm_base_boot import defaults_check
    base_defaults = defaults_check(root,tree)
    errors = list(compatibility['errors']) + list(requirements['errors']) + list(shell_report['errors'])
    if body['metadata'].get('deployment_contract') != dict(format='mojt-system-content-only-v1', initialization='profile-services-not-reviewed'):
        errors.append('candidate has no supported System initialization review contract')
    if not reviewed['description']['compatible']:errors.append('startup/service changes require a supported initialization contract: ' + ', '.join(reviewed['description']['blockers']))
    if not management_report['compatible']:errors.extend(management_report['errors'])
    if observed_defaults['missing']:errors.append('missing System defaults need explicit preparation: ' + ', '.join(observed_defaults['missing']))
    if base_defaults['missing']:errors.append('missing Base defaults need explicit preparation: ' + ', '.join(base_defaults['missing']))
    # Bind actual persistent/selection facts, not the running System label.
    if context['native']:
        from mpm_boot_selection import current
        from mpm_boot_selection import checked, MENU
        unchanged = checked(root/MENU) == menu
    else:unchanged = boot.checked_file(root/'boot/mojt/grub.cfg') == menu
    require(unchanged and system.target_identity(root) == physical, 'selection or target changed during System planning')
    require(common.state_inputs(root) == persistent and defaults(root, profile) == observed_defaults, 'persistent state changed during System planning')
    details = dict(target=str(root), target_identity=physical, installation=info['installation'], baseline=baseline,
        selected=context['selected'], selection_sha256=hashlib.sha256(menu).hexdigest(), root_uuid=old['boot']['root_uuid'],
        operation='system', retained_base=dict(old['base'], receipt=base_receipt['id'], realization=base_realized['id']),
        retained_kernel=copy.deepcopy(old['kernel']), kernel_bounds=bounds,
        candidate_system=dict(artifact=identifier, receipt=receipt['id'], realization=realized['id'], composition=realized['description']['composition'],
            manifest=candidate['id'], generation=candidate['description']['label'], runtime_outputs=outputs),
        state=persistent['evidence'], checks=dict(compatible=not errors, errors=errors, base=compatibility, management=management_report,
            providers=requirements, startup=reviewed, account_shells=shell_report, defaults=observed_defaults),
        writes=False, effects=False, stage_ready=False, boot_ready=False,
        remaining_gates=['authoritative native-v2 System staging/selection and runtime status join', 'bootstrap reuse of the same install/handover path',
                         'atomic next-boot selection and focused owner System boot/return acceptance'])
    if context['native']:
        details.update({key:context[key] for key in ('baseline_format','baseline_entry','selected_inputs','selected_system')})
        details['remaining_gates'] = ['active-v2 constructor/stage join', 'request/configuration-to-boot join',
                                     'bootstrap reuse of the same installation/staging APIs']
    fmt = NATIVE_FORMAT if context['native'] else FORMAT
    if joined:
        details.update(operation=area,baseline_inputs=context['baseline_inputs'],
                       boot_base=details.pop('retained_base'),boot_kernel=details.pop('retained_kernel'),
                       boot_system=details.pop('candidate_system'))
        details['remaining_gates'] = ['construct and admit exact deployment', 'explicit next-boot publication and owner boot acceptance']
        fmt = BOOT_FORMAT
    result = base.record(fmt,details)
    require(len(artifact.canonical(result)) <= artifact.MAX_METADATA, 'System plan exceeds metadata limit')
    return result


def boot_fields(value):
    """One candidate projection for legacy bootstrap and joined native updates."""
    require(type(value) is dict and value.get('format') in (FORMAT,NATIVE_FORMAT,BOOT_FORMAT),'unsupported boot preflight')
    d = base.envelope(value,value['format'])
    if value['format'] == BOOT_FORMAT:
        import mpm_boot_v2 as model
        before = model.inputs(d['baseline_inputs'])
        require(d['operation'] in ('base','system','kernel') and d['selected_inputs'] == d['baseline_inputs']['id'],
                'invalid boot transition area/baseline')
        result = {area:d['boot_'+area] for area in ('base','system','kernel')}
        for area in result:
            if area != d['operation']:
                require(all(result[area].get(k) == v for k,v in before[area].items()), 'boot transition changed another area: '+area)
        return result
    require(d['operation'] == 'system','unsupported legacy boot operation')
    return dict(base=d['retained_base'],kernel=d['retained_kernel'],system=d['candidate_system'])


def repeat(root, value, adapters):
    """Recompute under the caller's locks; a saved document never authorizes writes."""
    boot_fields(value);d = value['description']
    if value['format'] == BOOT_FORMAT:
        return _prepare(root,boot_fields(value)[d['operation']]['artifact'],None,adapters,
                        area=d['operation'],bounds=d['kernel_bounds'],joined=True)
    return _prepare(root,d['candidate_system']['artifact'],d['baseline'],adapters)


def prepare(root, identifier, *, baseline=None, adapters=None):
    root = system.target(root);boot.disk_root(root);base.io.identifier(identifier)
    with common.read_locks(root):return _prepare(root, identifier, baseline, adapters)


def recheck(root, plan, *, adapters=None):
    boot_fields(plan)
    d = base.envelope(plan,plan['format'])
    require(str(system.target(root)) == d['target'], 'System plan belongs to another target')
    with common.read_locks(system.target(root)):actual = repeat(system.target(root),plan,adapters)
    require(actual == plan, 'System transition inputs changed; prepare a fresh plan')
    return actual
