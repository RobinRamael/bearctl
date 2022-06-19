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
  };
in pkgs.mkShell {
  buildInputs = [
    pyEnv
    pkgs.python39Packages.pulsectl
    pkgs.python39Packages.pygobject3
    pkgs.python39Packages.lxml
    pkgs.python39Packages.pytest

  ];
  PYTHONBREAKPOINT = "ipdb.set_trace";
}

