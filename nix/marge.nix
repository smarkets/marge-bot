{ pkgs
, lib
}:
let
  python = import ./requirements.nix { inherit pkgs; };
  version = lib.fileContents ./version;
in
  python.mkDerivation {
    version = "${version}";
    name = "marge-${version}";
    src = lib.sourceByRegex ./. [
      "marge(/.*\.py)?"
      "tests(/.*\.py)?"
      "marge\.app"
      "pylintrc"
      "setup\.cfg"
      "setup\.py"
      "version"
    ];
    checkInputs = with python.packages; [
      pytest
      pytest-cov
      pytest-flake8
      pytest-pylint
      pytest-runner
    ];
    propagatedBuildInputs = with python.packages; [
      ConfigArgParse maya PyYAML requests
    ];
    meta = {
      homepage = "https://github.com/smarkets/marge-bot";
      description = "A build bot for GitLab";
      license = lib.licenses.bsd3;
      maintainers =  [
        "Alexander Schmolck <alexander.schmolck@smarkets.com>"
        "Jaime Lennox <jaime.lennox@smarkets.com>"
      ];
      platforms = pkgs.lib.platforms.linux ++ pkgs.lib.platforms.darwin;
    };
  }
