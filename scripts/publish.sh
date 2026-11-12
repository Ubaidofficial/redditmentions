#!/usr/bin/env bash
# One command to publish the site from your Mac:
#   ./scripts/publish.sh
# Pulls the latest code, rebuilds the site data from output/*.csv, and deploys to Cloudflare.
# Preview flags live in site/.env (PUBLIC_NOINDEX, PUBLIC_PRODUCT_IMAGES) so you never retype them.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "1/4 Getting the latest code..."
git pull --ff-only

echo "2/4 Building the site data..."
python3 scripts/build_site_data.py

echo "3/4 Installing site dependencies (only changes if package.json changed)..."
(cd site && npm install --silent)

if [ -f site/.env ]; then
  echo "Using flags from site/.env:"; sed 's/^/   /' site/.env
else
  echo "No site/.env found: deploying with defaults (indexable, no product photos)."
fi

echo "4/4 Building and deploying..."
(cd site && npm run deploy)
echo "Done."
