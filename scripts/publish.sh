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

TAG="${PUBLIC_AMAZON_TAG:-$( (grep -E '^PUBLIC_AMAZON_TAG=' site/.env 2>/dev/null || true) | head -1 | cut -d= -f2- )}"
if [ -n "$TAG" ]; then
  echo "Amazon Associates tag: $TAG (every Amazon link will be checked for it before deploying)"
else
  echo "WARNING: PUBLIC_AMAZON_TAG is not set in site/.env, so Amazon links would be untagged."
  echo "         The deploy will stop at the link check. Add PUBLIC_AMAZON_TAG=yourtag-20 to site/.env."
fi

echo "4/4 Building, checking Amazon links, and deploying..."
(cd site && npm run deploy)
echo "Done."
