<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# GitHub Base repository: first publication and short test

This is an acceptance procedure, not an announcement of an existing signed
channel. It reuses the already built Base 0.2.1 package. No Base/Kernel rebuild,
physical-machine update or return-boot round is required. Use the reviewed
`feature/github-base-repository` revision. The current implementation/trust
limits are in [Signed Base repository](../native-repository.md).

## 1. Debian host: prepare the publication

Work in **`$HOME/mojt-base-src`**. The existing build report must be at
`$HOME/mojt-base-021-result/result.json`. GitHub CLI must already be authenticated
as an account permitted to publish to `kjonasipersson-bert/mojt-linux`.
Do not send the private key or its passphrase in chat.

```bash
cd "$HOME/mojt-base-src"
git fetch origin feature/github-base-repository
git switch --detach origin/feature/github-base-repository
```

The following block creates a new lab, creates a key only if absent, and prepares
metadata. OpenSSL requests a passphrase for a new key and again while signing.
It does not upload anything. The source tree and old build remain unchanged.

```bash
bash <<'MOJT_PUBLICATION'
set -euo pipefail
cd "$HOME/mojt-base-src"
LAB="$HOME/mojt-repository-test"
test ! -e "$LAB"
install -d -m 700 "$LAB" "$HOME/.config/mojt"
KEY="$HOME/.config/mojt/base-signing.pem"
if [ ! -e "$KEY" ]; then
  (umask 077; openssl genpkey -algorithm ED25519 -aes-256-cbc -out "$KEY")
fi
python3 - "$HOME/mojt-base-021-result/result.json" "$LAB" "$KEY" <<'PY'
import json
from pathlib import Path
import sys
build,lab,key=map(Path,sys.argv[1:])
package=Path(json.loads(build.read_text())['package']['path']).resolve(strict=True)
url='https://github.com/kjonasipersson-bert/mojt-linux/releases/download/base-0.2.1-r1/'+package.name
text='format = 1\nname = "mojt-base"\nchannel = "stable"\nsequence = 1\n'
text+='key = '+json.dumps(str(key))+'\n[[packages]]\n'
text+='archive = '+json.dumps(str(package))+'\nurl = '+json.dumps(url)+'\n'
(lab/'repository.toml').write_text(text)
PY
python3 -I -B tools/mbt repo prepare \
  --config "$LAB/repository.toml" --output "$LAB/publication-1"
sha256sum "$LAB/publication-1/public.pem"
MOJT_PUBLICATION
```

Expect `stable.json`, `public.pem` and `publication.json`. Keep the printed
public-key fingerprint for the guest check. The private key remains under
`$HOME/.config/mojt`, outside the lab/publication/source directories.

## 2. Publish the exact archive, then the channel

Still on Debian, in **`$HOME/mojt-base-src`**. This block makes the public
`base-0.2.1-r1` release from a draft, then publishes metadata to a separate
`repository-base-stable` branch. It does not update `main`, merge the code PR,
overwrite an existing release, or force-push a branch. Use this first-publication
procedure once. The signed URL must match the actual asset filename.

```bash
bash <<'MOJT_PUBLISH'
set -euo pipefail
cd "$HOME/mojt-base-src"
LAB="$HOME/mojt-repository-test"
REPO=kjonasipersson-bert/mojt-linux
REVISION=$(git rev-parse HEAD)
PACKAGE=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["assets"][0]["file"])' \
  "$LAB/publication-1/publication.json")
gh release create base-0.2.1-r1 "$PACKAGE" --repo "$REPO" \
  --target "$REVISION" --title 'Mojt Base 0.2.1-r1' \
  --notes 'Whole source-built Mojt Base 0.2.1 package for x86_64.' --draft
gh release view base-0.2.1-r1 --repo "$REPO"
gh release edit base-0.2.1-r1 --repo "$REPO" --draft=false

git worktree add --detach "$LAB/channel-checkout" "$REVISION"
cd "$LAB/channel-checkout"
mkdir -p repository/base
cp "$LAB/publication-1/stable.json" repository/base/stable.json
cp "$LAB/publication-1/public.pem" repository/base/public.pem
git add repository/base/stable.json repository/base/public.pem
git commit -m 'Publish signed Base stable catalog sequence 1'
git push origin HEAD:refs/heads/repository-base-stable
MOJT_PUBLISH
```

If an operation fails, stop and retain the lab. In particular, do not retry a
published release with replacement assets. Later catalog changes need a new
sequence and a normal update on the channel branch; keep the same private key.

## 3. Short host-side test without changing the host OS

Run on Debian, from **`$HOME/mojt-base-src`**, as the ordinary user. This tests
real GitHub HTTPS, signatures, metadata retention and exact native cache import.
It does not install into Debian or change any boot selection.

```bash
bash <<'MOJT_FETCH'
set -euo pipefail
cd "$HOME/mojt-base-src"
LAB="$HOME/mojt-repository-test"
MPM=(python3 -I -B tools/mpm)
"${MPM[@]}" source add mojt-base --root "$LAB/sources" \
  --url https://raw.githubusercontent.com/kjonasipersson-bert/mojt-linux/repository-base-stable/repository/base/stable.json \
  --key-file "$LAB/publication-1/public.pem" -y
"${MPM[@]}" source update mojt-base --root "$LAB/sources" -y
"${MPM[@]}" source show mojt-base --root "$LAB/sources"
readarray -t EXACT < <(python3 - "$LAB/publication-1/stable.json" <<'PY'
import json,sys
c=json.load(open(sys.argv[1]))['repository']['catalog']['candidates'][0]
print(c['artifact']);print(c['integrity']['sha256'])
PY
)
"${MPM[@]}" cache fetch "${EXACT[0]}" --source mojt-base --kind base \
  --archive-sha256 "${EXACT[1]}" --sources-root "$LAB/sources" --root "$LAB/cache" -y
"${MPM[@]}" cache fetch "${EXACT[0]}" --source mojt-base --kind base \
  --archive-sha256 "${EXACT[1]}" --sources-root "$LAB/sources" --root "$LAB/cache" -y
MOJT_FETCH
```

Expect one metadata download, the declared Base release, `copied: true` on first
fetch, and `copied: false`/`changed: false` on the repeat. Report the first error,
or the final cache result and public-key fingerprint. No new build is needed.

## 4. Optional complete VM update

This is the target-side acceptance after publication. The previous System export
has no repository crypto helper; a new export/image is explicit. Use the retained
Base **0.2.0** build only to start the disposable VM, then install the published
0.2.1 through ordinary MPM. No Void compatibility or physical install is involved.

From Debian, enter `distrobox enter mojt-mpm-nix`, then run as the ordinary user:

```bash
cd "$HOME/mojt-base-src"
python3 -I -B tools/mojt-system-prepare.py --step 12 \
  --output "$HOME/mojt-repository-system" --dry-run
python3 -I -B tools/mojt-system-prepare.py --step 12 \
  --output "$HOME/mojt-repository-system" -y
exit
```

This imports binary System outputs from the exporter's explicit retained source
pin, including OpenSSL. It does not compile Base or a Kernel. Back on Debian,
in **`$HOME/mojt-base-src`**, reuse the saved Kernel locator with the new export:

```bash
cd "$HOME/mojt-base-src"
python3 - <<'PY'
import hashlib,json
from pathlib import Path
home=Path.home();lab=home/'mojt-repository-test';payload=home/'mojt-repository-system'
seed=json.loads((home/'mojt-normal-boot.CY1x3d/vm/input-check.json').read_text())
seed['system']['path']=str(payload)
seed['system']['record_sha256']=hashlib.sha256((payload/'system.json').read_bytes()).hexdigest()
(lab/'input-check.json').write_text(json.dumps(seed,indent=2)+'\n')
PY
TEST=(python3 -I -B tests/prepare-source-base-boot.py
  --from-check "$HOME/mojt-repository-test/input-check.json"
  --base-build "$HOME/mojt-base-result" --with-build-tools
  --output "$HOME/mojt-repository-vm")
"${TEST[@]}" --check-inputs
"${TEST[@]}"
QEMU_MEMORY_MIB=4096 bash "$HOME/mojt-repository-vm/image/run-qemu.sh"
```

The helper verifies the actual inputs and creates a new image only. It asks for a
VM root password through ordinary bootstrap. In the **new Mojt VM**, log in as
root. Download the public key and compare its SHA256 with the trusted Debian
output before registering it:

```sh
curl -fL https://raw.githubusercontent.com/kjonasipersson-bert/mojt-linux/repository-base-stable/repository/base/public.pem \
  -o /root/mojt-base-public.pem
sha256sum /root/mojt-base-public.pem
```

After the fingerprints match:

```sh
printf 'keep me\n' >/etc/mojt-repo-check
printf 'keep me\n' >/var/mojt-repo-check
mpm source add mojt-base \
  --url https://raw.githubusercontent.com/kjonasipersson-bert/mojt-linux/repository-base-stable/repository/base/stable.json \
  --key-file /root/mojt-base-public.pem
mpm source update mojt-base
mpm base upgrade --source mojt-base --dry-run
mpm base upgrade --source mojt-base
mpm base status
reboot
```

Approve the missing defaults and proposed next-boot selection. Relaunch the same
VM image on Debian with the QEMU command above, then check in **Mojt**:

```sh
cat /usr/lib/os-release
getconf GNU_LIBC_VERSION
getent services https/tcp
getent protocols tcp
cat /etc/mojt-repo-check /var/mojt-repo-check
mpm base status
systemctl --failed --no-pager
```

Expected: Base 0.2.1/glibc 2.44, both markers retained, IANA lookups succeed,
running/next boot agree, System/Kernel unchanged and no failed units. That is the
single new acceptance; a return round is unnecessary here.

## Automated evidence and remaining boundary

Local tests use real OpenSSL Ed25519 keys, a real TLS server trusted through a
test CA, the publisher, source CLI/resolver and native cache. They exercise bad
signatures/keys, TLS errors, HTTP redirects, transfer bounds, corrupted archives,
sequence rollback/equivocation, key/location reconfiguration and offline cache
reuse. A private user namespace also exercises real Base content import; the
executor filesystem does not support POSIX ACLs, so this is not ACL evidence.
System fixtures check step-12 retained-helper delivery and unchanged earlier
roles. These are not a real published GitHub or VM acceptance. Record those
results separately after running the corresponding sections above.
