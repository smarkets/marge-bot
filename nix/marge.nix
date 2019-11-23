{ makePoetryPackage
, lib
}:
makePoetryPackage {
  path = ../.;
  files = [
    "README.md"
    "marge(/.*\.py)?"
    "marge\.app"
    "tests(/.*\.py)?"
    "pylintrc"
    "version"
  ];
  checkPhase = "pytest";
}
