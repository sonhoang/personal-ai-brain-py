# Design Note: Rate Limiting for the Public API

> SYNTHETIC SAMPLE DOCUMENT. Written for the personal-ai-brain evaluation set.
> The company, systems, people and numbers are invented.

Status: accepted. Authors: platform team. Last revised: May 2024.

## Problem

A small number of integrations send bursts of requests that slow the API down for
everyone else. Today we only have a global connection limit at the load balancer, which
punishes all clients equally and gives them no signal about what they did wrong.

## Decision

We use a token bucket per API key, enforced in the gateway and stored in Redis.

- Standard plan: 600 requests per minute, bucket size (burst) 100.
- Enterprise plan: 3,000 requests per minute, burst 500.
- Unauthenticated requests: 60 per minute per IP address, burst 10.

Each request removes one token. Tokens are refilled continuously, not once per minute,
so a client that stays under the average rate never sees a rejection.

## Response to clients

A rejected request gets HTTP 429 Too Many Requests with a Retry-After header in seconds.
Every response, accepted or not, carries X-RateLimit-Limit, X-RateLimit-Remaining and
X-RateLimit-Reset so clients can slow down before they hit the limit.

## Alternatives considered

A fixed window counter is simpler but allows twice the limit at the boundary between two
windows. A sliding log is exact but stores one entry per request, which costs too much
memory at our traffic. The token bucket needs two numbers per key.

## Failure behaviour

If Redis is unreachable the gateway fails open: requests are allowed and a metric
rate_limiter_degraded is incremented. We chose availability over strict enforcement
because an outage of the limiter should not become an outage of the API. An alert fires
if the gateway stays degraded for more than 2 minutes.

## Rollout

Limits start in report-only mode for two weeks, logging what would have been rejected.
Customers above 80% of their limit are contacted before enforcement begins.
