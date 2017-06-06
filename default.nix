with import <nixpkgs> {};
let version = "0.0.1";
    python = (import ./requirements.nix { inherit pkgs; });
    py = python.packages;
in
python.mkDerivation {
  pversion = "${version}";
  name = "marge-${version}";
  src = ./.;
  # The dependencies, referring to variables in <nixpkgs>.
  buildInputs = [py.pylint py.pytest py.pytest-cov];
  propagatedBuildInputs = [py.maya py.requests pkgs.openssh pkgs.perl pkgs.git];
  checkPhase = ''
     export NO_TESTS_OVER_WIRE=1
     export PYTHONDONTWRITEBYTECODE=1
     #export PYTHONPATH=$PYTHONPATH:/.
     pylint marge
     # FIXME(alexander): why do I need to screw w/ PYTHONPATH?
     PYTHONPATH=$PYTHONPATH:. py.test --cov marge
  '';
  meta = {
    homepage = "http://git.hanson.smarkets.com/hanson/marge";
    description = "A build bot for gitlab";
    # license = with lib.licenses; [mit] ;
    maintainers =  [
      "Daniel Gorin <daniel.gorin@smarkets.com>"
      "Alexander Schmolck <alexander.schmolck@smarkets.com>"
    ];
    platforms = pkgs.lib.platforms.linux ++ pkgs.lib.platforms.darwin;
  };
 }
