let sources = import ./nix/sources.nix; in
with import sources.nixpkgs {};
{
  marge-bot = callPackage ./marge.nix {};
  docker-image = callPackage ./dockerize.nix {};
}
