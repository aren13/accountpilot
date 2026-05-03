# AccountPilot — Signed Helper for FDA-stable Distribution

## Context

AccountPilot (https://github.com/aren13/accountpilot) is an open-source Python
account-sync framework. Currently distributed via PyPI + a personal Homebrew tap
(aren13/homebrew-tap). The iMessage plugin reads ~/Library/Messages/chat.db,
which is gated by macOS Full Disk Access (FDA).

## Problem

FDA grants are keyed by Python interpreter cdhash + path. Every `brew upgrade
python@3.13` invalidates the grant. End users (non-technical) cannot be expected
to re-grant FDA after each upgrade — this kills the product's distribution
viability.

## Goal of this session

Design and build a Phase-1 proof-of-concept of a Developer-ID-signed Swift
helper binary that mediates all FDA-gated reads on behalf of the unsigned
Python daemon. After Phase 1, end-users will grant FDA *once* to the helper
and the grant survives all Python and accountpilot updates.

## Architectural decisions ALREADY MADE (do not re-litigate)

1. Helper is a separate signed binary, NOT a bundled Python distribution.
   - Reason: avoids py2app/PyInstaller fragility; keeps Python install
     channel-flexible (brew, pip, pipx).

2. Helper language: Swift.
   - Reason: best macOS API ergonomics, native codesigning/notarization
     toolchain, Apple-first-class support.

3. Helper scope: ONLY FDA-gated reads. No business logic, no orchestration,
   no DB writes. Narrow audit surface.

4. IPC: subprocess + JSON Lines on stdout for Phase 1.
   - Reason: simplest possible interface, no socket lifecycle to manage.
   - Phase 2 may upgrade to Unix-domain socket or XPC if perf demands.

5. Distribution: pre-built signed binary shipped via GitHub Releases.
   Homebrew formula downloads it as a `Resource` (binary, not source build).
   - Reason: source-built helper on user machine would be ad-hoc-signed,
     breaking TCC continuity.

6. Apple Developer Program enrollment ($99/yr) is acceptable. User will
   handle enrollment + cert issuance separately. Implementation should
   assume a `Developer ID Application: Your Name (TEAMID)` cert is available.

## Phase 1 deliverables

1. **Swift helper crate** at `helpers/fda-helper/` in the accountpilot repo:
   - Single command: `accountpilot-fda-helper read-imessages --since-ns <N>`
   - Reads ~/Library/Messages/chat.db using SQLite
   - Emits JSON Lines on stdout, one row per message
   - Schema documented in `helpers/fda-helper/PROTOCOL.md` (versioned, v1)
   - Bundle ID: `com.accountpilot.fda-helper`
   - Hardened runtime entitlement file
   - SwiftPM build (`swift build -c release`)

2. **Python integration** in `src/accountpilot/plugins/imessage/`:
   - New module `helper_client.py` that subprocess-execs the helper and
     parses JSON Lines
   - Replace direct `sqlite3.connect(chat.db)` calls in reader.py with
     helper_client calls (behind a feature flag `ACCOUNTPILOT_USE_FDA_HELPER=1`
     for Phase 1; flip to default-on in Phase 2)
   - Helper binary discovery: search PATH, then $HOMEBREW_PREFIX/bin, then
     bundled location

3. **Build + sign + notarize script** at `scripts/release-helper.sh`:
   - `swift build -c release`
   - `codesign --sign "Developer ID Application: ..." --options runtime
       --entitlements helper.entitlements`
   - `xcrun notarytool submit ... --wait`
   - `xcrun stapler staple`
   - Output: signed, notarized, stapled binary in `dist/`
   - Designed for GitHub Actions but runnable locally

4. **Brew formula update** in aren13/homebrew-tap:
   - Add `Resource` block fetching the signed binary from GitHub Releases
     (sha256-pinned)
   - `install` step copies it to `bin/accountpilot-fda-helper`
   - Update formula test to invoke `--version` on the helper

5. **Onboarding helper** in `accountpilot setup` CLI:
   - Detect missing FDA grant (try a probe read, catch EPERM)
   - On failure: print clear instructions + run
     `open "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"`
     to deep-link into the Privacy pane
   - Do NOT attempt to programmatically grant FDA — that's impossible without
     SIP disabled.

## Open questions — RESOLVE WITH USER BEFORE WRITING CODE

Use AskUserQuestion to batch these:

1. **Mail plugin scope**: Mail uses IMAP (no FDA). Should the helper also
   handle ~/Library/Mail/ reads for a future Apple-Mail.app plugin, or stay
   iMessage-only for Phase 1? (Affects helper API surface.)

2. **Cert ownership**: Will the cert be enrolled under user's personal name,
   or a registered LLC/business? (Affects bundle identifier prefix and
   marketing-name constraints.)

3. **Helper distribution scope**: Ship as part of the main `accountpilot`
   formula (always installed), or as a separate optional `accountpilot-fda`
   formula that mail-only users can skip? (Reduces friction for IMAP-only
   users.)

4. **CI signing**: Set up GitHub Actions signing now (with
   APPLE_DEVELOPER_CERT_P12 + APPLE_NOTARYTOOL_KEY secrets), or do manual
   local signing for Phase 1 and automate later?

5. **Existing user migration**: Current installs (the user is one) have FDA
   granted to /opt/anaconda3/bin/python or homebrew Python. After helper
   ships, what's the migration story — auto-detect old config, prompt to
   re-grant, leave old code path as fallback?

## Phase 1 verification gates

- [ ] `swift build -c release` produces a binary < 1MB
- [ ] `./accountpilot-fda-helper read-imessages --since-ns 0 | head -1`
      returns valid JSON Line on a machine with FDA granted
- [ ] Same command without FDA returns exit code 13 (EACCES) and a JSON
      error object on stderr — never crashes
- [ ] `codesign --verify --verbose=4 dist/accountpilot-fda-helper` passes
- [ ] `spctl --assess --type execute dist/accountpilot-fda-helper` reports
      "accepted" after notarization
- [ ] On a fresh Mac (or VM): brew install accountpilot, run setup, follow
      FDA prompt, run a sync — succeeds with exactly ONE manual permission
      grant
- [ ] After `brew upgrade python@3.13` to a newer patch version: sync
      continues to work with NO re-grant required (the critical test)

## What NOT to do in Phase 1

- Do not implement Unix sockets / XPC. Subprocess + JSON Lines only.
- Do not implement an in-app updater (Sparkle). Brew handles updates.
- Do not bundle Python with the helper. Helper is standalone.
- Do not add features beyond chat.db reads — Mail.app, Calendar, etc. are
  Phase 2+.
- Do not skip the entitlements file even if it "works without it" — hardened
  runtime is required for notarization.

## Reference repos / prior art

- Tailscale macOS helper: github.com/tailscale/tailscale (signed CLI in brew)
- 1Password CLI: how they ship a signed binary via brew Resource
- Apple's notarization docs:
    https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution

## Suggested order of work

1. Resolve open questions (batched AskUserQuestion).
2. Write PROTOCOL.md (define IPC schema BEFORE writing code).
3. Build minimal Swift helper, test locally with ad-hoc signing.
4. Wire Python helper_client.py behind feature flag, run existing test suite.
5. Set up signing/notarization script, validate end-to-end.
6. Update Homebrew formula in tap repo.
7. Write user-facing onboarding doc explaining the one-time grant.

Begin by reading CLAUDE.md and the current iMessage plugin code, then ask the
open questions.
