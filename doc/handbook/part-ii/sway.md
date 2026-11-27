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
  if [ ! -d /usr/local/bin ]; then
    install -d -m 0755 /usr/local/bin
  fi
  result=/var/lib/mojt/mojt-sway/result
  command_link=/usr/local/bin/mojt-sway
  target=$result/bin/mojt-sway
  if [ -e "$command_link" ] || [ -L "$command_link" ]; then
    if [ "$(readlink "$command_link" || true)" != "$target" ]; then
      echo "$command_link already exists with a different target" >&2
      exit 1
    fi
  fi
  drv=$(nix-instantiate ports/mojt-sway --argstr nixpkgs "$nixpkgs")
  nix-store --realise "$drv" --add-root "$result" \
    --indirect --option max-jobs 1
  if [ ! -L "$command_link" ]; then
    ln -sT "$target" "$command_link"
  fi
)
```

The command uses the installed System's pinned Nixpkgs source. Use the same
Nixpkgs pin and repository revision to reproduce the build on another machine.
Nix uses the configured cache for available dependencies. `--option max-jobs 1`
allows local builds for this command, including dependencies if their substitutes
are unavailable. The result link retains the session in the persistent Nix store
and exposes `mojt-sway` through `/usr/local/bin`. The runtime closure is about
2 GiB with the tested pin. Paths already in the store are shared.

## Start from the console

Log in as an ordinary user on a local virtual terminal and run:

```sh
mojt-sway
```

On older System builds, add `/usr/local/bin` to the login shell's `PATH` if
needed. Run `export PATH="$PATH:/usr/local/bin"` for the current shell, or add
that line after the System login hook in `/etc/profile` for future logins.

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

For GPU rendering, an administrator can grant the account access to
[DRM render nodes](../part-iii/hardware.md#82-device-detection) with
`usermod -aG render LOGIN_NAME`. Log out and back in to apply the new group
membership. If Mesa still reports permission denied, check the node's owner
and mode with `ls -l /dev/dri`.

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
rm /usr/local/bin/mojt-sway /var/lib/mojt/mojt-sway/result
```

Removing the result link releases this reference to the package. User
configuration stays in the home directory.
