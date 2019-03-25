# Read in the json spec for packages we want (so it can be auto-updated).
# niv: no_update
with builtins;
mapAttrs
  (_: spec: spec // { outPath = fetchTarball { inherit (spec) url sha256; }; })
  (fromJSON (readFile ./sources.json))
