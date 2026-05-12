# Database impact map

Tables and columns that hot-paths touch, and what depends on them.

## DB-001: Users + audit_log
- **Tables**: users, audit_log
- **Files**: services/users/repo.py, services/audit/repo.py
- **Component**: users-service

Writes to `users.email` mirror to `audit_log.actor_email` in the same
transaction. Any change to `users.email` shape (length, charset) must
update `audit_log.actor_email` in lockstep.

## DB-002: Tenants
- **Tables**: tenants, tenant_users, tenant_settings
- **Files**: services/tenants/repo.py
- **Component**: tenants-service

Multi-tenant scoping is enforced via `tenant_users.tenant_id`. Never query
tenants by name; always by id.

## DB-003: Events outbox
- **Tables**: events_outbox
- **Files**: services/notifier/outbox.py
- **Component**: notifier

The notifier reads from `events_outbox` and marks `delivered_at` on success.
Never delete from `events_outbox`; soft-delete via `delivered_at`.
