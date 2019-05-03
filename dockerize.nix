{ pkgs ? import ./pinnedNixpkgs.nix }:
let
  marge = pkgs.callPackage ./marge.nix {};
  version = marge.version;
in
  pkgs.dockerTools.buildImage {
    name = "smarkets/marge-bot";
    tag = "${version}";
    # minimal user setup, so ssh won't whine 'No user exists for uid 0'
    runAsRoot = ''
      #!${pkgs.stdenv.shell}
      ${pkgs.dockerTools.shadowSetup}
      mkdir -p /root/.ssh
    '';
    contents =
      with pkgs; [
        bash
        coreutils
        git
        glibcLocales
        openssh
      ] ++ [ marge ];
    config = {
      Entrypoint = [ "/bin/marge.app" ];
      Env = [
        "LANG=en_US.UTF-8"
        "LOCALE_ARCHIVE=/lib/locale/locale-archive"
      ];
    };
  }
