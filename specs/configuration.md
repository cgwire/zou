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

## LDAP / SAML

| Variable | Default | Description |
|----------|---------|-------------|
| `LDAP_HOST` | | LDAP server host |
| `LDAP_PORT` | | LDAP server port |
| `LDAP_BASE_DN` | | LDAP base distinguished name |
| `SAML_ENABLED` | false | Enable SAML SSO |
| `SAML_METADATA_URL` | | SAML IdP metadata URL |
