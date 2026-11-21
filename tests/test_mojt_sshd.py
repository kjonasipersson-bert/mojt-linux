# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Local SSH configuration, host-key persistence and no implicit service start."""
import base64
import hashlib
import os
import shutil
import subprocess
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import mojt_sshd as ssh


def public():
    kind=b'ssh-ed25519';blob=len(kind).to_bytes(4,'big')+kind+(32).to_bytes(4,'big')+b'x'*32
    return 'ssh-ed25519 '+base64.b64encode(blob).decode()+' test\n'


class PolicyTests(unittest.TestCase):
    def test_public_key_and_network_options_are_not_shell_fragments(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'key';p.write_text(public());self.assertTrue(ssh.public_key(p).endswith(b'\n'))
            for data in ('-----BEGIN OPENSSH PRIVATE KEY-----\n','command="id" '+public(),public()+public(),'ssh-ed25519 !!!\n'):
                p.write_text(data)
                with self.assertRaises((ValueError,UnicodeError)):ssh.public_key(p)
        for user,ip,port in [('root;id','127.0.0.1',22),('root','anywhere',22),('root','127.0.0.1',0)]:
            with self.assertRaises(ValueError):ssh.config(user,ip,port)

    def test_config_is_key_only_explicit_account_and_remote_mpm_path(self):
        config=ssh.config('root','0.0.0.0',22).decode()
        for line in ('AllowUsers root','PasswordAuthentication no','KbdInteractiveAuthentication no','AuthenticationMethods publickey','UsePAM yes','StrictModes yes','Subsystem sftp internal-sftp','PermitRootLogin prohibit-password'):
            self.assertIn(line,config)
        self.assertIn('PATH=/run/mojt-system/bin:/var/lib/mojt/ports/current/bin',config)
        self.assertIn('WantedBy=mojt.target',ssh.unit().decode())

    @unittest.skipUnless(shutil.which('sshd') and shutil.which('ssh-keygen'),'requires retained OpenSSH syntax tools')
    def test_configuration_is_accepted_by_real_openssh_without_starting_a_listener(self):
        with tempfile.TemporaryDirectory() as t:
            folder=Path(t);host=folder/'ssh_host_ed25519_key'
            subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(host)],check=True)
            path=folder/'sshd_config';path.write_text(ssh.config('root','127.0.0.1',22222).decode().replace('/etc/ssh/mojt',str(folder)))
            result=subprocess.run([shutil.which('sshd'),'-T','-f',str(path)],text=True,capture_output=True)
            if 'Missing privilege separation directory' in result.stderr:self.skipTest('host has no OpenSSH privilege-separation runtime directory')
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('passwordauthentication no',result.stdout);self.assertIn('authenticationmethods publickey',result.stdout)
            self.assertIn('allowusers root',result.stdout)


@unittest.skipUnless(os.geteuid()==0,'configuration needs numeric-root ownership')
class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.runtime=self.root/'runtime';(self.runtime/'bin').mkdir(parents=True);(self.runtime/'pam').mkdir()
        for name in ('sshd','ssh-keygen','systemd-sysusers','systemctl'):
            p=self.runtime/'bin'/name;p.write_text('fixture');p.chmod(0o755)
        for name in ('pam_unix','pam_loginuid','pam_systemd'):(self.runtime/'pam'/(name+'.so')).write_text('fixture')
        self.key=self.root/'client.pub';self.key.write_text(public());self.calls=[]
        self.enterContext(mock.patch.object(ssh,'ROOT',self.root));self.enterContext(mock.patch.object(ssh,'RUNTIME',self.runtime))
        self.enterContext(mock.patch.object(ssh.pwd,'getpwnam',side_effect=lambda name:SimpleNamespace(pw_shell='/bin/sh',pw_dir='/root',pw_uid=0) if name=='root' else SimpleNamespace(pw_shell='/bin/false',pw_dir='/var/empty',pw_uid=200)))
        def run(*args,**kwargs):
            self.calls.append(tuple(map(str,args)))
            if '-t' in args and 'ed25519' in args:
                host=Path(args[args.index('-f')+1]);host.write_bytes(b'private host-key fixture');host.chmod(0o600);host.with_suffix('.pub').write_text(public())
            return SimpleNamespace(returncode=0)
        self.enterContext(mock.patch.object(ssh,'run',side_effect=run))
        self.args=SimpleNamespace(user='root',listen='0.0.0.0',port=22,authorized_key=self.key)

    def test_repeat_keeps_host_identity_and_never_starts_service(self):
        ssh.configure(self.args);host=self.root/'etc/ssh/mojt/ssh_host_ed25519_key';before=host.read_bytes()
        ssh.configure(self.args);self.assertEqual(host.read_bytes(),before)
        self.assertEqual(sum('-t' in c and 'ed25519' in c for c in self.calls),1)
        self.assertFalse(any('enable' in c or 'start' in c for c in self.calls))
        self.assertTrue(any('-t' in c and c[0].endswith('/sshd') for c in self.calls))
        self.assertEqual((self.root/'etc/ssh/mojt/authorized_keys/root').stat().st_mode&0o777,0o644)
        self.assertEqual(ssh.main(['enable']),0);self.assertIn('enable',self.calls[-1])
        self.assertEqual(ssh.main(['disable']),0);self.assertIn('disable',self.calls[-1])

    def test_existing_configuration_and_links_are_preserved(self):
        ssh.configure(self.args);path=self.root/'etc/ssh/mojt/sshd_config';path.write_bytes(b'local config')
        with self.assertRaisesRegex(ValueError,'existing SSH configuration differs'):ssh.configure(self.args)
        self.assertEqual(path.read_bytes(),b'local config')
        path.unlink();outside=self.root/'outside';outside.write_bytes(b'untouched');path.symlink_to(outside)
        with self.assertRaisesRegex(ValueError,'unsafe SSH file'):ssh.configure(self.args)
        self.assertEqual(outside.read_bytes(),b'untouched')


if __name__=='__main__':unittest.main()
