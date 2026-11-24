<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Signed Base repository

A native repository distributes complete Mojt Base packages independently of Nix.
GitHub Releases can host the archives; a signed JSON document in Git supplies the
channel catalog. MPM uses ordinary HTTPS and does not need the GitHub API, an
account, a token, Git or `gh` on the target. Ports continue to use their configured
provider. This prototype supports Mojt Base (`mojt`), `x86_64-linux`, and one finite
release catalog per named source. System/Kernel repository publication is not yet
connected to this publisher.

## Tools and ownership

MPM belongs to System. MBT is an optional System component. Python, the retained
OpenSSL command and archive helpers belong to System; Base contains none of these
management dependencies. A compiler belongs to an explicitly selected build
environment, not Base. The publishing host needs Python 3.11+, OpenSSL 3+, zstd
and MBT. Signing and publication do not install or activate the package.

New System exports made with `mojt-system-prepare.py --step 12` include
`openssl.bin` from the pinned Nixpkgs source, in addition to the step-11 roles.
The assembler retains `libexec/mpm/bin/openssl` for MPM and exposes the ordinary
`openssl` command. Existing exports keep their declared roles. Installed MPM
requires the retained helper; it does not substitute an executable from Ports.
A checkout on a normal build host uses the host's OpenSSL command.

## Register, refresh, install

Obtain the publisher's Ed25519 **public** PEM key through a trusted channel and
check its fingerprint independently. Register its exact metadata URL and key as
administrator; replace the example URL and key path with your publisher's values:

```sh
mpm source add mojt-base \
  --url https://raw.githubusercontent.com/OWNER/REPO/main/repository/base/stable.json \
  --key-file /protected/mojt-base-public.pem
mpm source update mojt-base
mpm source show mojt-base
mpm base install --source mojt-base --dry-run
mpm base install --source mojt-base
mpm base status
```

Registration reads no network data. `update` downloads **one** signed metadata
file, authenticates it, validates its catalog/offers/descriptors and atomically
adopts the complete snapshot. It does not download package bodies or change an
installation. Installation uses the accepted snapshot without an implicit
refresh. The existing resolver selects the newest declared stable release;
`--release mojt@=0.2.1-r1` selects an exact retained catalog release. Unknown
compatibility is checked against the actual target during boot preparation;
a publisher signature is not a boot-compatibility claim.

`install` imports the selected package, adds approved missing regular defaults
and prepares a boot entry. It leaves running and next boot unchanged. To install,
prepare and select next boot in one ordinary flow:

```sh
mpm source update mojt-base
mpm base upgrade --source mojt-base --dry-run
mpm base upgrade --source mojt-base
mpm base status
```

Review the concrete selection change at the prompt, then reboot when ready.
Neither command reboots automatically. Base selection preserves the selected
System and Kernel, with compatibility checked during preparation. Existing
`/etc` files and `/var` survive. No extra mandatory `stage` is needed.
Preview validates catalog/installation metadata; boot compatibility is checked
when preparing the actual package.

Advanced callers can still supply `--expected-id`, `--archive-sha256`,
`--snapshot`, `--sources-root` and `--cache-root`. A supplied encoding must match
the selected catalog release. A historical snapshot must remain authorized by
the currently registered source/key. Offline `--disk-root` installation and
`--content-only` retain their content-only semantics. The local-file interfaces
continue to work without repository configuration.

## Publisher configuration

Create an Ed25519 signing key with standard OpenSSL, under a private directory.
Keep and back up the private key on the publishing host; never commit it or copy
it into packages, VM images or CI artifacts. For example:

```sh
install -d -m 700 "$HOME/.config/mojt"
umask 077
openssl genpkey -algorithm ED25519 -aes-256-cbc \
  -out "$HOME/.config/mojt/base-signing.pem"
```

The encrypted key's passphrase is read by OpenSSL. `repo prepare` invokes
OpenSSL to derive the public key and sign, so it can request the passphrase
twice. It accepts an executor-owned regular private key without group/other
permissions. The key path is explicit in the publishing configuration.

Create a TOML file outside the source checkout, replacing the paths/URL:

```toml
format = 1
name = "mojt-base"
channel = "stable"
sequence = 1
key = "/absolute/private/base-signing.pem"

[[packages]]
archive = "/absolute/build/package/EXACT_NATIVE_BASE.tar.zst"
url = "https://github.com/OWNER/REPO/releases/download/base-0.2.1-r1/EXACT_NATIVE_BASE.tar.zst"
```

Package/key paths are absolute or relative to this configuration file. List every
release offered in this snapshot, up to 64 packages; it is a complete catalog,
not an append instruction. `packages = []` can withdraw all current offers.
Keep one exact build per release. Increase `sequence`
for every metadata change, including withdrawal. Do not overwrite an already
published release archive. Keep older assets available for retained snapshots.
Run from a checkout root, or use installed `mbt`:

```sh
python3 -I -B tools/mbt repo prepare \
  --config /absolute/repository.toml --output /absolute/new-publication
```

The new output directory contains `stable.json` (or `CHANNEL.json`), `public.pem`
and `publication.json`. The last file lists exact local archive paths, public
URLs, compressed sizes/SHA256 and the public PEM fingerprint. It is a publisher
receipt, not client authority. Archives are read/verified and referenced, not
copied into the output. Private key contents are never exported. The output must
not already exist; a failed new output is not a published channel.

Upload the exact archives as GitHub Release assets first, using ordinary `gh`
or GitHub's UI. A draft permits checking all assets before publishing the release.
Then commit the signed channel file to the metadata path and distribute the
public key/fingerprint. Metadata must not advertise an unavailable archive.
Use a separate Base tag (for example `base-0.2.1-r1`); MPM never asks GitHub for
its repository-wide “latest release”. Re-sign a new snapshot to change URLs.
An existing Base build/package can be published without recompiling it.

## Authentication and failure behavior

The signature is Ed25519 over the bytes `Mojt native repository v1\n` followed
by the canonical `mpm_requests.canonical(repository)` JSON bytes, without a
trailing newline. The signed object contains its name, channel, positive sequence,
existing release catalog, acquisition-map envelope and the external descriptor
objects keyed by their logical relative paths. The JSON transport envelope is
`{format: "mojt-signed-repository-v1", repository: {...}, signature: "BASE64"}`.
SHA256 binds the exact compressed archive; it does not replace the signature.

The owner's protected `mojt-https-source-policy-v1` authorizes a URL, public key,
name/channel and compressed/expanded limits (the registration shortcut chooses
1 GiB/4 GiB). Source location is `{kind: "https-repository", url: ...}` and trust
is `{kind: "ed25519", policy: POLICY_ID}`. A local source snapshot binds the
registered source/policy and retains the signed envelope in `provider_snapshot`.
The signed payload format is `mojt-native-repository-v1`. The
[source/cache wire contracts](formats/draft-v1/sources-cache.md) retain their
existing local-directory variant.

HTTPS certificate verification stays enabled. Initial URLs must use HTTPS,
without credentials, query, fragments, encoded paths or traversal. Redirects must
also use HTTPS; CDN redirect query strings are permitted. Metadata is bounded by
the existing metadata cap; archive size and expansion are capped by owner policy.
Only the first signed archive URL is attempted. There is no hidden alternate
version/provider fallback. Archive acceptance uses the existing hash, descriptor,
archive-path and native-payload validation before cache/import publication.

A failed signature, TLS transfer, size/hash check or metadata refresh preserves
the last good snapshot. A lower refresh sequence or changed content at the same
sequence is rejected. Already accepted exact older snapshots remain available
for deliberate pins/rollback. Changing URL/key/policy requires explicit
`source add --replace`, clears current metadata and invalidates old authorization.
Cache acquisition can reuse accepted metadata/archive bytes with the server
offline; it still checks authorization and cached bytes. A successful signature
is reused only within the current command, not as a durable bypass.

This first trust model has no automatic expiration, key rotation/revocation feed,
threshold signing or independent freshness service. A new registration cannot
know a publisher's newest sequence, and an attacker can withhold a newer signed
snapshot. Manual key replacement is an owner operation. Do not describe this as
TUF or as authenticated solely by an archive hash.
