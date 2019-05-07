# generated using pypi2nix tool (version: 1.8.1)
# See more at: https://github.com/garbas/pypi2nix
#
# COMMAND:
#   pypi2nix -V 3.6 -r requirements.txt
#

{ pkgs ? import <nixpkgs> {}
}:

let

  inherit (pkgs) makeWrapper;
  inherit (pkgs.stdenv.lib) fix' extends inNixShell;

  pythonPackages =
  import "${toString pkgs.path}/pkgs/top-level/python-packages.nix" {
    inherit pkgs;
    inherit (pkgs) stdenv;
    python = pkgs.python36;
    # patching pip so it does not try to remove files when running nix-shell
    overrides =
      self: super: {
        bootstrapped-pip = super.bootstrapped-pip.overrideDerivation (old: {
          patchPhase = old.patchPhase + ''
            sed -i               -e "s|paths_to_remove.remove(auto_confirm)|#paths_to_remove.remove(auto_confirm)|"                -e "s|self.uninstalled = paths_to_remove|#self.uninstalled = paths_to_remove|"                  $out/${pkgs.python35.sitePackages}/pip/req/req_install.py
          '';
        });
      };
  };

  commonBuildInputs = [];
  commonDoCheck = false;

  withPackages = pkgs':
    let
      pkgs = builtins.removeAttrs pkgs' ["__unfix__"];
      interpreter = pythonPackages.buildPythonPackage {
        name = "python36-interpreter";
        buildInputs = [ makeWrapper ] ++ (builtins.attrValues pkgs);
        buildCommand = ''
          mkdir -p $out/bin
          ln -s ${pythonPackages.python.interpreter}               $out/bin/${pythonPackages.python.executable}
          for dep in ${builtins.concatStringsSep " "               (builtins.attrValues pkgs)}; do
            if [ -d "$dep/bin" ]; then
              for prog in "$dep/bin/"*; do
                if [ -f $prog ]; then
                  ln -s $prog $out/bin/`basename $prog`
                fi
              done
            fi
          done
          for prog in "$out/bin/"*; do
            wrapProgram "$prog" --prefix PYTHONPATH : "$PYTHONPATH"
          done
          pushd $out/bin
          ln -s ${pythonPackages.python.executable} python
          ln -s ${pythonPackages.python.executable}               python3
          popd
        '';
        passthru.interpreter = pythonPackages.python;
      };
    in {
      __old = pythonPackages;
      inherit interpreter;
      mkDerivation = pythonPackages.buildPythonPackage;
      packages = pkgs;
      overrideDerivation = drv: f:
        pythonPackages.buildPythonPackage (drv.drvAttrs // f drv.drvAttrs //                                            { meta = drv.meta; });
      withPackages = pkgs'':
        withPackages (pkgs // pkgs'');
    };

  python = withPackages {};

  generated = self: {

    "ConfigArgParse" = python.mkDerivation {
      name = "ConfigArgParse-0.14.0";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/55/ea/f0ade52790bcd687127a302b26c1663bf2e0f23210d5281dbfcd1dfcda28/ConfigArgParse-0.14.0.tar.gz"; sha256 = "2e2efe2be3f90577aca9415e32cb629aa2ecd92078adbe27b53a03e53ff12e91"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [
      self."PyYAML"
    ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/bw2/ConfigArgParse";
        license = licenses.mit;
        description = "A drop-in replacement for argparse that allows options to also be set via config files and/or environment variables.";
      };
    };



    "PyYAML" = python.mkDerivation {
      name = "PyYAML-5.1";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/9f/2c/9417b5c774792634834e730932745bc09a7d36754ca00acf1ccd1ac2594d/PyYAML-5.1.tar.gz"; sha256 = "436bc774ecf7c103814098159fbb84c2715d25980175292c648f2da143909f95"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/yaml/pyyaml";
        license = licenses.mit;
        description = "YAML parser and emitter for Python";
      };
    };



    "astroid" = python.mkDerivation {
      name = "astroid-2.2.5";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/85/e3/4ec967f7db4644b1fe849e4724191346d3e3f8172631ad7266f7f17a6018/astroid-2.2.5.tar.gz"; sha256 = "6560e1e1749f68c64a4b5dee4e091fce798d2f0d84ebe638cf0e0585a343acf4"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [
      self."lazy-object-proxy"
      self."six"
      self."typed-ast"
      self."wrapt"
    ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/PyCQA/astroid";
        license = licenses.lgpl3;
        description = "An abstract syntax tree for Python with inference support.";
      };
    };



    "atomicwrites" = python.mkDerivation {
      name = "atomicwrites-1.3.0";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/ec/0f/cd484ac8820fed363b374af30049adc8fd13065720fd4f4c6be8a2309da7/atomicwrites-1.3.0.tar.gz"; sha256 = "75a9445bac02d8d058d5e1fe689654ba5a6556a1dfd8ce6ec55a0ed79866cfa6"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/untitaker/python-atomicwrites";
        license = licenses.mit;
        description = "Atomic file writes.";
      };
    };



    "attrs" = python.mkDerivation {
      name = "attrs-19.1.0";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/cc/d9/931a24cc5394f19383fbbe3e1147a0291276afa43a0dc3ed0d6cd9fda813/attrs-19.1.0.tar.gz"; sha256 = "f0b870f674851ecbfbbbd364d6b5cbdff9dcedbc7f3f5e18a6891057f21fe399"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [
      self."coverage"
      self."pytest"
      self."six"
    ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://www.attrs.org/";
        license = licenses.mit;
        description = "Classes Without Boilerplate";
      };
    };



    "certifi" = python.mkDerivation {
      name = "certifi-2019.3.9";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/06/b8/d1ea38513c22e8c906275d135818fee16ad8495985956a9b7e2bb21942a1/certifi-2019.3.9.tar.gz"; sha256 = "b26104d6835d1f5e49452a26eb2ff87fe7090b89dfcaee5ea2212697e1e1d7ae"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://certifi.io/";
        license = licenses.mpl20;
        description = "Python package for providing Mozilla's CA Bundle.";
      };
    };



    "chardet" = python.mkDerivation {
      name = "chardet-3.0.4";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/fc/bb/a5768c230f9ddb03acc9ef3f0d4a3cf93462473795d18e9535498c8f929d/chardet-3.0.4.tar.gz"; sha256 = "84ab92ed1c4d4f16916e05906b6b75a6c0fb5db821cc65e70cbd64a3e2a5eaae"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/chardet/chardet";
        license = licenses.lgpl2;
        description = "Universal encoding detector for Python 2 and 3";
      };
    };



    "coverage" = python.mkDerivation {
      name = "coverage-4.5.3";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/82/70/2280b5b29a0352519bb95ab0ef1ea942d40466ca71c53a2085bdeff7b0eb/coverage-4.5.3.tar.gz"; sha256 = "9de60893fb447d1e797f6bf08fdf0dbcda0c1e34c1b06c92bd3a363c0ea8c609"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/nedbat/coveragepy";
        license = licenses.asl20;
        description = "Code coverage measurement for Python";
      };
    };



    "dateparser" = python.mkDerivation {
      name = "dateparser-0.7.1";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/51/6f/3bf59d1cfd7845a8614bae2c2ccd540074695015210285127aab9088ea14/dateparser-0.7.1.tar.gz"; sha256 = "42d51be54e74a8e80a4d76d1fa6e4edd997098fce24ad2d94a2eab5ef247193e"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [
      self."python-dateutil"
      self."pytz"
      self."regex"
      self."tzlocal"
    ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/scrapinghub/dateparser";
        license = licenses.bsdOriginal;
        description = "Date parsing library designed to parse dates from HTML pages";
      };
    };



    "entrypoints" = python.mkDerivation {
      name = "entrypoints-0.3";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/b4/ef/063484f1f9ba3081e920ec9972c96664e2edb9fdc3d8669b0e3b8fc0ad7c/entrypoints-0.3.tar.gz"; sha256 = "c70dd71abe5a8c85e55e12c19bd91ccfeec11a6e99044204511f9ed547d48451"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/takluyver/entrypoints";
        license = "";
        description = "Discover and load entry points from installed packages.";
      };
    };



    "flake8" = python.mkDerivation {
      name = "flake8-3.7.7";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/23/e7/80626da76ff2b4c94ac9bcd92898a1011d1c891e0ba1343f24109923462d/flake8-3.7.7.tar.gz"; sha256 = "859996073f341f2670741b51ec1e67a01da142831aa1fdc6242dbf88dffbe661"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [
      self."entrypoints"
      self."mccabe"
      self."pycodestyle"
      self."pyflakes"
    ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://gitlab.com/pycqa/flake8";
        license = licenses.mit;
        description = "the modular source code checker: pep8, pyflakes and co";
      };
    };



    "humanize" = python.mkDerivation {
      name = "humanize-0.5.1";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/8c/e0/e512e4ac6d091fc990bbe13f9e0378f34cf6eecd1c6c268c9e598dcf5bb9/humanize-0.5.1.tar.gz"; sha256 = "a43f57115831ac7c70de098e6ac46ac13be00d69abbf60bdcac251344785bb19"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "http://github.com/jmoiron/humanize";
        license = licenses.mit;
        description = "python humanize utilities";
      };
    };



    "idna" = python.mkDerivation {
      name = "idna-2.8";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/ad/13/eb56951b6f7950cadb579ca166e448ba77f9d24efc03edd7e55fa57d04b7/idna-2.8.tar.gz"; sha256 = "c357b3f628cf53ae2c4c05627ecc484553142ca23264e593d327bcde5e9c3407"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/kjd/idna";
        license = licenses.bsdOriginal;
        description = "Internationalized Domain Names in Applications (IDNA)";
      };
    };



    "isort" = python.mkDerivation {
      name = "isort-4.3.18";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/b5/3e/22308cdac59f5ef0e8157a33a01eb611e7a3a93e9711ed88ffc9a5b73ba0/isort-4.3.18.tar.gz"; sha256 = "f09911f6eb114e5592abe635aded8bf3d2c3144ebcfcaf81ee32e7af7b7d1870"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/timothycrosley/isort";
        license = licenses.mit;
        description = "A Python utility / library to sort Python imports.";
      };
    };



    "lazy-object-proxy" = python.mkDerivation {
      name = "lazy-object-proxy-1.3.1";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/55/08/23c0753599bdec1aec273e322f277c4e875150325f565017f6280549f554/lazy-object-proxy-1.3.1.tar.gz"; sha256 = "eb91be369f945f10d3a49f5f9be8b3d0b93a4c2be8f8a5b83b0571b8123e0a7a"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/ionelmc/python-lazy-object-proxy";
        license = licenses.bsdOriginal;
        description = "A fast and thorough lazy object proxy.";
      };
    };



    "maya" = python.mkDerivation {
      name = "maya-0.6.1";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/4e/90/e0e298b495164475331cc3fda906c640c9098a49fc933172fe5826393185/maya-0.6.1.tar.gz"; sha256 = "7f53e06d5a123613dce7c270cbc647643a6942590dba7a19ec36194d0338c3f4"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [
      self."dateparser"
      self."humanize"
      self."pendulum"
      self."pytz"
      self."snaptime"
      self."tzlocal"
    ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/kennethreitz/maya";
        license = licenses.mit;
        description = "Datetimes for Humans.";
      };
    };



    "mccabe" = python.mkDerivation {
      name = "mccabe-0.6.1";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/06/18/fa675aa501e11d6d6ca0ae73a101b2f3571a565e0f7d38e062eec18a91ee/mccabe-0.6.1.tar.gz"; sha256 = "dd8d182285a0fe56bace7f45b5e7d1a6ebcbf524e8f3bd87eb0f125271b8831f"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/pycqa/mccabe";
        license = licenses.mit;
        description = "McCabe checker, plugin for flake8";
      };
    };



    "more-itertools" = python.mkDerivation {
      name = "more-itertools-7.0.0";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/29/ed/3a85eb4afdce6dc33e78dad885e17c678db8055bf65353e0de4944c72a40/more-itertools-7.0.0.tar.gz"; sha256 = "c3e4748ba1aad8dba30a4886b0b1a2004f9a863837b8654e7059eebf727afa5a"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/erikrose/more-itertools";
        license = licenses.mit;
        description = "More routines for operating on iterables, beyond itertools";
      };
    };



    "pendulum" = python.mkDerivation {
      name = "pendulum-2.0.4";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/5b/57/71fc910edcd937b72aa0ef51c8f5734fbd8c011fa1480fce881433847ec8/pendulum-2.0.4.tar.gz"; sha256 = "cf535d36c063575d4752af36df928882b2e0e31541b4482c97d63752785f9fcb"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [
      self."python-dateutil"
      self."pytzdata"
    ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://pendulum.eustace.io";
        license = "";
        description = "Python datetimes made easy";
      };
    };



    "pluggy" = python.mkDerivation {
      name = "pluggy-0.9.0";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/a7/8c/55c629849c64e665258d8976322dfdad171fa2f57117590662d8a67618a4/pluggy-0.9.0.tar.gz"; sha256 = "19ecf9ce9db2fce065a7a0586e07cfb4ac8614fe96edf628a264b1c70116cf8f"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/pytest-dev/pluggy";
        license = licenses.mit;
        description = "plugin and hook calling mechanisms for python";
      };
    };



    "py" = python.mkDerivation {
      name = "py-1.8.0";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/f1/5a/87ca5909f400a2de1561f1648883af74345fe96349f34f737cdfc94eba8c/py-1.8.0.tar.gz"; sha256 = "dc639b046a6e2cff5bbe40194ad65936d6ba360b52b3c3fe1d08a82dd50b5e53"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "http://py.readthedocs.io/";
        license = licenses.mit;
        description = "library with cross-python path, ini-parsing, io, code, log facilities";
      };
    };



    "pycodestyle" = python.mkDerivation {
      name = "pycodestyle-2.5.0";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/1c/d1/41294da5915f4cae7f4b388cea6c2cd0d6cd53039788635f6875dfe8c72f/pycodestyle-2.5.0.tar.gz"; sha256 = "e40a936c9a450ad81df37f549d676d127b1b66000a6c500caa2b085bc0ca976c"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://pycodestyle.readthedocs.io/";
        license = licenses.mit;
        description = "Python style guide checker";
      };
    };



    "pyflakes" = python.mkDerivation {
      name = "pyflakes-2.1.1";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/52/64/87303747635c2988fcaef18af54bfdec925b6ea3b80bcd28aaca5ba41c9e/pyflakes-2.1.1.tar.gz"; sha256 = "d976835886f8c5b31d47970ed689944a0262b5f3afa00a5a7b4dc81e5449f8a2"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/PyCQA/pyflakes";
        license = licenses.mit;
        description = "passive checker of Python programs";
      };
    };



    "pylint" = python.mkDerivation {
      name = "pylint-2.3.1";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/01/8b/538911c0ebc2529f15004f4cb07e3ca562bb9aacea5df89cc25b62e01891/pylint-2.3.1.tar.gz"; sha256 = "723e3db49555abaf9bf79dc474c6b9e2935ad82230b10c1138a71ea41ac0fff1"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [
      self."astroid"
      self."isort"
      self."mccabe"
    ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/PyCQA/pylint";
        license = licenses.gpl1;
        description = "python code static checker";
      };
    };



    "pytest" = python.mkDerivation {
      name = "pytest-4.4.1";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/2b/b1/c9a84f79fc3bad226a9085289da11ecdd9bd2779a2c654195962b37d4110/pytest-4.4.1.tar.gz"; sha256 = "b7802283b70ca24d7119b32915efa7c409982f59913c1a6c0640aacf118b95f5"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [
      self."atomicwrites"
      self."attrs"
      self."more-itertools"
      self."pluggy"
      self."py"
      self."requests"
      self."six"
    ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://docs.pytest.org/en/latest/";
        license = licenses.mit;
        description = "pytest: simple powerful testing with Python";
      };
    };



    "pytest-cov" = python.mkDerivation {
      name = "pytest-cov-2.7.1";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/bb/0f/3db7ff86801883b21d5353b258c994b1b8e2abbc804e2273b8d0fd19004b/pytest-cov-2.7.1.tar.gz"; sha256 = "e00ea4fdde970725482f1f35630d12f074e121a23801aabf2ae154ec6bdd343a"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [
      self."coverage"
      self."pytest"
      self."six"
    ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/pytest-dev/pytest-cov";
        license = licenses.bsdOriginal;
        description = "Pytest plugin for measuring coverage.";
      };
    };



    "pytest-flake8" = python.mkDerivation {
      name = "pytest-flake8-1.0.4";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/f0/b5/e1360bfe5b1218fe4f7a7fd6038de8d990e980c6f5d55c922e216de7131b/pytest-flake8-1.0.4.tar.gz"; sha256 = "4d225c13e787471502ff94409dcf6f7927049b2ec251c63b764a4b17447b60c0"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [
      self."flake8"
      self."pytest"
    ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/tholo/pytest-flake8";
        license = licenses.bsdOriginal;
        description = "pytest plugin to check FLAKE8 requirements";
      };
    };



    "pytest-pylint" = python.mkDerivation {
      name = "pytest-pylint-0.14.0";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/52/58/cc27a07b8a7715411415c0f42d9e7c24bd2c646748b7406d2e7507da085f/pytest-pylint-0.14.0.tar.gz"; sha256 = "7bfbb66fc6dc160193a9e813a7c55e5ae32028f18660deeb90e1cb7e980cbbac"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [
      self."pylint"
      self."pytest"
      self."six"
    ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/carsongee/pytest-pylint";
        license = licenses.mit;
        description = "pytest plugin to check source code with pylint";
      };
    };



    "pytest-runner" = python.mkDerivation {
      name = "pytest-runner-4.4";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/15/0a/1e73c3a3d3f4f5faf5eacac4e55675c1627b15d84265b80b8fef3f8a3fb5/pytest-runner-4.4.tar.gz"; sha256 = "00ad6cd754ce55b01b868a6d00b77161e4d2006b3918bde882376a0a884d0df4"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [
      self."pytest"
      self."pytest-flake8"
    ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/pytest-dev/pytest-runner";
        license = licenses.mit;
        description = "Invoke py.test as distutils command with dependency resolution";
      };
    };



    "python-dateutil" = python.mkDerivation {
      name = "python-dateutil-2.8.0";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/ad/99/5b2e99737edeb28c71bcbec5b5dda19d0d9ef3ca3e92e3e925e7c0bb364c/python-dateutil-2.8.0.tar.gz"; sha256 = "c89805f6f4d64db21ed966fda138f8a5ed7a4fdbc1a8ee329ce1b74e3c74da9e"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [
      self."six"
    ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://dateutil.readthedocs.io";
        license = licenses.bsdOriginal;
        description = "Extensions to the standard Python datetime module";
      };
    };



    "pytz" = python.mkDerivation {
      name = "pytz-2019.1";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/df/d5/3e3ff673e8f3096921b3f1b79ce04b832e0100b4741573154b72b756a681/pytz-2019.1.tar.gz"; sha256 = "d747dd3d23d77ef44c6a3526e274af6efeb0a6f1afd5a69ba4d5be4098c8e141"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "http://pythonhosted.org/pytz";
        license = licenses.mit;
        description = "World timezone definitions, modern and historical";
      };
    };



    "pytzdata" = python.mkDerivation {
      name = "pytzdata-2019.1";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/f3/40/a33d54b253f4fb47df3ff9d1b724e70780140f6213bd16a4de32db232b1d/pytzdata-2019.1.tar.gz"; sha256 = "f0469062f799c66480fcc7eae69a8270dc83f0e6522c0e70db882d6bd708d378"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/sdispater/pytzdata";
        license = "";
        description = "The Olson timezone database for Python.";
      };
    };



    "regex" = python.mkDerivation {
      name = "regex-2019.4.14";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/11/d9/e37129676d508adf833fb3e3c3fbcb4e5a10183cf45b6c7edbaa57b4a1f2/regex-2019.04.14.tar.gz"; sha256 = "d56ce4c7b1a189094b9bee3b81c4aeb3f1ba3e375e91627ec8561b6ab483d0a8"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://bitbucket.org/mrabarnett/mrab-regex";
        license = licenses.psfl;
        description = "Alternative regular expression module, to replace re.";
      };
    };



    "requests" = python.mkDerivation {
      name = "requests-2.21.0";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/52/2c/514e4ac25da2b08ca5a464c50463682126385c4272c18193876e91f4bc38/requests-2.21.0.tar.gz"; sha256 = "502a824f31acdacb3a35b6690b5fbf0bc41d63a24a45c4004352b0242707598e"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [
      self."certifi"
      self."chardet"
      self."idna"
      self."urllib3"
    ];
      meta = with pkgs.stdenv.lib; {
        homepage = "http://python-requests.org";
        license = licenses.asl20;
        description = "Python HTTP for Humans.";
      };
    };



    "six" = python.mkDerivation {
      name = "six-1.12.0";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/dd/bf/4138e7bfb757de47d1f4b6994648ec67a51efe58fa907c1e11e350cddfca/six-1.12.0.tar.gz"; sha256 = "d16a0141ec1a18405cd4ce8b4613101da75da0e9a7aec5bdd4fa804d0e0eba73"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/benjaminp/six";
        license = licenses.mit;
        description = "Python 2 and 3 compatibility utilities";
      };
    };



    "snaptime" = python.mkDerivation {
      name = "snaptime-0.2.4";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/f3/f4/cb818c9bfdac4605f13296f7fcfe068aee7d1c3aa89f8cc22a064c1fab20/snaptime-0.2.4.tar.gz"; sha256 = "e3f1eb89043d58d30721ab98cb65023f1a4c2740e3b197704298b163c92d508b"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [
      self."python-dateutil"
      self."pytz"
    ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/zartstrom/snaptime";
        license = "";
        description = "Transform timestamps with a simple DSL";
      };
    };



    "typed-ast" = python.mkDerivation {
      name = "typed-ast-1.3.5";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/d3/b1/959c3ed4a9cc100feba7ad1a7d6336d8888937ee89f4a577f7698e09decd/typed-ast-1.3.5.tar.gz"; sha256 = "5315f4509c1476718a4825f45a203b82d7fdf2a6f5f0c8f166435975b1c9f7d4"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/python/typed_ast";
        license = licenses.asl20;
        description = "a fork of Python 2 and 3 ast modules with type comment support";
      };
    };



    "tzlocal" = python.mkDerivation {
      name = "tzlocal-1.5.1";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/cb/89/e3687d3ed99bc882793f82634e9824e62499fdfdc4b1ae39e211c5b05017/tzlocal-1.5.1.tar.gz"; sha256 = "4ebeb848845ac898da6519b9b31879cf13b6626f7184c496037b818e238f2c4e"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [
      self."pytz"
    ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/regebro/tzlocal";
        license = licenses.mit;
        description = "tzinfo object for the local timezone";
      };
    };



    "urllib3" = python.mkDerivation {
      name = "urllib3-1.24.3";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/8a/3c/1bb7ef6c435dea026f06ed9f3ba16aa93f9f4f5d3857a51a35dfa00882f1/urllib3-1.24.3.tar.gz"; sha256 = "2393a695cd12afedd0dcb26fe5d50d0cf248e5a66f75dbd89a3d4eb333a61af4"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [
      self."certifi"
      self."idna"
    ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://urllib3.readthedocs.io/";
        license = licenses.mit;
        description = "HTTP library with thread-safe connection pooling, file post, and more.";
      };
    };



    "wrapt" = python.mkDerivation {
      name = "wrapt-1.11.1";
      src = pkgs.fetchurl { url = "https://files.pythonhosted.org/packages/67/b2/0f71ca90b0ade7fad27e3d20327c996c6252a2ffe88f50a95bba7434eda9/wrapt-1.11.1.tar.gz"; sha256 = "4aea003270831cceb8a90ff27c4031da6ead7ec1886023b80ce0dfe0adf61533"; };
      doCheck = commonDoCheck;
      buildInputs = commonBuildInputs;
      propagatedBuildInputs = [ ];
      meta = with pkgs.stdenv.lib; {
        homepage = "https://github.com/GrahamDumpleton/wrapt";
        license = licenses.bsdOriginal;
        description = "Module for decorators, wrappers and monkey patching.";
      };
    };

  };
  localOverridesFile = ./requirements_override.nix;
  overrides = import localOverridesFile { inherit pkgs python; };
  commonOverrides = [

  ];
  allOverrides =
    (if (builtins.pathExists localOverridesFile)
     then [overrides] else [] ) ++ commonOverrides;

in python.withPackages
   (fix' (pkgs.lib.fold
            extends
            generated
            allOverrides
         )
   )