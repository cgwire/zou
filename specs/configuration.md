# Configuration

All configuration is in `zou/app/config.py`, read from environment variables.

## Database

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_HOST` | localhost | PostgreSQL host |
| `DB_PORT` | 5432 | PostgreSQL port |
| `DB_USERNAME` | postgres | Database user |
| `DB_PASSWORD` | mysecretpassword | Database password |
| `DB_DATABASE` | zoudb | Database name |
| `DB_POOL_SIZE` | 30 | Connection pool size |
| `DB_MAX_OVERFLOW` | 60 | Max additional connections |
| `DB_POOL_PRE_PING` | true | Verify connections before use |

## Authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | (generated) | Flask secret key for sessions |
| `JWT_SECRET_KEY` | (generated) | JWT signing key |
| `JWT_ACCESS_TOKEN_EXPIRES` | 604800 (7 days) | Access token TTL in seconds |
| `JWT_REFRESH_TOKEN_EXPIRES` | 1296000 (15 days) | Refresh token TTL |
| `MIN_PASSWORD_LENGTH` | 8 | Minimum password length |
| `BCRYPT_LOG_ROUNDS` | 12 | Bcrypt cost factor |
| `AUTH_STRATEGY` | auth_local_classic | Auth backend |

## Redis

| Variable | Default | Description |
|----------|---------|-------------|
| `KV_HOST` | localhost | Redis host |
| `KV_PORT` | 6379 | Redis port |
| `REDIS_DB` | 0 | Redis DB for events/blocklist |
| `CACHE_REDIS_DB` | 1 | Redis DB for caching |

## Storage

| Variable | Default | Description |
|----------|---------|-------------|
| `FS_BACKEND` | local | Storage backend: local, s3, swift |
| `FS_ROOT` | previews folder | Root path for local storage |
| `FS_S3_REGION` | | S3 region |
| `FS_S3_ENDPOINT` | | S3 endpoint URL |
| `FS_S3_ACCESS_KEY` | | S3 access key |
| `FS_S3_SECRET_KEY` | | S3 secret key |

## Optional services

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_JOB_QUEUE` | false | Enable Nomad job queue |
| `INDEXER_KEY` | | Meilisearch API key (enables search) |
| `INDEXER_HOST` | | Meilisearch host URL |
| `MAIL_SERVER` | localhost | SMTP server |
| `MAIL_PORT` | 25 | SMTP port |
| `SENTRY_DSN` | | Sentry error tracking |
| `PLUGIN_FOLDER` | | Path to plugins directory |

## Preview files

| Variable | Default | Description |
|----------|---------|-------------|
| `PREVIEW_SAVE_SOURCE_FILE` | false | Keep the uploaded source movie alongside the normalized preview. Ignored when the normalization runs on a remote worker: it reads the source from the object storage, so the source is uploaded there whatever this says (a warning is logged at startup) |
| `SKIP_NORMALIZATION_FULL` | false | Skip the movie normalization: the uploaded movie is stored as is, once, under `source` or `previews` (see below) |
| `SKIP_NORMALIZATION_HIGHDEF` | false | Skip only the high def (28M) encoding: the low def version is built and is the only movie stored |
| `SYNC_SOURCE_MOVIE_FILES` | false | Replicate the source movies when syncing from another instance |

With a Nomad setup (`ENABLE_JOB_QUEUE_REMOTE` + `JOB_QUEUE_NOMAD_NORMALIZE_JOB`),
the remote job is dispatched even when nothing has to be encoded
(`SKIP_NORMALIZATION_FULL`, or `?normalize=false` on the upload): it is what
builds the thumbnails and the tile, and Zou has no ffmpeg to fall back on.
The job then encodes and uploads nothing, and the uploaded source stays the
only movie — so the source is pushed to the object storage whatever
`PREVIEW_SAVE_SOURCE_FILE` says, since the job reads it from there.

The movie routes serve whichever version exists: `/movies/originals/` tries
`previews`, `lowdef` then `source`, and `/movies/low/` tries `lowdef`,
`previews` then `source`. So a setup skipping part of the normalization keeps
working without any client change. The source is served as `video/mp4`
whatever its real container, without the `+faststart` flag: browsers only
play it back when the upload is already a web-ready h264 mp4.
`/movies/source/preview-files/<id>.mp4` serves the source and only the source,
without that fallback.

### Skipping the normalization means syncing the sources

Where the movie lands depends on both the skip settings and the setup:

| | `source-<id>` | `previews-<id>` | `lowdef-<id>` |
|---|---|---|---|
| normalization on | only with `PREVIEW_SAVE_SOURCE_FILE` | encoded 28M | encoded 6M |
| `SKIP_NORMALIZATION_HIGHDEF` | only with `PREVIEW_SAVE_SOURCE_FILE` | no | encoded 6M |
| `SKIP_NORMALIZATION_FULL`, source kept | the uploaded movie | no | no |
| `SKIP_NORMALIZATION_FULL`, source not kept | no | the uploaded movie | no |

"Source kept" means `PREVIEW_SAVE_SOURCE_FILE=true`, or a remote (Nomad)
setup, which always pushes the source to the object storage since that is
where the worker reads it from. When the source is there, writing the same
bytes under `previews-<id>` would just be a second copy, and the movie routes
fall back on the source anyway. When it is not, the uploaded movie is stored
under `previews-<id>` instead, so the preview file always has a movie.

`PREVIEW_SAVE_SOURCE_FILE=true` alongside `SKIP_NORMALIZATION_FULL` is
therefore a sound setup — it is what a Nomad deployment does anyway — and it
is the way to keep a single stored movie on a local one.

Anything replicating a preview file has to carry the `source` prefix along,
or a copy made from a source-only instance ends up with no movie at all:

- **Between two instances**: set `SYNC_SOURCE_MOVIE_FILES=true` on the
  instance that pulls, when the other one runs `SKIP_NORMALIZATION_FULL` and
  keeps its source. It adds `/movies/source/preview-files/<id>.mp4` to the files
  fetched by `zou sync-full-files` and friends; without it the sync only asks
  for `previews` and `lowdef`, which that instance does not have. Leave it off
  otherwise: every missing source costs three retries and an error line in
  the logs (the 404 is not counted as a sync failure).
- **Inside one instance**: `copy_preview_file_in_another_one` (used by the
  comment automations) copies the `source` prefix too, unconditionally.

## LDAP / SAML

| Variable | Default | Description |
|----------|---------|-------------|
| `LDAP_HOST` | | LDAP server host |
| `LDAP_PORT` | | LDAP server port |
| `LDAP_BASE_DN` | | LDAP base distinguished name |
| `SAML_ENABLED` | false | Enable SAML SSO |
| `SAML_METADATA_URL` | | SAML IdP metadata URL |
| `SAML_IDP_NAME` | | Display name shown on the SAML login button |

## OIDC

OpenID Connect single sign-on. When enabled, a "Login with <provider>" button
is shown on the login page; users are redirected to the provider, and on return
a matching Kitsu account is found by email (or created on first login).

| Variable | Default | Description |
|----------|---------|-------------|
| `OIDC_ENABLED` | false | Enable OIDC SSO |
| `OIDC_IDP_NAME` | | Display name shown on the OIDC login button |
| `OIDC_DISCOVERY_URL` | | Provider OpenID configuration URL (ends with `/.well-known/openid-configuration`) |
| `OIDC_CLIENT_ID` | | OAuth client identifier registered with the provider |
| `OIDC_CLIENT_SECRET` | | OAuth client secret |
| `OIDC_SCOPES` | `openid email profile` | Space-separated scopes to request |
| `OIDC_EMAIL_CLAIM` | `email` | Claim used as the account email |
| `OIDC_GIVEN_NAME_CLAIM` | `given_name` | Claim used for the first name |
| `OIDC_FAMILY_NAME_CLAIM` | `family_name` | Claim used for the last name |
| `OIDC_REQUIRE_EMAIL_VERIFIED` | true | When true, the provider must assert `email_verified == true`; logins with an absent or false claim are rejected. Set to false only for providers that do not emit the claim and whose emails are otherwise trusted. |
| `OIDC_SKIP_2FA` | false | When true, OIDC sessions skip Kitsu's 2FA setup gate (trust the IdP for MFA). When false, `ENFORCE_2FA` applies as usual. |

The redirect URI to register with the provider is
`<DOMAIN_PROTOCOL>://<DOMAIN_NAME>/api/auth/oidc/callback`.

### Example: Keycloak

```
OIDC_ENABLED=true
OIDC_IDP_NAME=Keycloak
OIDC_DISCOVERY_URL=https://keycloak.example.com/realms/myrealm/.well-known/openid-configuration
OIDC_CLIENT_ID=kitsu
OIDC_CLIENT_SECRET=<secret from the Keycloak client>
```

Register `https://kitsu.example.com/api/auth/oidc/callback` as a valid redirect
URI on the Keycloak client. The same shape works for Azure AD, Okta, and Google
by pointing `OIDC_DISCOVERY_URL` at the provider's discovery document and, if the
provider uses non-standard claim names, overriding the `OIDC_*_CLAIM` variables.

> OIDC requires Flask's signed-cookie session to carry the `state`/`nonce`/PKCE
> values between `/auth/oidc/login` and `/auth/oidc/callback`, so `SECRET_KEY`
> must be set (it already is in any standard deployment).
