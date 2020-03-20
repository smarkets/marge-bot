{ pkgs, python }:
self: super:
let
  # Packages use setuptools-scm to try to infer version from source control metadata (say, git tag).
  # Authors put setuptools-scm in setup_requires.
  # Add it manually to affected packages.
  # NOTE: source tarballs don't have scm metadata.
  # setuptools-scm will just give up and emit 0.0.0.
  setuptools-scm = python.mkDerivation {
    name = "setuptools-scm";
    src = pkgs.fetchurl {
      url = "https://files.pythonhosted.org/packages/b2/f7/60a645aae001a2e06cf4b8db2fba9d9f36b8fd378f10647e3e218b61b74b/setuptools_scm-3.5.0.tar.gz";
      sha256 = "11qs1jvfgflx1msv39jgc6bj9d9a300ra35fwypkr44jayh23psv";
    };
  };

  addBuildInputs =
    pkg: buildInputs:
      python.overrideDerivation pkg (
        old: {
          buildInputs = old.buildInputs ++ buildInputs;
        }
      );
in
{
  # Break circular dependency: attrs <-> pytest
  attrs = python.overrideDerivation super.attrs (
    old: {
      propagatedBuildInputs = [ self.six ];
    }
  );

  # Break circular dependency: mccabe <-> pytest-runner
  mccabe = python.overrideDerivation super.mccabe (
    old: {
      postPatch = ''
        substituteInPlace setup.py --replace "setup_requires=['pytest-runner']," "setup_requires=[]," || true
      '';
    }
  );

  # pypi2nix does not handle setup_requires.
  astroid = addBuildInputs super.astroid [ self.pytest-runner ];
  pluggy = addBuildInputs super.pluggy [ setuptools-scm ];
  python-dateutil = addBuildInputs super.python-dateutil [ setuptools-scm ];
  py = addBuildInputs super.py [ setuptools-scm ];
  pylint = addBuildInputs super.pylint [ self.pytest-runner ];
  pytest = addBuildInputs super.pytest [ setuptools-scm ];
  pytest-runner = addBuildInputs super.pytest-runner [ setuptools-scm ];
  pytest-pylint = addBuildInputs super.pytest-pylint [ self.pytest-runner ];
}
