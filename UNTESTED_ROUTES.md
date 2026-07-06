# Untested Blueprint Routes

Snapshot of the known route-coverage gaps, refreshed during the
2026-07 code audit. The previous version of this file listed every
covered route; those tables rotted in both directions (they
under-reported auth/previews coverage and missed real holes), so this
file now only tracks what is **not** tested. Completed work belongs to
git history, not here.

To re-derive the list: compare the routes registered in
`zou/app/blueprints/*/__init__.py` with the paths exercised in
`tests/<blueprint>/`.

## Known gaps (2026-07-06)

| Area | Routes | Notes |
|---|---|---|
| FIDO/WebAuthn | `/auth/fido` (GET, PUT, POST, DELETE) | Needs a mocked WebAuthn authenticator (audit TEST-1) |
| SAML SSO | `/auth/saml/sso`, `/auth/saml/login` | Needs a fixture IdP assertion (audit TEST-1); the 2FA gate logic is shared with OIDC, which is tested |
| Batch comments (multipart) | `/actions/tasks/batch-comment` with attached preview files | JSON body path is covered; the multipart upload variant is not |
| Working file I/O | `/data/working-files/<id>/file` (GET, POST) | Skipped historically (binary I/O) |
| Attachment upload | `/actions/tasks/<id>/comments/<id>/add-attachment`, attachment download/delete routes | Service layer covered since the audit; route-level upload still untested |
| Output files with instances | `/data/asset-instances/<id>/entities/<id>/output-types/<id>/output-files` | Skipped historically (complex FK setup) |
| Production schedule apply | `/actions/production-schedule-versions/<id>/…` (3 action routes) | Skipped historically (complex schedule setup) |
| Playlist builds | `/data/playlists/<id>/build/mp4` and build-job routes | Need ffmpeg / a build job |
| Vendor isolation | `entities/*` sub-resources, chat attachments | Fixes shipped (audit SEC-11, SEC-14) but dedicated vendor-403 tests are still missing |
| Email OTP without auth | `/auth/email-otp` (GET) | Public endpoint, no rate-limit test (audit BUG-27) |
| Person invite | `/actions/persons/<id>/invite` | Sends email |

## Recently closed (2026-07 audit follow-up)

- 2FA routes: disable via recovery code, reset-password enumeration,
  restricted-token flows are covered in `tests/auth/`.
- Preview upload/serving happy paths are covered in
  `tests/thumbnails/`, including both `set-main-preview` routes.
- `/data/tasks/<id>/comments/<id>/ack` got its first test along with
  the session-conflict fix (audit BUG-37).
- Batch-comment routes (JSON body) and movie streaming
  (original/low/download/404) are covered in `tests/comments/` and
  `tests/previews/` (audit TEST-2).
