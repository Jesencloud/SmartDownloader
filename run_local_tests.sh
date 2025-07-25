#!/bin/bash

# ==============================================================================
#  SmartDownloader - Local Test Runner
# ==============================================================================
#
#  This script automates the process of running all local tests (linting,
#  unit tests, and end-to-end tests) within a Docker Compose environment,
#  mimicking the GitHub Actions CI workflow.
#
#  Usage:
#  Run this script from the project root directory:
#  ./run_local_tests.sh
#
# ==============================================================================

# Exit immediately if any command fails
set -e

# --- Pre-flight Check ---
# Check if Docker is running before proceeding
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running."
    echo "   Please start Docker Desktop and try again."
    exit 1
fi

# --- Cleanup Function ---
# This function will be called on script exit or interruption (Ctrl+C)
cleanup() {
    echo ""
    echo "🧹 Cleaning up Docker environment..."
    docker-compose down
    echo "✅ Cleanup complete."
}

# Register the cleanup function to be called on EXIT signal
trap cleanup EXIT

echo "🚀 Starting local test suite..."

echo ""
echo "1️⃣ Running Linter & Formatter Checks..."
docker-compose run --rm test-runner sh -c "ruff check . && ruff format --check ."

echo ""
echo "2️⃣ Running All Tests (Unit & E2E) and Generating Report..."
docker-compose run --rm test-runner pytest -v --html=test_report.html --self-contained-html

echo ""
echo "🎉 All local tests passed successfully!"