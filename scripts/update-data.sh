#!/usr/bin/env bash
# Rebuild the site data on your Mac and push it, so GitHub Actions deploys the site with it:
#   ./scripts/update-data.sh
# Run it after changing scripts/curation.json or the CSVs in output/. Code changes need no script: merging a pull
# request into main deploys automatically.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "1/3 Getting the latest code..."
git checkout main
git pull --ff-only

echo "2/3 Building the site data..."
python3 scripts/build_site_data.py

echo "3/3 Committing and pushing the data..."
git add site/src/data/generated site/public/_redirects
if git diff --cached --quiet; then
  echo "The data has not changed: nothing to commit, nothing to deploy."
  exit 0
fi
git diff --cached --stat | tail -1
git commit -m "Update site data"
git push
echo "Pushed. GitHub Actions is deploying it: see the Actions tab of the repository."
