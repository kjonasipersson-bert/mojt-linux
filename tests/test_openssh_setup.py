# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Real OpenSSH syntax and one-time setup, with service/account calls isolated."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

REPO=Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.geteuid()==0 and shutil.which('sshd') and shutil.which('ssh-keygen'),
                     'requires root and OpenSSH syntax tools')
class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);runtime=self.root/'run/mojt-system/bin';runtime.mkdir(parents=True)
        for name in ('sshd','ssh-keygen'):(runtime/name).symlink_to(shutil.which(name))
        self.log=self.root/'commands'
        for name in ('systemd-sysusers','systemctl'):
            path=runtime/name
            path.write_text("#!/bin/sh\nprintf '%s\\n' "+shlex.quote(name)+" \"$@\" >>"+shlex.quote(str(self.log))+"\n")
            path.chmod(0o755)
        source=(REPO/'tests/setup-openssh.sh').read_text()
        self.script=self.root/'setup.sh'
        self.script.write_text(source.replace('/etc/',str(self.root)+'/etc/')
            .replace('/run/',str(self.root)+'/run/').replace('/var/empty',str(self.root)+'/var/empty'))

    def test_standard_password_config_validates_and_enables_only_sshd_service(self):
        result=subprocess.run(['sh',str(self.script)],text=True,capture_output=True)
        if 'Missing privilege separation directory' in result.stderr:self.skipTest('host needs /run/sshd')
        self.assertEqual(result.returncode,0,result.stderr)
        config=self.root/'etc/ssh/sshd_config'
        effective=subprocess.run([shutil.which('sshd'),'-T','-f',str(config)],text=True,capture_output=True,check=True).stdout
        for line in ('permitrootlogin yes','passwordauthentication yes','authenticationmethods password','pubkeyauthentication no','permitemptypasswords no','usepam yes'):
            self.assertIn(line,effective)
        self.assertIn('enable\n--now\nsshd.service',self.log.read_text())
        self.assertTrue((self.root/'etc/pam.d/sshd').is_file())
        unit=(self.root/'etc/systemd/system/sshd.service').read_text()
        self.assertIn('WantedBy=mojt.target',unit)
        self.assertFalse((self.root/'etc/systemd/system/mojt-sshd.service').exists())
        self.assertEqual((self.root/'etc/ssh/ssh_host_ed25519_key').stat().st_mode&0o777,0o600)
        before={str(p):p.read_bytes() for p in (self.root/'etc').rglob('*') if p.is_file()}
        again=subprocess.run(['sh',str(self.script)],text=True,capture_output=True)
        self.assertNotEqual(again.returncode,0)
        self.assertIn('Existing SSH configuration',again.stderr)
        self.assertEqual(before,{str(p):p.read_bytes() for p in (self.root/'etc').rglob('*') if p.is_file()})

    def test_existing_policy_is_preserved_without_account_or_service_changes(self):
        config=self.root/'etc/ssh/sshd_config';config.parent.mkdir(parents=True);config.write_text('existing policy')
        result=subprocess.run(['sh',str(self.script)],text=True,capture_output=True)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(config.read_text(),'existing policy')
        self.assertFalse(self.log.exists())


if __name__=='__main__':unittest.main()
