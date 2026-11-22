# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Manager-owned v2 verification initramfs; no target code execution or selection."""
import hashlib
import os
import stat
import tempfile
from pathlib import Path

import mojt_artifact as artifact
import mojt_system as paths
import mojt_hardware as hardware
import mpm_base as base
import mpm_boot_early as early
import mpm_boot_inventory as inventory
import mpm_boot_v2 as model
import mpm_boot_v2_store as store
import mpm_kernel_boot as archive
import mpm_native_io as io
import mpm_system as system
import mpm_transaction as tx
import mpm_ui as ui
from mpm_request_plan import reference
from mpm_boot_v2 import record

RESERVED = {'bin','dev','etc','proc','sys','sysroot','newroot','modules','mojt','init','modules.list','shutdown'}
LAUNCH = "import sys\nsys.path.insert(0, '/mojt/code')\nfrom mpm_boot_early import main\nmain()\n"
require = artifact.require


class CompletedBuild(dict):
    """In-process constructor result; decoded JSON is never a stage admission."""
    def __init__(self, values, handover):
        super().__init__(values)
        self.handover = handover


def provider_paths(root, ref, adapters):
    reference(ref)
    require(adapters is not None and ref['provider'] in adapters, 'trusted boot provider adapter required')
    adapter = adapters[ref['provider']]
    require(hasattr(adapter,'boot_paths'), 'provider has no bounded boot-tree export contract')
    names = adapter.boot_paths(ref,root);early.roots(names)
    return names


def check_runtime_links(tree, runtime):
    d = early.runtime(runtime)
    for name,rows in d['trees'].items():
        for relative,row in rows.items():
            if row['type'] != 'symlink':continue
            guest = '/'+name+('' if relative == '.' else '/'+relative)
            resolved = paths.virtual_file(tree,guest);suffix = resolved.relative_to(tree).as_posix()
            require(resolved.exists() and any(suffix == p or suffix.startswith(p+'/') for p in d['trees']), 'bootstrap link escapes its measured closure: '+guest+' -> '+str(resolved))
    executable = paths.virtual_file(tree,d['interpreter'])
    require(executable.is_file() and executable.stat().st_mode & 0o001, 'bootstrap interpreter is not executable')


def describe_runtime(root, ref, interpreter, *, adapters):
    """Measure an explicitly retained runtime without copying it or creating state."""
    require(os.geteuid() == 0, 'bootstrap runtime preparation requires an administrator')
    root = Path(root).absolute();require(root == root.resolve(), 'linked bootstrap runtime source')
    reference(ref);require(adapters is not None and ref['provider'] in adapters, 'trusted runtime adapter required')
    adapter = adapters[ref['provider']]
    (adapter.verify if io.preparation_verify() else getattr(adapter,'inspect',adapter.verify))(ref,root)
    trees = {}
    for name in provider_paths(root,ref,adapters):
        require(name.split('/')[0] not in RESERVED, 'bootstrap provider overlaps initramfs controls')
        trees[name] = inventory.snapshot(inventory.path(root,name),maximum=model.MAX_BOOT)
    value = record(early.RUNTIME,dict(reference=reference(ref),interpreter=interpreter,trees=trees));early.runtime(value)
    check_runtime_links(root,value)
    return value


def freeze_runtime(root, ref, interpreter, output, *, adapters):
    """Explicit trusted runtime, independent of Base and the candidate interpreter."""
    root = Path(root).absolute()
    output = Path(output).absolute();require(output == output.resolve() and not os.path.lexists(output), 'bootstrap output must be new')
    require(output != root and root not in output.parents and output not in root.parents, 'bootstrap output overlaps source')
    value = describe_runtime(root,ref,interpreter,adapters=adapters);trees = value['description']['trees']
    output.mkdir(mode=0o700);(output/'tree').mkdir(mode=0o700)
    try:
        for name,rows in trees.items():
            destination = output/'tree'/name;destination.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
            require(destination == destination.resolve(), 'linked bootstrap destination')
            inventory.clone_runtime(inventory.path(root,name),destination,rows)
        check_runtime_links(output/'tree',value)
        io.write_json(output/'runtime.json',value)
    except BaseException:
        io.clean_stage(output);raise
    return value


def constructor(runtime, busybox, *, handover=False):
    """Implementation/runtime identity is known before inputs or archive exist."""
    early.runtime(runtime)
    code = {name:artifact.file_sha(Path(__file__).with_name(name)) for name in paths.MPM_FILES}
    return dict(provider='mojt',identity=dict(format='mojt-system-initramfs-constructor-v1' if handover else 'mojt-verification-initramfs-constructor-v1',
        code=code,runtime=runtime['id'],busybox_sha256=artifact.file_sha(busybox)))


def capture(root, source, adapters, *, entries=None):
    d = model.inputs(source)
    known={}
    def remember(key,value):
        require(key not in known or known[key]==value,'conflicting retained boot tree measurements')
        known[key]=value
    if not io.preparation_verify():
        # Retained proofs are expected measurements, never a claim of a fresh
        # audit. Reuse only the same immutable artifact/provider identity.
        from mpm_boot_selection import current
        if entries is None:unused,entries,unused_raw=current(root)
        for entry in entries.values():
            old=entry['record']['description']['inputs'];previous=model.inputs(old)
            proof=early.proof(entry['receipt']['description']['proof'],old)
            for area in ('base','system','kernel'):
                row=proof['modules' if area=='kernel' else area]
                remember((area,previous[area]['artifact'],row['path']),row['measurement'])
            for provider in proof['providers']:
                identity=artifact.digest(provider['reference'])
                for path,measured in provider['trees'].items():remember(('provider',identity,path),measured)
    def measurement(kind,identity,relative):
        path=inventory.path(root,relative)
        require(path.is_dir(),'boot tree is unavailable: '+relative)
        expected=known.get((kind,identity,relative))
        return dict(expected) if expected is not None else inventory.measure(path)
    def tree(area,relative):return dict(path=relative,measurement=measurement(area,d[area]['artifact'],relative))
    providers = [];seen = set()
    for ref in system.retained_providers(root,d['system']['artifact']):
        names = provider_paths(root,ref,adapters)
        fresh = [p for p in names if p not in seen];seen.update(names)
        if fresh:providers.append(dict(reference=ref,trees={p:measurement('provider',artifact.digest(ref),p) for p in fresh}))
    value = record(early.PROOF,dict(inputs=source['id'],constructor=d['constructor'],
        base=tree('base','realizations/base/'+d['base']['artifact'][7:]+'/tree/rootfs'),
        system=tree('system','realizations/system/'+d['system']['artifact'][7:]+'/profile'),
        modules=tree('kernel','kernel/installed/'+d['kernel']['artifact'][7:]+'/payload/lib/modules'),providers=providers))
    early.proof(value,source);return value


def script(source, interpreter, *, handover=False):
    d = model.inputs(source)
    # Interpreter path is data in a shell literal, never evaluated or discovered
    # through PATH. All runtime bytes came from the explicit trusted adapter.
    import shlex
    python = shlex.quote(interpreter)
    result = '''#!/bin/sh
# Mojt Linux; Copyright (C) 2026 Jonas Persson; SPDX-License-Identifier: GPL-2.0-only
PATH=/bin
export PATH
umask 022
exec </dev/console >/dev/console 2>&1
panic() {
    echo "Mojt native-v2: $*" >&2
    exec /bin/sh </dev/console >/dev/console 2>&1
}
mount -t devtmpfs devtmpfs /dev || panic "cannot mount /dev"
mount -t proc proc /proc || panic "cannot mount /proc"
mount -t sysfs sysfs /sys || panic "cannot mount /sys"
while IFS= read -r module; do
    [ -n "$module" ] || continue
    insmod "$module" || echo "Mojt native-v2: optional module unavailable: $module"
done </modules.list
tries=0
while :; do
    device=$(findfs UUID='''+d['boot']['root_uuid']+''') && break
    tries=$((tries+1))
    [ "$tries" -le 20 ] || panic "exact root UUID unavailable"
    sleep 1
done
mount -t ext4 -o ro "$device" /sysroot || panic "cannot mount exact root read-only"
/bin/busybox env -i PATH=/bin LC_ALL=C '''+python+''' -I -S -B /mojt/launch.py --root /sysroot --inputs /mojt/inputs.json --proof /mojt/trees.json \
    >/mojt/verified.json || panic "exact deployment verification failed"
cat /mojt/verified.json
panic "verification passed; System initialization and handover are not integrated"
'''
    if handover:
        start = result.index('/bin/busybox env -i')
        result = result[:start]+'exec /bin/busybox env -i PATH=/bin LC_ALL=C '+python+''' -I -S -B /mojt/launch.py --root /sysroot --inputs /mojt/inputs.json --proof /mojt/trees.json --handover /mojt/handover.json
'''
    return result


def decode_modules(modules, directory):
    """Bound output while decoding; the shared writer then sees ordinary .ko files."""
    import gzip
    import lzma
    import subprocess
    directory.mkdir();result = [];remaining = model.MAX_BOOT
    for number,source in enumerate(modules):
        process = None
        if source.suffix == '.ko':stream = source.open('rb')
        elif source.suffix == '.gz':stream = gzip.open(source,'rb')
        elif source.suffix == '.xz':stream = lzma.open(source,'rb')
        else:
            require(source.suffix == '.zst', 'unsupported early module encoding')
            process = subprocess.Popen(['zstd','-q','-d','-c','--',str(source)],stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
            stream = process.stdout
        target = directory/(str(number)+'.ko')
        try:
            with stream, target.open('xb') as output:
                while chunk := stream.read(min(128*1024,remaining+1)):
                    remaining -= len(chunk);require(remaining >= 0, 'decoded early modules exceed limit');output.write(chunk)
            if process is not None:require(process.wait() == 0, 'early module decoder failed')
        finally:
            if process is not None and process.poll() is None:process.kill();process.wait()
        result.append(target)
    return result


PAYLOAD_KEY = 'mojt-initramfs-payload-inputs-v1'
PAYLOAD_RECORD = 'mojt-initramfs-payload-v1'
PAYLOAD_INIT = '#!/bin/sh\necho "Mojt: deployment overlay missing" >&2\nexec /bin/busybox sh </dev/console >/dev/console 2>&1\n'


def payload_key(source, runtime, *, handover):
    """Heavy payload inputs deliberately exclude selected Base/System identities."""
    d = model.inputs(source);early.runtime(runtime)
    producer = d['constructor']['identity']
    names = ('mpm_boot_constructor.py','mpm_boot_inventory.py','mpm_native_io.py',
             'mpm_kernel_boot.py','mojt-vm-build.py','mojt_hardware.py','mojt_native_image.py')
    return record(PAYLOAD_KEY,dict(platform=d['platform'],kernel=d['kernel'],runtime=runtime['id'],
        busybox_sha256=producer['busybox_sha256'],profile=d['boot']['profile'],handover=handover,
        shutdown_sha256=hashlib.sha256(paths.SHUTDOWN.encode()).hexdigest() if handover else None,
        applets=sorted({'findfs','cat','env'} | (paths.SHUTDOWN_APPLETS-{'cp','ln'} if handover else set())),
        producer={name:producer['code'][name] for name in names}))


def cached_payload(root, key, create):
    """Private immutable content cache; a payload alone never admits a deployment.

    Existing store read locks protect its inputs; this separate lock serializes
    only cache publication. Corrupt entries fail instead of being overwritten.
    """
    model.envelope(key,PAYLOAD_KEY)
    parent = root/'boot/mpm/initramfs-payloads'
    tx.protected_directory(parent,write=True,label='initramfs payload cache')
    parent.mkdir(mode=0o755,exist_ok=True);io.sync_directory(parent.parent)
    with tx.file_lock(parent/'.lock'):
        destination = parent/key['id'][7:]
        if os.path.lexists(destination):
            info = io.directory(destination)
            require(info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o555
                    and {p.name for p in destination.iterdir()} == {'payload.json','initramfs.cpio.gz'},'unsafe/incomplete cached boot payload')
            for name in ('payload.json','initramfs.cpio.gz'):
                item = io.regular(destination/name)
                require(item.st_uid == 0 and stat.S_IMODE(item.st_mode) == 0o444,'unprotected cached boot payload')
            saved = early.read(destination/'payload.json');d = model.envelope(saved,PAYLOAD_RECORD)
            artifact.fields(d,('inputs','archive'));model.archive(d['archive'])
            require(d['inputs'] == key,'cached boot payload inputs differ')
            path = destination/'initramfs.cpio.gz'
            require(path.stat().st_size == d['archive']['size'],'cached boot payload size differs')
            raw = path.read_bytes()
            require(hashlib.sha256(raw).hexdigest() == d['archive']['sha256'],'cached boot payload bytes damaged')
            io.sync_directory(destination);io.sync_directory(parent)
            return raw,True
        require(sum(1 for p in parent.iterdir() if not p.name.startswith('.')) < model.MAX_ENTRIES,'boot payload cache limit')
        raw = create();require(0 < len(raw) <= model.MAX_BOOT,'boot payload exceeds size limit')
        stage = Path(tempfile.mkdtemp(prefix='.payload-',dir=parent))
        try:
            with (stage/'initramfs.cpio.gz').open('xb') as stream:
                stream.write(raw);os.fchmod(stream.fileno(),0o444);os.fsync(stream.fileno())
            value = record(PAYLOAD_RECORD,dict(inputs=key,archive=dict(sha256=hashlib.sha256(raw).hexdigest(),size=len(raw))))
            io.write_json(stage/'payload.json',value);stage.chmod(0o555);io.sync_directory(stage)
            tx.publish(stage,destination)
        finally:io.clean_stage(stage)
        return raw,False


def controls(root, source, runtime, trees, handover):
    """Small per-deployment member, following the unchanged early-reader contract."""
    d = source['description'];folder = root/'mojt';folder.mkdir();folder.chmod(0o755)
    code = folder/'code';code.mkdir();code.chmod(0o755)
    for name,checksum in d['constructor']['identity']['code'].items():
        actual,size = io.frozen_copy(Path(__file__).with_name(name),code/name,maximum=model.MAX_BOOT)
        require(actual == checksum,'constructor code changed: '+name)
    io.write_json(folder/'inputs.json',source);io.write_json(folder/'trees.json',trees)
    io.write_json(folder/'runtime.json',runtime)
    if handover is not None:io.write_json(folder/'handover.json',handover)
    (folder/'launch.py').write_text(LAUNCH);(folder/'launch.py').chmod(0o444)


def build(root, source, runtime_directory, busybox, work, *, bounds, adapters, handover=None,
          reuse_payload=False, runtime_value=None):
    """Standalone constructor: validate retained inputs before private assembly."""
    require(os.geteuid() == 0,'initramfs construction requires an administrator')
    root = store.target(root)
    from mpm_base_transition import read_locks
    with read_locks(root):
        store.audit_inputs(root,source,bounds,adapters=adapters)
        trees = capture(root,source,adapters)
        if handover is not None:
            import mpm_boot_handover as transfer
            transfer.recheck_locked(root,handover,source,adapters)
            transfer.check(root,source,trees,handover,verify_content=io.preparation_verify())
        return _build_locked(root,source,runtime_directory,busybox,work,bounds=bounds,
            adapters=adapters,handover=handover,reuse_payload=reuse_payload,runtime_value=runtime_value,trees=trees)


def _build_locked(root, source, runtime_directory, busybox, work, *, bounds, adapters, handover=None,
          reuse_payload=False, runtime_value=None, entries=None, trees=None):
    """Assemble checked inputs under caller-held locks; never select next boot."""
    require(os.geteuid() == 0, 'initramfs construction requires an administrator')
    root = store.target(root);work = Path(work).absolute()
    require(work == work.resolve() and not os.path.lexists(work), 'constructor work must be new')
    require(root != work and root not in work.parents and work not in root.parents, 'constructor work overlaps target')
    if runtime_directory is not None:
        runtime_directory = Path(runtime_directory).absolute()
        require(runtime_directory == runtime_directory.resolve(), 'linked bootstrap bundle')
        runtime = early.read(runtime_directory/'runtime.json')
        require(runtime_value is None or runtime_value == runtime,'frozen runtime descriptor differs')
    else:
        require(reuse_payload and runtime_value is not None,'missing explicit constructor runtime')
        runtime = runtime_value
    runtime_d = early.runtime(runtime)
    d = model.inputs(source);require(d['constructor'] == constructor(runtime,busybox,handover=handover is not None), 'constructor/runtime differs from boot inputs')
    trees = capture(root,source,adapters,entries=entries) if trees is None else trees
    work.mkdir(mode=0o700)
    frozen_busybox = work/'busybox';checksum,unused = io.frozen_copy(busybox,frozen_busybox,maximum=model.MAX_BOOT)
    require(checksum == d['constructor']['identity']['busybox_sha256'], 'BusyBox changed during copying');frozen_busybox.chmod(0o755)
    vm = archive.vm_module()
    require(vm.static_x86_64_elf(frozen_busybox), 'trusted static x86_64 BusyBox required')
    extra = tuple(sorted({'findfs','cat','env'} | (paths.SHUTDOWN_APPLETS-{'cp','ln'} if handover is not None else set())))
    vm.validate_busybox_applets(frozen_busybox,'password',extra=extra)
    payload = root/'kernel/installed'/d['kernel']['artifact'][7:]/'payload'
    module_tree = payload/'lib/modules'/d['kernel']['release']
    def make_payload():
        nonlocal runtime_directory
        if runtime_directory is None:
            runtime_directory = work/'runtime'
            frozen = freeze_runtime(root,runtime_d['reference'],runtime_d['interpreter'],runtime_directory,adapters=adapters)
            require(frozen == runtime,'manager runtime changed before construction')
        if d['boot']['profile'] in model.HARDWARE_PROFILES:
            machine = hardware.profile_for_boot(d['boot']['profile'])
            vm.module_paths(d['kernel']['release'],module_tree,names=hardware.runtime_modules(machine))
            modules = vm.module_paths(d['kernel']['release'],module_tree,names=hardware.early_modules(machine))
        else:modules = vm.module_paths(d['kernel']['release'],module_tree,network=True)
        for module in modules:
            require(module == module.resolve() and payload/'lib/modules' in module.parents,'early module outside exact Kernel tree')
        modules = decode_modules(modules,work/'decoded-modules')
        def assemble(initroot):
            check_runtime_links(runtime_directory/'tree',runtime)
            for name,rows in runtime_d['trees'].items():
                original = inventory.path(runtime_directory/'tree',name)
                require(inventory.snapshot(original,maximum=model.MAX_BOOT) == rows,'bootstrap bundle changed')
                destination = initroot/name;destination.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
                require(destination == destination.resolve(),'linked initramfs runtime destination')
                inventory.clone_runtime(original,destination,rows)
            if not reuse_payload:controls(initroot,source,runtime,trees,handover)
            return archive.write_initramfs(initroot)
        mask = os.umask(0o022)
        try:
            return vm.make_initramfs(work/'initroot',frozen_busybox,modules,
                    PAYLOAD_INIT if reuse_payload else script(source,runtime_d['interpreter'],handover=handover is not None),
                    paths.SHUTDOWN if handover is not None else None,extra_applets=extra,archive_writer=assemble)
        finally:os.umask(mask)
    reused = False;key = None
    if reuse_payload:
        key = payload_key(source,runtime,handover=handover is not None)
        with ui.phase('Build or reuse early-boot runtime and drivers'):
            raw,reused = cached_payload(root,key,make_payload)
        overlay = work/'overlay';overlay.mkdir(mode=0o755);overlay.chmod(0o755)
        controls(overlay,source,runtime,trees,handover)
        (overlay/'init').write_text(script(source,runtime_d['interpreter'],handover=handover is not None),encoding='ascii');(overlay/'init').chmod(0o755)
        # Linux unpacks concatenated gzip/newc archives in order. Both
        # members are independently inspected against their generated trees.
        addition = archive.write_initramfs(overlay)
        # Each independently inspected member is below 256 MiB, so its
        # gzip ISIZE is exact (not wrapped). Preserve the previous total
        # expansion limit as well as the compressed boot-file limit.
        expanded = int.from_bytes(raw[-4:],'little') + int.from_bytes(addition[-4:],'little')
        require(expanded <= archive.native.MAX_INITRAMFS,'combined initramfs expansion exceeds size limit')
        raw += addition
        require(len(raw) <= model.MAX_BOOT,'combined initramfs exceeds size limit')
    else:raw = make_payload()
    # The frozen original module inventory is rechecked after decompression.
    if io.preparation_verify():
        require(inventory.measure(payload/'lib/modules') == trees['description']['modules']['measurement'], 'Kernel modules changed during construction')
    binding = record(model.BINDING,dict(inputs=source['id'],constructor=d['constructor'],archive=dict(sha256=hashlib.sha256(raw).hexdigest(),size=len(raw))))
    model.binding(binding,source)
    return CompletedBuild(dict(archive=raw,binding=binding,proof=trees,boot_ready=False,selection_changed=False,handover_enabled=handover is not None,
                payload_key=key['id'] if key else None,payload_reused=reused,
                scope='System handover enabled; authoritative selection/status and owner boot acceptance remain.' if handover is not None else
                      'Verification initramfs only; initialization, mount handover and boot publication remain required.'),handover)
