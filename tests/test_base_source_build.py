# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Source producer boundaries, archive safety and unprivileged Base packaging."""
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('builder', REPO/'tools/mojt-base-build.py')
builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)


class SourceBuildTests(unittest.TestCase):
    def test_preview_never_fetches_compiles_or_writes_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'new-output'
            with mock.patch.object(builder.subprocess, 'run', side_effect=AssertionError('unexpected execution')):
                builder.main(['--dry-run', '--output', str(output)])
            self.assertFalse(output.exists())

    def test_existing_output_refused_before_any_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            sentinel = Path(tmp)/'existing'; sentinel.write_text('keep')
            with self.assertRaisesRegex(ValueError, 'output already exists'):
                builder.main(['--output', tmp, '--dry-run'])
            self.assertEqual(sentinel.read_text(), 'keep')

    def test_dangling_output_link_is_not_followed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'alias').symlink_to('absent')
            with self.assertRaisesRegex(ValueError, 'output already exists'):
                builder.main(['--output', str(root/'alias'), '--dry-run'])
            self.assertFalse((root/'absent').exists())

    def test_failed_input_leaves_incomplete_workspace_without_a_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); output = root/'work'
            previous = os.umask(0o077)
            try:
                with mock.patch.object(builder.shutil, 'which', return_value='/usr/bin/gcc'), \
                     mock.patch.object(builder, 'fetch', side_effect=ValueError('bad source')):
                    with self.assertRaisesRegex(ValueError, 'bad source'):
                        builder.main(['--output', str(output), '--cache', str(root/'cache')])
            finally:
                os.umask(previous)
            self.assertTrue((output/'INCOMPLETE').is_file())
            self.assertFalse((output/'releases').exists())
            self.assertEqual(output.stat().st_mode & 0o777, 0o700)
            self.assertEqual((output/'rootfs/usr').stat().st_mode & 0o777, 0o755)

    def test_nested_upstream_license_texts_are_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp); tree = work/'source'; (tree/'doc').mkdir(parents=True)
            (tree/'doc/COPYING').write_text('GPL text')
            (tree/'COPYING').write_text('GPL text')
            (tree/'LICENCE.md').write_text('additional notices')
            (work/'rootfs/usr/lib').mkdir(parents=True)
            (work/'rootfs/usr/lib/libgcc_s.so.1').write_bytes(b'runtime fixture')
            builder.licenses(work/'rootfs', {'coreutils':tree})
            result = work/'rootfs/usr/share/licenses/coreutils'
            self.assertEqual((result/'doc/COPYING').read_text(), 'GPL text')
            self.assertEqual((result/'LICENCE.md').read_text(), 'additional notices')
            notice = work/'rootfs/usr/share/licenses/bootstrap-libgcc'
            self.assertIn('GCC RUNTIME LIBRARY EXCEPTION', (notice/'COPYING.RUNTIME').read_text())
            self.assertEqual((notice/'COPYING.GPLv3').read_text(), 'GPL text')

    def test_bad_cached_source_is_not_reused_or_silently_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            row = dict(name='fixture', url='https://example.invalid/input.tar.xz', sha256='0'*64)
            target = cache/(row['sha256']+'-input.tar.xz'); target.write_bytes(b'corrupt')
            with mock.patch.object(builder.subprocess, 'run', side_effect=AssertionError('unexpected download')):
                with self.assertRaisesRegex(ValueError, 'checksum differs'):
                    builder.fetch(row, cache)
            self.assertEqual(target.read_bytes(), b'corrupt')

    def test_offline_missing_source_and_traversal_archive_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, 'offline source missing'):
                builder.fetch(dict(name='fixture',url='https://example.invalid/src.tar',sha256='0'*64), root, True)
            archive = root/'bad.tar'
            with tarfile.open(archive, 'w') as stream:
                entry = tarfile.TarInfo('../escape'); entry.size = 3
                stream.addfile(entry, io.BytesIO(b'bad'))
            with self.assertRaises(tarfile.FilterError):
                builder.unpack(archive, root/'source')
            self.assertFalse((root/'escape').exists())

    @unittest.skipUnless(all(shutil.which(name) for name in ('cp','tar','zstd')), 'requires real archive tools')
    def test_source_tree_packages_without_root_and_archive_is_root_owned(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp); root = work/'rootfs'; root.mkdir(); builder.skeleton(root); builder.defaults(root)
            (root/'usr/bin/sh').write_text('#!/bin/sh\n'); (root/'usr/bin/sh').chmod(0o755)
            config = work/'base.toml'
            config.write_text('format=1\n[base]\nname="mojt"\nversion="0.2.0"\narchitecture="x86_64"\n'
                              '[abi]\nlibc="glibc"\nlibc_version="2.44"\n[build]\nbackend="source"\n')
            before = (root/'usr/bin/sh').stat()
            result = subprocess.run([sys.executable, '-I', '-B', str(REPO/'tools/mojt-base-pack'),
                str(root), str(config), str(work/'releases'), '--normalize-owner'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            image = work/'releases/base-0.2.0-x86_64/rootfs.tar.zst'
            raw = subprocess.check_output(['zstd', '-dc', str(image)])
            with tarfile.open(fileobj=io.BytesIO(raw)) as stream:
                self.assertTrue(all((m.uid,m.gid) == (0,0) for m in stream))
                self.assertEqual(stream.getmember('./usr/etc/shadow').mode & 0o777, 0o600)
                self.assertFalse(any(m.name.startswith('./etc/') for m in stream))
            self.assertEqual((root/'usr/bin/sh').stat().st_uid, before.st_uid)
            self.assertFalse((root/'usr/lib/os-release').exists())  # Only the packer's copy changes.

    def test_target_flags_use_staged_sysroot_and_no_host_pkg_config_paths(self):
        env = builder.target_environment(dict(PATH='/usr/bin'), Path('/work/base/rootfs'), '/usr/bin/gcc')
        self.assertIn('--sysroot=/work/base/rootfs', env['CC'])
        self.assertIn('-static-libgcc', env['LDFLAGS'])
        self.assertEqual(env['PKG_CONFIG_LIBDIR'], '/work/base/rootfs/usr/lib/pkgconfig')
        self.assertNotIn('-rpath,', env['LDFLAGS'])


if __name__ == '__main__':
    unittest.main()
