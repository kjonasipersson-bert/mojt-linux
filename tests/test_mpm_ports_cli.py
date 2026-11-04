# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Joined frontend/filesystem flow; provider fixture is explicit, not live Nix."""
import contextlib
import copy
import inspect
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import mpm_cli as cli
import mpm_ports_cli as manager
import mpm_ports_profile as profiles
import mpm_request_plan as planning
import mpm_requests as wishes
import test_mpm_ports_profile as fixtures


class PortsCliTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.ProfileTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.root = self.f.root; self.parent = self.f.parent
        self.bundle = self.parent / 'sources.json'
        self.write_sources()
        self.patch = mock.patch.object(manager, 'adapters_for', return_value=self.f.adapters)
        self.patch.start(); self.addCleanup(self.patch.stop)

    def write_sources(self, sources=None):
        value = planning.record(manager.SOURCES, dict(platform=os.uname().machine + '-linux',
            sources=self.f.sources if sources is None else sources))
        self.bundle.write_text(json.dumps(value)); return value['id']

    def call(self, *args, success=True, runtime=None):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(['--root', str(self.root), 'ports', *args], runtime=runtime)
        self.assertEqual(code, 0 if success else 1, out.getvalue() + err.getvalue())
        if not success: return err.getvalue()
        try: return json.loads(out.getvalue())
        except ValueError: return out.getvalue()

    def state(self): return profiles.current(self.root)['record']['description']
    def output(self, name='hello'): return subprocess.check_output([str(self.root / 'current/bin' / name)], text=True).strip()

    def test_public_preview_empty_status_and_cancellation_write_nothing(self):
        self.assertEqual(self.call('status')['installed'], [])
        self.assertEqual(self.call('history', '--json'), [])
        preview = self.call('install', 'hello@2.12', '--sources', str(self.bundle), '--dry-run')
        self.assertTrue(preview['dry_run']); self.assertFalse(self.root.exists())
        self.assertEqual(self.f.adapter.fetches, 0)
        with mock.patch('builtins.input', return_value='n'):
            self.assertIn('Cancelled', self.call('install', 'hello', '--sources', str(self.bundle)))
        self.assertFalse(self.root.exists())

    def test_update_freezes_targets_even_when_latest_metadata_withdraws_them(self):
        self.call('install', 'hello@2.12', '--sources', str(self.bundle), '-y')
        before = self.state(); fetches = self.f.adapter.fetches
        self.write_sources({})
        self.call('update', '--sources', str(self.bundle), '-y')
        after = self.state()
        self.assertEqual(after['active'], before['active'])
        self.assertEqual(after['lock']['description']['resolutions'], before['lock']['description']['resolutions'])
        self.assertEqual(self.output(), '2.12.3'); self.assertEqual(fetches, self.f.adapter.fetches)
        count = len(profiles.history(self.root))
        self.assertFalse(self.call('update', '--sources', str(self.bundle), '-y')['changed'])
        self.assertEqual(len(profiles.history(self.root)), count)
        self.assertIn('missing named source', self.call('upgrade', 'hello', '-y', success=False))

    def test_new_install_does_not_upgrade_old_wish_and_explicit_upgrade_honors_pin(self):
        new = copy.deepcopy(self.f.candidates[1]); self.f.candidates[:] = self.f.candidates[:1]
        self.write_sources(); self.call('install', 'hello@2.12', '--sources', str(self.bundle), '-y')
        self.f.candidates.append(new); self.write_sources()
        self.call('install', 'hello@=2.12.3', '--sources', str(self.bundle), '-y')
        self.assertEqual(self.output(), '2.12.1'); self.assertEqual(self.output('hello-2.12'), '2.12.1')
        self.call('upgrade', 'hello', '-y')
        self.assertEqual(self.output(), '2.12.3'); self.assertEqual(self.output('hello-2.12'), '2.12.3')
        self.call('activate', 'hello@=2.12.1', '-y')
        self.assertEqual(self.output(), '2.12.1')
        before = os.readlink(self.root / 'current')
        self.assertFalse(self.call('upgrade', 'hello', '-y')['changed'])
        self.assertEqual(os.readlink(self.root / 'current'), before)
        self.call('activate', 'hello@2.12', '-y')
        self.assertEqual(self.output(), '2.12.3')
        rows = self.call('list', '--json'); self.assertEqual(len(rows), 2)
        self.assertIn(wishes.digest(self.f.refs['2.12.1']), self.call('list', '--exact'))

    def test_configuration_removal_retains_independent_user_wishes(self):
        config = self.parent / 'mojt-configuration.toml'
        config.write_text('format="mojt-configuration-v1"\nname="main"\n[ports]\nsource="local"\npackages=["hello@=2.12.1"]\n')
        self.call('apply', '--configuration', str(config), '--sources', str(self.bundle), '-y')
        self.call('install', 'hello@=2.12.3', '-y')
        self.call('activate', 'hello@=2.12.3', '-y')
        config.write_text('format="mojt-configuration-v1"\nname="main"\n')
        self.call('apply', '--configuration', str(config), '-y')
        self.assertEqual(self.output(), '2.12.3')
        self.assertEqual([p['release_id'] for p in self.state()['packages']], ['2.12.3'])
        self.assertTrue(all(c['origin']['kind'] == 'interactive' for c in self.state()['requests']['description']['claims']))

    def test_exact_accepted_build_survives_catalog_withdrawal_during_upgrade(self):
        self.call('install', 'hello@=2.12.1', '--sources', str(self.bundle), '-y')
        before = self.state()['lock']['description']['resolutions']
        self.write_sources({})
        self.call('update', '--sources', str(self.bundle), '-y')
        self.assertFalse(self.call('upgrade', 'hello', '-y')['changed'])
        self.assertEqual(self.state()['lock']['description']['resolutions'], before)
        self.assertEqual(self.output(), '2.12.1')

    def test_installed_selection_does_not_promote_unknown_stability_to_latest(self):
        for c in self.f.candidates: c['stability'] = 'unknown'
        self.write_sources()
        self.call('install', 'hello@=2.12.3', '--sources', str(self.bundle), '-y')
        self.assertIn('no eligible', self.call('activate', 'hello', '-y', success=False))
        self.call('activate', 'hello@=2.12.3', '-y')
        self.assertEqual(self.output(), '2.12.3')

    def test_following_activation_chooses_interactive_reason_shared_with_configuration(self):
        config = self.parent / 'shared.toml'
        config.write_text('format="mojt-configuration-v1"\nname="main"\n[ports]\nsource="local"\npackages=["hello@2.12"]\n')
        self.call('apply', '--configuration', str(config), '--sources', str(self.bundle), '-y')
        self.call('install', 'hello@2.12', '-y')
        self.call('activate', 'hello@2.12', '-y')
        choice = self.state()['requests']['description']['selections'][0]
        self.assertEqual(choice['origin']['kind'], 'interactive')
        config.write_text('format="mojt-configuration-v1"\nname="main"\n')
        self.call('apply', '--configuration', str(config), '-y')
        self.assertEqual(self.output(), '2.12.3')
        self.assertEqual(self.state()['requests']['description']['selections'][0], choice)

    def test_no_activate_and_exact_reference_selection(self):
        self.call('install', 'hello', '--sources', str(self.bundle), '--no-activate', '-y')
        self.assertFalse((self.root / 'current/bin/hello').exists())
        ref = self.state()['packages'][0]['reference']
        self.call('activate', wishes.digest(ref), '-y')
        self.assertEqual(self.output(), '2.12.3')
        self.assertEqual(self.call('info', wishes.digest(ref))['reference'], ref)

    def test_input_errors_and_unimplemented_areas_do_not_write(self):
        self.assertIn('identity differs', self.call('update', '--sources', str(self.bundle),
            '--expected-sources', 'sha256:' + '0' * 64, '-y', success=False))
        config = self.parent / 'full.toml'
        config.write_text('format="mojt-configuration-v1"\nname="main"\n[base]\nselector="base@=0.1.3"\n')
        self.assertIn('only Ports', self.call('apply', '--configuration', str(config), '--sources', str(self.bundle), '-y', success=False))
        self.assertFalse(self.root.exists()); self.assertEqual(self.f.adapter.fetches, 0)

    def test_literal_local_search_and_readers_do_not_load_provider(self):
        self.call('update', '--sources', str(self.bundle), '-y')
        with mock.patch.object(manager, 'adapters_for', side_effect=AssertionError('provider loaded')):
            self.assertEqual(self.call('search', 'hello', '--json')['matches'], ['hello'])
            self.assertEqual(self.call('search', 'h.*', '--json')['matches'], [])
            self.call('status'); self.call('history', '--json'); self.call('list', '--json')

    def test_installed_copy_can_publish_without_checkout_or_prototype(self):
        installed = self.parent / 'installed'; installed.mkdir()
        for name in ('mpm_cli.py', 'mpm_ports_cli.py', 'mpm_requests.py', 'mpm_request_plan.py',
                     'mpm_ports_profile.py', 'mpm_nix_binary.py', 'mpm_selection.py', 'mpm_transaction.py'):
            shutil.copyfile(Path(manager.__file__).parent / name, installed / name)
        # The acceptance harness supplies a trusted file-copy provider, just as
        # native boot fixtures substitute host tools. Production mapping stays Nix.
        script = '''import copy,hashlib,json,os,shutil,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import mpm_cli,mpm_ports_cli
''' + inspect.getsource(fixtures.CopyAdapter) + '''
mpm_ports_cli.adapters_for=lambda *args: {'copy':CopyAdapter()}
sys.exit(mpm_cli.main(sys.argv[2:]))
'''
        result = subprocess.run([sys.executable, '-I', '-B', '-c', script, str(installed),
            '--root', str(self.root), 'ports', 'install', 'hello@2.12', '--sources', str(self.bundle), '-y'],
            cwd='/', env=dict(os.environ, PATH='', PYTHONPATH='/invalid'), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output(), '2.12.3')
        self.assertTrue(json.loads(result.stdout)['changed'])
        self.assertEqual(len(profiles.history(self.root)), 1)

    def test_remove_shared_reason_preserves_config_package_and_repeats_without_history(self):
        config = self.parent / 'reasons.toml'
        config.write_text('format="mojt-configuration-v1"\nname="main"\n[ports]\nsource="local"\npackages=["hello@2.12"]\nactive={hello="hello@2.12"}\n')
        self.call('apply', '--configuration', str(config), '--sources', str(self.bundle), '-y')
        self.call('install', 'hello@2.12', '-y')
        self.call('activate', 'hello@2.12', '-y')
        fetches=self.f.adapter.fetches;self.f.adapter.fail=True
        preview=self.call('remove','hello','--dry-run')
        self.assertEqual(len(preview['plan']['description']['candidate']['requests']['description']['claims']),1)
        self.call('remove','hello','-y')
        self.assertEqual(self.output(),'2.12.3');self.assertEqual(self.f.adapter.fetches,fetches)
        self.assertEqual(self.state()['requests']['description']['selections'][0]['origin']['kind'],'configuration')
        before=profiles.history(self.root)
        self.assertFalse(self.call('remove','hello','-y')['changed'])
        self.assertEqual(profiles.history(self.root),before)

    def test_reset_restores_configuration_from_accepted_targets_after_metadata_withdrawal(self):
        config=self.parent/'reset.toml'
        config.write_text('format="mojt-configuration-v1"\nname="main"\n[ports]\nsource="local"\npackages=["hello@2.12"]\nactive={hello="hello@2.12"}\n')
        self.call('apply','--configuration',str(config),'--sources',str(self.bundle),'-y')
        self.call('install','hello@=2.12.1','-y');self.call('activate','hello@=2.12.1','-y')
        self.write_sources({});self.call('update','--sources',str(self.bundle),'-y')
        before=self.state();self.f.adapter.fail=True
        self.call('reset','hello','-y')
        self.assertEqual(self.output(),'2.12.3')
        self.assertEqual(self.state()['requests']['description']['claims'],before['requests']['description']['claims'])
        self.assertEqual(self.state()['lock']['description']['resolutions'],before['lock']['description']['resolutions'])
        self.assertFalse(self.call('reset','hello','-y')['changed'])

    def test_selector_removal_keeps_exact_pin_and_bare_removal_releases_current_profile_only(self):
        self.call('install','hello@2.12','--sources',str(self.bundle),'-y')
        self.call('activate','hello@=2.12.3','-y')
        old=profiles.current(self.root);target=Path(old['record']['description']['aliases']['hello'])
        self.call('remove','hello@2.12','-y')
        self.assertEqual(self.output(),'2.12.3');self.assertFalse((self.root/'current/bin/hello-2.12').exists())
        self.call('remove','hello','-y')
        self.assertEqual(self.state()['packages'],[]);self.assertEqual(self.state()['aliases'],{})
        self.assertTrue(target.is_file());self.assertTrue((self.root/old['path']).is_dir())
        self.assertFalse(self.call('remove','hello','-y')['changed'])

    def test_remove_and_reset_require_an_existing_profile(self):
        for command in ('remove','reset'):
            self.assertIn('existing Ports profile',self.call(command,'hello','-y',success=False))
        self.assertFalse(self.root.exists())

    def test_reset_conflict_preserves_profile_and_history(self):
        self.call('install','hello@=2.12.1','--sources',str(self.bundle),'-y')
        for name,selector in (('first','hello@=2.12.1'),('second','hello@=2.12.3')):
            config=self.parent/(name+'.toml')
            config.write_text('format="mojt-configuration-v1"\nname="'+name+'"\n[ports]\nsource="local"\npackages=["'+selector+'"]\nactive={hello="'+selector+'"}\n')
            self.call('apply','--configuration',str(config),'-y')
        before=os.readlink(self.root/'current');history=profiles.history(self.root)
        self.assertIn('conflicting configuration defaults',self.call('reset','hello','-y',success=False))
        self.assertEqual(os.readlink(self.root/'current'),before);self.assertEqual(profiles.history(self.root),history)
        self.assertEqual(self.output(),'2.12.1')

    def test_shared_remove_reset_are_denied_before_target_or_provider_access(self):
        with mock.patch.object(cli.os,'geteuid',return_value=1000):
            for action in ('remove','reset'):
                self.assertIn('administrator',self.call(action,'hello','-y',runtime=cli.Runtime(),success=False))
        self.assertFalse(self.root.exists());self.assertEqual(self.f.adapter.fetches,0)


if __name__ == '__main__': unittest.main()
