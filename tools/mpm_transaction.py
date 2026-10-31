# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Provider-independent lock and publication rules; area records stay authoritative."""
from contextlib import contextmanager, ExitStack
import fcntl
import os
from pathlib import Path
import stat


class PublicationUncertain(OSError):
    """The rename completed, but its directory flush failed. Retain new content."""
    committed = True


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def check_lock_file(path, *, shared=False):
    info = Path(path).lstat()
    _check_lock(info, shared=shared)


def _check_lock(info, *, shared):
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o022
            or (not shared and info.st_uid != os.geteuid())):
        raise ValueError("unsafe transaction lock")


@contextmanager
def file_lock(path, *, shared=False, create=None, mode=0o600):
    """Use a stable existing lock name; never truncate, replace or unlink it."""
    path = Path(os.path.abspath(path))
    if path != path.resolve():
        raise ValueError("transaction lock path traverses a symlink")
    flags = (os.O_RDONLY if shared else os.O_RDWR) | os.O_NOFOLLOW | os.O_NONBLOCK
    if create is None:
        create = not shared
    if create:
        flags |= os.O_CREAT
    fd = os.open(path, flags, mode)
    try:
        _check_lock(os.fstat(fd), shared=shared)
        fcntl.flock(fd, fcntl.LOCK_SH if shared else fcntl.LOCK_EX)
        # Refuse a replacement inode while waiting, instead of locking an orphan.
        current = path.lstat()
        held = os.fstat(fd)
        if (current.st_dev, current.st_ino) != (held.st_dev, held.st_ino):
            raise ValueError("transaction lock changed while waiting")
        _check_lock(current, shared=shared)
        yield
    finally:
        os.close(fd)


@contextmanager
def resource_locks(paths, *, modes=None):
    """Acquire distinct cooperating resources in one deterministic path order."""
    ordered = sorted({Path(os.path.abspath(path)) for path in paths})
    with ExitStack() as stack:
        for path in ordered:
            stack.enter_context(file_lock(path, mode=(modes or {}).get(path, 0o600)))
        yield


def boot_lock_paths(root):
    """The layout-v1 writers whose state is read by Kernel boot publication."""
    root = Path(root)
    return (root / ".install-lock", root / "boot/mpm/.lock", root / "kernel/.lock",
            root / "state/var/lib/mojt/ports/.lock")


def publish(source, destination, *, sync=sync_directory):
    """Publish one prepared pointer/file. The caller validates and holds locks.

    This is a single same-filesystem rename, not a multi-file transaction or a
    state rollback. A post-rename error must never trigger deletion of its target.
    """
    prepared = Path(source).lstat()
    try:
        os.replace(source, destination)
    except BaseException as error:
        # An asynchronous interruption can arrive just after the rename.
        try:
            current = Path(destination).lstat()
        except OSError:
            raise error
        if (current.st_dev, current.st_ino) == (prepared.st_dev, prepared.st_ino):
            raise PublicationUncertain("publication may have committed; retain content and inspect "
                                       + str(destination) + ": " + str(error)) from error
        raise
    try:
        sync(Path(destination).parent)
    except BaseException as error:
        raise PublicationUncertain(
            "publication may have committed; retain content and inspect "
            + str(destination) + ": " + str(error)) from error
