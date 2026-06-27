# Service Selector Mismatch / Empty Service Endpoints

## Problem

A Kubernetes Service has no active endpoints because its selector does not match the labels on the intended backend Pods.

## Common Symptoms

- Service exists but has no endpoints.
- Frontend or client pods cannot reach the backend Service.
- Application logs show connection refused, timeout, or service unreachable errors.
- Backend pods may be healthy, but traffic is not routed to them.

## Investigation Steps

1. Check the Service selector.

```bash
kubectl get svc <service-name> -n <namespace> -o yaml
```

2. Check backend Pod labels.

```bash
kubectl get pods -n <namespace> --show-labels
```

3. Check Service endpoints.

```bash
kubectl get endpoints <service-name> -n <namespace>
```

4. Compare the Service selector with the Pod labels.

## Recommended Fix

Update either:

- the Service selector to match the backend Pod labels, or
- the Deployment template labels to match the Service selector.

The safer live fix is usually to patch the Service selector if the backend pods are already healthy.

## Verification

After fixing the selector:

```bash
kubectl get endpoints <service-name> -n <namespace>
kubectl logs deployment/<frontend-deployment> -n <namespace> --tail=20
```

Expected result:

- Service endpoints should contain backend Pod IPs.
- Client/frontend logs should stop showing connection failures.