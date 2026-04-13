#!/bin/bash
# Stop on first error
set -e

# Order doesn't matter but auth tests manipulate environment variables
# and should be run separately
uv run pytest --cov-reset tests/test_auth.py::test_token_refresh
uv run pytest tests/test_auth.py::test_nexus_client_reloads_tokens
uv run pytest tests/test_auth.py::test_nexus_client_reloads_domain
uv run pytest tests/test_auth.py::test_token_refresh_expired
uv run pytest tests/test_auth.py::test_login_region_sg_uses_sg_domain_and_does_not_short_circuit


echo "Running non-auth tests"
uv run pytest tests/ -v --ignore=tests/test_auth.py

echo -e "\n🎉 All tests passed successfully!"