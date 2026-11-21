#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Legacy key-only helper retained for immutable delivery regression fixtures.

Not exported or included in current System management runtimes. Configure
OpenSSH directly with sshd_config and systemctl instead.
"""
import argparse
import base64
import ipaddress
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys

ROOT=Path('/')
RUNTIME=Path('/run/mojt-system')
UNIT='mojt-sshd.service'
FORMAT='mojt-sshd-local-v1'


def require(ok,message):
    if not ok:raise ValueError(message)


def directory(path,mode=0o755):
    require(path==path.absolute()==path.resolve(),'linked SSH configuration directory: '+str(path))
    for parent in reversed([path,*path.parents]):
        if not parent.exists():parent.mkdir(mode=mode);parent.chmod(mode)
        info=parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid==0 and (not info.st_mode&0o022 or parent!=path and info.st_mode&stat.S_ISVTX),
                'unprotected SSH directory: '+str(parent))


def plain(path):
    info=path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid==0 and info.st_nlink==1
            and not info.st_mode&0o022 and info.st_size<=1024*1024,'unsafe SSH file: '+str(path))
    return path.read_bytes()


def create(path,data,mode=0o600):
    """Missing defaults only; never replace a local file or follow a link."""
    directory(path.parent)
    if os.path.lexists(path):require(plain(path)==data,'existing SSH configuration differs; inspect '+str(path));return
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fchmod(stream.fileno(),mode);os.fsync(stream.fileno())


def public_key(path):
    require(path.is_file() and path.stat().st_size<=16384,'provide a bounded public-key file')
    data=path.read_text().strip().splitlines()
    require(len(data)==1,'provide one public key line, not a private key or options')
    parts=data[0].split()
    require(len(parts)>=2 and parts[0] in ('ssh-ed25519','ssh-rsa','ecdsa-sha2-nistp256','ecdsa-sha2-nistp384','ecdsa-sha2-nistp521'),
            'unsupported public key type; do not supply private keys or authorized_keys options')
    try:blob=base64.b64decode(parts[1],validate=True)
    except ValueError as error:raise ValueError('invalid public key encoding') from error
    require(len(blob)>=8 and int.from_bytes(blob[:4],'big')<=len(blob)-4
            and blob[4:4+int.from_bytes(blob[:4],'big')].decode('ascii')==parts[0],'public key type/encoding differs')
    return (' '.join(parts[:2])+'\n').encode()


def config(user,listen,port):
    require(re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}|root',user),'unsupported SSH account name')
    ipaddress.ip_address(listen);require(type(port) is int and 1<=port<=65535,'invalid SSH port')
    return f'''# Managed local Mojt SSH configuration
Port {port}
ListenAddress {listen}
HostKey /etc/ssh/mojt/ssh_host_ed25519_key
PidFile /run/sshd/mojt.pid
AuthorizedKeysFile /etc/ssh/mojt/authorized_keys/%u
AllowUsers {user}
PubkeyAuthentication yes
AuthenticationMethods publickey
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitEmptyPasswords no
PermitRootLogin prohibit-password
UsePAM yes
StrictModes yes
X11Forwarding no
AllowAgentForwarding no
AllowTcpForwarding no
PermitTunnel no
PermitUserEnvironment no
SetEnv PATH=/run/mojt-system/bin:/var/lib/mojt/ports/current/bin:/usr/local/bin:/usr/bin:/bin
Subsystem sftp internal-sftp
'''.encode()


def unit():
    return b'''[Unit]
Description=Mojt OpenSSH server
After=network.target mojt-setup.service

[Service]
Type=simple
ExecStartPre=/run/mojt-system/bin/sshd -t -f /etc/ssh/mojt/sshd_config
ExecStart=/run/mojt-system/bin/sshd -D -e -f /etc/ssh/mojt/sshd_config
RuntimeDirectory=sshd
RuntimeDirectoryMode=0755
Restart=on-failure
RestartSec=3
KillMode=process

[Install]
WantedBy=mojt.target
'''


def pam():
    prefix='/run/mojt-system/pam/'
    return (f'auth required {prefix}pam_unix.so\naccount required {prefix}pam_unix.so\n'
            f'session required {prefix}pam_loginuid.so\nsession required {prefix}pam_unix.so\n'
            f'session required {prefix}pam_systemd.so\n').encode()


def run(*args,**options):return subprocess.run(list(map(str,args)),check=True,**options)


def configure(args):
    require(os.geteuid()==0,'SSH configuration requires an administrator')
    key=public_key(args.authorized_key)
    account=pwd.getpwnam(args.user)
    require(account.pw_shell and Path(account.pw_shell).is_file(),'SSH account needs an installed executable shell')
    settings=dict(format=FORMAT,user=args.user,listen=args.listen,port=args.port)
    configuration=config(args.user,args.listen,args.port)
    for name in ('sshd','ssh-keygen','systemd-sysusers','systemctl'):
        path=RUNTIME/'bin'/name;require(path.is_file() and os.access(path,os.X_OK),'System has no retained '+name)
    for name in ('pam_unix','pam_loginuid','pam_systemd'):
        require((RUNTIME/'pam'/(name+'.so')).is_file(),'System has no '+name+' PAM module')
    home=ROOT/'etc/ssh/mojt';directory(home,0o755)
    state=home/'managed.json';encoded=(json.dumps(settings,sort_keys=True)+'\n').encode()
    if not os.path.lexists(state):require(not any(home.iterdir()),'refuse to adopt a pre-existing SSH directory')
    create(state,encoded)
    # Account and keys are explicit administrator configuration, never package hooks.
    create(home/'sysusers.conf',b'u sshd - "OpenSSH privilege separation" /var/empty /bin/false\n')
    run(RUNTIME/'bin/systemd-sysusers',home/'sysusers.conf')
    separator=pwd.getpwnam('sshd')
    require(separator.pw_uid!=0 and separator.pw_dir=='/var/empty' and separator.pw_shell.endswith(('nologin','false')),'existing sshd account has an incompatible purpose')
    empty=ROOT/'var/empty';directory(empty)
    require(not any(empty.iterdir()),'OpenSSH privilege-separation directory must be empty')
    directory(ROOT/'run/sshd')
    host=home/'ssh_host_ed25519_key'
    if not os.path.lexists(host):
        require(not os.path.lexists(host.with_suffix('.pub')),'incomplete foreign SSH host key')
        run(RUNTIME/'bin/ssh-keygen','-q','-t','ed25519','-N','','-f',host)
    require(plain(host) and not host.stat().st_mode&0o077,'SSH host key must be private')
    plain(host.with_suffix('.pub'))
    # Validate both incoming and retained public material with OpenSSH itself.
    incoming=home/'incoming-key.pub';create(incoming,key)
    try:
        run(RUNTIME/'bin/ssh-keygen','-l','-f',incoming)
        directory(home/'authorized_keys')
        authorized=home/'authorized_keys'/args.user
        if os.path.lexists(authorized):require(plain(authorized)==key,'existing authorized key differs; manage explicit rotation manually')
        else:create(authorized,key,0o644)
    finally:incoming.unlink(missing_ok=True)
    create(home/'sshd_config',configuration)
    create(ROOT/'etc/pam.d/sshd',pam(),0o644)
    create(ROOT/'etc/systemd/system'/UNIT,unit(),0o644)
    run(RUNTIME/'bin/sshd','-t','-f',home/'sshd_config')
    run(RUNTIME/'bin/systemctl','daemon-reload')
    run(RUNTIME/'bin/ssh-keygen','-l','-f',host.with_suffix('.pub'))
    print('SSH configured; host key and authorized key retained in /etc/ssh/mojt.')
    print('Service is not started. Run mojt-sshd enable to start now and on boot.')


def main(argv=None):
    p=argparse.ArgumentParser(prog='mojt-sshd',description=__doc__)
    sub=p.add_subparsers(dest='action',required=True)
    c=sub.add_parser('configure');c.add_argument('--authorized-key',type=Path,required=True)
    c.add_argument('--user',default='root');c.add_argument('--listen',default='0.0.0.0');c.add_argument('--port',type=int,default=22)
    for name in ('enable','disable','status'):sub.add_parser(name)
    args=p.parse_args(argv)
    try:
        if args.action=='configure':configure(args)
        elif args.action=='status':return run(RUNTIME/'bin/systemctl','status','--no-pager',UNIT).returncode
        else:
            require(os.geteuid()==0,'SSH service changes require an administrator')
            state=json.loads(plain(ROOT/'etc/ssh/mojt/managed.json'))
            require(state.get('format')==FORMAT,'missing managed SSH configuration')
            require(plain(ROOT/'etc/systemd/system'/UNIT)==unit(),'SSH unit changed; inspect before enabling/disabling')
            if args.action=='enable':
                require(plain(ROOT/'etc/ssh/mojt/sshd_config')==config(state['user'],state['listen'],state['port']),'SSH config changed; inspect it before enabling')
                run(RUNTIME/'bin/sshd','-t','-f',ROOT/'etc/ssh/mojt/sshd_config')
            run(RUNTIME/'bin/systemctl',args.action,'--now',UNIT)
        return 0
    except (OSError,ValueError,KeyError,TypeError,UnicodeError,subprocess.CalledProcessError) as error:
        print('mojt-sshd: '+str(error),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
