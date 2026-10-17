#!/usr/bin/env bash
# ==============================================================================
# Sync Roadmap Issues to GitHub Project Board (agentspace-ge)
# ==============================================================================
# Prerequisites:
#   Ensure your GitHub CLI token has 'project' and 'read:project' scopes:
#     gh auth refresh -h github.com -s project,read:project
#
# Usage:
#   ./scripts/sync_github_project.sh
# ==============================================================================

set -euo pipefail

OWNER="${GITHUB_OWNER:-agentspace-ge}"
REPO="${GITHUB_REPO:-agentspace-ge/agy-quota-config-dash}"
PROJECT_TITLE="${PROJECT_TITLE:-Antigravity Quota Portal Roadmap}"

echo "Checking GitHub Project permissions for owner '${OWNER}'..."
if ! PROJECT_LIST_JSON=$(gh project list --owner "${OWNER}" --format json 2>/dev/null); then
  echo "Error: Your GitHub CLI token is missing 'project' / 'read:project' scopes."
  echo "Run the following command once to grant project scope, then re-run this script:"
  echo ""
  echo "  gh auth refresh -h github.com -s project,read:project"
  echo ""
  exit 1
fi

PROJECT_NUMBER=$(python3 -c '
import json, sys
data = json.loads(sys.argv[1])
title = sys.argv[2]
for p in data.get("projects", []):
    if p.get("title") == title:
        print(p.get("number"))
        break
' "${PROJECT_LIST_JSON}" "${PROJECT_TITLE}")

if [[ -z "${PROJECT_NUMBER}" ]]; then
  echo "Creating GitHub Project '${PROJECT_TITLE}' under '${OWNER}'..."
  CREATE_JSON=$(gh project create --owner "${OWNER}" --title "${PROJECT_TITLE}" --format json)
  PROJECT_NUMBER=$(python3 -c 'import json, sys; print(json.loads(sys.argv[1])["number"])' "${CREATE_JSON}")
  echo "Created Project #${PROJECT_NUMBER}"
else
  echo "Found existing Project '${PROJECT_TITLE}' (#${PROJECT_NUMBER})"
fi

echo "Linking repository '${REPO}' to Project #${PROJECT_NUMBER}..."
gh project link "${PROJECT_NUMBER}" --owner "${OWNER}" --repo "${REPO}" || true

echo "Adding all 'roadmap'-labeled issues from '${REPO}' to Project #${PROJECT_NUMBER}..."
ISSUE_URLS=$(gh issue list --repo "${REPO}" --label "roadmap" --state all --json url --jq '.[].url')

for url in ${ISSUE_URLS}; do
  echo "  -> Adding ${url}"
  gh project item-add "${PROJECT_NUMBER}" --owner "${OWNER}" --url "${url}" >/dev/null
done

PROJECT_URL=$(gh project view "${PROJECT_NUMBER}" --owner "${OWNER}" --format json --jq '.url')
echo ""
echo "Roadmap sync complete! View your GitHub Project board at:"
echo "  ${PROJECT_URL}"
