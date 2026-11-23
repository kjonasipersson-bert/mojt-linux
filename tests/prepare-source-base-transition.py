#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Copy the working source Base VM and package a small local test successor."""
import argparse
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys

REPO=Path(__file__).resolve().parents[1]
source=runpy.run_path(str(Path(__file__).with_name('prepare-source-base-boot.py')))
shared=source['shared'];require=shared['require'];read=source['read']
sys.path.insert(0,str(REPO/'tools'))
import mojt_artifact as artifact
import mojt_boot
import mpm_base as base
import mpm_boot_v2 as model

VERSION='0.2.0-test1'
MARKER='usr/lib/mojt-source-base-transition'
VOLUME='MOJT_BASE_SWAP'


def inputs(args):
    image=args.vm.resolve(strict=True);build=args.base_build.resolve(strict=True)
    require(not (image.parent/'INCOMPLETE').exists() and not (build/'INCOMPLETE').exists(),'incomplete VM/Base build')
    require((image/'disk.img').is_file() and not (image/'disk.img').is_symlink(),'expected a regular VM disk.img')
    d=base.envelope(read(image/'bootstrap.json'),'mojt-bootstrap-result-v1')
    original=d['deployment'];i=model.deployment(original)['inputs']['description']
    require(d['layout']=='native-v2' and i['base']['release']=='0.2.0','test needs the working source Base 0.2.0 VM')
    result=source['read_build_result'](build/'result.json');release=Path(result['release'])
    require(result['format']=='mojt-base-source-build-v1' and release==release.resolve(strict=True)
            and release.parent==build/'releases','release must belong to the completed source Base build')
    spec,_=artifact.base_input(release,1)
    require(spec['provenance']['rootfs_sha256']==i['base']['rootfs_sha256'],'Base build differs from this VM')
    tree=build/'rootfs'
    require(tree.is_dir() and not tree.is_symlink(),'retained source build rootfs required; no recompilation')
    output=shared['fresh_output'](args.output,(REPO,image,build))
    return image,tree,release,original,output


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vm',type=Path,required=True,help='completed source Base VM image directory')
    parser.add_argument('--base-build',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--check-inputs',action='store_true')
    args=parser.parse_args(argv)
    require(os.geteuid()!=0,'run as the ordinary Debian user, without sudo')
    image,tree,release,original,output=inputs(args)
    os.environ['PATH']=shared['HOST_PATH']
    for name in ('qemu-img','mkfs.ext4','bash','tar','zstd'):
        require(shutil.which(name) is not None,'missing host command: '+name)
    print('Original VM (read only): '+str(image/'disk.img'))
    print('Copy: '+str(output/'image/disk.img'))
    print('Plan: Base 0.2.0 -> '+VERSION+' -> 0.2.0; same System/Kernel; no compilation')
    if args.check_inputs:
        print('PASS: input metadata checked; no copy, packaging, sudo or writes');return
    os.umask(0o022);output.mkdir(mode=0o700)
    (output/'INCOMPLETE').write_text('VM copy/input preparation incomplete.\n')
    copied=output/'image';copied.mkdir()
    disk=image/'disk.img';before=disk.stat()
    print('Copy the stopped VM through QEMU image locking...',flush=True)
    subprocess.run(['qemu-img','convert','-p','-f','raw','-O','raw',str(disk),str(copied/'disk.img')],check=True)
    after=disk.stat()
    require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)==
            (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns),'original VM disk changed during copy')
    print('Package a marked test successor of the retained source build...',flush=True)
    candidate=output/'candidate-tree';shutil.copytree(tree,candidate,symlinks=True)
    marker=candidate/MARKER
    require(not os.path.lexists(marker),'test marker already exists in the input tree')
    marker.write_text(VERSION+'\n');marker.chmod(0o644)
    config=output/'base.toml'
    config.write_text('format=1\n[base]\nname="mojt"\nversion="'+VERSION+'"\narchitecture="x86_64"\n'
                      '[abi]\nlibc="glibc"\nlibc_version="2.44"\n[build]\nbackend="source-transition-test"\n')
    subprocess.run([sys.executable,'-I','-B',str(REPO/'tools/mojt-base-pack'),str(candidate),str(config),
        str(output/'releases'),'--packages',str(release/'packages.txt'),'--normalize-owner'],check=True)
    data=output/'inputs';data.mkdir()
    packed=shared['run']([sys.executable,'-I','-B',REPO/'tools/mojt-artifact-pack.py','base',
        '--release',output/'releases'/('base-'+VERSION+'-x86_64'),'--revision','1','--output',data/'package'],
        result=output/'package.json')
    shutil.copyfile(REPO/'tests/run-source-base-transition.py',data/'bt.py')
    plan=dict(format='mojt-source-base-transition-inputs-v1',original=original,
        candidate=packed['artifact']['id'],release=VERSION,marker='/'+MARKER,
        archive='package/'+packed['archive']['file'],archive_sha256=packed['archive']['sha256'])
    (data/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    size=sum(p.stat().st_size for p in data.rglob('*') if p.is_file())
    input_disk=output/'inputs.img'
    with input_disk.open('xb') as stream:stream.truncate(((size//1024**2)+32)*1024**2)
    subprocess.run(['mkfs.ext4','-F','-q','-L',VOLUME,'-d',str(data),str(input_disk)],check=True);input_disk.chmod(0o400)
    script=shared['launcher'](mojt_boot.run_script(network=True),copied,input_disk)
    (output/'run-qemu.sh').write_text(script);(output/'run-qemu.sh').chmod(0o755)
    subprocess.run(['bash','-n',str(output/'run-qemu.sh')],check=True)
    (output/'INCOMPLETE').unlink()
    print('READY: '+str(output/'run-qemu.sh'))
    print('Original disk untouched. Boot this copy; ordinary installed MPM performs the test.')


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,KeyError,TypeError,subprocess.CalledProcessError) as error:
        raise SystemExit('Source Base transition preparation: '+str(error))
