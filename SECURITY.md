# Security policy

Ranzenpost holds a parent's school login and a two-factor secret, so please treat anything that
could expose them as urgent.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Use GitHub's private reporting instead: open the repository's **Security** tab and choose
**Report a vulnerability**. Only the maintainer sees the report. You will get an answer within a
week; a fix ships as a regular add-on update, and the report is published together with it.

Please include the add-on version, what an attacker would need (local network, the Home Assistant
login, a calendar link, …) and, if you have one, a way to reproduce against the fixture server
(`backend/tests/e2e_fixture_app.py`) — never against a real school.

## Scope

In scope: everything in this repository — the add-on, its Ingress UI, the calendar feed server
on port 8100, the setup wizard and the IServ client.

Out of scope: IServ itself, Home Assistant, and issues that need an already compromised Home
Assistant instance or physical access to the device.

## What the add-on does to protect you

- Login and the app's two-factor key are encrypted at rest; with a passphrase set in the add-on
  options the key is derived at runtime and never written to disk.
- Every calendar subscription has its own random token that can be rotated or revoked. The feed
  port is off by default.
- Write actions to IServ (absences, archiving, read confirmations) always ask first.
- Only the children IServ lists for the signed-in parent account are ever read.
- Supported: the latest released version. Older versions get no separate fixes.
