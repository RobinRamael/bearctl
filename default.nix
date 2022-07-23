{ pkgs ? import <nixpkgs> { } }:
let
  mach-nix = import (builtins.fetchGit {
    url = "https://github.com/DavHau/mach-nix";
    ref = "refs/tags/3.5.0";
  }) {};
in mach-nix.buildPythonApplication {
  pname = "bearctl";
  src = ./.;
  requirements = ''
    dasbus
    click
    pygobject
    pipewire_python
  '';
}
