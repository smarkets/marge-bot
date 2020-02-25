# Read in the json spec for packages we want (so it can be auto-updated).
# niv: no_update

# make travis happy, reasonably new nix doesn't need this
let
  mapAttrs = builtins.mapAttrs or
    (
      f: set:
        builtins.listToAttrs (map (attr: { name = attr; value = f attr set.${attr}; }) (builtins.attrNames set))
    );
in
  with builtins;
  mapAttrs
    (_: spec: spec // { outPath = fetchTarball { inherit (spec) url sha256; }; })
    (fromJSON (readFile ./sources.json))
