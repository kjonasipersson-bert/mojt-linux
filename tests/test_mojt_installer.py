# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Whole-disk installer confirmation and handoff."""
from contextlib import ExitStack
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import mojt_installer as installer


class InstallerTests(unittest.TestCase):
    def install_fixture(self, answers, *, changed=False, build=False):
        disk = dict(path='/dev/vdz', number='254:48', bytes=20*installer.GIB,
                    model='Test disk', serial='123', sequence='2')

        with ExitStack() as patches:
            def patch(target, attribute, **kwargs):
                return patches.enter_context(mock.patch.object(target, attribute, **kwargs))
            scratch = Path(patches.enter_context(tempfile.TemporaryDirectory()))
            work = scratch/'work'; work.mkdir()
            device = scratch/'device'; device.touch()
            real_open = installer.os.open
            patch(installer.os, 'geteuid', return_value=0)
            patch(installer.sys.stdin, 'isatty', return_value=True)
            patch(installer.sys.stdout, 'isatty', return_value=True)
            patch(installer.Path, 'is_dir', return_value=True)
            real_read = Path.read_text
            def read(path, *args, **kwargs):
                if str(path) == '/proc/filesystems':
                    return 'btrfs\nvfat\n'
                return real_read(path, *args, **kwargs)
            patch(installer.Path, 'read_text', autospec=True, side_effect=read)
            patch(installer.tempfile, 'mkdtemp', return_value=str(work))
            patch(installer.mounted, 'command')
            patch(installer, 'disks', side_effect=[[disk], [] if changed else [disk]])
            patch(installer.mounted, 'storage_drivers', return_value=['virtio_blk'])
            patch(installer.bootstrap, 'preflight')
            config = mock.Mock(hardware_profile=None, kernel_registry=Path('/fake/kernel'), kernel_artifact='sha256:abc')
            patch(installer.bootstrap, 'parser', return_value=mock.Mock(**{'parse_args.return_value':config}))
            def expand(argv, *, details):
                details['id'] = 'test'
                return argv
            patch(installer.inputs, 'expand', side_effect=expand)
            patch(installer.native, 'preview', return_value={
                'kernel': {'metadata': {'kernel_release':'6.12.107-mojt1'}},
                'base': {'version': {'upstream':'0.2.1'}},
            })
            patches.enter_context(mock.patch('mpm_kernel_boot.vm_module'))
            patches.enter_context(mock.patch('builtins.input', side_effect=answers))
            actions = patch(installer.mounted, 'run')
            plan = []
            def partition(disk, rows):
                plan.extend(rows)
                return {name: Path('/dev')/name for name, _, _, _ in rows}
            partitioner = patch(installer, 'partition', side_effect=partition)
            def open_device(path, flags, *args, **kwargs):
                return real_open(device if path == disk['path'] else path, flags, *args, **kwargs)
            fd = patch(installer.os, 'open', side_effect=open_device)
            patch(installer, 'device_number', return_value='254:48')
            def inspect(*args, **kwargs):
                return dict(root=dict(partuuid=plan[-1][3], uuid='root-uuid', disk_device=disk['number']),
                            efi=dict(partuuid=plan[0][3]))
            patch(installer.mounted, 'inspect', side_effect=inspect)
            builder = patch(installer.mounted, 'build')

            if changed:
                with self.assertRaisesRegex(ValueError,'identity or usage changed'):
                    installer.install(Path('/kit'))
            else:
                installer.install(Path('/kit'))

            if build:
                partitioner.assert_called_once()
                self.assertEqual([call.args[0] for call in actions.call_args_list],
                                 ['mkfs.vfat','mkfs.btrfs','mkswap','mount','mount','umount','umount'])
                self.assertEqual(config.expected_root_uuid,'root-uuid')
                self.assertEqual(config.expected_efi_partuuid,plan[0][3])
                self.assertIn('configure',builder.call_args.kwargs)
            else:
                partitioner.assert_not_called()
                actions.assert_not_called()
                builder.assert_not_called()
                if not changed:
                    self.assertFalse(any(call.args[0] == disk['path'] for call in fd.call_args_list))

    def test_cancel_before_writes(self):
        self.install_fixture(['1','0','no'])

    def test_disk_change_refuses_partitioning(self):
        self.install_fixture(['1','0','/dev/vdz'], changed=True)

    def test_confirmed_disk_hands_btrfs_efi_and_swap_to_bootstrap(self):
        self.install_fixture(['1','2','/dev/vdz'], build=True)

    def test_zero_swap_creates_only_two_partitions(self):
        self.assertEqual([name for name, *_ in installer.layout(0)],['MOJT-EFI','MOJT'])
