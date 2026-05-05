#!/usr/bin/env bash
# Agent integration smoke: simulates an agent doing the full
# add-account → OAuth → sync → search loop using only the CLI.
#
# Required: a real Gmail account and your willingness to do the
# OAuth consent flow in the browser. Set ACCOUNTPILOT_DATA_DIR
# to a tmp dir so this doesn't pollute your real install.
#
# Usage:
#   ACCOUNTPILOT_DATA_DIR=/tmp/agent-smoke \
#       tests/integration/agent_smoke.sh ada@example.com Ada Lovelace

set -euo pipefail

EMAIL="${1:?usage: agent_smoke.sh <email> <first> <last>}"
FIRST="${2:?missing first name}"
LAST="${3:?missing last name}"

CLI="${ACCOUNTPILOT_CLI:-accountpilot}"

echo "==> 1. Add account"
ADD_OUT="$("$CLI" accounts add --provider gmail \
    --identifier "$EMAIL" --owner-name "$FIRST" --owner-surname "$LAST" --json)"
echo "$ADD_OUT" | python3 -m json.tool
ACCOUNT_ID="$(echo "$ADD_OUT" | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"]["account"]["id"])')"
echo "    new account id: $ACCOUNT_ID"

echo "==> 2. OAuth login (browser opens, user consents)"
"$CLI" oauth login google "$ACCOUNT_ID" --json | python3 -m json.tool

echo "==> 3. Sync once"
"$CLI" sync-once mail "$ACCOUNT_ID" --json | python3 -m json.tool

echo "==> 4. List a few messages"
"$CLI" messages list --account "$ACCOUNT_ID" --limit 3 --json \
    | python3 -m json.tool

echo "==> 5. Search the inbox"
"$CLI" search "interview" --limit 3 --json \
    | python3 -m json.tool

echo "==> done"
