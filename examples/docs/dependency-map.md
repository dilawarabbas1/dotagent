# Service dependency map

Which services depend on which. Edges are sync HTTP unless tagged async.

## DEP-001: Auth flow
- **Services**: api-gateway, auth-service, users-service
- **Tags**: sync

Request → api-gateway → auth-service (verify JWT) → users-service (load
user). All sync; api-gateway times out at 2s.

## DEP-002: Notification flow
- **Services**: api → events_outbox → notifier → (slack | webhook | email)
- **Tags**: async

Producers write to `events_outbox`. notifier polls (2s) and dispatches.
Slack/webhook/email failures retry per ANTI-003.

## DEP-003: Tenant resolution
- **Services**: api-gateway → tenants-service
- **Tags**: sync, cached

Tenant lookup is hot-pathed via a 5-minute LRU in api-gateway. Invalidation
is best-effort on tenant config change; consistency is eventual.
