{ pkgs ? import <nixpkgs> { } }:
let
  mach-nix = import (builtins.fetchGit {
    url = "https://github.com/DavHau/mach-nix";
    ref = "refs/tags/3.5.0";
  }) { };
  bearCtl = mach-nix.buildPythonApplication {
    pname = "bearctl";
    src = ./.;
    version = "0.1.0";
    requirements = ''
      dasbus
      click
      pygobject
      pipewire_python
    '';
  };
in pkgs.writeShellScriptBin "bearctl" ''
  PATH=$PATH:${
    pkgs.lib.makeBinPath [ pkgs.pipewire ]
  } exec ${bearCtl}/bin/bearctl "$@"
''

