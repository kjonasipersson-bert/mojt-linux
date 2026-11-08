# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Bounded, no-follow boot inventories; neither import nor execute target code."""
import hashlib
import os
from pathlib import Path
import stat

import mojt_artifact as artifact
import mpm_native_io as io

MAX_NODES = 100000
require = artifact.require


def verify(root, expected, cache=None):
    """One operation-local proof per immutable path; never reuse across calls."""
    key = str(root);wanted = artifact.digest(expected)
    if cache is not None and key in cache:
        require(cache[key] == wanted,'conflicting immutable tree proofs')
        return
    require(snapshot(root) == expected,'immutable tree differs: '+key)
    if cache is not None:cache[key] = wanted


def path(root, relative):
    artifact.relative(relative)
    root = Path(root).absolute();target = root / relative
    require(target == target.resolve(), 'linked boot inventory root: ' + relative)
    return target


def snapshot(root, *, maximum=artifact.MAX_CONTENT):
    """Include modes, owners, xattrs and within-tree hardlinks, not timestamps."""
    rows = {};links = {};total = 0
    def visit(node, name):
        nonlocal total
        require(len(rows) < MAX_NODES, 'boot inventory node limit')
        before = node.lstat()
        row = dict(mode=stat.S_IMODE(before.st_mode), uid=before.st_uid, gid=before.st_gid,
                   xattrs={n:os.getxattr(node,n,follow_symlinks=False).hex() for n in sorted(os.listxattr(node,follow_symlinks=False))})
        if stat.S_ISLNK(before.st_mode):
            require(name != '.', 'linked boot inventory root')
            row.update(type='symlink', target=os.readlink(node))
        elif stat.S_ISDIR(before.st_mode):row['type'] = 'directory'
        else:
            require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= maximum, 'unsupported/unbounded boot file')
            total += before.st_size;require(total <= maximum, 'boot inventory content limit')
            fd = os.open(node, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                opened = os.fstat(fd)
                require((opened.st_dev,opened.st_ino,opened.st_size) == (before.st_dev,before.st_ino,before.st_size), 'boot file changed before reading')
                with os.fdopen(fd,'rb',closefd=False) as stream:
                    checksum = hashlib.sha256();size = 0
                    while chunk := stream.read(128*1024):
                        size += len(chunk);require(size <= before.st_size, 'boot file grew while reading');checksum.update(chunk)
                after = os.fstat(fd)
                require(size == before.st_size and (after.st_size,after.st_mtime_ns,after.st_ctime_ns) ==
                        (before.st_size,before.st_mtime_ns,before.st_ctime_ns), 'boot file changed while reading')
            finally:os.close(fd)
            row.update(type='file', size=size, sha256=checksum.hexdigest())
            key = (before.st_dev,before.st_ino)
            if key in links:row['hardlink_to'] = links[key]
            else:links[key] = name
        rows[name] = row
        if row['type'] == 'directory':
            children = []
            with os.scandir(node) as entries:
                for child in entries:
                    require(len(rows)+len(children) < MAX_NODES, 'boot inventory node limit');children.append(child.name)
            for child in sorted(children):visit(node/child, child if name == '.' else name+'/'+child)
    visit(Path(root), '.')
    require(len(artifact.canonical(rows)) < artifact.MAX_METADATA, 'boot inventory metadata limit')
    return rows


def clone_runtime(source, destination, expected):
    """Copy only an already verified runtime snapshot into a private initramfs."""
    require(not os.path.lexists(destination), 'runtime output collision')
    require(all(r['uid'] == r['gid'] == 0 and not r['xattrs'] and
                (r['type'] == 'symlink' or not r['mode'] & 0o6022) for r in expected.values()),
            'runtime requires root-owned nonprivileged immutable content')
    # Files and symlinks first; preserve actual within-tree hardlinks separately.
    for name,row in expected.items():
        target = destination if name == '.' else destination/name
        origin = source if name == '.' else source/name
        if row['type'] == 'directory':target.mkdir(mode=0o700)
        elif row['type'] == 'symlink':target.symlink_to(row['target'])
        elif 'hardlink_to' not in row:
            checksum,size = io.frozen_copy(origin,target)
            require((checksum,size) == (row['sha256'],row['size']), 'runtime changed during copying')
    for name,row in expected.items():
        if 'hardlink_to' in row:os.link(destination/row['hardlink_to'],destination/name,follow_symlinks=False)
    for name,row in reversed(list(expected.items())):
        target = destination if name == '.' else destination/name
        if row['type'] != 'symlink':target.chmod(row['mode'])
    require(snapshot(destination) == expected, 'copied runtime inventory differs')
