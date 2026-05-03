# Security Policy

## Reporting a vulnerability

Email `ardaeren13@gmail.com` with a description of the issue and a
minimal reproduction. Expect an acknowledgment within ~7 days.

Please do NOT open a public GitHub issue for security-sensitive
problems.

## Supported versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1.0 | :x:                |

## Known security considerations

- AccountPilot stores OAuth refresh tokens in plaintext at
  `<data_dir>/secrets/oauth/<provider>/<id>.json` with mode `0600`.
  Anyone with read access to that file (root, anyone with the user
  account, anyone who steals an unencrypted disk image) can use the
  token until it's revoked or expires.
- The local SQLite database contains the full text of synced
  emails and iMessages. Treat it as sensitive.
- The interactive `accountpilot oauth login` flow opens a localhost
  callback on a random port. The OAuth client must register
  `http://localhost` as a redirect URI.
