# Configuration

All configuration is read from environment variables in `zou/app/config.py`.
The tables below list every variable the module reads; `tests/misc/test_configuration_doc.py`
fails when one is added to the code and not here, or documented and no longer read.

## Server

| Variable | Default | Description |
|----------|---------|-------------|
| `DEBUG` | false | Debug mode: verbose errors, no refusal of the default `SECRET_KEY`, local telemetry URL |
| `DEBUG_HOST` | 127.0.0.1 | Bind address of the development server (`zou run`) |
| `DEBUG_PORT` | 5000 | Port of the development server |
| `SECRET_KEY` | mysecretkey | Flask secret, also the JWT signing key. The HTTP server refuses to start with the default outside `DEBUG`; the CLI and the tests are exempt |
| `DOMAIN_NAME` | localhost:8080 | Public host of the instance, used in the links of the emails and in the OIDC and SAML redirect URIs |
| `DOMAIN_PROTOCOL` | https | Public scheme of the instance |
| `CORS_ALLOWED_ORIGINS` | (none) | Semicolon-separated origins allowed to call the API from a browser; CORS is disabled when empty |
| `CLIENT_CACHE_MAX_AGE` | 604800 | `Cache-Control: max-age` of the served pictures and movies, in seconds |
| `NB_RECORDS_PER_PAGE` | 100 | Page size of the paginated listings when the client gives none |
| `MAX_CONTENT_LENGTH` | 10737418240 | Cap on any request body, in bytes (10 GiB). `0` removes the limit |
| `MAX_IMAGE_PIXELS` | 400000000 | Pillow decompression bomb threshold for uploaded pictures |
| `TMP_DIR` | <system tmp>/zou | Working directory for uploads, encodings and the storage cache |
| `IS_SELF_HOSTED` | true | Announced to the client through `/config`; `false` on the Kitsu cloud offer |
| `CRISP_TOKEN` | (none) | Crisp chat widget token announced to the client through `/config` |
| `TELEMETRY_URL` | account.cg-wire.com endpoint | Where `zou telemetry` posts its anonymous usage figures |
| `DEFAULT_FILE_TREE` | default | File tree template applied to new productions (`zou/app/file_trees/`) |
| `DEFAULT_TIMEZONE` | Europe/Paris | Timezone of new accounts and of the studio, also stored in Redis (see `zou config`) |
| `DEFAULT_LOCALE` | en_US | Locale of new accounts and of the emails, also stored in Redis |
| `USER_LIMIT` | 100 | Maximum number of active human accounts; imports and sync refuse to create more |
| `REMOVE_FILES` | false | Delete the stored pictures and movies when their database row is deleted |
| `LOG_FILE_NOT_FOUND` | false | Log every picture or movie requested but absent from the store |
| `EVENT_HANDLERS_FOLDER` | ./event_handlers | Directory added to the Python path to load custom event handlers |
| `PLUGIN_FOLDER` | ./plugins | Directory where `zou install-plugin` unpacks the plugins |

## Database

PostgreSQL, through psycopg 3.

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_DRIVER` | postgresql+psycopg | SQLAlchemy driver |
| `DB_HOST` | localhost | PostgreSQL host |
| `DB_PORT` | 5432 | PostgreSQL port |
| `DB_USERNAME` | postgres | Database user |
| `DB_PASSWORD` | mysecretpassword | Database password |
| `DB_DATABASE` | zoudb | Database name |
| `DB_POOL_SIZE` | 30 | Connection pool size |
| `DB_MAX_OVERFLOW` | 60 | Connections opened beyond the pool under load |
| `DB_POOL_PRE_PING` | true | Check a connection before using it, drops the stale ones |
| `DB_POOL_RECYCLE` | 3600 | Recycle a connection after this many seconds |
| `DB_POOL_RESET_ON_RETURN` | commit | What SQLAlchemy does to a connection returned to the pool |

## Authentication and accounts

The JWT settings (7 days access, 15 days refresh, cookies and headers, `SameSite=Lax`) are fixed in `config.py`, not read from the environment.

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTH_STRATEGY` | auth_local_classic | `auth_local_classic` (database passwords), `auth_local_no_password` or `auth_remote_ldap` |
| `BCRYPT_LOG_ROUNDS` | 12 | Cost of the password hashes |
| `MIN_PASSWORD_LENGTH` | 8 | Minimum length accepted for a new password |
| `ENFORCE_2FA` | false | Require every account to set up a second factor; accounts without one get restricted tokens |
| `2FA_EXEMPT_USERS` | (none) | Comma-separated emails exempt from `ENFORCE_2FA` |
| `PROTECTED_ACCOUNTS` | (none) | Semicolon-separated emails that cannot be deactivated, deleted or changed by the sync and the imports |
| `ADMIN_TOKEN` | (none) | When set, mounts `/admin/config/check`, a bearer-token route comparing the environment and the stored configuration |

## LDAP

Used when `AUTH_STRATEGY=auth_remote_ldap` and by `zou sync-with-ldap-server`. The bind password comes from `LDAP_PASSWORD` and the bind user from `LDAP_USER`, read by the sync command.

| Variable | Default | Description |
|----------|---------|-------------|
| `LDAP_HOST` | 127.0.0.1 | Directory host |
| `LDAP_PORT` | 389 | Directory port |
| `LDAP_BASE_DN` | cn=Users,dc=zou,dc=local | Base of the user search |
| `LDAP_DOMAIN` | zou.local | NTLM domain (Active Directory) |
| `LDAP_GROUP` | (none) | Restrict the sync to the members of this group |
| `LDAP_IS_AD` | false | The directory is an Active Directory (NTLM bind, `sAMAccountName`) |
| `LDAP_IS_AD_SIMPLE` | false | Active Directory with a simple bind and `cn` as login |
| `LDAP_SSL` | false | Connect with LDAPS |
| `LDAP_FALLBACK` | false | When the directory is unreachable, accept the local password of the account |

## SAML

| Variable | Default | Description |
|----------|---------|-------------|
| `SAML_ENABLED` | false | Enable SAML single sign-on |
| `SAML_IDP_NAME` | (none) | Display name shown on the SAML login button |
| `SAML_METADATA_URL` | (none) | Identity provider metadata URL |
| `SAML_SKIP_2FA` | false | SAML sessions skip the 2FA setup gate (the identity provider handles MFA) |

## OIDC

OpenID Connect single sign-on. When enabled, a "Login with <provider>" button is shown on the login page; users are redirected to the provider, and on return a matching Kitsu account is found by email (or created on first login).

| Variable | Default | Description |
|----------|---------|-------------|
| `OIDC_ENABLED` | false | Enable OIDC SSO |
| `OIDC_IDP_NAME` | (none) | Display name shown on the OIDC login button |
| `OIDC_DISCOVERY_URL` | (none) | Provider OpenID configuration URL (ends with `/.well-known/openid-configuration`) |
| `OIDC_CLIENT_ID` | (none) | OAuth client identifier registered with the provider |
| `OIDC_CLIENT_SECRET` | (none) | OAuth client secret |
| `OIDC_SCOPES` | openid email profile | Space-separated scopes to request |
| `OIDC_EMAIL_CLAIM` | email | Claim used as the account email |
| `OIDC_GIVEN_NAME_CLAIM` | given_name | Claim used for the first name |
| `OIDC_FAMILY_NAME_CLAIM` | family_name | Claim used for the last name |
| `OIDC_REQUIRE_EMAIL_VERIFIED` | true | The provider must assert `email_verified == true`; set to false only for providers that do not emit the claim and whose emails are otherwise trusted |
| `OIDC_SKIP_2FA` | false | OIDC sessions skip Kitsu's 2FA setup gate (trust the IdP for MFA); when false, `ENFORCE_2FA` applies as usual |

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

## Redis

One Redis instance, five databases fixed in `config.py`: 0 revoked tokens, 1 memoization, 2 events, 3 job queue, 4 stored configuration.

| Variable | Default | Description |
|----------|---------|-------------|
| `KV_HOST` | localhost | Redis host |
| `KV_PORT` | 6379 | Redis port |
| `KV_PASSWORD` | (none) | Redis password |
| `CACHE_TYPE` | (none) | Flask-Caching backend override; `simple` keeps the memoization in process (the tests use it) |

## Event stream

| Variable | Default | Description |
|----------|---------|-------------|
| `EVENT_STREAM_HOST` | localhost | Host of the WebSocket event daemon (`zou-events`) |
| `EVENT_STREAM_PORT` | 5001 | Port of the event daemon |

## Search

Meilisearch is optional; the search routes answer nothing when `INDEXER_KEY` is unset.

| Variable | Default | Description |
|----------|---------|-------------|
| `INDEXER_HOST` | localhost | Meilisearch host |
| `INDEXER_PORT` | 7700 | Meilisearch port |
| `INDEXER_PROTOCOL` | http | Meilisearch scheme |
| `INDEXER_KEY` | (none) | Meilisearch master key; enables the indexer |
| `INDEXER_TIMEOUT` | 5000 | Meilisearch client timeout, in milliseconds |

## Mail

| Variable | Default | Description |
|----------|---------|-------------|
| `MAIL_ENABLED` | true | Send emails at all |
| `MAIL_SERVER` | localhost | SMTP server |
| `MAIL_PORT` | 25 | SMTP port |
| `MAIL_USERNAME` | (none) | SMTP user |
| `MAIL_PASSWORD` | (none) | SMTP password |
| `MAIL_USE_TLS` | false | STARTTLS |
| `MAIL_USE_SSL` | false | Implicit TLS |
| `MAIL_DEFAULT_SENDER` | no-reply@your-studio.com | From address |
| `MAIL_DEBUG` | false | Flask-Mail debug mode |
| `MAIL_DEBUG_BODY` | false | Log the body of every email sent |
| `MAIL_CHECK_DELIVERABILITY` | true | Check the domain of an email address when creating an account |

## Storage

Pictures, movies and files are stored through flask-fs2: on disk, in S3 or in Swift.

| Variable | Default | Description |
|----------|---------|-------------|
| `FS_BACKEND` | local | `local`, `s3` or `swift` |
| `PREVIEW_FOLDER` | ./previews | Root of the local storage and of the storage cache of the remote backends. `THUMBNAIL_FOLDER` is its former name |
| `THUMBNAIL_FOLDER` | (none) | Former name of `PREVIEW_FOLDER`, still read as a fallback |
| `FS_BUCKET_PREFIX` | (none) | Prefix of the bucket or container names |
| `FS_S3_REGION` | (none) | S3 region |
| `FS_S3_ENDPOINT` | (none) | S3 endpoint URL, for S3-compatible stores |
| `FS_S3_ACCESS_KEY` | (none) | S3 access key |
| `FS_S3_SECRET_KEY` | (none) | S3 secret key |
| `FS_S3_CREATE_BUCKET` | false | Create the buckets when they are missing |
| `FS_S3_AES256_ENCRYPTED` | false | Ask S3 for server-side AES-256 encryption |
| `FS_S3_AES256_KEY` | (none) | Customer key for the server-side encryption |
| `FS_SWIFT_AUTHURL` | (none) | Keystone authentication URL |
| `FS_SWIFT_USER` | (none) | Swift user |
| `FS_SWIFT_KEY` | (none) | Swift password |
| `FS_SWIFT_TENANT_NAME` | (none) | Swift tenant |
| `FS_SWIFT_REGION_NAME` | (none) | Swift region |
| `FS_SWIFT_AUTH_VERSION` | 3 | Keystone version |
| `FS_SWIFT_CREATE_CONTAINER` | false | Create the containers when they are missing |
| `FS_SWIFT_AES256_ENCRYPTED` | false | Ask Swift for server-side encryption |
| `FS_SWIFT_AES256_KEY` | (none) | Key for the server-side encryption |
| `FS_SWIFT_POOL_SIZE` | 20 | Connections kept to Swift |
| `FS_SWIFT_TIMEOUT` | 60 | Swift request timeout, in seconds |
| `FS_SWIFT_RETRIES` | 5 | Retries of a failed Swift request |
| `FS_SWIFT_TOKEN_CACHE_TTL` | 3600 | Seconds a Keystone token is shared through Redis between processes, `0` authenticates on every new connection; keep it below the token lifetime set in Keystone |
| `FS_SWIFT_ETAG_MISMATCH_POLICY` | log | When the ETag returned by Swift does not match the uploaded content: `log`, `raise` or `raise_and_delete` |

## Preview files

| Variable | Default | Description |
|----------|---------|-------------|
| `PREVIEW_SAVE_SOURCE_FILE` | false | Keep the uploaded source movie alongside the normalized preview. Ignored when the normalization runs on a remote worker: it reads the source from the object storage, so the source is uploaded there whatever this says (a warning is logged at startup) |
| `SKIP_NORMALIZATION_FULL` | false | Skip the movie normalization: the uploaded movie is stored as is, once, under `source` or `previews` (see below) |
| `SKIP_NORMALIZATION_HIGHDEF` | false | Skip only the high def (28M) encoding: the low def version is built and is the only movie stored |
| `SYNC_SOURCE_MOVIE_FILES` | false | Replicate the source movies when syncing from another instance |
| `MOVIE_HIGHDEF_BITRATE` | 28 | Default bitrate of the normalized movies, in Mbit/s; projects and task type links can override it |
| `MOVIE_LOWDEF_BITRATE` | 6 | Default bitrate of the low definition movies, in Mbit/s |
| `MOVIE_ENCODING_PRESET` | medium | x264 preset of the movie normalization |
| `MOVIE_VBV_BUFSIZE_FACTOR` | 2 | VBV buffer size as a multiple of the bitrate, which is also the cap; `0` drops the cap and keeps a plain average bitrate target |
| `PREVIEW_MISSING_FILE_RECHECK_DELAY` | 3600 | Seconds during which a preview known missing is answered 404 without asking the storage again |

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

## Job queue

Heavy work (normalization, playlist builds, tiles) can leave the web process for an RQ queue, and from there for Nomad jobs.

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_JOB_QUEUE` | false | Run the encodings and builds on the RQ queue (Redis database 3) instead of the request |
| `ENABLE_JOB_QUEUE_REMOTE` | false | Dispatch the queued jobs to Nomad |
| `JOB_QUEUE_NOMAD_HOST` | zou-nomad-01.zou | Nomad API host |
| `JOB_QUEUE_NOMAD_NORMALIZE_JOB` | (none) | Nomad job of the movie normalization |
| `JOB_QUEUE_NOMAD_PLAYLIST_JOB` | zou-playlist | Nomad job of the playlist builds |
| `JOB_QUEUE_NOMAD_TILE_JOB` | (none) | Nomad job of the tile sheets |
| `JOB_QUEUE_TIMEOUT` | 3600 | Timeout of a queued job, in seconds |

## Monitoring

| Variable | Default | Description |
|----------|---------|-------------|
| `SENTRY_ENABLED` | false | Report the server errors to Sentry |
| `SENTRY_DSN` | (none) | Sentry DSN of the API |
| `SENTRY_SR` | 1.0 | Sentry traces sample rate of the API |
| `SENTRY_DEBUG_URL` | (none) | When set, a route at this path raises on purpose to check the Sentry wiring |
| `SENTRY_KITSU_ENABLED` | false | Announce a Sentry configuration to the Kitsu front end through `/config` |
| `SENTRY_KITSU_DSN` | (none) | Sentry DSN handed to the front end |
| `SENTRY_KITSU_SR` | 0.1 | Sentry sample rate handed to the front end |
| `PROMETHEUS_METRICS_ENABLED` | false | Expose Prometheus metrics (needs the `monitoring` extra) |
