#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Build a separate versioned kernel/module input with a private compiler environment.

No activation, boot-menu editing, running-kernel replacement or Base changes.
"""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

# Commands used by the driver and upstream config/Kbuild scripts. Keep this
# independent of the package backend and reject incomplete private PATHs early.
REQUIRED_COMMANDS = (
    'make', 'bash', 'gcc', 'g++', 'ld', 'as', 'ar', 'nm', 'objcopy', 'objdump',
    'strip', 'depmod', 'modinfo', 'git', 'bc', 'flex', 'bison', 'perl',
    'pkg-config', 'gzip', 'mv', 'cp', 'rm', 'mkdir', 'sed', 'grep', 'tr',
    'cat', 'sort', 'uniq', 'expr', 'wc', 'cut', 'head', 'tail', 'ln', 'touch',
    'readlink', 'basename', 'dirname', 'date', 'uname', 'od', 'dd', 'printf',
    'test', 'echo',
)


def require(ok, message):
    if not ok: raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def read_plan(path):
    p=json.loads(Path(path).read_text())
    require(set(p)=={'format','source','version','localversion','configuration'} and p['format']=='mojt-kernel-plan-v1','unsupported kernel plan')
    require(set(p['source'])=={'url','tag','commit'} and p['source']['url']=='https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git','unsupported source policy')
    require(re.fullmatch(r'[0-9a-f]{40}',p['source']['commit']) and p['source']['tag']=='v'+p['version'],'invalid source identity')
    require(re.fullmatch(r'[0-9]+(?:\.[0-9]+){2}',p['version']) and re.fullmatch(r'-[a-zA-Z0-9._-]+',p['localversion']),'invalid kernel release')
    c=p['configuration'];require(set(c)=={'enable','disable','strings'},'unsupported config policy')
    for key in ('enable','disable'):
        require(isinstance(c[key],list) and all(re.fullmatch(r'[A-Z0-9_]+',x) for x in c[key]),'invalid config symbols')
    require(not set(c['enable'])&set(c['disable']),'contradictory config policy')
    require(isinstance(c['strings'],dict) and all(re.fullmatch(r'[A-Z0-9_]+',k) and isinstance(v,str) and '\n' not in v for k,v in c['strings'].items()),'invalid string config policy')
    return p


def config_values(path):
    result={}
    for line in Path(path).read_text().splitlines():
        m=re.fullmatch(r'CONFIG_([A-Z0-9_]+)=(.*)',line)
        if m:result[m[1]]=m[2]
        m=re.fullmatch(r'# CONFIG_([A-Z0-9_]+) is not set',line)
        if m:result[m[1]]='n'
    return result


def check_config(path, plan):
    values=config_values(path);c=plan['configuration']
    errors=[]
    for key in c['enable']:
        if values.get(key)!='y':errors.append('required built-in/config missing: '+key)
    for key in c['disable']:
        if values.get(key,'n')!='n':errors.append('disabled config re-enabled: '+key)
    for key,value in dict(c['strings'],LOCALVERSION=plan['localversion']).items():
        # scripts/config writes quoted strings; initial policy uses plain safe strings.
        if values.get(key,json.dumps(''))!=json.dumps(value):errors.append('config string differs: '+key)
    require(not errors,'kernel config policy mismatch:\n  '+'\n  '.join(errors))


def make_command(source, output, environment, jobs, *targets):
    b=Path(environment)/'bin'
    return [str(b/'make'),'-C',str(source),'O='+str(output),'ARCH=x86',
            'LOCALVERSION=',
            'SHELL='+str(b/'bash'),'CONFIG_SHELL='+str(b/'bash'),
            'CC='+str(b/'gcc'),'HOSTCC='+str(b/'gcc'),'HOSTCXX='+str(b/'g++'),
            'LD='+str(b/'ld'),'AR='+str(b/'ar'),'NM='+str(b/'nm'),
            'OBJCOPY='+str(b/'objcopy'),'OBJDUMP='+str(b/'objdump'),'STRIP='+str(b/'strip'),
            '-j'+str(jobs),*targets]


def build(args):
    plan=read_plan(args.plan)
    require(type(args.jobs) is int and 1<=args.jobs<=4,'initial kernel build uses 1-4 jobs')
    require(re.fullmatch(r'[0-9a-f]{64}',args.config_sha256 or ''),'provide the frozen Debian config SHA256')
    require(sha(args.config)==args.config_sha256,'Debian config hash differs')
    require(config_values(args.config).get('X86_64')=='y','first kernel requires an x86_64 base config')
    environment=args.environment.resolve(strict=True)
    require(not (environment/'.preparing').exists(),'compiler environment incomplete')
    record=json.loads((environment/'environment.json').read_text())
    require(record.get('format')=='mojt-build-env-v1' and record.get('profile')=='kernel'
            and 'compiler' in record.get('probes',{}),'use a successfully probed kernel environment')
    output=args.output.resolve()
    require(not os.path.lexists(args.output),'kernel output must not exist')
    existing_source=getattr(args,'source',None)
    if existing_source is not None:
        existing_source=existing_source.resolve(strict=True)
        require(existing_source.is_dir() and (existing_source/'.git').is_dir(),'source must be an existing Git checkout')
    for p in (args.config.resolve(),args.plan.resolve(),environment,*([existing_source] if existing_source else [])):
        require(output!=p and output not in p.parents and p not in output.parents,'output and input paths must be separate')
    missing=[x for x in REQUIRED_COMMANDS if not
             ((environment/'bin'/x).is_file() and os.access(environment/'bin'/x, os.X_OK))]
    require(not missing,'kernel tools missing or not executable: '+', '.join(missing))
    print('Plan: '+plan['source']['tag']+' -> '+plan['version']+plan['localversion'])
    print('Output: '+str(output)+'; jobs: '+str(args.jobs))
    if existing_source:print('Reuse source (commit and clean tree checked before config/build): '+str(existing_source))
    if args.dry_run:
        print('Preview only; no source fetch, compiler execution or output writes.')
        return
    if not args.yes and input('Build this kernel in a new private directory? [y/N] ').lower()!='y':return
    output.mkdir(parents=True)
    (output/'.building').write_text('Incomplete kernel build; never activate\n')
    source=existing_source or output/'source'
    if not existing_source:source.mkdir()
    objects=output/'objects';objects.mkdir();staged=output/'root';staged.mkdir()
    # Every external command starts through the static clean launcher.
    def command(parts, capture=False):
        p=subprocess.run([str(environment/'run'),*map(str,parts)],check=True,text=True,
                         stdout=subprocess.PIPE if capture else None)
        return p.stdout.strip() if capture else None
    git=environment/'bin/git'
    if not existing_source:
        command([git,'-C',source,'init'])
        command([git,'-C',source,'remote','add','origin',plan['source']['url']])
        command([git,'-C',source,'fetch','--depth=1','origin','refs/tags/'+plan['source']['tag']])
    commit=command([git,'-C',source,'rev-parse','HEAD^{commit}' if existing_source else 'FETCH_HEAD^{commit}'],True)
    require(commit==plan['source']['commit'],'fetched source commit differs from plan')
    if existing_source:
        require(command([git,'-C',source,'remote','get-url','origin'],True)==plan['source']['url'],'cached source origin differs from plan')
    else:command([git,'-C',source,'checkout','--detach',commit])
    require(not command([git,'-C',source,'status','--porcelain'],True),'source is not clean')
    copied=output/'debian.config';shutil.copyfile(args.config,copied)
    require(sha(copied)==args.config_sha256,'config changed while copying')
    shutil.copyfile(copied,objects/'.config')
    conf=[str(environment/'bin/bash'),str(source/'scripts/config'),'--file',str(objects/'.config')]
    for option in plan['configuration']['enable']:command(conf+['--enable',option])
    for option in plan['configuration']['disable']:command(conf+['--disable',option])
    for key,value in dict(plan['configuration']['strings'],LOCALVERSION=plan['localversion']).items():
        command(conf+['--set-str',key,value])
    make=lambda *targets:make_command(source,objects,environment,args.jobs,*targets)
    command(make('olddefconfig'))
    (output/'config.diff').write_text(''.join(difflib.unified_diff(copied.read_text().splitlines(True),
        (objects/'.config').read_text().splitlines(True),fromfile='debian.config',tofile='mojt.config')))
    check_config(objects/'.config',plan)
    # KBUILD variables are explicit command-line make assignments, not inherited host identity.
    identity=['KBUILD_BUILD_USER=mojt','KBUILD_BUILD_HOST=mojt-build','KBUILD_BUILD_VERSION=1',
              'KBUILD_BUILD_TIMESTAMP=Thu Jan 1 00:00:00 UTC 1970']
    # -s and no directory messages make kernelrelease unambiguous.
    release_output=command(make('-s','--no-print-directory','kernelrelease'),True)
    require(release_output,'kernelrelease returned no identity')
    release=release_output.splitlines()[-1]
    require(release==plan['version']+plan['localversion'],'unexpected compiled kernel release: '+release)
    command(make(*identity,'bzImage','modules'))
    command(make(*identity,'INSTALL_MOD_PATH='+str(staged),'INSTALL_MOD_STRIP=1',
                 'DEPMOD='+str(environment/'bin/depmod'),'modules_install'))
    command([environment/'bin/depmod','-b',staged,'-a',release])
    boot=staged/'boot';boot.mkdir()
    kernel=boot/('vmlinuz-'+release);shutil.copyfile(objects/'arch/x86/boot/bzImage',kernel)
    shutil.copyfile(objects/'.config',boot/('config-'+release));shutil.copyfile(objects/'System.map',boot/('System.map-'+release))
    modules=staged/'lib/modules'/release
    require(modules.is_dir() and (modules/'modules.dep').is_file(),'matching module output missing')
    module_files=sorted(modules.rglob('*.ko'))
    require(module_files,'no loadable modules produced from the intended Debian configuration')
    vermagic=command([environment/'bin/modinfo','-F','vermagic',module_files[0]],True)
    require(vermagic.split() and vermagic.split()[0]==release,'module vermagic differs from kernel release')
    # Build/source links point to scratch and are unnecessary for boot consumption.
    for name in ('build','source'):
        p=modules/name
        if p.is_symlink():p.unlink()
    paths={}
    for path in sorted(staged.rglob('*')):
        require(not path.is_symlink(),'unexpected link in kernel boot input: '+str(path))
        if path.is_file():paths[path.relative_to(staged).as_posix()]=dict(sha256=sha(path),mode=path.stat().st_mode&0o777)
    result=dict(format='mojt-kernel-input-v1',release=release,architecture='x86_64',source=plan['source'],
                base_config_sha256=args.config_sha256,config_sha256=sha(objects/'.config'),plan=plan,
                compiler_environment_sha256=sha(environment/'environment.json'),
                files=paths,module_count=len(module_files),sample_vermagic=vermagic,scope='Build artifact; boot acceptance not yet performed.')
    result['id']='sha256:'+hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    (output/'kernel.json').write_text(json.dumps(result,indent=2)+'\n')
    require(not command([git,'-C',source,'status','--porcelain'],True),'source changed during build')
    (output/'.building').unlink()
    print('READY: '+str(output/'kernel.json'))
    print('Kernel and modules staged together; running kernel/Base/System not changed.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('plan','config','environment','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--source',type=Path,help='reuse a clean checkout at the pinned commit; no source fetch')
    p.add_argument('--config-sha256',required=True);p.add_argument('--jobs',type=int,default=2)
    p.add_argument('--dry-run',action='store_true');p.add_argument('-y','--yes',action='store_true')
    args=p.parse_args()
    try:build(args)
    except (ValueError,OSError,KeyError,TypeError,subprocess.CalledProcessError) as error:
        p.exit(1,'mojt-kernel-build: '+str(error)+'\nIncomplete new output is retained; never activate it.\n')


if __name__=='__main__':main()
