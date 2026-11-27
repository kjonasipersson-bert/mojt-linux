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
access, kernel modesetting and a local login managed by systemd-logind.
Use the same repository revision on each machine to install the same session.
From a trusted checkout, run these commands as an administrator in the repository
root:

```sh
source_ref="path:$PWD/ports/mojt-sway"
nix --extra-experimental-features 'nix-command flakes' profile add \
  --max-jobs 1 --profile /nix/var/nix/profiles/mojt-sway "$source_ref"
```

The lock file pins Nixpkgs. Nix uses the configured cache for available
dependencies and can build the Mojt package locally. `--max-jobs 1` allows
builds for this command, including dependencies if their substitutes are
unavailable. The dedicated Nix profile retains the session and its dependencies
in the persistent Nix store. It uses its own command path and leaves MPM's
active Ports and the installed System start-up configuration alone.
The runtime closure is about 2 GiB. Paths already in the store are shared.

## Start from the console

Log in as an ordinary user on a local virtual terminal and run:

```sh
/nix/var/nix/profiles/mojt-sway/bin/mojt-sway
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
a DejaVu font fallback. Check that `loginctl session-status` reports an
active local session if Sway cannot open graphics or input devices. Use
`nmtui` from Kitty to open NetworkManager's text interface on a System that
provides it. Waybar indicates local network status.

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
nix --extra-experimental-features 'nix-command flakes' profile remove \
  --profile /nix/var/nix/profiles/mojt-sway mojt-sway
```

This removes the start command from the active profile. Previous Nix profile
versions can still retain the package, and user configuration stays in the home
directory.
