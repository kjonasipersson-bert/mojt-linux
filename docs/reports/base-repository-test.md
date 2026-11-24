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
`$HOME/mojt-base-021-result/result.json`. Publish with an account permitted to create a GitHub Release in
`kjonasipersson-bert/mojt-linux`; the GitHub website is sufficient.
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

Still on Debian, in **`$HOME/mojt-base-src`**. On the GitHub website, create a
release tagged `base-0.2.1-r1`, upload the exact archive listed in
`$HOME/mojt-repository-test/publication-1/publication.json`, and publish it.
Do not replace an existing published asset. No `gh` command is required.

After the archive is publicly downloadable at the URL in the signed metadata,
publish the already signed channel files with ordinary Git:

```bash
bash <<'MOJT_PUBLISH'
set -euo pipefail
cd "$HOME/mojt-base-src"
LAB="$HOME/mojt-repository-test"
REPO=kjonasipersson-bert/mojt-linux
REVISION=$(git rev-parse HEAD)
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
"${MPM[@]}" base repo add mojt-base --root "$LAB/sources" \
  --url https://raw.githubusercontent.com/kjonasipersson-bert/mojt-linux/repository-base-stable/repository/base/stable.json \
  --key-file "$LAB/publication-1/public.pem" -y
"${MPM[@]}" base repo update mojt-base --root "$LAB/sources" -y
"${MPM[@]}" base repo show mojt-base --root "$LAB/sources"
readarray -t EXACT < <(python3 - "$LAB/publication-1/stable.json" <<'PY'
import json,sys
c=json.load(open(sys.argv[1]))['repository']['catalog']['candidates'][0]
print(c['artifact']);print(c['integrity']['sha256'])
PY
)
"${MPM[@]}" base repo fetch "${EXACT[0]}" --repo mojt-base \
  --archive-sha256 "${EXACT[1]}" --repos-root "$LAB/sources" --root "$LAB/cache" -y
"${MPM[@]}" base repo fetch "${EXACT[0]}" --repo mojt-base \
  --archive-sha256 "${EXACT[1]}" --repos-root "$LAB/sources" --root "$LAB/cache" -y
MOJT_FETCH
```

Expect one metadata download, the declared Base release, `copied: true` on first
fetch, and `copied: false`/`changed: false` on the repeat. Report the first error,
or the final cache result and public-key fingerprint. No new build is needed.

## 4. Existing Mojt VM: install the repository-enabled System tools

Use the already running **Mojt VM**, logged in as root. Keep its current Base,
Kernel, disk and configuration. The ordinary Ports installation has already
acquired this exact OpenSSL output:
`/nix/store/gvglnxscmvx4mh9my0cy0xgi0l1z6l9s-openssl-3.5.9-bin`.
The new System owns its own exact reference; it does not depend on Ports aliases.

Fetch the reviewed commit's source archive into a new directory under
`/var/lib/mojt`, extract it into `source`, and enter that source directory.
From **that Mojt checkout root**, package just a Runtime successor:

```bash
WORK=$(mktemp -d /var/lib/mojt/repository-tools.XXXXXX)
python3 -I -B tools/mbt package system --running --firmware keep \
  --openssl-output /nix/store/gvglnxscmvx4mh9my0cy0xgi0l1z6l9s-openssl-3.5.9-bin \
  --generation system-repository-tools --output "$WORK/kit" >"$WORK/result.json"
```

Then, in the same shell, import that package with installed MPM and prepare it
with the candidate's new management code. This uses normal System APIs and
preserves running/next boot. The selected older manager does not yet authorize
the new helper addition, which is why the retained candidate frontend prepares
this first tooling transition:

```bash
python3 - "$WORK" <<'PYTHON'
import json,subprocess,sys
from pathlib import Path
work=Path(sys.argv[1]);kit=work/'kit'
r=json.loads((work/'result.json').read_text());identifier=r['artifact']
command=['mpm','system','install','--from-file',str(kit/r['generation']),
         '--expected-id',identifier,'--content-only','-y']
for relative in r['dependency_files']:command+=['--dependency-file',str(kit/relative)]
subprocess.run(command,check=True)
profile=Path('/run/mojt-disk/realizations/system')/identifier.removeprefix('sha256:')/'profile'
subprocess.run([sys.executable,'-I','-B',str(profile/'tools/mpm-system'),
                'system','stage','--artifact',identifier,'-y'],check=True)
PYTHON
mpm system activate
```

Choose `system-repository-tools`, review the concrete next-boot change, and
approve it. Reboot and relaunch **the same VM disk** on Debian:

```bash
QEMU_MEMORY_MIB=4096 bash "$HOME/mojt-base-update-test/run-qemu.sh"
```

In **Mojt**, confirm the running System and new public interface:

```sh
mpm system status
mpm base upgrade --help
openssl version
```

Register the same public Base repository under its area. Old unscoped
registrations remain on disk; no automatic migration or private key is needed.
Download the public key and verify the independently recorded fingerprint:

```sh
curl -fL https://raw.githubusercontent.com/kjonasipersson-bert/mojt-linux/repository-base-stable/repository/base/public.pem \
  -o /root/mojt-base-public.pem
printf '%s  %s\n' 02ab200c8be22fbf66a41c3ef165d7effa75559066b09684ffedaac9b8b3b808 /root/mojt-base-public.pem | sha256sum -c -
```

After that check succeeds:

```sh
mpm base repo add mojt-base \
  --url https://raw.githubusercontent.com/kjonasipersson-bert/mojt-linux/repository-base-stable/repository/base/stable.json \
  --key-file /root/mojt-base-public.pem
mpm base update
mpm base upgrade mojt@0.2 --dry-run
mpm base upgrade mojt@0.2
mpm base status
mpm base upgrade --dry-run
systemctl --failed --no-pager
```

Expected: the prepared Base is still 0.2.1, status reports the saved `mojt@0.2`
request, and the last preview follows it without an explicit selector. No extra
Base reboot is needed when this exact Base is already running/selected. System
and Kernel do not change during these Base commands. This checks repository
client delivery and saved-policy reuse, not a new Base version transition.

## Automated evidence and remaining boundary

Local tests use real OpenSSL Ed25519 keys, a real TLS server trusted through a
test CA, the publisher, source CLI/resolver and native cache. They exercise bad
signatures/keys, TLS errors, HTTP redirects, transfer bounds, corrupted archives,
sequence rollback/equivocation, key/location reconfiguration and offline cache
reuse. A private user namespace also exercises real Base content import; the
executor filesystem does not support POSIX ACLs, so this is not ACL evidence.
System fixtures check retained-helper delivery, independent provider references
and unchanged earlier export roles. A local run on 2026-11-24 passed 74 focused
repository, Base flow, System component, dispatcher and adapter tests in a
private root user namespace. A subsequent focused run passed 18 tests with one
unmapped-UID namespace test skipped. Neither run boots the owner's VM. These are not a real published GitHub or VM acceptance. Record those
results separately after running the corresponding sections above.
