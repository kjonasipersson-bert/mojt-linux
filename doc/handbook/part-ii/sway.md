<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# An optional Sway desktop

`mojt-sway` packages a Wayland session with Sway, Waybar, Kitty and the Mojt
wallpaper. Waybar shows workspaces, network status, battery status when a
battery is present, and the date and time. X11 applications require XWayland,
which is disabled in the supplied configuration.

## Install the session

Use a Mojt x86-64 installation with the System Nix tools, working Internet
access, kernel modesetting and a local login managed by systemd-logind. From a
trusted checkout, run these commands as an administrator in the repository root:

```sh
(
  set -eu
  nixpkgs=$(sed -n 's/^path = "\(.*\)"$/\1/p' /run/mojt-system/ports.toml)
  test -f "$nixpkgs/default.nix"
  install -d -m 0755 /var/lib/mojt/mojt-sway
  drv=$(nix-instantiate ports/mojt-sway --argstr nixpkgs "$nixpkgs")
  nix-store --realise "$drv" --add-root /var/lib/mojt/mojt-sway/result \
    --indirect --option max-jobs 1
)
```

The command uses the installed System's pinned Nixpkgs source. Use the same
Nixpkgs pin and repository revision to reproduce the build on another machine.
Nix uses the configured cache for available dependencies. `--option max-jobs 1`
allows local builds for this command, including dependencies if their substitutes
are unavailable. The result link retains the session in the persistent Nix store
and gives it a dedicated command path. The runtime closure is about 2 GiB with
the tested pin. Paths already in the store are shared.

## Start from the console

Log in as an ordinary user on a local virtual terminal and run:

```sh
/var/lib/mojt/mojt-sway/result/bin/mojt-sway
```

| Shortcut | Action |
| --- | --- |
| Super+Enter | Open Kitty |
| Super+1–9 | Switch workspace |
| Super+Shift+1–9 | Move a window to a workspace |
| Super+arrow keys | Move focus |
| Super+Shift+arrow keys | Move the focused window |
| Super+Shift+Q | Close the focused window |
| Super+Shift+C | Reload Sway configuration |
| Super+Shift+E | Exit to the console |

The wallpaper is fitted to each output. The session provides Mesa drivers and
a DejaVu font fallback. It reuses an existing D-Bus session bus or starts one
with the packaged configuration. If Sway cannot open graphics or input devices,
check `XDG_SESSION_ID` and `XDG_RUNTIME_DIR` from the local login. An administrator
can inspect the session with `loginctl list-sessions` over SSH. Waybar indicates
local network status.

## Set the Wayland keyboard layout

Create `~/.config/mojt-sway/config` as the user running Sway. For a Swedish
keyboard, add:

```text
input type:keyboard xkb_layout se
```

Use `gb` for a British keyboard. This is Sway's XKB layout and can be set
independently of the text console layout. The session reads the file after its
packaged defaults, and installing the package never writes to the file.

## Remove the session

Exit Sway and run this command as an administrator:

```sh
rm /var/lib/mojt/mojt-sway/result
```

Removing the result link releases this reference to the package. User
configuration stays in the home directory.
