#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Read-only timing of the installed native-v2 reader and current-state gates.

This rechecks the RUNNING deployment, not the next-boot selection. It never
enters the handover, executes a provider, mounts anything or publishes state.
Running-system caches and interpreter differ from the actual early boot.
"""
import argparse
from contextlib import contextmanager, ExitStack
import functools
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time

FORMAT = 'mojt-boot-profile-v1'
COMPARISON = 'mojt-boot-profile-comparison-v1'


class Timings:
    def __init__(self):
        self.phases = [];self.calls = {};self.trees = [];self.files = []

    @contextmanager
    def phase(self, name):
        print('Mojt boot profile: '+name+'...',file=sys.stderr,flush=True)
        start = time.perf_counter();ok = False
        try:
            yield
            ok = True
        finally:self.phases.append(dict(name=name,seconds=time.perf_counter()-start,ok=ok))

    @contextmanager
    def observe(self, module, name, *, detail=None):
        """Observe unchanged calls/results/errors; restore even on refusal."""
        original = getattr(module,name);key = module.__name__+'.'+name
        @functools.wraps(original)
        def wrapped(*args, **kwargs):
            start = time.perf_counter();result = None;ok = False
            try:
                result = original(*args,**kwargs);ok = True
                return result
            finally:
                elapsed = time.perf_counter()-start
                row = self.calls.setdefault(key,dict(calls=0,seconds=0.0,failed=0))
                row['calls'] += 1;row['seconds'] += elapsed;row['failed'] += not ok
                if detail is not None:
                    entry = dict(operation=name,path=str(args[0]),seconds=elapsed,ok=ok)
                    if ok and name == 'measure':entry.update(nodes=result['nodes'],content_bytes=result['content_bytes'])
                    detail.append(entry)
        setattr(module,name,wrapped)
        try:yield
        finally:setattr(module,name,original)

    def report(self):
        return dict(format=FORMAT,scope='running-system recheck; not a cold-boot measurement',
                    phases=self.phases,calls=self.calls,trees=self.trees,files=self.files)


def installed_tools():
    """Use the actual installed manager, without changing its measured files."""
    directory = Path('/run/mojt-system/tools')
    if directory != directory.resolve() or not directory.is_dir():
        raise ValueError('installed System tools directory is unavailable')
    # These are trusted executable inputs, not package-supplied profiling code.
    for path in (directory,*directory.glob('*.py')):
        info = path.lstat()
        if info.st_uid != 0 or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode):
            raise ValueError('unprotected installed System tools: '+str(path))
    return directory


@contextmanager
def temporary_inventory(module, candidate):
    """Process-local diagnostic substitution, never edit the installed files."""
    saved = {name:getattr(module,name) for name in ('measure','snapshot')}
    try:
        for name in saved:setattr(module,name,candidate[name])
        yield
    finally:
        for name,value in saved.items():setattr(module,name,value)


def load_candidate(path, expected):
    """Explicit reviewed code for comparison, read/hash once before compiling."""
    if len(expected) != 64 or any(c not in '0123456789abcdef' for c in expected):
        raise ValueError('candidate requires its exact SHA256')
    fd = os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 64*1024:raise ValueError('unsafe/unbounded candidate')
        raw = stream.read(64*1024+1)
    if len(raw) > 64*1024 or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('candidate checksum differs; no code loaded')
    namespace = dict(__name__='mojt_boot_inventory_candidate',__file__=str(path))
    exec(compile(raw,str(path),'exec'),namespace)
    if not all(callable(namespace.get(n)) for n in ('measure','snapshot')):
        raise ValueError('candidate lacks inventory entry points')
    return namespace


def measure_boot(*, candidate=None):
    if os.geteuid() != 0:raise ValueError('run as root in the existing native-v2 VM')
    directory = installed_tools();sys.path.insert(0,str(directory))
    timings = Timings()
    with timings.phase('load installed reader'):
        import mojt_artifact as artifact
        import mpm_boot_inventory as inventory
        import mpm_boot_early as early
        import mpm_boot_handover as handover
        import mpm_boot_v2_store as store
        import mpm_boot_selection as selection
        from mpm_boot_status import read_running
        from mpm_cli import Runtime
    runtime = Runtime();root = runtime.disk
    with timings.phase('read running deployment and retained receipt'):
        running = read_running(runtime)
        if running is None or running['format'] != 'mojt-boot-deployment-v2':
            raise ValueError('a running exact native-v2 deployment is required')
        source = running['description']['inputs']
        receipt = selection.ready(root,running['id'],verify=False)['receipt']['description']
        cmdline = Path('/proc/cmdline').read_text();release = os.uname().release
    with ExitStack() as stack:
        if candidate is not None:stack.enter_context(temporary_inventory(inventory,candidate))
        for module,name,detail in ((inventory,'measure',timings.trees),(inventory,'snapshot',timings.trees),
                                   (artifact,'file_sha',timings.files),(artifact,'canonical',None),
                                   (store,'inspect',None),(handover,'validate',None)):
            stack.enter_context(timings.observe(module,name,detail=detail))
        with timings.phase('exact early verification'):
            verified = early.verify(root,source,receipt['proof'],cmdline,release)
        with timings.phase('current-state and boot-Base gates'):
            handover.check(root,source,receipt['proof'],receipt['handover'])
    result = timings.report()
    result.update(deployment=running['id'],kernel=release,tools=str(directory),
                  verified=verified['verified'],handover_executed=False)
    return result


def compare(candidate, checksum):
    # Bracket the candidate with the installed implementation: the last scan
    # gives a warm baseline rather than crediting cache warming to the change.
    runs = []
    for name,code in (('installed before',None),('candidate',candidate),('installed after',None)):
        print('\nMojt boot profile: '+name,file=sys.stderr,flush=True)
        runs.append(dict(name=name,report=measure_boot(candidate=code)))
    identities = {(r['report']['deployment'],r['report']['kernel']) for r in runs}
    covered = [sorted((t['operation'],t['path'],t.get('nodes'),t.get('content_bytes')) for t in r['report']['trees']) for r in runs]
    if len(identities) != 1 or any(c != covered[0] for c in covered):
        raise ValueError('comparison changed deployment or covered trees')
    return dict(format=COMPARISON,scope='running-system installed/candidate/installed; not cold boot',
                candidate_sha256=checksum,runs=runs,handover_executed=False)


def comparison_summary(report):
    print('Running deployment: '+report['runs'][0]['report']['deployment'])
    print('Candidate SHA256: '+report['candidate_sha256'])
    print('Warm rechecks; installed baseline brackets the process-local candidate.')
    print('                         early verification    current-state gates')
    for run in report['runs']:
        phases = {r['name']:r['seconds'] for r in run['report']['phases']}
        print('%-22s %12.3f s %19.3f s'%(run['name'],phases['exact early verification'],phases['current-state and boot-Base gates']))
    candidate = report['runs'][1]['report'];baseline = report['runs'][2]['report']
    by_path = {(r['operation'],r['path']):r['seconds'] for r in baseline['trees']}
    print('\nSlowest candidate trees:       installed-after -> candidate')
    for row in sorted(candidate['trees'],key=lambda row:row['seconds'],reverse=True)[:8]:
        print('%8.3f -> %8.3f s  %s'%(by_path[(row['operation'],row['path'])],row['seconds'],row['path']))
    print('\nPASS: both implementations passed the same exact proofs and current-state gates')
    print('Installed implementation restored; no file replacement, handover or publication performed.')


def summary(report):
    print('Running deployment: '+report['deployment'])
    print('Kernel: '+report['kernel'])
    print('Timing: running-system recheck (warm caches possible), not cold boot')
    for row in report['phases']:print('%8.3f s  %s'%(row['seconds'],row['name']))
    print('\nNested calls (overlap with the phases above; do not add these totals):')
    for name,row in sorted(report['calls'].items(),key=lambda item:item[1]['seconds'],reverse=True):
        print('%8.3f s  %6d calls  %s'%(row['seconds'],row['calls'],name))
    trees = report['trees'];nodes = sum(t.get('nodes',0) for t in trees)
    content = sum(t.get('content_bytes',0) for t in trees)
    print('\n%d tree scans; measure() covered %d nodes / %.1f MiB'%(len(trees),nodes,content/1024**2))
    print('Slowest trees (snapshot() bytes/nodes are not counted above):')
    for row in sorted(trees,key=lambda row:row['seconds'],reverse=True)[:8]:
        print('%8.3f s  %s  %s'%(row['seconds'],row['operation'],row['path']))
    print('\nRetained boot-file hashes:')
    for row in report['files']:print('%8.3f s  %s'%(row['seconds'],row['path']))
    print('\nPASS: installed verification and current-state gates; no handover or publication performed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json',action='store_true',help='full versioned report on stdout')
    parser.add_argument('--compare-inventory',type=Path,help='explicit reviewed candidate code; process-local comparison only')
    parser.add_argument('--expected-sha256',help='required exact checksum of candidate code')
    args = parser.parse_args()
    try:
        if bool(args.compare_inventory) != bool(args.expected_sha256):raise ValueError('supply candidate and checksum together')
        if args.compare_inventory is not None:
            if os.geteuid() != 0:raise ValueError('run as root in the existing native-v2 VM')
            # Select the installed dependencies before importing candidate code.
            sys.path.insert(0,str(installed_tools()))
            candidate = load_candidate(args.compare_inventory,args.expected_sha256)
            result = compare(candidate,args.expected_sha256)
        else:result = measure_boot()
        if args.json:print(json.dumps(result,sort_keys=True,indent=2))
        elif args.compare_inventory is not None:comparison_summary(result)
        else:summary(result)
    except (OSError,ValueError) as error:
        print('Mojt boot profile: '+str(error),file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':raise SystemExit(main())
