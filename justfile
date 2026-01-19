# List the available commands
help:
    @just --list --justfile {{justfile()}}

# Run basic formatting, linting and typechecking
qfmt:
    echo -e "Running formatting, linting and typechecking 🧹 🔧 \n"

    uv run ruff check --select I --fix
    uv run ruff check 
    uv run ruff format 
    uv run mypy qnexus/ tests/ integration/

# Re-compile test hugr files.
recompile-test-files:
    @echo "---- Recompiling example guppy programs ----"
    just tests/data/recompile