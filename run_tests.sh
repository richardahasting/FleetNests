#!/usr/bin/env bash
# Run the FleetNests test suite.
# Usage:
#   ./run_tests.sh              # all tests
#   ./run_tests.sh tests/test_auth.py        # single file
#   ./run_tests.sh -k "login"   # matching test names
#   ./run_tests.sh --cov        # with coverage report

set -e
cd "$(dirname "$0")"

# Install test deps if needed
pip install -q -r requirements-test.txt

# Run pytest, forwarding all args
pytest "$@"
