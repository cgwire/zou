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
| `PREVIEW_SAVE_SOURCE_FILE` | false | Keep the uploaded source movie alongside the normalized preview |

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
