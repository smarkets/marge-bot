let
  sources = import ./nix/sources.nix;
  niv = (import sources.niv {}).niv;
  pkgs = import sources.nixpkgs {};
  poetry = pkgs.callPackage (sources.poetry2nix + /pkgs/poetry) {
    python = pkgs.python3;
    inherit poetry2nix;
  };
  poetry2nixOverrides = [
    poetry2nix.defaultPoetryOverrides
    (
      self: super: {
        astroid = super.astroid.overrideAttrs (
          old: {
            postPatch = ''
              substituteInPlace setup.py --replace "setup_requires=[\"pytest-runner\"]," "setup_requires=[]," || true
            '';
          }
        );
      }
    )
  ];
  poetry2nix = import sources.poetry2nix {
    inherit pkgs poetry;
  };
  mkPoetryApplication = args: poetry2nix.mkPoetryApplication (
    args // { overrides = poetry2nixOverrides; }
  );

  inherit (pkgs) callPackage mkShell;
in
rec {
  marge-bot = callPackage ./nix/marge-bot.nix {
    mkPoetryApplication=mkPoetryApplication;
  };
  marge-bot-image = callPackage ./nix/marge-bot-image.nix {
    inherit marge-bot;
  };
  shell = mkShell {
    inputsFrom = [ marge-bot ];
    buildInputs = [
      niv
    ];
  };
}
