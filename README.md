<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Mojt Linux

```text
       |  |  |
   +---+--+--+---+
 --|             |--
 --|   .-----.   |--
 --|  (  @@@  )  |--
   |   '-----'   |
   |   |||||||   |
   +---+--+--+---+
       |  |  |
```

**A small Linux base. Independently managed system components and applications.**

*Mojt* is an engineering-slang word from Lund, Sweden, roughly meaning a gadget
or contraption. Mojt is an experimental Linux distribution inspired by the BSD
separation of a base operating system and Ports.

## Start here

- [Mojt Handbook](doc/handbook/README.md): concepts, MPM/MBT commands and the
  filesystem layout.
- [Architecture](docs/architecture.md): layer boundaries, boot selection and
  persistent state.
- [Documentation index](docs/README.md): reference material, proposals and test
  reports.
- [Roadmap](docs/roadmap.md): current capabilities and future work.
- [Manifesto](docs/manifesto.md): design goals.

## System model

| Area | Unit of change |
| --- | --- |
| Base | Complete immutable glibc-based Unix userspace releases |
| System | Versioned service/tool profiles and retained runtime dependencies |
| Kernel | Exact Kernel builds with matching module trees, selected independently |
| Ports | Parallel application versions with explicit active choices and wishes |
| Persistent state | Machine configuration, service data, homes and local files |

Native-v2 boot entries bind exact compatible Base, System and Kernel choices.
Installing or selecting code does not restore earlier configuration or user data.
The running root is writable; selected release content stays read-only. See the
[filesystem chapter](doc/handbook/part-iii/filesystem-layout.md).

## On an installed Mojt system

```sh
mpm system status
mpm base status
mpm kernel status
mpm ports list
mpm ports install neovim
man nvim
```

A live System installation prepares a boot entry without selecting it. Use
`mpm system activate` to review and choose next boot, then reboot deliberately.
Base/Kernel installation currently requires explicit preparation. Full content
audits are opt-in with `--verify`. See the [MPM chapter](doc/handbook/part-i/mpm.md)
for native package inputs, exact IDs, offline imports and compatibility limits.

MPM manages acquisition, installed content and choices. [MBT](doc/handbook/part-i/mbt.md)
handles explicit builds, packaging and fresh-image bootstrap using retained
inputs. Importing binaries or assembling images is not complete source self-hosting.

## Development

The tools target Linux x86-64. Host workflows use Bash, Python 3.11+, `curl`,
`tar`, `zstd` and standard Unix tools; individual build/VM guides specify their
additional dependencies. Mount, chroot and disk tests need the relevant Linux
privileges. Base itself has no Python runtime requirement; System supplies MPM's
management runtime.

Base has a pinned source builder; Nix remains the binary provider for System
and Ports. Neither provider defines Mojt's area or release model. The
[signed Base repository prototype](docs/native-repository.md) joins native
publication, HTTPS acquisition and the ordinary MPM install/upgrade flow.
A general production installer, broader native repository coverage and complete
source self-hosting remain development work.

[Working instructions](AGENTS.md) govern changes and documentation. The
[Handbook website guide](docs/handbook-web.md) describes local mdBook builds and
the `handbook.mojt.org` hosting configuration.

## Project layout

| Path | Contents |
| --- | --- |
| `bootstrap/` | Host-side bootstrap backends |
| `manifests/` | Pinned inputs and build/package manifests |
| `tools/` | Management, build, packaging and bootstrap tools |
| `tests/` | Automated tests and acceptance helpers |
| `doc/handbook/` | User Handbook |
| `docs/` | Technical references and proposals |
| `docs/reports/` | Historical development and test records |

## License and copyright

Mojt-owned code and documentation are **GPL-2.0-only**, Copyright (C) 2026
**Jonas Persson**. See [LICENSE](LICENSE). Included packages and other upstream
components retain their own licenses and copyright notices.
