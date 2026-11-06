#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Owner native-VM acceptance: source install, stage, select, then one real reboot."""
import argparse
import copy
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import uuid

ROOT = Path('/run/mojt-disk')
RUNTIME = Path('/run/mojt-system')
LAB = Path('/var/lib/mojt/kernel-source-boot')
FORMAT = 'mojt-kernel-source-boot-acceptance-v1'


def require(ok, message):
    if not ok:raise ValueError(message)


def call(*args):
    result = subprocess.run([str(RUNTIME/'bin/mpm'), *args], text=True, capture_output=True)
    require(result.returncode == 0, result.stderr + result.stdout)
    return json.loads(result.stdout)


def boot_id():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def write_state(value):
    temporary = LAB/('.state-' + uuid.uuid4().hex)
    try:
        kernel.write_json(temporary, value)
        transaction.publish(temporary, LAB/'state.json')
    finally:
        temporary.unlink(missing_ok=True)


def runtime_record():
    value = deployment.read_json(Path('/run/mojt/deployment.json'))
    d = deployment.validate_deployment(value)
    require(d['kernel']['release'] == os.uname().release, 'runtime release differs')
    require(Path('/run/mojt/native-kernel-artifact').read_text().strip() == d['kernel']['artifact'],
            'native runtime artifact differs')
    return value, d


def installed_object(identifier):
    return ROOT/'kernel/installed'/kernel.identifier(identifier)


def prepare():
    require(not os.path.lexists(LAB), 'acceptance lab exists; inspect its checkpoint instead of overwriting')
    running, d = runtime_record()
    status = call('kernel', 'status', '--json')
    require(status['selected'] == running['id'] and status['running_is_selected'],
            'native selected and running baseline must agree')
    obj = installed_object(d['kernel']['artifact'])
    old, _ = kernel.object_record(obj, d['kernel']['artifact'], verify=True)
    spec = {k:copy.deepcopy(old[k]) for k in
            ('kind','name','platform','dependencies','requirements','provides','provenance','metadata')}
    spec['format'] = artifact.SPEC_FORMAT
    spec['version'] = {k:copy.deepcopy(old['version'][k]) for k in ('upstream','scheme','revision')}
    spec['version']['revision'] = (spec['version']['revision'] or 0) + 1
    spec['metadata']['acceptance_only'] = 'registered-source-exact-deployment'
    LAB.mkdir(mode=0o700)
    print('Preparing a distinct package revision from the retained Kernel build...', flush=True)
    attachments = {p.name:p for p in (obj/'provenance').iterdir()} if (obj/'provenance').exists() else {}
    package = artifact.pack(obj/'payload', spec, LAB/'package', attachments)
    require(package['artifact']['id'] != old['id'], 'a distinct artifact is required')
    require(not any(r['artifact'] == package['artifact']['id'] for r in status['installed']),
            'candidate is already installed; this would only test a no-op')
    fixture = runpy.run_path(str(Path(__file__).with_name('run-kernel-source-acceptance.py')))
    source_lab = LAB/'source'; source_lab.mkdir(mode=0o700)
    name = 'kernel-source-boot-acceptance'
    body, checksum = fixture['prepare_repository'](LAB/'package'/package['archive']['file'], source_lab,
                                                  name, artifact=artifact, cache=cache)
    call('source', 'add', name, '--from-file', str(source_lab/'source.json'),
         '--policy-file', str(source_lab/'policy.json'), '-y')
    call('source', 'update', name, '-y')
    request = ('kernel', 'install', '--source', name, '--expected-id', body['id'], '--archive-sha256', checksum)
    require(call(*request, '--dry-run')['dry_run'], 'missing installation preview')
    print('Installing through the selected System MPM...', flush=True)
    require(call(*request, '-y')['changed'], 'expected one new source installation')
    require(not call(*request, '-y')['changed'], 'installation repeat changed state')
    _, receipt = kernel.object_record(installed_object(body['id']), body['id'], verify=True)
    require(receipt['trust']['kind'] == 'registered-native-source', 'source origin was not retained')
    after = call('kernel', 'status', '--json')
    require(after['selected'] == running['id'] and after['running_is_selected'], 'installation changed boot choice')
    checkpoint = dict(format=FORMAT, phase='prepared', script_sha256=artifact.file_sha(Path(__file__)),
        old_deployment=running['id'], old_kernel=old['id'], old_release=d['kernel']['release'],
        new_kernel=body['id'], new_release=body['metadata']['kernel_release'],
        base=d['base'], system=d['system'], machine_id=Path('/etc/machine-id').read_text().strip(),
        initial_boot=boot_id(), origin=receipt['acquisition'],
        installed_record_sha256=artifact.file_sha(installed_object(body['id'])/'installed.json'))
    # Staging/boot must use retained installed content, not a live source archive.
    (source_lab/'repository/kernel.tar.zst').unlink()
    write_state(checkpoint)
    print('PASS: exact source-installed candidate and origin retained; initial boot choice unchanged')
    print('Same compiled Kernel release; exact artifact/deployment IDs distinguish this test.')
    print('Candidate:', body['id'])


def verify(checkpoint, old=False):
    expected = checkpoint['old_deployment'] if old else checkpoint['new_deployment']
    identifier = checkpoint['old_kernel'] if old else checkpoint['new_kernel']
    release = checkpoint['old_release'] if old else checkpoint['new_release']
    record, d = runtime_record()
    require(record['id'] == expected and d['kernel']['artifact'] == identifier and os.uname().release == release,
            'wrong running exact deployment or Kernel')
    require(boot_id() != checkpoint['initial_boot'], 'a new boot has not been observed')
    require(d['base'] == checkpoint['base'] and d['system'] == checkpoint['system'], 'Base/System changed')
    require(Path('/etc/machine-id').read_text().strip() == checkpoint['machine_id'], 'machine identity changed')
    status = call('kernel', 'status', '--json')
    require(status['selected'] == expected and status['running_is_selected'], 'selected/running state differs')
    _, installed = kernel.object_record(installed_object(checkpoint['new_kernel']), checkpoint['new_kernel'], verify=True)
    require(installed['acquisition'] == checkpoint['origin'] and
            artifact.file_sha(installed_object(checkpoint['new_kernel'])/'installed.json') == checkpoint['installed_record_sha256'],
            'candidate origin/install record changed across deployment')
    mount = subprocess.run(['findmnt','--json','-T','/lib/modules','-o','SOURCE,OPTIONS'],
                           check=True, text=True, capture_output=True)
    rows = json.loads(mount.stdout)['filesystems']
    require(len(rows) == 1 and '/kernel/installed/'+kernel.identifier(identifier)+'/payload/lib/modules' in rows[0]['source']
            and 'ro' in rows[0]['options'].split(','), 'wrong or writable native module tree')
    failed = subprocess.run(['systemctl','--failed','--no-legend','--no-pager'],
                            check=True, text=True, capture_output=True)
    require(not failed.stdout.strip(), 'failed units: '+failed.stdout)
    require(checkpoint['old_deployment'] in status['staged'] and checkpoint['new_deployment'] in status['staged'],
            'previous/candidate deployment was not retained')
    print('PASS: '+('previous exact deployment restored' if old else 'source-installed exact Kernel deployment is running'))
    print('PASS: source origin/install record, read-only modules, Base/System and machine identity retained')
    print('PASS: selected/running IDs agree and no units failed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare','stage','select','check','rollback','check-old'))
    args = parser.parse_args()
    require(os.geteuid() == 0 and os.path.ismount(ROOT), 'run as root in a disposable native Mojt VM copy')
    require((RUNTIME/'tools/mpm_kernel_source.py').is_file() and Path('/run/mojt/deployment.json').is_file(),
            'updated delivered MPM and a native boot baseline are required; installation-only images are insufficient')
    sys.path.insert(0, str(RUNTIME/'tools'))
    global artifact, kernel, deployment, transaction, cache
    import mojt_artifact as artifact
    import mpm_kernel as kernel
    import mpm_deployment as deployment
    import mpm_transaction as transaction
    import mpm_native_cache as cache
    from mpm_cli import Runtime
    runtime = Runtime()
    os.environ['PATH'] = ':'.join((str(runtime.helpers), str(runtime.system_bin), '/usr/bin', '/bin'))
    if args.action == 'prepare':
        prepare(); return
    with transaction.file_lock(LAB/'.acceptance-lock'):
        checkpoint = deployment.read_json(LAB/'state.json')
        require(checkpoint['format'] == FORMAT and checkpoint['script_sha256'] == artifact.file_sha(Path(__file__)),
                'unsupported or changed acceptance checkpoint/script')
        if args.action == 'stage':
            require(checkpoint['phase'] == 'prepared', 'stage requires prepared candidate')
            before = (ROOT/'boot/mojt/grub.cfg').read_bytes()
            call('kernel','stage','--artifact',checkpoint['new_kernel'],'--dry-run')
            print('Staging exact Kernel with retained modules and a new bound initramfs...', flush=True)
            result = call('kernel','stage','--artifact',checkpoint['new_kernel'],'-y')
            repeated = call('kernel','stage','--artifact',checkpoint['new_kernel'],'-y')
            require(not repeated['changed'] and repeated['deployment'] == result['deployment'], 'stage repeat differs')
            require((ROOT/'boot/mojt/grub.cfg').read_bytes() == before, 'stage changed next boot')
            checkpoint.update(phase='staged', new_deployment=result['deployment'])
            print('PASS: source-installed candidate staged; next boot unchanged; repeat is a no-op')
        elif args.action == 'select':
            require(checkpoint['phase'] == 'staged', 'select requires a staged checkpoint')
            command = ('kernel','select','--deployment',checkpoint['new_deployment'],
                       '--expected-selected',checkpoint['old_deployment'])
            call(*command,'--dry-run'); call(*command,'-y')
            status = call('kernel','status','--json')
            require(status['selected'] == checkpoint['new_deployment'] and
                    status['running']['artifact'] == checkpoint['old_kernel'] and not status['running_is_selected']
                    and boot_id() == checkpoint['initial_boot'], 'selection confused next boot with running state')
            checkpoint['phase'] = 'selected'
            print('PASS: next boot selected; running deployment unchanged')
            print('READY: power off and restart this SAME VM copy, then run check')
            print('New default deployment:', checkpoint['new_deployment'])
        elif args.action == 'check':
            require(checkpoint['phase'] in ('selected','checked'), 'check requires selected candidate')
            verify(checkpoint); checkpoint['phase'] = 'checked'
        elif args.action == 'rollback':
            require(checkpoint['phase'] == 'checked', 'rollback requires successful candidate boot')
            call('kernel','rollback','--expected-selected',checkpoint['new_deployment'],'-y')
            checkpoint['phase'] = 'rollback-selected'
            print('READY: previous deployment selected; restart this SAME VM, then run check-old')
        else:
            require(checkpoint['phase'] in ('rollback-selected','complete'), 'check-old requires rollback selection')
            verify(checkpoint, old=True); checkpoint['phase'] = 'complete'
        write_state(checkpoint)


if __name__ == '__main__':
    try:main()
    except (ValueError,OSError,KeyError,subprocess.CalledProcessError) as error:
        print('Kernel source boot acceptance:',error,file=sys.stderr)
        print('Existing data retained; inspect the VM checkpoint before retrying.',file=sys.stderr)
        sys.exit(1)
