# Authentication and Authorization

## Authentication methods

| Method | Description |
|--------|-------------|
| Local | Email + password (bcrypt hashed) |
| LDAP | Active Directory integration |
| SAML | SSO via SAML metadata URL |
| API key | Bot/service account tokens (jti-based) |

## JWT tokens

- **Access token**: 7-day TTL, sent via cookie or `Authorization: Bearer` header
- **Refresh token**: 15-day TTL, httpOnly cookie (browser) or header (API)
- **Claims**: `sub` (user_id), `identity_type` (person/bot/person_api), `jti` (revocation ID)
- **Revocation**: Redis blocklist (DB 0), checked on every `@jwt_required()` call

## Two-factor authentication

Supported methods:
1. **TOTP** — Google Authenticator compatible (RFC 6238)
2. **Email OTP** — Time-limited code sent to registered email
3. **FIDO** — WebAuthn hardware/software authenticators
4. **Recovery codes** — Backup access codes

Flow: Login → 2FA challenge → Verify → Full access token issued.

If 2FA is required but not set up, a restricted token with `requires_2fa_setup=true` is issued, limiting the user to setup endpoints only.

## Roles

| Role | Level | Description |
|------|-------|-------------|
| admin | Highest | Full access to everything |
| manager | High | Project management, team assignment |
| supervisor | Medium | Task oversight within assigned projects |
| user (artist) | Standard | Work on assigned tasks |
| client | Restricted | View-only access to specific projects |
| vendor | Restricted | Limited access to assigned tasks only |

## Permission checking

Blueprints call permission helpers from `zou/app/utils/permissions.py`:

```python
check_admin_permissions()              # admin only
check_manager_permissions()            # admin or manager
check_at_least_supervisor_permissions() # supervisor, manager, or admin
has_client_permissions()               # True if role is client
has_vendor_permissions()               # True if role is vendor
```

Project/entity-level access is checked via `user_service`:

```python
user_service.check_project_access(project_id)    # user is team member
user_service.check_entity_access(entity_id)       # user has project access
user_service.check_manager_project_access(project_id) # user is manager of project
```

## Password policy

- Minimum length: 8 characters (configurable via `MIN_PASSWORD_LENGTH`)
- Bcrypt hashing with configurable rounds (`BCRYPT_LOG_ROUNDS`, default 12)
- Failed login attempt tracking (`login_failed_attemps` on Person model)
- Protected accounts (`PROTECTED_ACCOUNTS` config) exempt from password reset
