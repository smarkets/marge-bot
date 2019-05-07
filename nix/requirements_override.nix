{ pkgs, python }:

self: super: {
  # Break circular dependency: pytest depends on attrs and attrs depends on
  # pytest to test itself. It certainly hasn't got it as a runtime dep though,
  # so remove it.
  "attrs" = python.overrideDerivation super."attrs" (old: {
     propagatedBuildInputs = [ self."six" ];
  });
}
