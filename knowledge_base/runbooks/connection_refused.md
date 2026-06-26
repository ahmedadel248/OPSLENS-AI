# Runbook: Application ConnectionRefused

## When to use
Use this runbook when application logs show ConnectionRefused while calling another service.

## Possible causes
- Target service has no ready endpoints.
- Service targetPort is wrong.
- Dependency pod is not Ready.
- Application is calling the wrong host or port.
- NetworkPolicy or firewall blocks traffic.

## Checks
1. Check client logs.
2. Check target Service and endpoints.
3. Check target pod readiness.
4. Check Service DNS name and port.
5. Check recent Kubernetes events.

## Fix
- Fix the service port/targetPort if incorrect.
- Fix readiness probe if it prevents endpoints from being created.
- Ensure target deployment has available replicas.
- Re-test the client call.
