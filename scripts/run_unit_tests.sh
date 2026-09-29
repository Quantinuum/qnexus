#!/bin/bash
# Stop on first error
set -e

# Auth tests manipulate environment variables and can interfere with each other
# We need to run the test_token_refresh first, and then the others
# can be run sequentially
uv run pytest --cov-reset tests/test_auth.py::test_token_refresh -n 0
uv run pytest tests/test_auth.py --deselect tests/test_auth.py::test_token_refresh -n 0

echo "Running non-auth tests"
uv run pytest tests/ -v --ignore=tests/test_auth.py

echo -e "\n🎉 All tests passed successfully!"
