{ pkgs, lib, config, inputs, ... }:
let
  pkgs-unstable = import inputs.nixpkgs-unstable { system = pkgs.stdenv.system; };
in
{

  # https://devenv.sh/packages/
  packages = [ 
    pkgs-unstable.uv
    pkgs.commitizen
    pkgs.git
    pkgs.just
  ];

  dotenv.enable = true;

  # https://devenv.sh/scripts/
  scripts.qfmt.exec = ''
    just qfmt
  '';
  scripts.qtest.exec = ''
    echo -e "Running unit tests  📏🔍\n"

    uv run scripts/run_unit_tests.sh
  '';

  enterShell = ''
    export LD_LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib}/lib:$LD_LIBRARY_PATH"
    echo -e 'Welcome to the qnexus repo! 😊 ➡️ 🖥️ ➡️ ⚛️\n'
  '';

  # https://devenv.sh/tests/
  enterTest = ''
    echo -e "Running tests \n"
    git --version | grep --color=auto "${pkgs.git.version}"
    uv --version | grep --color=auto "${pkgs-unstable.uv.version}"
    cz version | grep --color=auto "${pkgs.commitizen.version}"
  '';

  # https://devenv.sh/pre-commit-hooks/
  # pre-commit.hooks.shellcheck.enable = true;

  # See full reference at https://devenv.sh/reference/options/
}
