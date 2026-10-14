# Q3 2024 Reliability Review

> SYNTHETIC SAMPLE DOCUMENT. Written for the personal-ai-brain evaluation set.
> The company, systems, people and numbers are invented.

## Headline numbers

The customer-facing availability target is 99.9% per quarter. In Q3 2024 the API
reached 99.95%, checkout 99.91% and the mobile app backend 99.87%, which missed the
target. Median time to acknowledge a page was 3 minutes; median time to resolve was
38 minutes.

## Incidents

There were 7 incidents in Q3, down from 11 in Q2. Two were severity 1. The mobile
backend miss came from one 2-hour outage on 4 August, when an expired TLS certificate
on an internal service broke push notifications and login refresh. Certificate expiry
is now monitored with a 21-day warning.

## Follow-up on earlier action items

The quarterly failover drill introduced after the orders database incident ran in July
and September. Both drills promoted the standby in under 60 seconds. The analytics export
now runs on a read replica.

Pump station telemetry from the water operations team is included in this review for the
first time. Two vibration alarms were raised in Q3, both traced to bearing wear on the
same pump, which was replaced in September.

## Priorities for Q4

1. Bring the mobile backend back above 99.9%.
2. Cut median time to resolve below 30 minutes by attaching runbooks to every alert.
3. Retire the last services that still deploy without a canary.
