"""Shared constants used across the qnexus integration test suite."""

# Timeout (in seconds) passed to `qnx.jobs.wait_for(..., timeout=JOB_TIMEOUT)` calls.
# Kept under the CI job's pytest --timeout (currently 600s) so that a
# stuck job raises a clean asyncio.TimeoutError from wait_for itself,
# rather than relying on pytest-timeout which ayncio does not respect. 
JOB_TIMEOUT = 500.0
