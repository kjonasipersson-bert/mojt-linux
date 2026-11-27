# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
{ nixpkgs }:
let
  pkgs = import (builtins.toPath nixpkgs) {
    system = "x86_64-linux";
    config = { };
    overlays = [ ];
  };
in
pkgs.callPackage ./package.nix { }
