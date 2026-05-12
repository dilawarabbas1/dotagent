# Architecture

High-level shape of the system. Each H2 is one component or boundary.

## Front door: api-gateway
- **Service**: api-gateway
- **Files**: services/api-gateway/

All ingress lands here. Validates JWT, applies rate limits (see RED-002),
resolves tenant (DEP-003), routes to backing services.

## Auth: auth-service
- **Service**: auth-service
- **Files**: services/auth/

Issues and verifies JWTs. Holds the session cache (RED-001). Token rotation
is a critical hot path — see ANTI-002.

## Users: users-service
- **Service**: users-service
- **Files**: services/users/
- **Tables**: users, audit_log (DB-001)

Owner of `users` + `audit_log`. All other services read users via this
service's API, not directly.

## Tenants: tenants-service
- **Service**: tenants-service
- **Tables**: tenants, tenant_users, tenant_settings (DB-002)

Multi-tenant config + membership. Always lookup by id, never by name.

## Notifier
- **Service**: notifier
- **Tables**: events_outbox (DB-003)
- **Files**: services/notifier/

Async: reads from `events_outbox`, dispatches to slack/webhook/email,
marks `delivered_at`. See DEP-002.
