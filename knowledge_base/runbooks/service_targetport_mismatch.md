# Runbook: Kubernetes Service targetPort mismatch

## When to use
Use this runbook when a Kubernetes Service targetPort does not match the containerPort exposed by the selected pods.

## Typical symptoms
- Service has no ready endpoints.
- Frontend or client logs show ConnectionRefused.
- Readiness probe may fail if it points to the same wrong port.
- Pods may be Running but not Ready.

## Checks
1. Inspect the Service:
   kubectl get svc <service> -n <namespace> -o yaml
2. Inspect matching pod labels:
   kubectl get pods -n <namespace> --show-labels
3. Inspect container ports:
   kubectl get pod <pod> -n <namespace> -o yaml
4. Inspect endpoints:
   kubectl get endpoints <service> -n <namespace>
5. Inspect readiness probe:
   kubectl describe pod <pod> -n <namespace>

## Fix
- Update Service targetPort to match the real containerPort.
- Update readinessProbe port if it points to the wrong port.
- Re-apply manifests.
- Verify pods become Ready.
- Verify Service endpoints are created.
- Verify client logs no longer show ConnectionRefused.

## Verification
kubectl get pods -n <namespace>
kubectl get endpoints <service> -n <namespace>
kubectl logs deployment/<client-deployment> -n <namespace> --tail=20
