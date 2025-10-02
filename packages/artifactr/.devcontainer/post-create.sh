#!/usr/bin/env bash
set -e

# Install python virtual environment
uv venv --python 3.12

# Install dependencies
uv sync --all-groups

# Install pre-commit hooks
uv run pre-commit install

wget -qO- https://get.pnpm.io/install.sh | ENV="$HOME/.bashrc" SHELL="$(which bash)" bash -

pnpm install playwright

pnpm exec playwright install-deps

pnpm exec playwright install

curl -s https://packages.stripe.dev/api/security/keypair/stripe-cli-gpg/public | gpg --dearmor | sudo tee /usr/share/keyrings/stripe.gpg
echo "deb [signed-by=/usr/share/keyrings/stripe.gpg] https://packages.stripe.dev/stripe-cli-debian-local stable main" | sudo tee -a /etc/apt/sources.list.d/stripe.list
sudo apt update
sudo apt install stripe