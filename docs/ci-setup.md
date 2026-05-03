# CI setup for AccountPilot releases

This page is for the maintainer / release engineer. End users don't
need to read it.

AccountPilot has two release pipelines, both driven by GitHub Actions:

| Workflow | Triggered by | What it does |
|---|---|---|
| `.github/workflows/publish-pypi.yml` | tag `v*` | builds sdist + wheel, publishes to PyPI via OIDC Trusted Publishing |
| `.github/workflows/release-helper.yml` | tag `fda-helper-v*` | builds, signs (Developer ID), notarizes (App Store Connect API), attaches to the GH Release |

This doc walks through the **one-time setup** for both. After it's
done, future releases are just: bump version, tag, push.

---

## 1. PyPI Trusted Publisher

No tokens. PyPI verifies a short-lived OIDC identity that GitHub
Actions issues per workflow run.

1. Sign in to https://pypi.org with the project owner account.
2. Manage project `accountpilot` → **Publishing** → **Add a new
   pending publisher**.
3. Fill in:

   | Field | Value |
   |---|---|
   | Publisher | GitHub |
   | Owner | `aren13` |
   | Repository name | `accountpilot` |
   | Workflow filename | `publish-pypi.yml` |
   | Environment name | `pypi` |

4. **Save.**

Then in GitHub:

1. https://github.com/aren13/accountpilot/settings/environments
2. **New environment** → name `pypi` → Configure.
3. (Optional but recommended) **Required reviewers**: add yourself, so
   each PyPI publish requires a manual approve click.

Test:

```sh
git tag v0.1.1
git push --tags
```

Watch the run at https://github.com/aren13/accountpilot/actions.

---

## 2. Apple signing + notarization secrets

Two artifacts to generate:

### 2a. Developer ID code-signing certificate (.p12)

You already have the Developer ID Application cert installed locally
(see `apple_developer_account.md`). Export it for CI:

```sh
# Find the cert hash
security find-identity -v -p codesigning | grep "FAZLA GIDA"
# 1) <SHA1> "Developer ID Application: FAZLA GIDA ANONIM SIRKETI (P2R7PD8VGY)"

# Export the cert + private key into a .p12 (you'll be prompted for
# the keychain password and a NEW password for the .p12).
security export -k login.keychain-db \
    -t identities \
    -f pkcs12 \
    -P "$(openssl rand -hex 16 | tee ~/Desktop/p12-password.txt)" \
    -o ~/Desktop/accountpilot-cert.p12 \
    "Developer ID Application: FAZLA GIDA ANONIM SIRKETI (P2R7PD8VGY)"
```

If `security export` complains, do it manually via Keychain Access:
1. Open **Keychain Access**.
2. Select **login** keychain → **My Certificates**.
3. Right-click the FAZLA GIDA cert → **Export** → save as
   `accountpilot-cert.p12`. Set a password and remember it.

Then base64-encode for the GitHub secret:

```sh
base64 -i ~/Desktop/accountpilot-cert.p12 | pbcopy
```

The base64 is now on your clipboard. **Paste it into GitHub secret
`APPLE_CERT_P12_BASE64`.** Paste the .p12 password into
`APPLE_CERT_PASSWORD`.

### 2b. App Store Connect API key (.p8)

1. Sign in at https://appstoreconnect.apple.com with the team account
   holder Apple ID (Hasan Arda Eren).
2. **Users and Access** → **Integrations** tab → **Team Keys**.
3. **Generate API Key** (or **+**). Name: `AccountPilot CI`. Access:
   **Developer**. Save.
4. Apple will let you download the `.p8` **once**. Save it as
   `~/Desktop/AuthKey_<KEYID>.p8`.
5. Note the **Key ID** (10-character string visible in the table) and
   the **Issuer ID** (UUID near the top of the page).

Encode the .p8 for GitHub:

```sh
base64 -i ~/Desktop/AuthKey_*.p8 | pbcopy
```

### 2c. Add the secrets

https://github.com/aren13/accountpilot/settings/secrets/actions →
**New repository secret** for each:

| Secret | Value |
|---|---|
| `APPLE_CERT_P12_BASE64` | base64 of the `.p12` |
| `APPLE_CERT_PASSWORD` | the `.p12` password |
| `APPLE_API_KEY_BASE64` | base64 of the `.p8` |
| `APPLE_API_KEY_ID` | the 10-char Key ID |
| `APPLE_API_ISSUER_ID` | the UUID Issuer ID |

### 2d. Securely store the originals offline

After the secrets are saved in GitHub:

```sh
shred -u ~/Desktop/p12-password.txt   # if you used the openssl trick
# Move the .p12 and .p8 to a password manager / encrypted backup.
```

Then test:

```sh
git tag fda-helper-v0.1.1
git push --tags
gh release create fda-helper-v0.1.1 --generate-notes  # if needed
```

The workflow will rebuild the helper with a fresh keychain in CI,
sign, notarize, and attach assets.

---

## 3. After the helper publishes — refresh the brew formula

Once the new helper artifact lands on the GH Release, grab its sha256
and update the tap:

```sh
curl -L -O https://github.com/aren13/accountpilot/releases/download/fda-helper-v0.1.1/accountpilot-fda-helper-0.1.1-arm64.tar.gz
shasum -a 256 accountpilot-fda-helper-0.1.1-arm64.tar.gz
```

Update `aren13/homebrew-tap/Formula/accountpilot.rb` — both the helper
resource URL/sha256 and the top-level `url`/`sha256` for the new PyPI
sdist:

```sh
curl -s https://pypi.org/pypi/accountpilot/<version>/json | \
    python3 -c "import json,sys; d=json.load(sys.stdin)['urls']; \
                s=[u for u in d if u['packagetype']=='sdist'][0]; \
                print(s['url']); print(s['digests']['sha256'])"
```

Then `git push` the tap. `brew install aren13/tap/accountpilot` now
delivers the new release.

---

## 4. What's intentionally NOT automated

- **Bumping versions** — happens in `pyproject.toml` and the helper's
  `HELPER_VERSION` constant before tagging. Leaving this manual avoids
  accidental publishes.
- **CHANGELOG entries** — released versions get an entry before the
  tag. Future automation could derive entries from PR titles, but for
  a one-maintainer project the manual entry is more accurate.
- **Brew formula bump after PyPI publish** — could be a follow-up
  workflow that opens a PR to `homebrew-tap`. Not worth the
  complexity until release cadence picks up.
