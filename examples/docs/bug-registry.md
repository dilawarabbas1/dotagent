# Bug Registry

Every shipped bug we want our AI agents to know about. Newest first.

## BUG-007: Stale JWT cache accepts revoked tokens
- **Severity**: critical
- **Files**: services/auth/jwt.py, services/cache/redis.js
- **Component**: auth-service
- **Tags**: security, auth, cache

The JWT cache TTL (60s) exceeded the token rotation window (30s), so revoked
tokens kept verifying for up to 60s after rotation. Fixed by tying cache
expiry to the JWT's own `exp` claim.

**Prevention**: any caching of auth artifacts must inherit the artifact's
own expiry — never a fixed TTL.

## BUG-006: Pagination cursor leaked into logs
- **Severity**: medium
- **File**: services/api/list.py
- **Component**: api
- **Tags**: privacy

Pagination cursors contained user-id segments and were logged at INFO. Now
hashed before logging.

## BUG-005: Migration order mismatch on cold deploy
- **Severity**: high
- **Tables**: users, audit_log
- **Files**: migrations/2026_03_users.sql, migrations/2026_03_audit.sql
- **Component**: db

`audit_log` migration referenced `users.id` before the column existed on
fresh databases. Now both tables are created in the same transaction.

## BUG-004: Slack webhook retry storm
- **Severity**: medium
- **File**: services/notifier/slack.py
- **Component**: notifier

A 502 from Slack triggered an unbounded retry loop. Now capped at 3
attempts with exponential backoff.
