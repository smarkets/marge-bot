let
  pkgs = import ./pinnedNixpkgs.nix;
in
  pkgs.callPackage ./marge.nix {}
