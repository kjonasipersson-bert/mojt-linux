#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Regression test: the packaged Base / is root-owned, not host-user-owned.

Requires root, Python 3.11+, GNU cp/tar and zstd. Uses a synthetic rootfs,
never changes the host root or any existing Mojt release.
Run: sudo python3 -m unittest discover -s tests -p 'test_base_pack_root.py' -v
"""

import os
from pathlib import Path
import shutil
import stat
import subprocess
import tarfile
import tempfile
import unittest


REPO = Path(__file__).resolve().parent.parent
PACKER = REPO / "tools/mojt-base-pack"


@unittest.skipUnless(
    os.geteuid() == 0 and all(shutil.which(x) for x in ("cp", "tar", "zstd")),
    "requires root, GNU cp/tar and zstd",
)
class RootOwnershipTests(unittest.TestCase):
    def test_archive_root_is_root_owned_and_input_is_unchanged(self):
        with tempfile.TemporaryDirectory(prefix="mojt-pack-root-test-") as work:
            directory = Path(work)
            source = directory / "input-rootfs"
            (source / "usr/bin").mkdir(parents=True)
            (source / "usr/lib").mkdir()
            (source / "etc").mkdir()
            # Void is only a bootstrap backend; never ship its login banner.
            (source / "etc/issue").write_text("Void Linux\n", encoding="ascii")
            (source / "usr/bin/sh").write_text("#!/bin/sh\n", encoding="ascii")
            (source / "bin").symlink_to("usr/bin")
            os.chown(source, 1000, 1000)
            os.chmod(source, 0o775)

            manifest = directory / "base.toml"
            manifest.write_text(
                'format = 1\n'
                '[base]\nname = "mojt"\nversion = "0.1.99-test"\n'
                'architecture = "x86_64"\n'
                '[abi]\nlibc = "glibc"\nlibc_version = "2.41"\n'
                '[build]\nbackend = "void"\n',
                encoding="ascii",
            )
            output = directory / "releases"
            subprocess.run(
                [str(PACKER), str(source), str(manifest), str(output)],
                check=True, capture_output=True, text=True,
            )
            image = output / "base-0.1.99-test-x86_64" / "rootfs.tar.zst"
            tar_path = directory / "image.tar"
            with tar_path.open("wb") as destination:
                subprocess.run(["zstd", "-dc", str(image)],
                               stdout=destination, check=True)
            with tarfile.open(tar_path, "r:") as archive:
                archive_root = archive.getmember(".")
                self.assertTrue(archive_root.isdir())
                self.assertEqual((archive_root.uid, archive_root.gid), (0, 0))
                self.assertEqual(stat.S_IMODE(archive_root.mode), 0o755)
                with archive.extractfile("./usr/etc/issue") as stream:
                    self.assertEqual(stream.read(), b"Mojt Linux Base 0.1.99-test\n")
                self.assertTrue(archive.getmember("./etc").isdir())
                self.assertFalse(any(item.name == "./etc/issue" for item in archive))

            self.assertEqual((source / "etc/issue").read_bytes(), b"Void Linux\n")
            original = source.stat()
            self.assertEqual((original.st_uid, original.st_gid), (1000, 1000))
            self.assertEqual(stat.S_IMODE(original.st_mode), 0o775)


if __name__ == "__main__":
    unittest.main()
