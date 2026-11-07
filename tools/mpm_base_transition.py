# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Read-only Base-transition preflight. No initramfs, slot, effects or selection."""
from contextlib import ExitStack, contextmanager
import copy
import hashlib
import os
from pathlib import Path
import stat
import tomllib

import mojt_artifact as artifact
import mojt_system as system
import mojt_system_manifest as manifests
import mpm_base as base
import mpm_catalog as catalog
import mpm_deployment as deployment
import mpm_kernel as kernel
import mpm_kernel_boot as boot
import mpm_ports_profile as ports
import mpm_transaction as tx

FORMAT='mojt-base-transition-preflight-v1'


def checked_bytes(path):
    path=Path(path).absolute()
    base.require(path==path.resolve(),'transition evidence traverses a symlink')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        before=os.fstat(stream.fileno())
        base.require(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size<=artifact.MAX_METADATA,
                     'unsafe/unbounded transition evidence')
        base.require(before.st_uid in (0,os.geteuid()) and not before.st_mode&0o022,'unprotected transition evidence')
        raw=stream.read(artifact.MAX_METADATA+1);after=os.fstat(stream.fileno())
        base.require(len(raw)==before.st_size and (before.st_size,before.st_mtime_ns,before.st_ctime_ns)==
                     (after.st_size,after.st_mtime_ns,after.st_ctime_ns),'transition evidence changed during inspection')
    return raw


def candidate_checks(body, release, selected, manifest, kernel_body, bounds, facts):
    """Pure declared gates; no inference of a new System, Kernel or ABI policy."""
    base.acceptable(body)
    old=deployment.validate_deployment(selected)
    manifests.validate(manifest);manifests.validate_context(facts)
    base.require(old['system']==dict(manifest=manifest['id'],generation=manifest['description']['label']),
                 'System manifest does not bind the selected generation')
    base.require(deployment.kernel_identity(kernel_body)==old['kernel'], 'Kernel differs from selected exact build')
    base.require(kernel_body['version']['scheme']=='dotted-v1','unsupported Kernel upstream version scheme')
    base.require(not kernel_body['dependencies'] and not kernel_body['requirements'],'unsupported retained Kernel requirements')
    base.require(release.get('format')==1 and type(release.get('base')) is dict and type(release.get('state')) is dict,
                 'unsupported candidate Base manifest')
    base.require(release['base'].get('name')=='mojt' and release['base'].get('version')==body['version']['upstream'],
                 'candidate Base release identity differs')
    abi=copy.deepcopy(release.get('abi'))
    base.require(type(abi) is dict and abi and all(type(k) is str and type(v) is str and v for k,v in abi.items()),
                 'candidate Base needs explicit ABI declarations; do not inherit the running ABI')
    bounds=catalog.base_context(bounds)
    candidate=dict(artifact=body['id'],release=body['version']['upstream'])
    base.require(bounds['base']==candidate,'Kernel bounds are not bound to this exact candidate Base')
    base.require(type(release['base'].get('architecture')) is str, 'missing candidate Base architecture')
    base.require(bounds['platform']==body['platform']==old['platform'] and
                 release['base'].get('architecture')+'-linux'==body['platform'],'Base/platform mismatch')
    layout=release['state'].get('layout_version')
    base.require(type(layout) is int and layout==1,'unsupported candidate state layout')
    candidate_facts=dict(copy.deepcopy(facts),architecture=release['base']['architecture'],base_abi=abi)
    # facts.state_layout comes from actual persistent state, never the candidate.
    report=manifests.check(manifest,candidate_facts)
    errors=list(report['errors'])
    if layout!=facts['state_layout']:errors.append('candidate Base requires another persistent state layout')
    upstream=kernel_body['version']['upstream']
    if not (catalog.compare_versions(bounds['kernel_min'],upstream)<=0 and catalog.compare_versions(upstream,bounds['kernel_max'])<=0):
        errors.append('selected Kernel is outside candidate Base bounds; no implicit Kernel upgrade')
    return dict(declared_compatible=not errors,errors=errors,system_check=report,
                candidate_base=candidate,system=copy.deepcopy(old['system']),kernel=copy.deepcopy(old['kernel']),
                candidate_facts=candidate_facts,kernel_bounds=bounds,
                scope='Declared compatibility only; no runtime libc, state-schema or boot-readiness proof.')


@contextmanager
def read_locks(root):
    # Never create a lock while inspecting. Publication will need all resources
    # initialized, acquired exclusively and rechecked in the same path order.
    names={root/'.artifact-store.lock',root/'artifacts/.lock',*tx.boot_lock_paths(root)}
    with ExitStack() as stack:
        for path in sorted(names):
            if os.path.lexists(path):stack.enter_context(tx.file_lock(path,shared=True,create=False))
        yield


def state_inputs(root):
    for relative in ('state','state/etc','state/var','state/home','state/root'):
        path=root/relative;tx.protected_directory(path,label='Persistent state')
        base.require(path.is_dir(),'persistent state directory missing: '+relative)
    raw=checked_bytes(root/'state/layout-version')
    base.require(raw.strip()==b'1','unsupported or missing persistent state layout')
    passwd=checked_bytes(root/'state/etc/passwd')
    base_paths=[];system_paths=[]
    for line in passwd.decode('utf-8').splitlines():
        parts=line.split(':');base.require(len(parts)==7,'malformed persistent passwd entry')
        shell=parts[6]
        if not shell:continue
        base.require(shell.startswith('/') and not any(v in ('.','..') for v in shell.split('/')),'unsafe persistent account shell')
        (system_paths if shell.startswith('/run/mojt-system/') else base_paths).append(shell)
    # Use the existing profile reader, including confined current-pointer and
    # exact profile/history identity validation. This does not load adapters.
    selected_ports=ports.current(root/'state/var/lib/mojt/ports')
    port_facts=None
    if selected_ports is not None:
        port_facts=dict(format=selected_ports['record']['format'],capabilities=dict(reader='mpm-request-origins-v1',writer='mpm-request-origins-v1'))
    os_release=root/'state/etc/os-release'
    base.require(os_release.is_symlink() and os.readlink(os_release)=='../usr/lib/os-release',
                 'persistent os-release is not the supported relative link; do not overwrite local configuration')
    evidence=dict(layout_sha256=hashlib.sha256(raw).hexdigest(),passwd_sha256=hashlib.sha256(passwd).hexdigest(),
                  ports=selected_ports['record']['id'] if selected_ports else None,os_release_link=os.readlink(os_release))
    return dict(layout=1,ports=port_facts,base_shells=sorted(set(base_paths)),system_shells=sorted(set(system_paths)),evidence=evidence)


def account_shell_check(root, candidate_root, persistent, manifest):
    """Base paths must exist in Base; System-owned paths use its provider reader."""
    manifests.validate(manifest)
    errors = []; retained = []
    for shell in persistent['base_shells']:
        try:
            proof = system.retained_provider_executable(root, manifest, shell)
            if proof is not None:
                retained.append(proof)
                continue
            file = system.virtual_file(candidate_root, shell)
            if not file.is_file() or not file.stat().st_mode & 0o111:
                errors.append('candidate Base lacks executable account shell: ' + shell)
        except (OSError, ValueError) as error:
            errors.append(str(error))
    return dict(compatible=not errors,errors=errors,retained_system_provider_paths=retained)


def _prepare(root,identifier,bounds,baseline):
    base.require(os.geteuid()==0,'verified Base preflight requires access to the protected rootfs')
    state,entries,raw=boot.current(root,baseline)
    selected=entries[state['selected']];old=selected['record']['description']
    manifest,_,_=boot.live_context(root,selected)
    body,receipt=base.object_record(root,identifier,verify=True)
    realized=base.realization(root,identifier,receipt,verify=True)
    base.require(realized is not None,'Base is retained but not installed; complete realization first')
    wrapper=base.object_path(root,identifier)
    manifest_raw=checked_bytes(wrapper/'payload/manifest.toml')
    release=tomllib.loads(manifest_raw.decode('utf-8'))
    persistent=state_inputs(root)
    facts=dict(format=manifests.CONTEXT,architecture=old['platform'].removesuffix('-linux'),
        base_abi=manifest['description']['requirements']['base_abi'],state_layout=persistent['layout'],
        ports=persistent['ports'],required_system_paths=persistent['system_shells'])
    kernel_body,kernel_record=kernel.object_record(root/'kernel/installed'/kernel.identifier(old['kernel']['artifact']),old['kernel']['artifact'],verify=True)
    report=candidate_checks(body,release,selected['record'],manifest,kernel_body,bounds,facts)
    tree=base.realization_path(root,identifier)/'tree/rootfs'
    report['account_shells']=account_shell_check(root,tree,persistent,manifest)
    report['errors'].extend(report['account_shells']['errors'])
    report['declared_compatible']=not report['errors']
    # Check the observed components again, not just labels, before returning one
    # coherent input snapshot. Recheck is still mandatory before future effects.
    base.require(boot.current(root,baseline)[2]==raw,'boot selection changed during Base preflight')
    base.require(boot.live_context(root,selected)[0]==manifest,'System changed during Base preflight')
    base.require(base.object_record(root,identifier,verify=True)[1]==receipt and
                 base.realization(root,identifier,receipt,verify=True)==realized,'candidate Base changed during preflight')
    base.require(kernel.object_record(root/'kernel/installed'/kernel.identifier(old['kernel']['artifact']),old['kernel']['artifact'],verify=True)[1]==kernel_record,
                 'selected Kernel changed during preflight')
    base.require(state_inputs(root)==persistent,'persistent state observations changed during preflight')
    return base.record(FORMAT,dict(target=str(root),baseline=baseline,selected=selected['record']['id'],
        selection_sha256=hashlib.sha256(raw).hexdigest(),root_uuid=old['boot']['root_uuid'],
        installation=receipt['description']['installation'],
        candidate_base=dict(report['candidate_base'],receipt=receipt['id'],realization=realized['id'],
                            inventory=realized['description']['inventory'],manifest_sha256=hashlib.sha256(manifest_raw).hexdigest()),
        retained_system=report['system'],retained_kernel=report['kernel'],kernel_receipt=artifact.digest(kernel_record),
        state=persistent['evidence'],kernel_bounds=report['kernel_bounds'],checks=report,
        writes=False,boot_ready=False,stage_ready=False,
        remaining_gates=['explicit defaults/lifecycle preparation and state/management capability checks',
                         'new bound initramfs and complete deployment publication',
                         'explicit next-boot selection and owner boot acceptance']))


def prepare(root,identifier,bounds,*,baseline=None):
    root=base.target(root);boot.disk_root(root);kernel.identifier(identifier)
    with read_locks(root):return _prepare(root,identifier,bounds,baseline)


def recheck(root,value):
    d=base.envelope(value,FORMAT)
    base.require(str(base.target(root))==d['target'],'Base preflight belongs to another target')
    actual=prepare(root,d['candidate_base']['artifact'],d['kernel_bounds'],baseline=d['baseline'])
    base.require(actual==value,'Base transition inputs changed; prepare a fresh preflight')
    return actual
