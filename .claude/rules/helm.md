---
description: Apply when creating or editing Helm templates, values files, or Chart.yaml. Covers values layering, ConfigMap injection, TLS, security contexts, naming, and ArgoCD compatibility.
globs: helm/**
---

## Values layering

- `values.yaml` must define **every** key used in templates. Per-environment files only override what differs.
- Never use `--set` in CI or GitOps — all config must be traceable to a committed file. Deploy as: `-f values.yaml -f values-{env}.yaml`.

## ConfigMap

- App env vars (`APPLICATION_NAME`, `ENVIRONMENT`, `VERSION`) are injected via `configmap.yaml` using `envFrom.configMapRef` in the Deployment.
- The Deployment's `checksum/config` annotation causes pods to roll when the ConfigMap changes. Do not remove it.
- Never store secrets in a ConfigMap. Use a Kubernetes `Secret` or External Secrets Operator for sensitive values.

## TLS and Ingress

- TLS terminates at the Ingress. The Flask app speaks HTTP only — do not add TLS to the application container.
- Required annotation: `cert-manager.io/cluster-issuer: letsencrypt-prod`. The ClusterIssuer must exist in the cluster before deploying.
- `ingress.tls[].secretName` must be unique per environment (e.g. `hello-platform-staging-tls`).
- `ingressClassName` comes from `values.yaml` — do not hardcode it in a template.

## Security contexts

Do not weaken these values:

```yaml
podSecurityContext:
  runAsNonRoot: true
  runAsUser: 999            # matches the 'app' user in the Dockerfile

securityContext:
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop: [ALL]
```

If a container needs a writable path, add an `emptyDir` volume mount — do not set `readOnlyRootFilesystem: false`.

## Naming

- Use `_helpers.tpl` named templates for all `name`, `labels`, and `selector` fields. Never hardcode the release name in a template.
- New templates follow the `hello-platform.<resource>` naming pattern.

## ArgoCD compatibility

ArgoCD runs `helm template` internally. A chart that fails `helm lint` or produces invalid Kubernetes YAML stalls the sync silently.

Always validate before pushing:

```bash
helm lint helm/
helm template hello-platform helm/ -f helm/values.yaml -f helm/values-prod.yaml \
  | kubeconform --strict --kubernetes-version 1.28.0 --summary
```

Do not use `helm.sh/hook` annotations for normal resources. Use `argocd.argoproj.io/sync-wave` if ordering is needed.
