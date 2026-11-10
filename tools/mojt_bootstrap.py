# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Fresh native-v2 image bootstrap using the existing MPM installation APIs."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

# The private worker is also invoked directly with Python -I, which omits the
# script directory. Only this fixed bundled directory may supply sibling code.
sys.path.insert(0,str(Path(__file__).resolve().parent))
import mojt_artifact as artifact
import mojt_native_image as native
import mojt_system as paths
import mpm_base as base
import mpm_boot_v2 as model
import mpm_transaction as tx

REQUEST = 'mojt-bootstrap-request-v1'
RESULT = 'mojt-bootstrap-result-v1'
TOOLS = ('unshare','mount','umount','chroot')
CODE = ('mojt_bootstrap.py','mojt_system_package.py')
require = artifact.require


def code_identity():
    return {name:artifact.file_sha(Path(__file__).with_name(name)) for name in CODE}


def request(value):
    d = base.envelope(value,REQUEST)
    artifact.fields(d,('tree','result','tree_identity','creator_mount_namespace','seed','archive','system_version','system_revision','code'))
    from mpm_deployment import validate_deployment
    old = validate_deployment(d['seed'])
    require(old['platform'] == 'x86_64-linux' and old['boot']['console'] in ('serial','local'),'unsupported bootstrap platform/console')
    for key in ('tree','result'):require(type(d[key]) is str and Path(d[key]).is_absolute(),'absolute private bootstrap path required')
    require(type(d['tree_identity']) is list and len(d['tree_identity']) == 2 and all(type(n) is int for n in d['tree_identity']), 'invalid bootstrap directory identity')
    require(type(d['creator_mount_namespace']) is str and d['creator_mount_namespace'].startswith('mnt:['),'missing creator mount namespace')
    artifact.fields(d['archive'],('sha256','size'));model.hexadecimal(d['archive']['sha256'])
    require(type(d['archive']['size']) is int and 0 < d['archive']['size'] <= base.io.MAX_ARCHIVE,'invalid bootstrap archive size')
    artifact.version(dict(upstream=d['system_version'],scheme='dotted-v1',revision=d['system_revision']))
    require(type(d['code']) is dict and set(d['code']) == set(CODE),'unsupported bootstrap implementation')
    for checksum in d['code'].values():model.hexadecimal(checksum)
    return d


def run(*args, **kwargs):
    return subprocess.run([str(v) for v in args],check=True,**kwargs)


def isolated(command, proc, **kwargs):
    """Helpers cannot outlive this construction and pin its temporary store."""
    return run('unshare','--pid','--fork','--kill-child','--mount-proc='+str(proc),*command,**kwargs)


def fresh_tree(tree, result, value):
    d = request(value);tree = Path(tree).absolute();result = Path(result).absolute()
    require(os.geteuid() == 0,'bootstrap construction requires an administrator')
    require(tree == tree.resolve() and result == result.resolve() and tree.name == 'filesystem' and result.name == 'result'
            and tree.parent == result.parent and tree.parent.name.startswith('.mojt-vm-'), 'only a new private builder tree is accepted')
    require(str(tree) == d['tree'] and str(result) == d['result'] and
            [tree.stat().st_dev,tree.stat().st_ino] == d['tree_identity'],'bootstrap target changed')
    for name in ('artifacts','realizations','boot/mpm/format','boot/mpm/grub.cfg'):
        require(not os.path.lexists(tree/name),'existing installation/selection cannot be bootstrapped: '+name)
    require(base.read(result/'selected-deployment.json') == d['seed'],'bootstrap seed changed')
    old = d['seed']['description'];folder = tree/'boot/mojt'/old['system']['generation']/old['base']['release']
    require(base.read(folder/'deployment.json') == d['seed'],'private tree differs from exact seed')
    profile = tree/'system'/old['system']['generation']
    require(all(artifact.file_sha(profile/'tools'/name) == artifact.file_sha(Path(__file__).with_name(name)) for name in paths.MPM_FILES),
            'bootstrap manager differs from delivered System')
    require(d['code'] == code_identity(),'bootstrap implementation changed')
    return old,profile


def finalize(*, tree, result, base_package, system_version, system_revision):
    """Manager-owned tree callback, before mkfs and before image publication."""
    tree,result,base_package = map(lambda p:Path(p).absolute(),(tree,result,base_package))
    require(os.geteuid() == 0,'bootstrap construction requires an administrator')
    seed = base.read(result/'selected-deployment.json')
    value = base.record(REQUEST,dict(tree=str(tree),result=str(result),tree_identity=[tree.stat().st_dev,tree.stat().st_ino],
        creator_mount_namespace=os.readlink('/proc/self/ns/mnt'),seed=seed,
        archive=dict(sha256=artifact.file_sha(base_package),size=base_package.stat().st_size),
        system_version=system_version,system_revision=system_revision,code=code_identity()))
    fresh_tree(tree,result,value)
    metadata = result/'bootstrap-request.json';base.io.write_json(metadata,value)
    print('Mojt bootstrap: install native content, construct initramfs and select initial deployment...',file=sys.stderr,flush=True)
    run('unshare','--mount','--propagation','private',sys.executable,'-I','-B',Path(__file__),
        '--finalize-tree',tree,'--result',result,'--base-package',base_package)
    actual = inspect_result(result,base_artifact=seed['description']['base']['artifact'],kernel_artifact=seed['description']['kernel']['artifact'],files=False)
    import mpm_boot_selection as selection
    choice,entries,unused = selection.current(tree,verify=True)
    require(choice == actual['selection'] and entries[choice['description']['selected']]['record'] == actual['deployment'],
            'native-v2 bootstrap result differs from the completed tree')
    return actual


def finalize_child(tree, result, base_package):
    """Disposable private-mount-namespace worker; never touches a disk device."""
    value = base.read(result/'bootstrap-request.json');d = request(value)
    require(os.readlink('/proc/self/ns/mnt') != d['creator_mount_namespace'],'bootstrap worker requires a private mount namespace')
    old,profile = fresh_tree(tree,result,value)
    require(artifact.file_sha(base_package) == d['archive']['sha256'] and base_package.stat().st_size == d['archive']['size'], 'Base archive changed')
    work = Path(tempfile.mkdtemp(prefix='bootstrap-',dir=tree.parent));jail = work/'chroot'
    # A disposable execution root, separate from every measured Base. Only the
    # explicitly accepted System's pinned Python/Nix helper executes here.
    shutil.copytree(tree/'base'/old['base']['release'],jail,symlinks=True)
    prep = jail/'run/preparation';(prep/'code').mkdir(parents=True)
    shutil.copyfile(base_package,prep/'base.tar.zst');base.io.write_json(prep/'request.json',value)
    for name in CODE:
        shutil.copyfile(Path(__file__).with_name(name),prep/'code'/name)
        require(artifact.file_sha(prep/'code'/name) == d['code'][name],'bootstrap helper changed while copying')
    (prep/'construct.py').write_text("import sys\nsys.path.insert(0,'/run/mojt-system/tools')\nsys.path.insert(0,'/run/preparation/code')\n"
        "from pathlib import Path\nimport mojt_bootstrap as b\nb.base.io.write_json(Path('/run/preparation/result.json'),"
        "b.construct(Path('/run/mojt-disk'),Path('/run/mojt-system'),b.base.read(Path('/run/preparation/request.json')),Path('/run/preparation/work')))\n")
    mounted = []
    def bind(source, destination, readonly=False):
        destination.mkdir(parents=True,exist_ok=True)
        require(destination == destination.resolve(),'linked bootstrap mount destination')
        run('mount','--bind',source,destination);mounted.append(destination)
        if readonly:run('mount','-o','remount,bind,ro',source,destination)
    try:
        for source,destination,ro in ((tree,jail/'run/mojt-disk',False),(tree/'nix',jail/'nix',False),
                (profile,jail/'run/mojt-system',True),(tree/'state/etc',jail/'etc',True),(Path('/dev'),jail/'dev',False)):
            bind(source,destination,ro)
        (jail/'proc').mkdir(exist_ok=True)
        environment = dict(PATH='/run/mojt-system/libexec/mpm/bin:/run/mojt-system/bin:/usr/bin:/bin',LC_ALL='C',HOME='/root')
        isolated(['chroot',jail,'/run/mojt-system/bin/python3','-I','-B','/run/preparation/construct.py'],jail/'proc',env=environment)
        record_result(tree,result,base.read(prep/'result.json'))
    finally:
        errors = []
        for point in reversed(mounted):
            try:run('umount',point)
            except (OSError,subprocess.CalledProcessError) as error:errors.append(str(point)+': '+str(error))
        require(not errors,'bootstrap namespace cleanup failed: '+'; '.join(errors))
    shutil.rmtree(work)


def record_result(tree, result, outcome):
    model.envelope(outcome,RESULT)
    details = outcome['description']
    for name,body in (('bootstrap.json',outcome),('selected-deployment.json',details['deployment']),
                      ('deployment.json',details['deployment']),('initramfs-binding.json',details['deployment']['description']['initramfs'])):
        base.io.write_json(result/name,body) if not (result/name).exists() else (result/name).write_bytes(artifact.canonical(body)+b'\n')
    selected = details['deployment']['description']['inputs']['description']
    shutil.copyfile(tree/'realizations/system'/selected['system']['artifact'][7:]/'profile/manifest.json',result/'system-manifest.json')
    # Sidecars must describe the selected v2 deployment, never the transient
    # assembly seed. Its provenance is retained in bootstrap-request.json.
    for name in ('kernel-plan-request.json','kernel-plan.json','system-context.json','native-build-inputs.json'):
        (result/name).unlink()


def mountpoint(path):
    # os.path.ismount cannot recognize bind mounts on the same filesystem.
    escaped = str(path).replace('\\','\\134').replace(' ','\\040').replace('\t','\\011').replace('\n','\\012')
    return any(len(row) > 4 and row[4] == escaped for row in (line.split() for line in Path('/proc/self/mountinfo').read_text().splitlines()))


def construct(root, runtime, value, work, *, adapter=None):
    """Install and stage exactly one fresh System using ordinary MPM libraries."""
    d = request(value);old = d['seed']['description']
    require(os.geteuid() == 0 and mountpoint(root),'fresh mounted bootstrap target required')
    require(d['code'] == code_identity(),'bootstrap worker implementation differs')
    require(not Path('/run/mojt/deployment.json').exists() and not Path('/run/mojt/native-v2.json').exists(), 'bootstrap cannot run on the live installation')
    for name in ('artifacts','realizations','boot/mpm/format','boot/mpm/grub.cfg'):
        require(not os.path.lexists(root/name),'bootstrap target already initialized')
    require([root.stat().st_dev,root.stat().st_ino] == d['tree_identity'],'bootstrap target identity differs')
    require(base.read(root/'boot/mojt'/old['system']['generation']/old['base']['release']/'deployment.json') == d['seed'],'bootstrap deployment differs')
    archive = work.parent/'base.tar.zst'
    require(artifact.file_sha(archive) == d['archive']['sha256'] and archive.stat().st_size == d['archive']['size'],'bootstrap archive differs')
    import mojt_system_package as packer
    import mojt_system_manifest as manifests
    import mpm_system as system
    import mpm_system_transition as transition
    import mpm_boot_constructor as constructor
    import mpm_boot_handover as handover
    import mpm_boot_selection as selection
    import mpm_deployment as deployment
    import mpm_kernel as kernel
    if adapter is None:
        from mpm_nix_boot import NixBootAdapter
        adapter = NixBootAdapter(runtime/'bin/nix-store')
    adapters = {'nix':adapter};work.mkdir(mode=0o700)
    with (runtime/'registration').open('rb') as stream:
        subprocess.run([adapter.binary,'--load-db'],executable=adapter.executable,stdin=stream,check=True)
    base.install(root,archive,old['base']['artifact'],yes=True,tar=str(runtime/'libexec/mpm/bin/tar'))
    manifest = manifests.validate(base.read(runtime/'manifest.json'))
    require(manifest['id'] == old['system']['manifest'],'bootstrap System manifest differs')
    packed = packer.package(root,old['system']['generation'],d['system_version'],d['system_revision'],work/'kit',adapter=adapter)
    kit = work/'kit';generation = base.read(kit/'generation/archive.json');component = base.read(kit/'component/archive.json')
    identifier = packed['kit']['description']['generation']
    system.install(root,kit/'generation'/generation['file'],identifier,
        dependency_files=[kit/'component'/component['file']],adapters=adapters,yes=True)
    python_output = manifest['description']['artifacts']['nix']['packages']['python']['output']
    ref = next(r for r in system.retained_providers(root,identifier) if r['provider'] == 'nix' and r['identity'].get('output') == python_output)
    bundle = work/'python-runtime'
    python = constructor.freeze_runtime(root,ref,python_output+'/bin/python3',bundle,adapters=adapters)
    baseline = 'boot/mojt/'+old['system']['generation']+'/'+old['base']['release']
    bounds = base.read(root/baseline/'base-context.json')
    plan = transition.prepare(root,identifier,baseline=baseline,adapters=adapters)
    require(plan['description']['checks']['compatible'],'initial deployment blocked: '+'; '.join(plan['description']['checks']['errors']))
    realized = system.realization(root,identifier);body,receipt = base.object_record(root,old['base']['artifact'])
    realized_base = base.realization(root,body['id'],receipt)
    kernel_body,_ = kernel.object_record(root/'kernel/installed'/old['kernel']['artifact'][7:],old['kernel']['artifact'],verify=True)
    source = model.record(model.INPUTS,dict(installation=base.store_info(root)['installation'],platform=old['platform'],layout='native-v2',
        base=dict(old['base'],rootfs_sha256=realized_base['description']['rootfs_sha256'],kernel_min=bounds['kernel_min'],
                  kernel_max=bounds['kernel_max'],bounds_evidence=artifact.digest(bounds)),
        system=dict(artifact=identifier,composition=realized['description']['composition'],manifest=realized['description']['manifest'],generation=old['system']['generation']),
        kernel=dict(deployment.kernel_identity(kernel_body),upstream=kernel_body['version']['upstream']),firmware=[],
        boot=dict(root_uuid=old['boot']['root_uuid'],console=old['boot']['console'],
                  profile=model.HARDWARE_PROFILE if old['boot']['console'] == 'local' else model.PROFILE,extra_args=['quiet']),
        constructor=constructor.constructor(python,runtime/'busybox',handover=True),state_requirements=[],management_required=selection.MANAGEMENT_SUPPORT))
    contract = handover.prepare(root,source,plan,adapters=adapters,tar=str(runtime/'libexec/mpm/bin/tar'))
    staged = selection.stage(root,source,bundle,runtime/'busybox',work/'construction',bounds=bounds,adapters=adapters,contract=contract)
    hook = root/'boot/mojt/grub.cfg';temporary = hook.with_name('.bootstrap-hook')
    with temporary.open('xb') as stream:stream.write(selection.HOOK);os.fchmod(stream.fileno(),0o444);os.fsync(stream.fileno())
    tx.publish(temporary,hook)
    selected = selection.initialize(root,staged['deployment']);_,entries,_ = selection.current(root,verify=True)
    return base.record(RESULT,dict(layout='native-v2',installation=base.store_info(root)['installation'],
        base=old['base']['artifact'],kernel=old['kernel']['artifact'],system=identifier,
        deployment=entries[staged['deployment']]['record'],selection=selected,request=value['id'],
        system_version=packed['kit']['description']['version'],boot_acceptance=False))


def inspect_result(directory, *, base_artifact, kernel_artifact, files=True):
    directory = Path(directory);value = base.read(directory/'bootstrap.json');d = model.envelope(value,RESULT)
    artifact.fields(d,('layout','installation','base','kernel','system','deployment','selection','request','system_version','boot_acceptance'))
    model.identity(d['request'])
    require(d['system_version'] == artifact.version({k:d['system_version'][k] for k in ('upstream','scheme','revision')}),'bootstrap System package version differs')
    require(d['layout'] == 'native-v2' and d['base'] == base_artifact and d['kernel'] == kernel_artifact and d['boot_acceptance'] is False,'bootstrap result scope differs')
    model.installation(d['installation']);model.deployment(d['deployment']);model.selection(d['selection'])
    selected = d['deployment'];i = selected['description']['inputs']['description']
    require(d['selection']['description']['selected'] == selected['id'] and i['installation'] == d['installation']
            and i['base']['artifact'] == d['base'] and i['kernel']['artifact'] == d['kernel'] and i['system']['artifact'] == d['system'],'bootstrap selection/result differ')
    for name,row in (('initramfs.cpio.gz',selected['description']['files'][0]),('vmlinuz',selected['description']['files'][1])):
        if files:
            path = directory/name;base.io.regular(path)
            require(path.stat().st_size == row['size'] and artifact.file_sha(path) == row['sha256'],'bootstrap boot-file hash differs')
    require(base.read(directory/'selected-deployment.json') == selected,'selected deployment sidecar differs')
    require(not (directory/'run-qemu-direct.sh').exists(),'native-v2 must not expose a direct-boot bypass')
    return d


def build(args):
    require(args.login_mode == 'password','native-v2 bootstrap requires password login')
    version = dict(upstream=args.system_version,scheme='dotted-v1',revision=args.system_revision);artifact.version(version)
    missing = [name for name in TOOLS if shutil.which(name) is None];require(not missing,'bootstrap host tools missing: '+', '.join(missing))
    if args.dry_run:
        preview = native.preview(args)
        require(preview['system_record']['step'] >= 10,'first native-v2 bootstrap requires account-enabled System step 10')
        return dict(format='mojt-bootstrap-preview-v1',layout='native-v2',base=preview['base']['id'],kernel=preview['kernel']['id'],
            system_payload=artifact.digest(preview['system_record']),system_version=artifact.version(version),
            boot_profile=model.HARDWARE_PROFILE if preview['hardware'] is not None else model.PROFILE,hardware_inputs=preview['hardware'],
            output=str(Path(args.output).absolute()),image_written=False,boot_acceptance=False)
    require(paths.load_payload(args.system_payload)['step'] >= 10,'first native-v2 bootstrap requires account-enabled System step 10')
    def finish(**values):return finalize(system_version=args.system_version,system_revision=args.system_revision,**values)
    image = native.build(args,finalize_tree=finish)
    details = inspect_result(Path(image['output']),base_artifact=args.base_artifact,kernel_artifact=args.kernel_artifact)
    return dict(format='mojt-bootstrap-image-v1',output=image['output'],layout='native-v2',
                boot_profile=details['deployment']['description']['inputs']['description']['boot']['profile'],
                deployment=details['deployment']['id'],base=details['base'],system=details['system'],kernel=details['kernel'],boot_acceptance=False)


def main(argv=None, *, prog=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ['--finalize-tree']:
        parser = argparse.ArgumentParser(description='Internal fresh-tree bootstrap worker')
        parser.add_argument('--finalize-tree',type=Path,required=True);parser.add_argument('--result',type=Path,required=True)
        parser.add_argument('--base-package',type=Path,required=True);args = parser.parse_args(argv)
        finalize_child(args.finalize_tree,args.result,args.base_package);return 0
    parser = native.parser(prog=prog or 'mbt bootstrap')
    parser.description = __doc__
    parser.add_argument('--system-version',default=paths.VERSION,help='Mojt System packaging version (not third-party package versions)')
    parser.add_argument('--system-revision',type=int,default=1)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(build(args),indent=2,sort_keys=True));return 0
    except (OSError,ValueError,KeyError,TypeError,RecursionError,EOFError,StopIteration,subprocess.CalledProcessError) as error:
        print('mojt-bootstrap: '+str(error),file=sys.stderr);return 1


if __name__ == '__main__':raise SystemExit(main())
