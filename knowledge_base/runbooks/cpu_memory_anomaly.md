# Runbook: CPU and Memory anomaly

## When to use
Use this runbook when node or workload metrics show abnormal CPU and memory behavior.

## Possible causes
- Traffic spike.
- Batch job.
- Infinite loop or runaway process.
- Memory leak.
- Recent deployment causing resource pressure.
- Resource requests/limits are missing or too low.

## Checks
1. kubectl top nodes
2. kubectl top pods -A
3. Check recent deployments.
4. Check pod restart count.
5. Check OOMKilled events.
6. Check application logs.

## Fix
- Identify top resource-consuming pods.
- Scale or restart affected workloads if needed.
- Tune requests/limits.
- Roll back bad deployment if correlated.
- Continue correlating with logs, events, and config signals before declaring it the root cause.
