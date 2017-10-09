let
  fetchFromGitHub = (import <nixpkgs> {}).fetchFromGitHub;
  pkgs = import (fetchFromGitHub {
                   owner  = "NixOS";
                   repo   = "nixpkgs";
                   rev    = "90afb0c10fe6f437fca498298747b2bcb6a77d39";
                   sha256 = "0mvzdw5aygi1vjnvm0bc8bp7iwb9rypiqg749m6a6km84m7srm0w";
                 }) {};
in pkgs
