let pkgs = import <nixpkgs> {};
in
pkgs.callPackage ./marge.nix {}
