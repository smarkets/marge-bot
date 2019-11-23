let
  sources = import ./nix/sources.nix;
  niv = (import sources.niv {}).niv;
  pkgs = import sources.nixpkgs {};
  poetry2nix = import sources.poetry2nix {
    inherit pkgs;
  };
  inherit (pkgs) callPackage mkShell;
in
rec {
  marge = callPackage ./nix/marge.nix {
    inherit (poetry2nix) makePoetryPackage;
  };
  marge-image = callPackage ./nix/marge-image.nix {
    inherit marge;
  };
  shell = mkShell {
    inputsFrom = [ marge ];
    buildInputs = [
      niv
    ];
  };
}
