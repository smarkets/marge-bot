{ pkgs ? import ./pinnedNixpkgs.nix }:
with pkgs;
let callPackage = pkgs.lib.callPackageWith (pkgs);
  marge = callPackage ./marge.nix {};
  version = marge.version;
in
dockerTools.buildImage {
  name = "smarketshq/marge-bot";
  tag = "${version}";
  # minimal user setup, so ssh won't whine 'No user exists for uid 0'
  runAsRoot = ''
  #!${stdenv.shell}
  ${dockerTools.shadowSetup}
  mkdir -p /root/.ssh
  '';
  contents = [marge pkgs.bash pkgs.coreutils pkgs.openssh pkgs.glibcLocales];
  config = {
    Entrypoint = [ "/bin/marge.app" ];
    Env = ["LANG=en_US.UTF-8" ''LOCALE_ARCHIVE=/lib/locale/locale-archive''];
  };
}
