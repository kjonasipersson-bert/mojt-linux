<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Mojt Ports repository

A Mojt metapackage is a native Port. Its source manifest and payload are
developed in the main source tree. The published channel contains the signed
catalog, and each version has an exact native archive. External programs and
resources named in the manifest are installed as ordinary Ports, with their own
package records and manuals.

## Publish a package

Build the exact release from a trusted source checkout:

```sh
mbt package port --manifest ports/mojt-sway/manifest.toml --output mojt-sway-package
```

The manifest uses the native artifact spec, with its payload in the sibling
`payload/` directory. The `metadata.ports` list declares package selectors from
the installed System's pinned Nixpkgs source. `provides.commands` exports
executables under `payload/bin/`. The first implementation accepts regular
files and directories with no install hooks or nested native dependencies.
Programs and data-only packages from Nixpkgs are both supported.

Create a repository configuration for the existing signing tool. Set a
monotonically increasing sequence, and retain older package rows when those
releases should remain available. The archive URL must identify the uploaded,
immutable archive, such as a tagged GitHub Release asset.

```toml
format = 1
area = "ports"
name = "mojt-ports"
channel = "stable"
sequence = 1
key = "publisher-private.pem"

[[packages]]
archive = "mojt-sway-package/port-mojt-sway-<version>-x86_64-linux-<id>.tar.zst"
url = "https://github.com/OWNER/REPO/releases/download/TAG/ARCHIVE"
```

```sh
mbt repo prepare --config ports-repository.toml --output ports-publication
```

Host the archive at its recorded URL and publish `stable.json` under
`ports/` on the repository publication branch. Keep the private key outside the
source tree and the published metadata. Use the repository administrator's
trusted public key when registering the channel.

## Use a published repository

Configure the Ports channel once, with the actual catalog URL and independently
obtained publisher public key:

```sh
mpm ports repo add mojt-ports --url HTTPS_CATALOG_URL --key-file publisher-public.pem
mpm ports repo update mojt-ports
mpm ports install mojt-sway
mpm ports list
```

MPM reads the accepted catalog snapshot and checks the signed archive binding.
Each metapackage wish owns the dependency wishes for its selected release.
Repeated installs preserve accepted references. An explicit metapackage upgrade
can change the dependency wishes, and removal releases that metapackage's own
wishes. Other installation wishes and explicit selections remain independent.

`mpm ports path NAME` prints the output path of an active Nix Port. Programs
can use this for resources such as fonts and graphics drivers. Shell commands
and manuals use the normal active Ports profile.
