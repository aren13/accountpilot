# AccountPilot release procedure

This document covers (a) the one-time setup needed before the first
release and (b) the steps to cut a new release.

## One-time setup

### Sparkle EdDSA keypair

Sparkle verifies update authenticity with an EdDSA signature.
Generate a keypair on a trusted machine:

```bash
# Locate sign_update / generate_keys after `xcodebuild build` resolves Sparkle
find ~/Library/Developer/Xcode/DerivedData -name "generate_keys" -type f -print -quit
find app/build -name "generate_keys" -type f -print -quit
# Run the one that's found:
<path>/generate_keys
```

The tool stores the keypair in your Keychain under the
`https://sparkle-project.org` service. Print the public key:

```bash
<path>/generate_keys -p
```

Paste the public key into `app/project.yml`'s
`AccountPilot.info.properties.SUPublicEDKey` (replacing the
`REPLACE_AFTER_GENERATING_KEY` placeholder). **Commit this**.

Export the private key for CI:

```bash
<path>/generate_keys -x /tmp/sparkle-private.b64
gh secret set SPARKLE_PRIVATE_KEY < /tmp/sparkle-private.b64
shred -u /tmp/sparkle-private.b64    # or rm -P on macOS
```

### Apple Developer ID Application certificate

Export the certificate from Keychain Access as a `.p12`
(right-click → Export) with a password. Then:

```bash
base64 -i developer-id.p12 | pbcopy   # copies to clipboard
```

Add as GitHub Actions secrets:

- `APPLE_CERT_P12_BASE64` — the base64 string
- `APPLE_CERT_PASSWORD` — the password you set during export

### App Store Connect API key (for notarytool in CI)

Create an API key at https://appstoreconnect.apple.com/access/api
with the **Developer** role. Download the `.p8` file (you can only
download it once).

```bash
base64 -i AuthKey_XXXXXXXXXX.p8 | pbcopy
```

Add as GitHub Actions secrets:

- `APPLE_API_KEY_BASE64` — the base64 string
- `APPLE_API_KEY_ID` — the 10-character key ID (e.g. `WHX8YQB959`)
- `APPLE_API_ISSUER_ID` — the UUID issuer ID for your team

### Bootstrap the gh-pages branch

```bash
git worktree add -b gh-pages /tmp/accountpilot-gh-pages
cd /tmp/accountpilot-gh-pages
git rm -rf . || true
cat > appcast.xml <<'XML'
<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle"
     xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel>
    <title>AccountPilot Updates</title>
    <link>https://aren13.github.io/accountpilot/appcast.xml</link>
    <description>AccountPilot release feed</description>
    <language>en</language>
  </channel>
</rss>
XML
cat > index.html <<'HTML'
<!doctype html>
<title>AccountPilot</title>
<h1>AccountPilot release feed</h1>
<p>Sparkle appcast: <a href="appcast.xml">appcast.xml</a></p>
HTML
git add appcast.xml index.html
git commit -m "build(release): bootstrap gh-pages with empty appcast"
git push -u origin gh-pages
cd "$REPO_ROOT"
git worktree remove /tmp/accountpilot-gh-pages
git branch -D gh-pages
```

Then in GitHub Settings → Pages: source `gh-pages` branch, root
folder. Verify https://aren13.github.io/accountpilot/appcast.xml
serves the XML.

## Cutting a release

Cutting a release is a single command:

```bash
git tag v0.2.1
git push --tags
```

The `.github/workflows/release-app.yml` workflow runs on
`macos-latest`. It takes ~10-15 minutes (most of that is the
notarization round-trip — twice, once for the .app and once for
the DMG). When complete:

- `https://github.com/aren13/accountpilot/releases/tag/v0.2.1` has
  the DMG attached
- `https://aren13.github.io/accountpilot/appcast.xml` has a new
  `<item>` for v0.2.1
- Existing AccountPilot installs see "Update available" within
  Sparkle's check interval (default: 24h, override via
  `SUScheduledCheckInterval` in Info.plist)

Watch the workflow at
https://github.com/aren13/accountpilot/actions.

If notarization fails: read the workflow log; the
`xcrun notarytool log <id> --key …` invocation prints the JSON of
why Apple rejected. Most common cause: an unsigned binary somewhere
in the .app bundle that `app/scripts/codesign-app.sh`'s find-loop
missed — check Sparkle.framework's nested helpers if a Sparkle
update changed the structure.

## Local DMG production (for manual testing)

To build a DMG locally without going through CI:

```bash
./app/scripts/build-app.sh    # produces dist/AccountPilot.app
./app/scripts/build-dmg.sh    # produces dist/AccountPilot-<version>.dmg
```

Both scripts use the local keychain profile `accountpilot-notary`
(see `scripts/release-helper.sh` for the auth resolution).
