let
  addBuildTools = pkg: tools: pkg.overrideAttrs
     (oldAttrs: { nativeBuildInputs = oldAttrs.nativeBuildInputs ++ tools; });
  sources = import ./nix/sources.nix;
  ## Tool to bump versions of sources written as json entries to git repos etc.
  ## We use it bump nixpkgs itself ATM (just `niv update`).
  niv = (import sources.niv {}).niv;
  pkgs = (import sources.nixpkgs {});
  pypi2nix = pkgs.pypi2nix;
  make = pkgs.make;
  marge-bot = (import ./.).marge-bot;
in
  ## create a version of the marge-bot env that has niv
  addBuildTools marge-bot [ niv pypi2nix ]
