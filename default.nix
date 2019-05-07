let sources = import ./nix/sources.nix; in
with import sources.nixpkgs {};
{
  marge-bot = callPackage ./nix/marge.nix {};
  docker-image = callPackage ./nix/dockerize.nix {};
}
