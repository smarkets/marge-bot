{ pkgs ? import ./pinnedNixpkgs.nix }:
let
  marge = pkgs.callPackage ./marge.nix {};
  version = marge.version;
  basicShadow =
    # minimal user setup, so ssh won't whine 'No user exists for uid 0'
    pkgs.runCommand "basic-shadow-setup" {}
      ''
        mkdir -p $out
        cd $out
        ${pkgs.dockerTools.shadowSetup}
        mkdir -p root/.ssh
      '';
in
  pkgs.dockerTools.buildImage {
    name = "smarkets/marge-bot";
    tag = "${version}";
    contents =
      with pkgs; [
        basicShadow
        bash
        coreutils
        git
        glibcLocales
        openssh
      ] ++ [ marge ];
    config = {
      Entrypoint = [ "/bin/marge.app" ];
      Env = ["LANG=en_US.UTF-8" ''LOCALE_ARCHIVE=/lib/locale/locale-archive''];
    };
  }
