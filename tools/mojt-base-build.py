#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Build one private, source-built x86-64 Base release; never install or activate it."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import time

REPO = Path(__file__).resolve().parents[1]
LOCK = REPO/'bootstrap/base-sources.json'
ORDER = ('glibc', 'attr', 'acl', 'libcap', 'gmp', 'pcre2', 'dash', 'coreutils',
         'grep', 'sed', 'findutils', 'tar', 'gzip')
TOOLS = ('gcc', 'make', 'as', 'ld', 'ar', 'ranlib', 'strip', 'gawk', 'bison', 'm4', 'perl',
         'rsync', 'patch', 'pkg-config', 'readelf', 'curl', 'tar', 'zstd', 'xz', 'bzip2')
FLAGS = {
    'attr': [], 'acl': [],
    'gmp': ['--enable-fat', '--disable-cxx'],
    'pcre2': ['--enable-jit', '--enable-pcre2-16', '--enable-pcre2-32', '--disable-pcre2grep-libz',
              '--disable-pcre2grep-libbz2', '--disable-pcre2test-libreadline'],
    'dash': ['--without-libedit'],
    'coreutils': ['--enable-acl', '--enable-libcap', '--without-selinux', '--without-openssl'],
    'grep': ['--enable-perl-regexp'], 'sed': [],
    'findutils': ['--localstatedir=/var/cache'], 'tar': ['--with-posix-acls', '--with-xattrs'], 'gzip': [],
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def sources(path):
    value = json.loads(Path(path).read_text())
    require(value['format'] == 1 and value['architecture'] == 'x86_64', 'unsupported Base source lock')
    rows = value['sources']
    require(len(rows) == len(ORDER) + 1 and {r['name'] for r in rows} == {*ORDER, 'linux-headers'}, 'incomplete source set')
    for row in rows:
        require(re.fullmatch(r'[a-z0-9.-]+', row['version']) and row['url'].startswith('https://')
                and re.fullmatch(r'[0-9a-f]{64}', row['sha256']), 'invalid pinned source: ' + row['name'])
    return value, {row['name']:row for row in rows}


def fetch(row, cache, offline=False):
    target = cache/(row['sha256'] + '-' + row['url'].rsplit('/', 1)[1])
    if target.exists():
        require(target.is_file() and not target.is_symlink() and sha(target) == row['sha256'], 'cached source checksum differs: ' + str(target))
        return target
    require(not offline, 'offline source missing: ' + row['name'])
    partial = target.with_name(target.name + '.part')
    require(not os.path.lexists(partial), 'partial download already exists: ' + str(partial))
    try:
        subprocess.run(['curl', '--fail', '--location', '--retry', '2', '--proto', '=https',
                        '--proto-redir', '=https', '--output', str(partial), row['url']], check=True)
        require(sha(partial) == row['sha256'], 'download checksum differs: ' + row['name'])
        partial.rename(target)
    finally:
        partial.unlink(missing_ok=True)
    return target


def unpack(archive, destination):
    destination.mkdir()
    # Python 3.11's data filter rejects escaping links, traversal and special files.
    # Do not invoke an unaudited tar extraction into a compiler workspace.
    with tarfile.open(archive) as source:
        source.extractall(destination, filter='data')
    roots = list(destination.iterdir())
    require(len(roots) == 1 and roots[0].is_dir() and not roots[0].is_symlink(), 'source must have one top-level directory')
    return roots[0]


def skeleton(root):
    for name in ('usr/bin', 'usr/sbin', 'usr/lib', 'usr/include', 'usr/etc', 'usr/share', 'usr/local',
                 'etc', 'var', 'home', 'root', 'srv', 'opt', 'mnt', 'media', 'run', 'tmp', 'dev', 'proc', 'sys', 'boot', 'nix'):
        (root/name).mkdir(parents=True, exist_ok=True)
    (root/'tmp').chmod(0o1777); (root/'root').chmod(0o700)
    for name, target in (('bin', 'usr/bin'), ('sbin', 'usr/sbin'), ('lib', 'usr/lib'),
                         ('lib64', 'usr/lib'), ('usr/lib64', 'lib')):
        (root/name).symlink_to(target)


def defaults(root):
    files = {
        'passwd': 'root:x:0:0:root:/root:/bin/sh\n', 'group': 'root:x:0:\n',
        'shadow': 'root:!:0:0:99999:7:::\n',
        'nsswitch.conf': 'passwd: files\ngroup: files\nshadow: files\nhosts: files dns\nnetworks: files\n',
        'hosts': '127.0.0.1 localhost\n::1 localhost\n',
        'shells': '/bin/sh\n/bin/dash\n',
        'profile': 'export PATH=/usr/local/bin:/usr/bin:/bin\nexport LANG=${LANG:-C.UTF-8}\n'
                   'for file in /etc/profile.d/*.sh; do\n    [ ! -r "$file" ] || . "$file"\ndone\nunset file\n',
    }
    for name, data in files.items():
        path = root/'usr/etc'/name; path.write_text(data); path.chmod(0o600 if name == 'shadow' else 0o644)


def licenses(root, trees):
    for name, tree in trees.items():
        if name == 'linux-headers':continue
        destination = root/'usr/share/licenses'/name; destination.mkdir(parents=True)
        for folder in (tree, tree/'doc'):
            if not folder.is_dir():continue
            for path in folder.iterdir():
                if not path.name.lower().startswith(('copying', 'license', 'licence')):continue
                target = destination/path.relative_to(tree); target.parent.mkdir(parents=True, exist_ok=True)
                if path.is_dir():shutil.copytree(path, target)
                elif path.is_file():shutil.copyfile(path, target)
        require(any(destination.iterdir()), 'upstream license text missing: ' + name)
    if (root/'usr/lib/libgcc_s.so.1').exists():
        destination = root/'usr/share/licenses/bootstrap-libgcc'; destination.mkdir()
        shutil.copyfile(trees['coreutils']/'COPYING', destination/'COPYING.GPLv3')
        shutil.copyfile(REPO/'bootstrap/licenses/gcc-runtime-exception.txt', destination/'COPYING.RUNTIME')


def target_environment(environment, root, cc):
    result = dict(environment)
    # The target compiler uses the new libc's headers/crt objects. libgcc is
    # linked statically so the Base does not import the host compiler runtime.
    result.update(CC=f'{shlex.quote(cc)} --sysroot={root} -B{root}/usr/lib/',
        CFLAGS='-O2 -g0 -march=x86-64 -mtune=generic',
        CPPFLAGS=f'-I{root}/usr/include',
        LDFLAGS=f'-L{root}/usr/lib -Wl,-rpath-link,{root}/usr/lib -static-libgcc -Wl,--dynamic-linker=/lib64/ld-linux-x86-64.so.2',
        PKG_CONFIG_SYSROOT_DIR=str(root), PKG_CONFIG_LIBDIR=str(root/'usr/lib/pkgconfig'),
        CC_FOR_BUILD=cc, BUILD_CC=cc)
    return result


def compiler_runtime(root, cc):
    """glibc dlopens the GCC unwinder for cancellation/backtraces."""
    name = subprocess.check_output([cc, '-print-file-name=libgcc_s.so.1'], text=True).strip()
    path = Path(name).resolve(strict=True)
    require(path.is_absolute() and path.is_file() and '/nix/store/' not in str(path), 'plain native compiler runtime required')
    shutil.copyfile(path, root/'usr/lib/libgcc_s.so.1')
    return dict(path=str(path), input_sha256=sha(root/'usr/lib/libgcc_s.so.1'))


def prune(root):
    # Development inputs are kept in the workspace until every consumer builds.
    for name in ('usr/include', 'usr/lib/pkgconfig', 'usr/share/aclocal', 'usr/share/info',
                 'usr/share/i18n', 'usr/share/locale'):
        shutil.rmtree(root/name, ignore_errors=True)
    for path in (root/'usr/lib').rglob('*'):
        if path.is_file() and path.suffix in ('.a', '.la', '.o'):
            path.unlink()
    # glibc installs linker scripts for -lc/-lm; these are build-only, too.
    for name in ('libc.so', 'libm.so'):
        path = root/'usr/lib'/name
        if path.is_file() and not path.is_symlink():
            path.unlink()
    for name in ('usr/bin/pcre2-config', 'usr/bin/pcre2grep', 'usr/bin/pcre2test', 'usr/sbin/nscd',
                 'usr/bin/mtrace', 'usr/bin/xtrace', 'usr/bin/sotruss', 'usr/bin/tzselect'):
        (root/name).unlink(missing_ok=True)
    # glibc's ldd uses Bash only for gettext's $"..." quoting. The English-only
    # Base uses the same upstream logic with POSIX quoting and the Base shell.
    ldd = root/'usr/bin/ldd'
    if ldd.exists():
        data = ldd.read_text()
        require(data.startswith('#!/bin/bash\n'), 'review changed upstream ldd interpreter')
        ldd.write_text(data.replace('#!/bin/bash\n', '#!/bin/sh\n', 1).replace('$"', '"'))
    for name in ('etc', 'var'):
        for child in (root/name).iterdir():
            if child.is_dir() and not child.is_symlink():shutil.rmtree(child)
            else:child.unlink()


def audit(root, work):
    """Producer boundary: reject accidental host/Nix linkage before packaging."""
    count = 0
    for path in root.rglob('*'):
        if path.is_symlink() or not path.is_file():continue
        with path.open('rb') as stream:magic = stream.read(4096)
        if magic.startswith(b'#!'):
            line = magic.splitlines()[0].decode()
            require(shlex.split(line[2:])[0] in ('/bin/sh', '/usr/bin/sh'), 'non-Base script interpreter: ' + str(path))
            subprocess.run([str(root/'usr/lib/ld-linux-x86-64.so.2'), '--library-path', str(root/'usr/lib'),
                            str(root/'usr/bin/dash'), '-n', str(path)], check=True)
            continue
        if not magic.startswith(b'\x7fELF'):continue
        count += 1
        output = subprocess.check_output(['readelf', '--wide', '--program-headers', '--dynamic', str(path)], text=True)
        require('/nix/store/' not in output and str(work) not in output, 'non-Base ELF linkage: ' + str(path))
        searches = re.findall(r'\((?:RPATH|RUNPATH)\).*?\[([^\]]+)\]', output)
        for search in searches:
            require(all(part in ('/usr/lib', '/usr/lib64', '/lib', '/lib64', '$ORIGIN') for part in search.split(':')),
                    'non-Base library search path: ' + str(path))
        match = re.search(r'Requesting program interpreter: ([^\]]+)', output)
        require(not match or match[1] in ('/lib64/ld-linux-x86-64.so.2', '/usr/lib/ld-linux-x86-64.so.2'), 'unexpected ELF loader: ' + str(path))
        for needed in re.findall(r'\(NEEDED\).*?\[([^\]]+)\]', output):
            require('/' not in needed, 'non-local library name: ' + needed)
            candidates = [root/'usr/lib'/needed]
            if any('$ORIGIN' in search.split(':') for search in searches):candidates.append(path.parent/needed)
            require(any(p.exists() and p.resolve().is_relative_to(root) for p in candidates),
                    'missing Base library ' + needed + ' for ' + str(path))
        subprocess.run(['strip', '--strip-debug', str(path)], check=True)
    require(count > 0, 'no Base ELF programs built')
    for name in ('sh', 'dash', 'ls', 'cp', 'mkdir', 'getent', 'grep', 'sed', 'find', 'xargs', 'tar', 'gzip'):
        require((root/'usr/bin'/name).is_file(), 'missing Base command: ' + name)
    return count


def build_projects(output, root, trees, jobs, environment, cc, run):
    kernel = trees['linux-headers']
    run('Export Linux UAPI headers', ['make', '-j'+str(jobs), 'ARCH=x86', 'INSTALL_HDR_PATH='+str(root/'usr'), 'headers_install'], kernel)
    glibc = output/'build-glibc'; glibc.mkdir(exist_ok=True)
    run('Configure glibc', [trees['glibc']/'configure', '--prefix=/usr', '--libdir=/usr/lib', '--sysconfdir=/etc',
        '--with-headers='+str(root/'usr/include'), '--disable-werror', '--disable-nscd',
        '--enable-stack-protector=strong', '--enable-bind-now', 'libc_cv_slibdir=/usr/lib'], glibc)
    run('Build glibc', ['make', '-j'+str(jobs)], glibc)
    run('Stage glibc', ['make', 'install_root='+str(root), 'install'], glibc)
    (root/'usr/lib/locale').mkdir(exist_ok=True)
    locale_env = dict(environment, I18NPATH=str(trees['glibc']/'localedata'))
    run('Generate C.UTF-8 locale', [root/'usr/lib/ld-linux-x86-64.so.2', '--library-path', root/'usr/lib',
        root/'usr/bin/localedef', '--no-archive', '--prefix='+str(root), '-i', 'C', '-f', 'UTF-8', 'C.UTF-8'], glibc, locale_env)
    runtime = compiler_runtime(root, cc)
    target = target_environment(environment, root, cc)
    common = ['--prefix=/usr', '--libdir=/usr/lib', '--sysconfdir=/etc',
              '--build=x86_64-pc-linux-gnu', '--host=x86_64-mojt-linux-gnu']
    for name in ORDER[1:]:
        tree = trees[name]
        if name == 'libcap':
            flags = ['prefix=/usr', 'lib=lib', 'PAM_CAP=no', 'GOLANG=no', 'RAISE_SETFCAP=no',
                     'CC='+target['CC'], 'BUILD_CC='+cc, 'CFLAGS='+target['CFLAGS']+' -fPIC',
                     'LDFLAGS='+target['LDFLAGS']]
            run('Build libcap', ['make', '-C', 'libcap', '-j'+str(jobs), *flags], tree, target)
            run('Stage libcap', ['make', '-C', 'libcap', *flags, 'DESTDIR='+str(root), 'install'], tree, target)
            continue
        if name == 'tar':
            run('Apply tar ACL compatibility fix', ['patch', '-p1', '-i', REPO/'bootstrap/tar-acl-2.4.patch'], tree)
        objects = output/('build-' + name); objects.mkdir(exist_ok=True)
        options = (['--disable-static'] if name in ('attr','acl','gmp','pcre2','dash') else [])
        if name in ('attr','acl','coreutils','grep','sed','findutils','tar'):
            options += ['--disable-nls', '--disable-rpath']
        # GMP 6.3's configure probes require pre-C23 function declaration rules.
        package_env = dict(target, CFLAGS=target['CFLAGS']+' -std=c99') if name == 'gmp' else target
        run('Configure ' + name, [tree/'configure', *common, *options, *FLAGS[name]], objects, package_env)
        run('Build ' + name, ['make', '-j'+str(jobs), 'SHELL=/bin/sh'], objects, package_env)
        run('Stage ' + name, ['make', 'SHELL=/bin/sh', 'DESTDIR='+str(root), 'install'], objects, package_env)
    return runtime


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('base-result'))
    parser.add_argument('--cache', type=Path, default=Path.home()/'.cache/mojt/base-sources')
    parser.add_argument('--version', default='0.2.0')
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    require(re.fullmatch(r'[0-9]+(?:\.[0-9]+)+', args.version) and 1 <= args.jobs <= 256, 'invalid Base version/jobs')
    require(sys.platform == 'linux' and os.uname().machine == 'x86_64', 'first Base builder supports x86_64 Linux only')
    value, rows = sources(LOCK)
    require(not os.path.lexists(args.output), 'output already exists; choose a new private directory: ' + str(args.output))
    output = args.output.resolve(); cache = args.cache.resolve()
    require(re.fullmatch(r'/[A-Za-z0-9_./+-]+', str(output)), 'build output path needs plain shell-safe characters')
    print(f"Base {args.version}; glibc {rows['glibc']['version']}; {len(ORDER)} source projects + build-only Linux headers")
    print('Order: ' + ' -> '.join(ORDER)); print(f'Output: {output}; jobs: {args.jobs}')
    if args.dry_run:
        print('Preview only; no downloads, compiler execution or output writes.'); return
    missing = [name for name in TOOLS if not shutil.which(name)]
    require(not missing, 'missing build commands: ' + ', '.join(missing))
    require(hasattr(tarfile, 'data_filter'), 'Python 3.11 with tarfile security updates required')
    cc = shutil.which('gcc')
    # This first native bootstrap expects a plain host GCC, not a provider
    # wrapper which injects another libc. Compiler-provider integration is separate.
    require('/nix/store/' not in cc, 'use a plain native GCC for this first bootstrap')
    implementation = {name:sha(REPO/name) for name in ('tools/mojt-base-build.py', 'tools/mojt-base-pack',
        'bootstrap/tar-acl-2.4.patch', 'bootstrap/licenses/gcc-runtime-exception.txt')}
    os.umask(0o022)  # Public runtime files; the workspace itself stays private.
    output.mkdir(parents=True, mode=0o700); cache.mkdir(parents=True, exist_ok=True)
    root = output/'rootfs'; root.mkdir(); skeleton(root)
    logs = output/'logs'; logs.mkdir()
    (output/'INCOMPLETE').write_text('Build output only; never install an incomplete tree.\n')
    shutil.copyfile(LOCK, output/'sources.json')
    environment = dict(PATH=os.environ['PATH'], HOME=str(output), LC_ALL='C', LANG='C', TZ='UTC',
        SOURCE_DATE_EPOCH=str(value['source_date_epoch']), CONFIG_SHELL='/bin/bash', SHELL='/bin/bash',
        FORCE_UNSAFE_CONFIGURE='1')
    timings = []
    def run(label, command, cwd, env=environment):
        start = time.monotonic(); print(label + '...', flush=True)
        with (logs/(str(len(timings)) + '.log')).open('w') as log:
            try:subprocess.run(list(map(str,command)), cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
            except subprocess.CalledProcessError as error:
                raise ValueError(f'{label} failed; see {log.name}') from error
        elapsed = time.monotonic()-start; timings.append(dict(phase=label, seconds=elapsed))
        print(f'{label}: done ({elapsed:.2f} s)', flush=True)
    trees = {}
    for name in ('linux-headers', *ORDER):
        print('Source: ' + name, flush=True)
        archive = fetch(rows[name], cache, args.offline)
        trees[name] = unpack(archive, output/('source-' + name))
    runtime = build_projects(output, root, trees, args.jobs, environment, cc, run)
    (root/'usr/bin/sh').symlink_to('dash')
    licenses(root, trees)
    provenance = root/'usr/share/mojt'; provenance.mkdir(parents=True)
    shutil.copyfile(LOCK, provenance/'base-sources.json')
    defaults(root); prune(root)
    elf_count = audit(root, output)
    runtime['installed_sha256'] = sha(root/'usr/lib/libgcc_s.so.1')
    config = output/'base.toml'
    config.write_text(f'format=1\n[base]\nname="mojt"\nversion="{args.version}"\narchitecture="x86_64"\n'
        f'[abi]\nlibc="glibc"\nlibc_version="{rows["glibc"]["version"]}"\n[build]\nbackend="source"\n')
    inventory = output/'packages.txt'
    inventory.write_text(''.join(f'{name} {rows[name]["version"]} sha256:{rows[name]["sha256"]}\n' for name in ORDER)
        + f'bootstrap libgcc_s.so.1 input-sha256:{runtime["input_sha256"]} installed-sha256:{runtime["installed_sha256"]}\n'
        + ''.join(f'producer {name} sha256:{checksum}\n' for name,checksum in implementation.items()))
    run('Pack Base release', [sys.executable, '-I', '-B', REPO/'tools/mojt-base-pack', root, config,
        output/'releases', '--packages', inventory, '--normalize-owner'], REPO)
    result = dict(format='mojt-base-source-build-v1', version=args.version, sources=value, implementation=implementation,
                  compiler=subprocess.check_output([cc, '--version'], text=True).splitlines()[0],
                  compiler_path=cc, compiler_runtime=runtime, elf_files=elf_count, phases=timings,
                  release=str(output/'releases'/f'base-{args.version}-x86_64'),
                  libc_sharing='Independent FHS Base runtime; no substitution of retained Nix runtimes.')
    (output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    (output/'INCOMPLETE').unlink()
    print('READY: ' + result['release'] + '\nPackages only; no installation or boot selection changed.')


if __name__ == '__main__':
    try:main()
    except (ValueError, OSError, tarfile.TarError, subprocess.CalledProcessError) as error:
        raise SystemExit('mojt-base-build: ' + str(error))
