# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Frozen acceptance delivery with real component imports and simulated boot staging."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from test_mpm_system import REPO
from test_system_components import Components
import test_mpm_boot_v2 as fixtures
import mbt_runtime
import mpm_cli
import mpm_boot_update as update
import mpm_boot_selection as selection
import mpm_boot_constructor as constructor
import mpm_native_io as native
import mpm_base_transition as common
import mpm_system as system

spec=importlib.util.spec_from_file_location('components_delivery',REPO/'tools/mojt-system-components-test.py')
driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)


class GuardTests(unittest.TestCase):
    def test_firmware_guard_refuses_data_and_archives_without_suppressing_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);firmware=root/'firmware';firmware.mkdir();file=firmware/'data';file.write_text('firmware')
            archive=root/'archive';archive.write_text('compressed data')
            with contextlib.ExitStack() as stack:
                driver.FirmwareIO([firmware],{archive}).observe(stack)
                for path in (file,archive):
                    with self.assertRaisesRegex(ValueError,'firmware data accessed'):path.read_bytes()
                    with self.assertRaisesRegex(ValueError,'firmware data accessed'):open(path,'rb')
                    with self.assertRaisesRegex(ValueError,'firmware data accessed'):os.open(path,os.O_RDONLY)
                with self.assertRaises(FileNotFoundError):(root/'absent').read_bytes()
            self.assertEqual(file.read_text(),'firmware')


@unittest.skipUnless(os.geteuid()==0 and shutil.which('zstd'),'requires protected native execution and codec')
class DeliveryTests(Components):
    def test_one_prepare_builds_two_distinct_generations_using_frozen_code_and_records_both_timings(self):
        run=self.work/'run-driver';run.mkdir(mode=0o700)
        code=Path(tempfile.mkdtemp(prefix=mbt_runtime.PREFIX,dir=run));execution=mbt_runtime.freeze(REPO,code)
        hashes={}
        for name,path in driver.SUPPORT.items():
            data=(REPO/path).read_bytes();(run/name).write_bytes(data);(run/name).chmod(0o444);hashes[name]=hashlib.sha256(data).hexdigest()
        saved=dict(format=driver.FORMAT,baseline=dict(running=self.body['id'],selected='original-slot'),code=str(code),execution=execution,support=hashes)
        driver.save(run/'context.json',saved)
        snapshot=SimpleNamespace(unchanged=mock.Mock());original_load=driver.load
        def load(name,path):return snapshot if name=='snapshot' else original_load(name,path)
        runtime=mpm_cli.Runtime(disk=self.root,helpers=Path(shutil.which('zstd')).parent)
        with mock.patch.object(driver,'ROOT',self.root),mock.patch.object(driver,'load',side_effect=load),\
             mock.patch.object(sys,'path',list(sys.path)),mock.patch.object(common,'state_inputs',return_value={'evidence':{'fixture':True}}),\
             mock.patch.object(mpm_cli,'Runtime',return_value=runtime),mock.patch.object(selection,'present',return_value=True),\
             mock.patch.object(os.path,'ismount',return_value=True),mock.patch.object(update,'stage',return_value=dict(changed=True,deployment='prepared-slot',initramfs_payload={'reused':True})),\
             contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(driver.prepare_child(run),0)
        completed=json.loads((run/'completed.json').read_text())
        self.assertNotEqual(completed['first']['artifact'],completed['candidate']['artifact'])
        self.assertEqual(completed['firmware'],self.reference);self.assertEqual(completed['firmware_data_accesses'],0)
        self.assertGreater(completed['build_seconds'],0);self.assertGreater(completed['install_seconds'],0)
        self.assertEqual(snapshot.unchanged.call_count,3);self.assertFalse(self.marker.exists())
        for number in (1,2):
            report=json.loads((run/('sample-'+str(number))/'profile.json').read_text())
            self.assertEqual(report['io']['mpm_system.build_profile'].get('copy_calls',0),0)

    def test_native_component_capture_uses_descriptor_measurements_without_reading_firmware(self):
        candidate=self.build();self.import_package(candidate)
        source=fixtures.fixture()['description'];realized=system.realization(self.root,candidate['artifact'])['description']
        source['system']=dict(artifact=candidate['artifact'],composition=realized['composition'],manifest=realized['manifest'],generation=candidate['label'])
        for path in ('realizations/base/'+source['base']['artifact'][7:]+'/tree/rootfs',
                     'kernel/installed/'+source['kernel']['artifact'][7:]+'/payload/lib/modules'):
            (self.root/path).mkdir(parents=True)
        old=system.object_path(self.root,self.reference['artifact'])
        guard=driver.FirmwareIO([old/'payload/kernel/lib/firmware',old/'payload/kernel/licenses'],{old/'archive.tar.zst'})
        with contextlib.ExitStack() as stack,native.preparation():
            guard.observe(stack)
            stack.enter_context(mock.patch.object(selection,'current',return_value=(None,{},None)))
            proof=constructor.capture(self.root,constructor.model.record(constructor.model.INPUTS,source),{})
        components=[r for r in proof['description']['providers'] if r['reference']['provider']=='mojt-system-component']
        self.assertEqual(len(components),2)
