{
  description = "Homtying an entire os";

  inputs = {
    flake-utils.url = "github:numtide/flake-utils";
    nixpkgs.url = "github:nixos/nixpkgs/nixos-23.11";
    poetry2nix = {
      url = "github:nix-community/poetry2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = inputs@{ self, nixpkgs, flake-utils, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        poetry2nix = inputs.poetry2nix.lib.mkPoetry2Nix { inherit pkgs; };
      in {
        packages = {
          bear = poetry2nix.mkPoetryApplication {
            packageName = "bearctl";
            projectDir = ./.;

            overrides = poetry2nix.overrides.withDefaults (self: super: {

              # For some reason, since a while the build of pycairo fails with an error
              # like
              #
              #   ERROR: File 'cairo/_cairo.cpython-311-x86_64-linux-gnu.so' could not be found
              #
              # because that file gets copied somewhere else. Here we explicitly copy it
              # under the build/cairo directory.
              #
              # See also https://discourse.nixos.org/t/poetry2nix-and-pycairo/30173
              # for future referenceL debugging with cntr seems to be sort of useful here
              pycairo = super.pycairo.overridePythonAttrs (old: {
                format = "other";
                nativeBuildInputs = old.nativeBuildInputs or [ ] ++ [
                  self.setuptools
                  self.meson
                  pkgs.ninja
                  pkgs.buildPackages.pkg-config
                ];
                propagatedBuildInputs = old.propagatedBuildInputs or [ ]
                  ++ [ pkgs.cairo ];
                preInstall = ''
                  cp `find lib* -name '_cairo.*.so'` cairo
                '';
                mesonFlags =
                  [ "-Dpython=${if self.isPy3k then "python3" else "python"}" ];
              });
              pygobject = super.pygobject.overridePythonAttrs (old: {
                buildInputs = (old.buildInputs or [ ]) ++ [ super.setuptools ];
              });

              urllib3 = super.urllib3.overridePythonAttrs (old: {
                buildInputs = (old.buildInputs or [ ]) ++ [ self.hatch-vcs ];
              });

              pipewire-python = super.pipewire-python.overridePythonAttrs
                (old: {
                  buildInputs = (old.buildInputs or [ ]) ++ [ self.flit-core ];
                });

            });
            buildInputs =
              (with pkgs; [ pkgs.pipewire pkgs.lorri pkgs.xorg.xset pkgs.i3 pkgs.polybar pkgs.eww-wayland]);

          };
          default = self.packages.${system}.bear;
        };

        devShells.default = pkgs.mkShell {
          inputsFrom = [ self.packages.${system}.bear ];
          packages = [ pkgs.poetry ];
          shellHook = ''
            export PYTHONBREAKPOINT="ipdb.set_trace"
            export BEARCTL_EXECUTABLE=/home/robin/devel/bearctl/result/bin/bearctl
            export DEBUG=1
            export EWW_CONFIG=/home/robin/.config/home-manager/eww
          '';
        };
      });
}
