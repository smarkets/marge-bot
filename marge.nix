{pkgs ? import ./pinnedNixpkgs.nix }:
with pkgs;
let version = builtins.replaceStrings ["\n"] [""] (builtins.readFile ./version);
    python = (import ./requirements.nix { inherit pkgs; });
    py = python.packages;
in
python.mkDerivation {
  version = "${version}";
  name = "marge-${version}";
  src = ./.;
  # The dependencies, referring to variables in <nixpkgs>.
  buildInputs = [py.pylint py.pytest py.pytest-cov];
  propagatedBuildInputs = [py.maya py.requests pkgs.openssh pkgs.git];
  checkPhase = ''
     export NO_TESTS_OVER_WIRE=1
     export PYTHONDONTWRITEBYTECODE=1
     #export PYTHONPATH=$PYTHONPATH:/.
     pylint marge || [[ $? = 8 ]]  # ignore refactoring comments for exit code
     # FIXME(alexander): why do I need to mess w/ PYTHONPATH?
     PYTHONPATH=$PYTHONPATH:. py.test --cov marge
  '';

  meta = {
    homepage = "https://github.com/smarkets/marge-bot";
    description = "A build bot for gitlab";
    license = with lib.licenses; [bsd3] ;
    maintainers =  [
      "Daniel Gorin <daniel.gorin@smarkets.com>"
      "Alexander Schmolck <alexander.schmolck@smarkets.com>"
    ];
    platforms = pkgs.lib.platforms.linux ++ pkgs.lib.platforms.darwin;
  };
 }
