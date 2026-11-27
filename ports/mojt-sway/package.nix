# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
{
  lib,
  runCommand,
  runtimeShell,
  makeWrapper,
  makeFontsConf,
  dbus,
  dejavu_fonts,
  fontconfig,
  kitty,
  mesa,
  noto-fonts,
  sway,
  swaybg,
  waybar,
}:

let
  fonts = makeFontsConf {
    fontDirectories = [ dejavu_fonts noto-fonts ];
    includes = [ "${fontconfig.out}/etc/fonts/conf.d" "/etc/fonts/conf.d" ];
  };
in
runCommand "mojt-sway-0.1.3"
  {
    nativeBuildInputs = [ makeWrapper ];
    meta = {
      description = "Mojt Sway session with Waybar and Kitty";
      license = lib.licenses.gpl2Only;
      platforms = [ "x86_64-linux" ];
      mainProgram = "mojt-sway";
    };
  }
  ''
    session="$out/share/mojt-sway"
    mkdir -p "$session" "$out/bin"
    cp ${./mojt_logo.png} "$session/mojt_logo.png"
    cp ${./waybar.jsonc} "$session/waybar.jsonc"
    cp ${./waybar.css} "$session/waybar.css"
    cp ${./kitty.conf} "$session/kitty.conf"
    ln -s ${sway}/share/man "$out/share/man"

    substitute ${./sway.conf} "$session/sway.conf" \
      --replace-fail @kitty@ ${lib.getExe kitty} \
      --replace-fail @session@ "$session"

    # Sway passes its bar ID as arguments to this executable.
    makeWrapper ${lib.getExe waybar} "$session/waybar" \
      --add-flags "--config $session/waybar.jsonc --style $session/waybar.css"

    makeWrapper ${lib.getExe sway} "$session/sway" \
      --add-flags "--config $session/sway.conf" \
      --prefix PATH : ${lib.makeBinPath [ sway swaybg ]} \
      --run 'export MANPATH="'"$out"'/share/man:''${MANPATH-}"' \
      --run 'export TERMINFO_DIRS="${kitty.terminfo}/share/terminfo:''${TERMINFO_DIRS-}"' \
      --set-default FONTCONFIG_FILE "${fonts}" \
      --set-default LIBGL_DRIVERS_PATH "${mesa}/lib/dri" \
      --set-default __EGL_VENDOR_LIBRARY_DIRS "${mesa}/share/glvnd/egl_vendor.d"

    substitute ${./mojt-sway.sh} "$out/bin/mojt-sway" \
      --replace-fail @shell@ ${runtimeShell} \
      --replace-fail @sway@ "$session/sway" \
      --replace-fail @dbus@ ${dbus}
    chmod 0755 "$out/bin/mojt-sway"
  ''
