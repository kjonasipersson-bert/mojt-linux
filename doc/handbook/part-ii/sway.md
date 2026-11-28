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

Use an x86-64 Mojt installation with native Ports support and a configured
[Mojt Ports repository](https://github.com/kjonasipersson-bert/mojt-linux/blob/main/docs/ports-repository.md). The repository
provides the session files, theme and command. MPM acquires Sway, swaybg,
Waybar, Kitty, fonts and graphics resources through the System's pinned Ports
provider. Install as an administrator:

```sh
mpm ports install mojt-sway
mpm ports list
```

MPM records the metapackage and its package wishes in one Ports transaction.
The component packages appear individually in the list, with their normal
installation and activation rules.

If you used the standalone Sway prototype, remove its administrator-created
command and manual links after verifying the active Ports command and manuals.

## Start from the console

Log in as an ordinary user on a local virtual terminal. The start script
uses Sway, swaybg, Waybar and Kitty from the session's `PATH`. Run:

```sh
mojt-sway
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

Select **Exit** on the status bar and confirm to return to the console. From
Kitty, `swaymsg exit` exits immediately. Run `man sway` for the command manual
or `man 5 sway` for configuration. Kitty defaults to DejaVu Sans Mono at
13 points and reads `~/.config/kitty/kitty.conf` for user overrides. MPM's
ordinary manual lookup also supplies `man kitty`.

The wallpaper is fitted to each output. Graphical applications use the fonts
and graphics drivers configured in the login environment. If your installation
requires custom settings such as `FONTCONFIG_FILE` or `LIBGL_DRIVERS_PATH`,
set them before starting the session. Applications that need a D-Bus session
bus use the bus provided by the login environment. If Sway cannot open graphics
or input devices, check `XDG_SESSION_ID` and `XDG_RUNTIME_DIR` from
the local login. An administrator can inspect the session with
`loginctl list-sessions` over SSH. Waybar indicates local network status.

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
mpm ports remove mojt-sway
```

Removing the metapackage releases its dependency wishes. A package with a
separate installation wish or exact active selection stays installed.
User configuration is stored in the home directory.
