# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Execute final-shutdown control flow with isolated mount-table/command doubles."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("shutdown_system", REPO / "tools/mojt_system.py")
system = importlib.util.module_from_spec(spec)
spec.loader.exec_module(system)


class ShutdownOrderTests(unittest.TestCase):
    def simulate(self, mounts, *, busy=(), action="poweroff"):
        with tempfile.TemporaryDirectory(prefix="mojt-exitrd-test-") as temporary:
            root = Path(temporary)
            binaries = root / "bin"
            binaries.mkdir()
            table, log, configuration = root / "mountinfo", root / "log", root / "config.json"
            table.write_text("".join(f"{i} 1 {dev} / {name} rw - ext4 /dev/fixture rw\n"
                                     for i, (name, dev) in enumerate(mounts, 2)))
            configuration.write_text(json.dumps(dict(table=str(table), log=str(log), busy=list(busy))))
            # This double never invokes host mount, umount, sync or poweroff.
            wrapper = r'''import json,os,subprocess,sys
from pathlib import Path
c=json.loads(Path(os.environ['MOJT_SHUTDOWN_TEST']).read_text())
command,args=sys.argv[1],sys.argv[2:]
with Path(c['log']).open('a') as out: out.write(json.dumps([command,*args])+'\n')
if command in ('sync','poweroff','reboot','halt'): raise SystemExit(0)
if command=='sort':
    lines=Path(args[-1]).read_text().splitlines(True)
    sys.stdout.write(''.join(sorted(lines,reverse=True)))
elif command=='printf':
    raise SystemExit(subprocess.run(['/usr/bin/printf',*args]).returncode)
elif command=='mount':
    assert args[:2]==['-o','remount,ro'], args
elif command=='umount':
    assert len(args)==1 and args[0].startswith('/oldroot'),args
    target=args[0]
    rows=Path(c['table']).read_text().splitlines(True)
    def decode(p): return bytes(p,'ascii').decode('unicode_escape')
    names=[decode(row.split()[4]) for row in rows]
    if target in c['busy'] or any(n.startswith(target+'/') for n in names): raise SystemExit(1)
    matches=[i for i,n in enumerate(names) if n==target]
    if not matches: raise SystemExit(1)
    del rows[matches[-1]]
    Path(c['table']).write_text(''.join(rows))
else: raise AssertionError('unexpected command '+command)
'''
            (binaries / "busybox").write_text("#!" + sys.executable + "\n" + wrapper)
            (binaries / "busybox").chmod(0o755)
            script = system.SHUTDOWN.replace("PATH=/bin", "PATH='" + str(binaries) + "'")
            script = script.replace("cd / ||", "cd '" + str(root) + "' ||")
            script = script.replace("/proc/self/mountinfo", str(table)).replace("/mojt-oldroot-", str(root / "mojt-oldroot-"))
            result = subprocess.run(["/bin/sh", "-c", script, "shutdown", action], capture_output=True,
                                    text=True, timeout=15, env=dict(os.environ, MOJT_SHUTDOWN_TEST=str(configuration)))
            self.assertEqual(result.returncode, 0, result.stderr)
            operations = [json.loads(line) for line in log.read_text().splitlines()]
            return result.stdout, operations, table.read_text()

    def test_children_before_parents_and_api_mounts_are_retained(self):
        output, calls, table = self.simulate([('/oldroot','8:2'),('/proc','0:1'),('/dev','0:2'),
            ('/oldroot/var','8:2'),('/oldroot/usr/lib/modules','8:2'),('/oldroot/run/mojt-system','8:2')])
        self.assertEqual([c[1] for c in calls if c[0]=='umount'],
                         ['/oldroot/var','/oldroot/usr/lib/modules','/oldroot/run/mojt-system','/oldroot'])
        self.assertIn("old root and backing filesystem fully unmounted", output)
        self.assertNotIn("ERROR", output)
        self.assertFalse(any(c[0]=='mount' for c in calls))
        self.assertIn('/proc',table)
        self.assertIn('/dev',table)
        self.assertEqual(calls[0],['sync'])
        self.assertEqual(calls[-2:],[['sync'],['poweroff','-f']])

    def test_remaining_reference_reports_error_and_readonly_fallback(self):
        output,calls,table=self.simulate([('/oldroot','8:2'),('/oldroot/var','8:2'),('/proc','0:1')],
                                        busy=('/oldroot/var',))
        self.assertIn('ERROR: old root/backing filesystem remains',output)
        self.assertNotIn('fully unmounted',output)
        self.assertEqual(sum(c==['umount','/oldroot/var'] for c in calls),3)
        self.assertTrue(any(c[:2]==['mount','-o'] for c in calls))
        self.assertTrue(all('-l' not in c and '-a' not in c for c in calls if c[0]=='umount'))
        self.assertIn('/oldroot',table)

    def test_escaped_spaces_backslashes_and_stacked_mounts(self):
        output,calls,table=self.simulate([('/oldroot','8:2'),('/oldroot/a\\040b','8:2'),
            ('/oldroot/a\\040b','8:2'),('/oldroot/back\\134slash','8:2'),('/proc','0:1')])
        self.assertEqual(sum(c==['umount','/oldroot/a b'] for c in calls),2)
        self.assertIn(['umount','/oldroot/back\\slash'],calls)
        self.assertIn('fully unmounted',output)

    def test_backing_filesystem_alias_outside_oldroot_prevents_false_success(self):
        output,calls,table=self.simulate([('/oldroot','8:2'),('/elsewhere','8:2'),('/proc','0:1')])
        self.assertIn('ERROR',output)
        self.assertIn(['mount','-o','remount,ro','/elsewhere','/elsewhere'],calls)

    def test_missing_oldroot_never_claims_success(self):
        output,calls,table=self.simulate([('/proc','0:1')],action='reboot')
        self.assertIn('ERROR',output)
        self.assertEqual(calls[-1],['reboot','-f'])
        self.assertFalse(any(c[0]=='umount' for c in calls))

    def test_runtime_policy_has_correct_escaped_names_and_no_api_overrides(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            script=system.shutdown_mount_policy().replace('/newroot',str(root))
            result=subprocess.run(['/bin/sh','-c',script],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            units=root/'run/systemd/system'
            for name in ('run-mojt\\x2dsystem.mount','run-mojt\\x2ddisk.mount','usr-lib-modules.mount','var.mount','nix.mount'):
                self.assertEqual((units/(name+'.d')/'10-mojt-exitrd.conf').read_text(),
                                 '[Unit]\nDefaultDependencies=no\n')
            for name in ('dev.mount','proc.mount','sys.mount','run-kernel\\x2dtest.mount'):
                self.assertFalse((units/(name+'.d')).exists())


if __name__ == '__main__':
    unittest.main()
