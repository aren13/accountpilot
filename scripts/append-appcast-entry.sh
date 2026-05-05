#!/usr/bin/env bash
# Append a new <item> to appcast.xml for a tagged release.
#
# Inputs:
#   $1   path to appcast.xml (mutated in place)
#   $2   version string (e.g. "0.2.1")
#   $3   path to the DMG (used for size lookup; not modified)
#   $4   download URL (the GitHub Release asset URL)
#   $5   Sparkle ed signature line ('sparkle:edSignature="..." length="..."')
#
# Idempotent: if the same version is already in the appcast, replaces it.
# Inserts the new item before the closing </channel> tag.

set -euo pipefail

APPCAST="${1:?usage: append-appcast-entry.sh appcast.xml version dmg url ed-sig-line}"
VERSION="${2:?missing version}"
DMG="${3:?missing dmg path}"
URL="${4:?missing download url}"
ED_SIG_LINE="${5:?missing ed-signature line}"

test -f "$APPCAST" || { echo "error: $APPCAST not found" >&2; exit 1; }
test -f "$DMG" || { echo "error: $DMG not found" >&2; exit 1; }

PUB_DATE="$(date -u +"%a, %d %b %Y %H:%M:%S %Z")"

# Build the new <item> XML in a single string we'll inject into the file.
NEW_ITEM=$(cat <<XML
    <item>
      <title>Version $VERSION</title>
      <pubDate>$PUB_DATE</pubDate>
      <sparkle:version>$VERSION</sparkle:version>
      <sparkle:shortVersionString>$VERSION</sparkle:shortVersionString>
      <sparkle:minimumSystemVersion>13.0</sparkle:minimumSystemVersion>
      <enclosure url="$URL" type="application/octet-stream" $ED_SIG_LINE />
    </item>
XML
)

# Use python3 to do the surgery — sed/awk multi-line replacement is brittle.
NEW_ITEM="$NEW_ITEM" VERSION="$VERSION" APPCAST_PATH="$APPCAST" python3 - <<'PY'
import os
import re

appcast_path = os.environ["APPCAST_PATH"]
new_item = os.environ["NEW_ITEM"]
version = os.environ["VERSION"]

with open(appcast_path, encoding="utf-8") as f:
    xml = f.read()

# Idempotency: strip an existing <item> with the same version.
# Matches the whole <item>…</item> block containing this <sparkle:version>.
existing_pattern = (
    r"\s*<item>(?:(?!</item>).)*?<sparkle:version>"
    + re.escape(version)
    + r"</sparkle:version>(?:(?!</item>).)*?</item>\s*"
)
xml = re.sub(existing_pattern, "\n", xml, flags=re.DOTALL)

# Insert the new <item> immediately before </channel>.
if "</channel>" not in xml:
    raise SystemExit("error: appcast missing </channel> tag")
xml = xml.replace("</channel>", new_item + "\n  </channel>")

with open(appcast_path, "w", encoding="utf-8") as f:
    f.write(xml)
PY

echo "==> appended version $VERSION to $APPCAST"
