# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Declared System compatibility and read-only inspection; no Nix/VM boot."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import mojt_system_manifest as model
spec = importlib.util.spec_from_file_location("system_inspection", REPO / "tools/mojt-system-inspect.py")
inspect = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspect)


def manifest():
    return model.create(dict(label="system-A", architecture="x86_64",
        requirements=dict(base_abi={"libc": "glibc", "libc_version": "2.41"}, state_layout=1),
        support=dict(ports=dict(read=[1,2,3], write=[1,2,3], capabilities=["mpm-ports-selectors-v1"])),
        provides=["/run/mojt-system/bin/bash"], artifacts={"archive": {"object": "opaque-1"}},
        provenance={"source": "pinned-source"}, profile={"bin/bash": {"link": "opaque-target"}}))


def context():
    return dict(format=model.CONTEXT, architecture="x86_64", base_abi={"libc":"glibc", "libc_version":"2.41"},
        state_layout=1, ports=dict(format=3, capabilities=dict(reader="mpm-ports-selectors-v1", writer="mpm-ports-selectors-v1")),
        required_system_paths=["/run/mojt-system/bin/bash"])


class ManifestTests(unittest.TestCase):
    def test_compatible_pure_data_and_input_immutability(self):
        m, c = manifest(), context()
        old = copy.deepcopy((m,c))
        self.assertTrue(model.check(m,c)["compatible"])
        self.assertEqual((m,c),old)
        # Backend names and payload identity syntax do not enter compatibility policy.
        m["description"]["artifacts"] = {"another-backend": {"path": "anything", "integrity": {"opaque": True}}}
        m = model.create(m["description"])
        self.assertTrue(model.check(m,c)["compatible"])

    def test_old_writer_and_unknown_capability_stop_candidate(self):
        d = manifest()["description"]
        d["support"]["ports"]["write"] = [1,2]
        self.assertIn("not supported for write", model.check(model.create(d),context())["errors"][0])
        c = context()
        c["ports"]["capabilities"]["writer"] = "future-v2"
        self.assertFalse(model.check(manifest(),c)["compatible"])

    def test_architecture_abi_layout_and_system_shell_are_checked(self):
        for key, value in (("architecture","aarch64"),("base_abi",{"libc":"other"}),
                           ("state_layout",2),("required_system_paths",["/run/mojt-system/bin/missing"])):
            with self.subTest(key=key):
                c = context(); c[key] = value
                self.assertFalse(model.check(manifest(),c)["compatible"])

    def test_absent_ports_has_no_metadata_requirement(self):
        c=context(); c["ports"]=None
        d=manifest()["description"]; d["support"]["ports"]=dict(read=[],write=[],capabilities=[])
        self.assertTrue(model.check(model.create(d),c)["compatible"])

    def test_unknown_format_tampered_identity_and_incomplete_context_fail(self):
        for m in (dict(manifest(),format="future"),dict(manifest(),id="forged")):
            with self.assertRaises(ValueError): model.check(m,context())
        c=context(); c["ports"]["capabilities"]={}
        with self.assertRaises(ValueError): model.check(manifest(),c)

    def test_selected_is_unknown_until_explicit_and_changes_are_exact(self):
        current=manifest(); d=copy.deepcopy(current["description"])
        d["artifacts"]={"archive":{"object":"new"}}; candidate=model.create(d)
        r=model.compare(candidate,current)
        self.assertIsNone(r["selected"])
        self.assertEqual(set(r["changes"]),{"artifacts"})
        self.assertEqual(model.compare(candidate,current,current)["selected"],current["id"])

    def test_cli_accepts_and_rejects_without_touching_supplied_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); m=root/"manifest.json"; c=root/"context.json"
            m.write_text(json.dumps(manifest())); c.write_text(json.dumps(context()))
            before={p.name:p.read_bytes() for p in root.iterdir()}
            cmd=[sys.executable,"-I",str(REPO/"tools/mojt-system-inspect.py"),"--candidate",str(m),"--context",str(c)]
            result=subprocess.run(cmd,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIsNone(json.loads(result.stdout)["selected"])
            self.assertEqual({p.name:p.read_bytes() for p in root.iterdir()},before)
            value=context(); value["ports"]["format"]=4; c.write_text(json.dumps(value))
            result=subprocess.run(cmd,text=True,capture_output=True)
            self.assertEqual(result.returncode,1)
            self.assertFalse(json.loads(result.stdout)["compatible"])

    def test_target_reader_does_not_mistake_dangling_state_for_absence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/"releases").mkdir()
            (root/"releases/base-1.toml").write_text('format=1\n[base]\nversion="1"\narchitecture="x86_64"\n[abi]\nlibc="glibc"\n[state]\nlayout_version=1\n')
            self.assertIsNone(inspect.context_from_target(root,"1")["ports"])
            ports=root/"state/var/lib/mojt/ports"; ports.mkdir(parents=True)
            self.assertIsNone(inspect.context_from_target(root,"1")["ports"])
            (ports/"current").symlink_to("profiles/missing")
            with self.assertRaises(OSError): inspect.context_from_target(root,"1")


if __name__ == "__main__":
    unittest.main()
