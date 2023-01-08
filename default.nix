let sources = import ./nix/sources.nix; in
with import sources.nixpkgs
{
  overlays = [
    (self: super: {

      # Update NSS to a more recent version so we have an up-to-date
      # CA certificate bundle.
      nss =
        self.callPackage
          (import
            (builtins.fetchurl "https://raw.githubusercontent.com/NixOS/nixpkgs/2473837984348f435be4d7679133a19853690000/pkgs/development/libraries/nss/generic.nix")
            {
              version = "3.87";
              sha256 = "sha256-aKGJRJbT0Vi6vHX4pd2j9Vt8FWBXOTbjsQGhD6SsFS0=";
            })
          { };
    })
  ];
};

{
  marge-bot = callPackage ./marge.nix { };
  docker-image = callPackage ./dockerize.nix { };
}
