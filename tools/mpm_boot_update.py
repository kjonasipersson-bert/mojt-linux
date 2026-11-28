# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""One exact installed-candidate path for native Base/System/Kernel updates."""
import copy
import os
from pathlib import Path
import sys
import tempfile
import time

import mojt_artifact as artifact
import mpm_base as base
import mpm_base_transition as common
import mpm_boot_constructor as constructor
import mpm_boot_early as early
import mpm_boot_handover as handover
import mpm_boot_selection as selection
import mpm_boot_v2 as model
import mpm_system as system
import mpm_system_transition as transition
import mpm_native_io as io
import mpm_ui as ui

require = artifact.require


def prepare(root, area, identifier, *, bounds=None, adapters=None):
    root = system.target(root);model.identity(identifier)
    with common.read_locks(root):
        return transition._prepare(root,identifier,None,adapters,area=area,bounds=bounds,joined=True)


def runtime_reference(root, runtime, adapters):
    """Use the running manager's retained interpreter, never the candidate's code."""
    require(runtime is not None,'offline construction requires an explicit frozen runtime and static BusyBox')
    from mpm_boot_status import read_running, description
    running = read_running(runtime)
    require(running is not None,'missing authoritative running deployment')
    refs = system.retained_providers(root,description(running)['system']['artifact'])
    interpreter = str(Path(sys.executable).resolve())
    for ref in refs:
        adapter = adapters[ref['provider']]
        if hasattr(adapter,'contains') and adapter.contains(ref,interpreter):
            adapter.verify_path(ref,interpreter,executable=True)
            return ref,interpreter
    raise ValueError('running interpreter is outside the retained manager closure')


def boot_busybox(runtime, explicit):
    require(explicit is not None or runtime is not None,
            'offline construction requires an explicit static BusyBox')
    if explicit is not None:
        busybox = Path(explicit)
    else:
        from mpm_boot_status import read_running, description
        running_path = runtime.system_bin.parent / 'busybox'
        busybox = running_path.resolve(strict=True)
        if busybox != running_path:
            running = read_running(runtime)
            require(running is not None, 'missing authoritative running deployment')
            profile = system.realization_path(runtime.disk, description(running)['system']['artifact']) / 'profile'
            require(system.profile_file(profile, 'busybox') == busybox,
                    'running BusyBox differs from the retained System profile')
    require(busybox == busybox.absolute() and busybox == busybox.resolve(), 'canonical static BusyBox required')
    return busybox


def source_for(plan, runtime, busybox):
    candidate = transition.boot_fields(plan);p = plan['description']
    d = copy.deepcopy(p['baseline_inputs']['description'])
    for area in ('base','system','kernel'):
        d[area] = {key:candidate[area][key] for key in d[area]}
    d['constructor'] = constructor.constructor(runtime,busybox,handover=True)
    required = {row['family']:row for row in d['management_required']}
    for row in selection.MANAGEMENT_SUPPORT:
        current = required.setdefault(row['family'],dict(family=row['family'],read=[],write=[],capabilities=[]))
        for key in ('read','write','capabilities'):current[key] = sorted(set(current[key]) | set(row[key]))
    d['management_required'] = [required[key] for key in sorted(required)]
    source = model.record(model.INPUTS,d);model.inputs(source)
    return source


def stage(root, area, identifier, *, bounds=None, adapters=None, runtime=None,
          runtime_directory=None, busybox=None, tar='tar', dry_run=False, yes=False,
          expected_preflight=None, expected_inputs=None, verify=False):
    with io.preparation(verify=verify):
        return _stage(root,area,identifier,bounds=bounds,adapters=adapters,runtime=runtime,
            runtime_directory=runtime_directory,busybox=busybox,tar=tar,dry_run=dry_run,yes=yes,
            expected_preflight=expected_preflight,expected_inputs=expected_inputs)


def _stage(root, area, identifier, *, bounds=None, adapters=None, runtime=None,
          runtime_directory=None, busybox=None, tar='tar', dry_run=False, yes=False,
          expected_preflight=None, expected_inputs=None):
    require(os.geteuid() == 0,'boot updates require an administrator')
    root = system.target(root)
    if not yes and not dry_run:
        preview = _stage(root,area,identifier,bounds=bounds,adapters=adapters,runtime=runtime,
            runtime_directory=runtime_directory,busybox=busybox,tar=tar,dry_run=True,yes=True,
            expected_preflight=expected_preflight,expected_inputs=expected_inputs)
        if preview['action'] == 'no-change':return preview
        require(input('Prepare this exact '+area+' for next boot? [y/N] ').strip().lower() in ('y','yes'),'staging cancelled')
        expected_preflight,expected_inputs = preview['preflight'],preview['inputs']
    locks = common.read_locks(root) if dry_run else selection.locked(root)
    with locks:
        return _stage_locked(root,area,identifier,bounds=bounds,adapters=adapters,runtime=runtime,
            runtime_directory=runtime_directory,busybox=busybox,tar=tar,dry_run=dry_run,
            expected_preflight=expected_preflight,expected_inputs=expected_inputs)


def _stage_locked(root, area, identifier, *, bounds=None, adapters=None, runtime=None,
          runtime_directory=None, busybox=None, tar='tar', dry_run=False,
          expected_preflight=None, expected_inputs=None):
    """One plan and one locked transaction; dry-run never constructs or writes."""
    require(os.geteuid() == 0,'boot updates require an administrator')
    started = time.monotonic()
    print('Checking exact '+area+' candidate and compatibility...',file=sys.stderr,flush=True)
    root = system.target(root)
    context = transition.selected_context(root,None)
    with ui.phase('Check candidate and compatibility'):
        plan = transition._prepare(root,identifier,None,adapters,area=area,bounds=bounds,joined=True,context=context)
    print('Candidate checks: %.2f s' % (time.monotonic()-started),file=sys.stderr,flush=True)
    require(expected_preflight is None or plan['id'] == expected_preflight,'boot inputs changed after approval; repeat preview')
    p = plan['description'];require(p['checks']['compatible'],'boot update blocked: '+'; '.join(p['checks']['errors']))
    before = p['baseline_inputs']['description']
    report = dict(area=area,artifact=identifier,selected=p['selected'],changed=False,dry_run=dry_run,
                  verification_requested=io.preparation_verify(),
                  selection_changed=False,running_changed=False,persistent_state_changed=False,
                  checks=p['checks'],preflight=plan['id'],deployment=None)
    candidate = transition.boot_fields(plan)[area]
    report['release'] = candidate.get('release',candidate.get('generation'))
    if all(candidate.get(key) == value for key,value in before[area].items()):
        if io.preparation_verify():selection.ready(root,p['selected'],verify=True)
        return dict(report,action='no-change',deployment=p['selected'])
    if runtime_directory is not None:
        runtime_directory = Path(runtime_directory).absolute()
        require(runtime_directory == runtime_directory.resolve(),'linked constructor runtime')
        measured = early.read(runtime_directory/'runtime.json');early.runtime(measured)
        ref,interpreter = None,None
    else:
        ref,interpreter = runtime_reference(root,runtime,adapters)
        with ui.phase('Inspect boot runtime'):
            measured=constructor.retained_runtime(root,ref,interpreter,context['entries'][context['selected']],adapters=adapters)
            if measured is None:
                measured=constructor.describe_runtime(root,ref,interpreter,adapters=adapters)
                if not dry_run:constructor.retain_runtime(root,measured)
    busybox = boot_busybox(runtime, busybox)
    source = source_for(plan,measured,busybox)
    require(expected_inputs is None or source['id'] == expected_inputs,'constructor/runtime changed after approval')
    report['inputs'] = source['id']
    # Reuse only fully admitted exact inputs. An interrupted raw slot never
    # becomes bootable merely because its files happen to exist.
    entries,_ = selection.summaries(root)
    matches = [key for key,row in entries.items() if row['record']['description']['inputs'] == source]
    require(len(matches) <= 1,'multiple deployments for exact constructor inputs')
    if matches:
        if io.preparation_verify():selection.ready(root,matches[0],verify=True)
        return dict(report,action='no-change',deployment=matches[0])
    if dry_run:return dict(report,action='stage',inputs=source['id'])
    print('Preparing exact '+area+' deployment'+(' with full content verification' if io.preparation_verify() else '')+'...',file=sys.stderr,flush=True)
    if io.preparation_verify():selection.store.audit_inputs(root,source,p['kernel_bounds'],adapters=adapters)
    with tempfile.TemporaryDirectory(prefix='mojt-boot-update-') as temporary:
        work = Path(temporary)
        with ui.phase('Prepare Base and machine handover'):
            contract = handover.prepare_locked(root,source,plan,context,adapters=adapters,tar=tar)
        result = selection._stage_locked(root,source,runtime_directory,busybox,work/'construction',
                                 bounds=p['kernel_bounds'],adapters=adapters,contract=contract,entries=context['entries'],runtime_value=measured)
    payload = result['initramfs_payload']
    print('Early-boot runtime/drivers: '+('reused' if payload['reused'] else 'built'),file=sys.stderr,flush=True)
    return dict(report,action='stage',changed=True,deployment=result['deployment'],initramfs_payload=payload)


def upgrade(root, area, identifier, *, expected_selected=None, dry_run=False, yes=False, verify=False, **options):
    """Stage and publish next boot. The single menu remains the commit point."""
    require(os.geteuid() == 0,'boot updates require an administrator')
    root = system.target(root)
    with common.read_locks(root):
        value,_,_ = selection.selected(root)
        require(value is not None,'native-v2 initial selection is missing')
        selected = value['description']['selected']
        require(expected_selected is None or selected == expected_selected,'selected deployment changed; repeat preview')
    # Preview and approval precede all construction, even when activation
    # composes several existing low-level operations.
    preview = stage(root,area,identifier,dry_run=True,verify=verify,**options)
    require(preview['selected'] == selected,'selection changed during update preview')
    if dry_run:
        show_preview(root,area,identifier,preview)
        return dict(preview,action='activate',selection_would_change=preview['deployment'] != selected)
    if preview['deployment'] == selected:return dict(preview,dry_run=False,action='no-change',selection_would_change=False)
    show_preview(root,area,identifier,preview)
    if not yes:require(input('Select this exact '+area+' update for NEXT boot? [y/N] ').strip().lower() in ('y','yes'),'activation cancelled')
    with common.read_locks(root):
        require(selection.selected(root)[0]['description']['selected'] == selected,'selection changed after approval')
    started = time.monotonic()
    staged = stage(root,area,identifier,yes=True,verify=verify,expected_preflight=preview['preflight'],
                   expected_inputs=preview.get('inputs'),**options)
    require(staged['selected'] == selected,'selection changed before construction')
    print('Deployment preparation: %.2f s' % (time.monotonic()-started),file=sys.stderr,flush=True)
    started = time.monotonic()
    print('Publishing boot selection...',file=sys.stderr,flush=True)
    chosen = selection.select(root,staged['deployment'],area=area,expected_selected=selected,yes=True,verify=verify)
    print('Selection verification/publication: %.2f s' % (time.monotonic()-started),file=sys.stderr,flush=True)
    return dict(staged,action='activate',changed=chosen['changed'],dry_run=False,
                selection_changed=chosen['changed'],selected=chosen['selected'],previous=chosen['previous'])


def activate(root, area, identifier, *, expected_selected=None, dry_run=False, yes=False, verify=False, running_record=None):
    """Select an already admitted entry; never construct or audit content by default."""
    require(os.geteuid() == 0,'boot activation requires an administrator')
    root = system.target(root);model.identity(identifier)
    with common.read_locks(root):
        value,entries,_ = selection.selected(root)
        require(value is not None,'native-v2 initial selection is missing')
        selected = value['description']['selected']
        require(expected_selected is None or expected_selected == selected,'selected deployment changed; repeat preview')
        before = entries[selected]['record']['description']['inputs']['description']
        available,_ = selection.summaries(root)
        preserved = [key for key in ('base','system','kernel','platform','boot','firmware','state_requirements') if key != area]
        matches = {key:item for key,item in available.items()
                   if (inputs := item['record']['description']['inputs']['description'])[area]['artifact'] == identifier
                   and all(inputs[key] == before[key] for key in preserved)}
        require(matches,'no prepared '+area+' boot entry; run mpm '+area+' stage --artifact '+identifier+' first')
        require(selected in matches or len(matches) == 1,'multiple prepared boot entries; use select --deployment with an exact deployment ID')
        deployment = selected if selected in matches else next(iter(matches))
        candidate = matches[deployment]['record']['description']['inputs']['description'][area]
    preview = dict(area=area,artifact=identifier,release=candidate.get('generation',candidate.get('release')),
                   selected=selected,deployment=deployment)
    chosen = selection.select(root,deployment,area=area,expected_selected=selected,
                              dry_run=dry_run,yes=yes,verify=verify,running_record=running_record)
    return dict(preview | chosen,action='activate',selection_changed=chosen['changed'],
                selection_would_change=deployment != selected,running_changed=False,persistent_state_changed=False)


def choose_artifact(root, area, *, prepared=False):
    """Metadata-only installed inventory; compatibility is checked after choice."""
    if prepared:
        value,current_entries,_ = selection.selected(root)
        require(value is not None,'native-v2 initial selection is missing')
        before=current_entries[value['description']['selected']]['record']['description']['inputs']['description']
        entries,_ = selection.summaries(root)
        preserved=[key for key in ('base','system','kernel','platform','boot','firmware','state_requirements') if key!=area]
        entries={key:item for key,item in entries.items() if all(item['record']['description']['inputs']['description'][field]==before[field] for field in preserved)}
        candidates = {item['record']['description']['inputs']['description'][area]['artifact']:
                      item['record']['description']['inputs']['description'][area] for item in entries.values()}
        installed=system.status(root)['installed'] if area=='system' else __import__('mpm_kernel').status(root/'kernel')['installed'] if area=='kernel' else []
        rows = [dict(artifact=key,label=next((r.get('label',row.get('generation',row.get('release'))) for r in installed if r['artifact']==key),row.get('generation',row.get('release'))),
            version=next((r['version'] for r in installed if r['artifact']==key),dict(release_id=row.get('generation',row.get('release'))))) for key,row in sorted(candidates.items())]
    elif area == 'kernel':
        import mpm_kernel
        rows = mpm_kernel.status(root/'kernel')['installed']
    elif area == 'base':
        import mpm_base_status
        rows = mpm_base_status.status(root)['installed']
    else:
        rows = system.status(root)['installed']
    require(rows,'no '+('prepared' if prepared else 'installed')+' '+area+' candidates; '+('run stage first' if prepared else 'install content first'))
    print(('Prepared' if prepared else 'Installed')+' '+area+' candidates:',file=sys.stderr)
    for number,row in enumerate(rows,1):
        print('  %d. %s [%s]' % (number,ui.name(row),ui.short(row['artifact'])),file=sys.stderr)
    while True:
        answer = input('Candidate number, or q to cancel: ').strip()
        require(answer.lower() != 'q','candidate selection cancelled')
        if answer.isascii() and answer.isdecimal() and 1 <= int(answer) <= len(rows):
            return rows[int(answer)-1]['artifact']
        print('Choose a listed number, or q.',file=sys.stderr)


def show_preview(root, area, identifier, preview):
    from mpm_boot_status import description
    value,entries,unused=selection.selected(root)
    before=description(entries[preview['selected']]['record']);after=copy.deepcopy(before)
    after[area]['artifact']=identifier
    after[area]['generation' if area=='system' else 'release']=preview['release']
    ui.input_preview(root,before,after,before_id=preview['selected'],after_id=preview.get('deployment'))


def main(area, argv, *, runtime=None):
    """Shared public boot operations; preflight is an internal implementation step."""
    import argparse
    import json
    import subprocess
    import tarfile
    parser = argparse.ArgumentParser(prog='mpm '+area)
    commands = parser.add_subparsers(dest='action',required=True)
    for action in ('activate','upgrade','stage','select','rollback'):
        command = commands.add_parser(action)
        if action in ('activate','upgrade','stage'):
            command.add_argument('--artifact',help='exact installed candidate; does not fetch or build')
            if area == 'base':command.add_argument('--base-context',type=Path,help='Kernel bounds for this exact Base')
            if action != 'stage':
                command.add_argument('--expected-selected')
            command.add_argument('--verify',action='store_true',help='explicitly audit retained content')
        else:
            if action == 'select':command.add_argument('--deployment',required=True)
            command.add_argument('--expected-selected',required=True)
            command.add_argument('--verify',action='store_true',help='explicitly audit retained content before selection')
        command.add_argument('--disk-root',type=Path)
        command.add_argument('--dry-run',action='store_true')
        command.add_argument('-y','--yes',action='store_true')
        command.add_argument('--json',action='store_true')
    args = parser.parse_args(argv)
    try:
        require(args.disk_root is not None or runtime is not None,'specify --disk-root for an offline target')
        root = args.disk_root or runtime.disk
        live = runtime if args.disk_root is None else None
        from mpm_boot_status import read_running
        running=read_running(live) if live is not None else None
        if live is not None:require(os.path.ismount(root),'running installation disk is unavailable')
        require(selection.present(root),'this operation requires native-v2 boot selection')
        if args.action in ('select','rollback'):
            result = selection.select(root,getattr(args,'deployment',None),area=area,expected_selected=args.expected_selected,
                rollback=args.action == 'rollback',dry_run=args.dry_run,yes=args.yes,verify=args.verify,
                running_record=running)
        else:
            if args.artifact is None:
                require(not args.yes and not args.json and sys.stdin.isatty(),
                        '--artifact is required with --yes, --json or noninteractive input')
                args.artifact = choose_artifact(root,area,prepared=True) if args.action == 'activate' else choose_artifact(root,area)
            if args.action == 'activate':
                result = activate(root,area,args.artifact,expected_selected=args.expected_selected,
                                  verify=args.verify,dry_run=args.dry_run,yes=args.yes,running_record=running)
            else:
                from mpm_system_cli import ProviderAdapters
                adapters = ProviderAdapters(live)
                context = getattr(args,'base_context',None)
                options = dict(bounds=base.read(context) if context else None,adapters=adapters,runtime=live,
                               tar=str(live.helpers/'tar') if live else 'tar',dry_run=args.dry_run,yes=args.yes)
                if args.action == 'stage':result = stage(root,area,args.artifact,verify=args.verify,**options)
                else:
                    result = upgrade(root,area,args.artifact,expected_selected=args.expected_selected,verify=args.verify,**options)
                    result['action'] = 'upgrade' if result['action'] != 'no-change' else 'no-change'
        if args.json:print(json.dumps(result,sort_keys=True,indent=2))
        else:
            if result.get('artifact'):print('Candidate:',result['release'],'['+ui.short(result['artifact'])+']')
            if args.dry_run:
                print('Preview only; no content or boot selection written.')
                if result.get('action') == 'no-change':print('No changes.')
            elif not result['changed']:print('No changes.')
            elif args.action == 'stage':print('Prepared boot:',result.get('release',''),'['+ui.short(result['deployment'])+']\nNext boot unchanged.')
            else:print('Next boot:',', '.join(k+' '+v for k,v in result.get('next_boot',{}).items()) or result.get('release',''),
                       '['+ui.short(result['selected'])+']\nRunning system unchanged. Reboot when ready.')
        return 0
    except (OSError,ValueError,KeyError,TypeError,RecursionError,EOFError,subprocess.CalledProcessError,tarfile.TarError) as error:
        print('mpm '+area+': '+str(error),file=sys.stderr)
        return 1
