{ mkPoetryApplication
, lib
}:
mkPoetryApplication {
  pwd = ../.;
  pyproject = ../pyproject.toml;
  poetrylock = ../poetry.lock;
  src = lib.sourceByRegex ../. [
    "README.md"
    "marge(/.*\.py)?"
    "marge\.app"
    "tests(/.*\.py)?"
    "pyproject.toml"
    "pylintrc"
    "version"
  ];
  checkPhase = "pytest";
}
