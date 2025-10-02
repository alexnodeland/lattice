#!/usr/bin/env bash
set -e

# Install python virtual environment
uv venv --python 3.12

# Install dependencies
uv sync --all-groups

# Install pre-commit hooks
uv run pre-commit install

sudo apt update
