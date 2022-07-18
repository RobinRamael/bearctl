{ pkgs ? import <nixpkgs> { } }:
let
  mach-nix = import (builtins.fetchGit {
    url = "https://github.com/DavHau/mach-nix";
    ref = "refs/tags/3.4.0";
  }) { };
  pyEnv = mach-nix.mkPython {
    requirements = ''
      ipdb
      pexpect
      ipython
      click
      dasbus
      pulsectl
    '';
    packagesExtra = [
      pkgs.python39Packages.pulsectl
      pkgs.python39Packages.pygobject3
      pkgs.python39Packages.lxml
      pkgs.python39Packages.pytest

    ];
  };
in pkgs.mkShell {
  buildInputs = [pyEnv];
}

# { pkgs ? import <nixpkgs> { } }:
# let
#   mach-nix = import (builtins.fetchGit {
#     url = "https://github.com/DavHau/mach-nix";
#     ref = "refs/tags/3.4.0";
#   }) { };
# in mach-nix.buildPythonApplication rec {
#   src = ./.;
#   pname = "bearctl";
#   version = "0.1.0";
#   requirements = ''
#     click
#     dasbus
#     pulsectl
#   '';
#   _.pulsectl.buildInputs.add = [ pkgs.libpulseaudio ];
#   _.dasbus.buildInputs.add = [ pkgs.python39Packages.pygobject3 pkgs.gobject-introspection ];
#   buildInputs = [
#     pkgs.libpulseaudio
#     # pkgs.python39Packages.pulsectl
#     pkgs.gobject-introspection
#     pkgs.python39Packages.pygobject3
#     pkgs.python39Packages.lxml
#   ];
# }
