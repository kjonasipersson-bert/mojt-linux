<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Read-only libc inventory

This is an optional diagnostic for an unknown reference or a concrete runtime
problem. The [runtime ownership map](mpm-libc-policy.md) describes normal Base,
System and Ports linkage; unchanged Nix imports do not require a fresh process
inventory. Its DNS and locale probes exercise selected shared configuration/data
boundaries, not a general proof of libc ABI compatibility.

Run `tools/mojt-libc-inventory.py` **inside the running Mojt guest**, not on its
Debian host. An older VM is useful: the report identifies its Base, System and
Kernel. Its observations apply to those versions, not automatically to another
machine or a newer generation.

The script is standalone Python 3.11+ and may be copied as a single file. It
does not require a current checkout, native-v2 boot records, modern MPM or a new
System installation. Copy it into the guest, for example as
`/tmp/mojt-libc-inventory.py`, then run:

```sh
python3 -I -B /tmp/mojt-libc-inventory.py > /tmp/mojt-libc-inventory.json
```

Progress goes to stderr; stdout is the JSON report. Root access may be needed
to read PID 1's mappings. No Nix operations, downloads, installations, service
starts or selection changes are performed. Only the report redirection writes
a file. Probes exercise existing account lookup, localhost lookup and a System
UTF-8 locale in short-lived processes. They do not authenticate or start SSH.

Optional external name resolution requires network/DNS access:

```sh
python3 -I -B /tmp/mojt-libc-inventory.py --dns-name cache.nixos.org \
  > /tmp/mojt-libc-inventory.json
```

## Report contents and limits

The report records selected Base shell/core tools, PID 1, Python, System Bash,
login/sshd and active Git/Neovim paths. Missing optional programs are recorded
and do not prevent the rest of the inventory.

- `interpreter` comes from the executable's ELF PT_INTERP, even without binutils.
- `loader_list` uses that exact loader's `--list`, rather than whichever `ldd`
  happens to be on PATH. The program's entry point is not run.
- If `readelf` is available, `dynamic` records NEEDED/RPATH/RUNPATH and
  `required_glibc_versions` lists GLIBC version needs, excluding definitions.
  No tools are installed automatically if it is unavailable.
- `mapped_libraries` records observed libc, loader, NSS and PAM mappings in PID 1
  and the inventory's Python process. This differs from dependency resolution
  for another program; it does not prove every service loaded the same modules.
- `probes` records exit status/errors for Base and System identity/localhost
  lookup, System UTF-8 locale, and optional DNS. Account contents are omitted.

Loader inspection and probes use a clean environment; the report does not model
custom LD_PRELOAD/LD_LIBRARY_PATH or service-specific settings. It does not scan
all store objects or generations, validate every ELF/plugin, test PAM login,
prove compatibility with a replacement Base, or change the
[declared compatibility policy](system-manifest.md#base-abi-requirements).
