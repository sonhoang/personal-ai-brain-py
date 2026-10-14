# Incident Report INC-2024-017: Orders Database Failover

> SYNTHETIC SAMPLE DOCUMENT. Written for the personal-ai-brain evaluation set.
> The company, systems, people and numbers are invented.

## Summary

On 12 March 2024 the primary PostgreSQL instance behind the orders service (orders-db-1)
became unresponsive at 09:41 UTC after its data volume reached 100% of capacity. The
automatic failover to the standby (orders-db-2) did not complete because the standby was
behind the primary by 9 minutes of write-ahead log. Customers could not place orders for
14 minutes. Read-only pages such as order history stayed available from the cache.

## Timeline (UTC)

- 09:41 Disk on orders-db-1 reaches 100%. Writes start failing.
- 09:43 Paging alert "orders error rate above 5%" fires. On-call engineer acknowledges.
- 09:46 Patroni refuses to promote orders-db-2 because replication lag exceeds the
  configured maximum_lag_on_failover of 1 MB.
- 09:49 On-call deletes old WAL archive files on orders-db-1 to free space; writes resume
  partially.
- 09:55 Full recovery. Orders backlog drains within 6 minutes.

## Root cause

A nightly analytics export had been moved onto orders-db-1 two weeks earlier. It wrote
temporary files to the same volume as the database and grew by about 40 GB per night.
The disk-usage alert threshold was set at 95%, but the export filled the remaining 5% in
under three minutes, so the alert and the outage arrived together.

The standby lag had a separate cause: the replication slot on orders-db-2 was throttled by
a network bandwidth limit of 50 Mbit/s that was left over from a data-centre migration.

## What went well

The cached read path kept order history and tracking pages working for every customer.
The on-call engineer found the full disk within five minutes using the runbook dashboard.

## Action items

1. Move the analytics export to a read replica. Owner: data platform team. Due 29 March.
2. Lower the disk-usage warning to 80% and page at 90%. Owner: SRE. Due 19 March.
3. Remove the 50 Mbit/s replication bandwidth limit. Owner: network team. Done 13 March.
4. Add an alert when replication lag is above 30 seconds for 5 minutes. Owner: SRE.
5. Run a failover drill every quarter, starting in Q2 2024.
