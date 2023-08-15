{
  description = "Homtying an entire os";

  # Nixpkgs / NixOS version to use.
  inputs = {
    nixpkgs.url = "nixpkgs/nixos-23.05";
    poetry2nix = {
      url = "github:nix-community/poetry2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, poetry2nix }:
    let
      # System types to support.
      supportedSystems = [ "x86_64-linux" "aarch64-linux" ];

      # Helper function to generate an attrset '{ x86_64-linux = f "x86_64-linux"; ... }'.
      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;

      # Nixpkgs instantiated for supported system types.
      nixpkgsFor = forAllSystems (system: import nixpkgs { inherit system; });

    in {

      # Provide some binary packages for selected system types.
      packages = forAllSystems (system:
        let
          pkgs = nixpkgsFor.${system};
          poetry = poetry2nix.legacyPackages.${system};
        in {
          # The default package for 'nix build'. This makes sense if the
          # flake provides only one package or there is a clear "main"
          # package.

          default = poetry.mkPoetryApplication {
            packageName = "bearctl";
            projectDir = ./.;

            overrides = poetry.overrides.withDefaults (self: super: {

              pycairo = super.pycairo.overridePythonAttrs (old: {
                nativeBuildInputs =
                  [ self.meson pkgs.buildPackages.pkg-config ];
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
              (with pkgs; [ pkgs.pipewire pkgs.lorri pkgs.xorg.xset ]);
          };

        });
    };
}
