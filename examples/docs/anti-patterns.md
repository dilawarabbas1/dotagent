# Anti-patterns

Patterns the AI should not introduce. Past evidence is the strongest signal —
each entry cites the bugs it caused.

## ANTI-001: Direct DB writes from controllers
- **Severity**: high
- **Files**: services/api/controllers/*.py
- **Component**: api
- **Tags**: layering

Controllers must call repositories. Direct `cursor.execute()` from a
controller bypasses transaction scoping, retries, and audit. Caused BUG-005.

## ANTI-002: Fixed-TTL caching of expiring artifacts
- **Severity**: critical
- **Files**: services/auth/jwt.py, services/cache/redis.js
- **Tags**: security, cache

Any artifact with its own `exp` claim must be cached with that exp, not a
fixed TTL. Caused BUG-007.

## ANTI-003: Unbounded retry loops on external HTTP
- **Severity**: medium
- **Files**: services/notifier/*.py
- **Tags**: reliability

Every external HTTP call needs a retry cap + exponential backoff. Caused
BUG-004.
