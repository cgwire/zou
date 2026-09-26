# Untested Blueprint Routes

Snapshot of the route-coverage gaps, refreshed on 2026-09-26 during the
code audit. Only what is **not** tested is listed; completed work belongs
to git history.

To re-derive the list: compare the rules of `app.url_map` with the paths
exercised in `tests/blueprints/<name>/`. Many tests build their URLs by
concatenation (`f"/shared/playlists/{token}{suffix}"`), so match on path
segments, not on whole paths.

## Known gaps

| Area | Routes | Notes |
|---|---|---|
| Guest annotations | `PUT /shared/playlists/<token>/annotations` | The only write a share link guest can do; the other `shared/` routes are covered in `tests/blueprints/shared/` |
| Public probes | `GET /status/influx`, `/status/resources`, `/status/test-event` | `tests/blueprints/index/test_index.py` covers `/`, `/status` and `/stats` only |
| OIDC flow | `GET /auth/oidc/login` and the callback | `tests/blueprints/auth/test_oidc.py` covers the claims helper only |
| FIDO/WebAuthn | `/auth/fido` happy path | The 400 branches are covered in `tests/blueprints/auth/test_fido.py`; a successful assertion needs a mocked authenticator |
| SAML SSO | `/auth/saml/sso`, `/auth/saml/login` | Needs a fixture IdP assertion; the 2FA gate is shared with OIDC |
| Attachment thumbnail | `GET /pictures/thumbnails/attachment-files/<id>.png` | The download route of the same file is covered in `tests/blueprints/tasks/test_task_change.py` |
| Day off aggregations | `GET /data/persons/<id>/day-offs/{month,week,year}/…` | The unit day-off routes and the studio-wide month view are covered |
| Department items | `GET /data/departments/<id>/hardware-items/<id>` | Its DELETE is covered, the GET is not (the software one is) |
| Batch comments (multipart) | `/actions/tasks/batch-comment` with attached preview files | The JSON body path is covered |
| Working file I/O | `POST /data/working-files/<id>/file` | The GET, its 404 and its 403 are covered |
| Attachment upload | `/actions/tasks/<id>/comments/<id>/add-attachment` | Service layer covered; the route-level upload is not |
| Output files with instances | `/data/asset-instances/<id>/entities/<id>/output-types/<id>/output-files` | Complex FK setup |
| Production schedule apply | `/actions/production-schedule-versions/<id>/…` (3 action routes) | Complex schedule setup |
| Playlist builds | `/data/playlists/<id>/build/mp4` and build-job routes | Need ffmpeg / a build job |
| Shotgun legacy | `/import/shotgun/projectconnections` | The removal route is covered since 2026-09 |
| Person invite | `/actions/persons/<id>/invite` | Sends email |

## Fragile spots worth knowing

- `tests/blueprints/previews/test_tiles.py` wraps the tile extraction in a
  bare `try/except: pass`: the test cannot fail on that step.
- `tests/stores/test_auth_tokens_store.py` sleeps one real second to test
  a one second TTL.
