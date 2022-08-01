{
  description = "Homtying an entire os";

  # Nixpkgs / NixOS version to use.
  inputs = {
    mach-nix.url = "mach-nix/3.5.0";
    nixpkgs.url = "nixpkgs/nixos-21.11";
  };

  outputs = { self, nixpkgs, mach-nix }:
    let
      # System types to support.
      supportedSystems =
        [ "x86_64-linux" "x86_64-darwin" "aarch64-linux" "aarch64-darwin" ];

      # Helper function to generate an attrset '{ x86_64-linux = f "x86_64-linux"; ... }'.
      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;

      # Nixpkgs instantiated for supported system types.
      nixpkgsFor = forAllSystems (system: import nixpkgs { inherit system; });

      bearRequirements =
        "	dasbus\n	click\n	pygobject\n	pipewire_python\n	notify2\n  ";

    in {

      # Provide some binary packages for selected system types.
      packages = forAllSystems (system:
        let
          pkgs = nixpkgsFor.${system};
          mach = mach-nix.lib."${system}";
        in {
          # The default package for 'nix build'. This makes sense if the
          # flake provides only one package or there is a clear "main"
          # package.
          default = mach.buildPythonApplication {
            pname = "bearctl";
            src = ./.;
            version = "0.1.0";
            requirements = bearRequirements;
            postFixup = ''
              wrapProgram $out/bin/bearctl --prefix PATH : ${
                pkgs.lib.makeBinPath (with pkgs; [ pkgs.pipewire pkgs.lorri ])
              }
            '';
          };
        });
      devShells = forAllSystems (system:
        let
          pkgs = nixpkgsFor.${system};
          mach = mach-nix.lib."${system}";
        in {
          default = mach.mkPythonShell { requirements = bearRequirements; };
        });
    };
}
