# Redis key registry

Every key prefix our services use, who owns it, and TTL conventions.

## RED-001: Session cache
- **Service**: auth-service
- **Keys**: `session:{user_id}`, `session:meta:{user_id}`
- **TTL**: inherited from JWT `exp` (see ANTI-002)
- **Tags**: auth

## RED-002: Rate-limit buckets
- **Service**: api-gateway
- **Keys**: `ratelimit:{route}:{ip}`, `ratelimit:{route}:{user_id}`
- **TTL**: 60s sliding window

## RED-003: Pub/sub channels
- **Service**: notifier
- **Keys**: `channel:slack:{tenant}`, `channel:webhook:{tenant}`
- **TTL**: n/a (channels, not keys)
