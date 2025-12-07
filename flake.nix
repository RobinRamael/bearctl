{
  description = "Homtying an entire os";
  inputs = {
    flake-utils.url = "github:numtide/flake-utils";
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    poetry2nix = {
      url = "github:nix-community/poetry2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };
  outputs =
    inputs@{
      self,
      nixpkgs,
      flake-utils,
      ...
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python311;
        poetry2nix = inputs.poetry2nix.lib.mkPoetry2Nix {
          inherit pkgs;
        };
      in
      {
        packages = {
          bear = poetry2nix.mkPoetryApplication {
            packageName = "bearctl";
            projectDir = ./.;
            python = python; # More explicit
            preferWheels = true; # Try to use wheels when available

            overrides = poetry2nix.overrides.withDefaults (
              self: super: {
                pycairo = pkgs.python311Packages.pycairo;

                pygobject = super.pygobject.overridePythonAttrs (old: {
                  nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ [
                    pkgs.meson
                    pkgs.ninja
                    pkgs.pkg-config
                    pkgs.gobject-introspection
                  ];
                  buildInputs = (old.buildInputs or [ ]) ++ [
                    pkgs.glib
                    pkgs.gobject-introspection
                    pkgs.libffi
                  ];
                  format = "other";

				  doCheck = false;

                  configurePhase = ''
                    runHook preConfigure
                    cd $NIX_BUILD_TOP/$sourceRoot
                    meson setup $NIX_BUILD_TOP/mesonbuild --prefix=$out --buildtype=plain -Dtests=false
                    runHook postConfigure
                  '';

                  buildPhase = ''
                    runHook preBuild
                    cd $NIX_BUILD_TOP/mesonbuild
                    ninja
                    runHook postBuild
                  '';

                  installPhase = ''
                    runHook preInstall
                    cd $NIX_BUILD_TOP/mesonbuild
                    ninja install
                    runHook postInstall
                  '';

                  dontUsePipBuild = true;
                  dontUsePipInstall = true;
                });

                urllib3 = super.urllib3.overridePythonAttrs (old: {
                  buildInputs = (old.buildInputs or [ ]) ++ [ self.hatch-vcs ];
                });

                pytest-sugar = super.pytest-sugar.overridePythonAttrs (old: {
                  buildInputs = (old.buildInputs or [ ]) ++ [ self.pytest ];
                });
              }
            );
            buildInputs = (
              with pkgs;
              [
                eww
                tlp
              ]
            );
            nativeBuildInputs = [ pkgs.makeWrapper ];
            makeWrapperArgs = [
              "--prefix PATH : ${pkgs.tlp}/bin"
              "--prefix GI_TYPELIB_PATH : ${pkgs.gobject-introspection}/lib/girepository-1.0"
              "--prefix GI_TYPELIB_PATH : ${pkgs.glib.out}/lib/girepository-1.0"
            ];
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
            export EWW_EXECUTABLE=/home/robin/.nix-profile/bin/eww
            run_eww() {
              $EWW_EXECUTABLE -c $EWW_CONFIG kill
              $EWW_EXECUTABLE -c $EWW_CONFIG daemon
              $EWW_EXECUTABLE -c $EWW_CONFIG open top-bar
              $EWW_EXECUTABLE -c $EWW_CONFIG open bottom-bar
              $EWW_EXECUTABLE -c $EWW_CONFIG logs
            }
          '';
        };
      }
    );
}
