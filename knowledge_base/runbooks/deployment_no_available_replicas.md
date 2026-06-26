# Runbook: Deployment has no available replicas

## When to use
Use this runbook when a Deployment desired replicas count is greater than zero but available replicas is zero.

## Possible causes
- Pods are not Ready.
- Readiness probe is failing.
- Image pull failure.
- Scheduling failure.
- Application startup failure.
- Wrong service or probe configuration.

## Checks
1. kubectl rollout status deployment/<deployment> -n <namespace>
2. kubectl describe deployment <deployment> -n <namespace>
3. kubectl get pods -n <namespace>
4. kubectl describe pod <pod> -n <namespace>
5. kubectl logs <pod> -n <namespace>

## Fix
- Resolve the underlying pod readiness/startup issue.
- Fix readiness probe, image pull, scheduling, or application startup configuration.
- Verify available replicas becomes greater than zero.
