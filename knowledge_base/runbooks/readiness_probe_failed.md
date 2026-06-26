# Runbook: Kubernetes readiness probe failed

## When to use
Use this runbook when Kubernetes events show Unhealthy or readiness probe failures.

## Possible causes
- Probe checks the wrong port.
- Probe checks the wrong path.
- Application is not listening yet.
- Application startup is slow.
- Service dependency is missing.

## Checks
1. kubectl describe pod <pod> -n <namespace>
2. Check readinessProbe configuration.
3. Check container ports.
4. Check application logs.
5. Check whether the application listens on the expected port.

## Fix
- Update readinessProbe port/path to match the application.
- Increase initialDelaySeconds if startup is slow.
- Fix application startup or dependency configuration.
- Verify pod becomes Ready.
