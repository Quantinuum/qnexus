#!/bin/bash
# Stop on first error
set -e

# Order doesn't matter but auth tests manipulate environment variables
# and should be run separately
uv run pytest --cov-reset tests/test_auth.py::test_token_refresh
uv run pytest tests/test_auth.py::test_nexus_client_reloads_domain
uv run pytest tests/test_auth.py::test_token_refresh_expired


echo "Running non-auth tests"
uv run pytest tests/ -v --ignore=tests/test_auth.py

echo -e "\n🎉 All tests passed successfully!"
