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
import json
import os
from pathlib import Path
import stat
import sys
import time

FORMAT = 'mojt-boot-profile-v1'


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


def measure_boot():
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
    args = parser.parse_args()
    try:
        result = measure_boot()
        if args.json:print(json.dumps(result,sort_keys=True,indent=2))
        else:summary(result)
    except (OSError,ValueError) as error:
        print('Mojt boot profile: '+str(error),file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':raise SystemExit(main())
