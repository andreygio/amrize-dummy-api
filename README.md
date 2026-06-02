# hello-platform

A minimal, stateless Flask API that returns application metadata as JSON. Built to demonstrate a production-ready containerized service with GitOps-compatible Helm packaging.

---

## Overview

### What was built

| Layer | Technology | Purpose |
|---|---|---|
| Application | Python 3.13 + Flask | HTTP API serving two endpoints |
| Runtime | Gunicorn | Production WSGI server with multi-worker/thread support |
| Container | Docker (python:3.13-slim) | Reproducible, minimal image |
| Kubernetes packaging | Helm v3 | Parameterised manifests for multi-environment GitOps |
| TLS | NGINX Ingress + cert-manager | HTTPS termination outside the application |

### Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Returns application metadata as JSON |
| `GET` | `/health` | Liveness/readiness probe — returns `{"status":"ok"}` |

**Info response example:**
```json
{
  "application": "hello-platform",
  "environment": "dev",
  "version": "1.0.0"
}
```

### Architecture summary

```
Internet
   │  HTTPS (443)
   ▼
NGINX Ingress Controller
   │  TLS terminated here; cert-manager provisions Let's Encrypt certs
   │  HTTP (80) forwarded internally
   ▼
Kubernetes Service (ClusterIP :80)
   │
   ▼
Pod(s) — Gunicorn on :8080
   │  env vars injected from ConfigMap
   └─ app/main.py (Flask)
```

The application itself is pure HTTP. TLS is a platform concern handled at the Ingress layer, keeping the application code free of certificate management.

Configuration flows in via environment variables only — no files, no databases, no shared state between instances. Any number of replicas can run identically.

---

## Setup Instructions

### Prerequisites

| Tool | Minimum version | Notes |
|---|---|---|
| Docker | 24+ | Image build and local testing |
| kubectl | 1.28+ | Cluster interaction |
| Helm | 3.12+ | Chart rendering and deployment |
| A Kubernetes cluster | 1.28+ | EKS / GKE / AKS / local (kind/k3d) |
| NGINX Ingress Controller | any | `helm install ingress-nginx ingress-nginx/ingress-nginx` |
| cert-manager | 1.14+ | `helm install cert-manager jetstack/cert-manager --set installCRDs=true` |

### Local development (Docker only)

```bash
# Copy and adjust env vars
cp .env.example .env

# Build
docker build -t hello-platform:1.0.0 .

# Run
docker run --rm -p 8080:8080 --env-file .env hello-platform:1.0.0

# Verify
curl http://localhost:8080/
curl http://localhost:8080/health
```

### Kubernetes deployment

**1. Push the image to your registry**

```bash
docker tag hello-platform:1.0.0 <your-registry>/hello-platform:1.0.0
docker push <your-registry>/hello-platform:1.0.0
```

Update `image.repository` in [helm/values.yaml](helm/values.yaml) to match.

**2. Create a cert-manager ClusterIssuer** (if not already present)

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: your-email@example.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
      - http01:
          ingress:
            class: nginx
```

```bash
kubectl apply -f clusterissuer.yaml
```

**3. Deploy**

```bash
# Dev
helm upgrade --install hello-platform ./helm \
  --namespace hello-platform --create-namespace

# Staging
helm upgrade --install hello-platform ./helm \
  --namespace hello-platform-staging --create-namespace \
  -f helm/values.yaml \
  -f helm/values-staging.yaml

# Production
helm upgrade --install hello-platform ./helm \
  --namespace hello-platform-prod --create-namespace \
  -f helm/values.yaml \
  -f helm/values-prod.yaml
```

**4. Verify the deployment**

```bash
kubectl -n hello-platform get pods,svc,ingress

# Once the Ingress has an IP/hostname and TLS cert is Ready:
curl https://hello-platform.example.com/
curl https://hello-platform.example.com/health
```

### Cleanup

```bash
helm uninstall hello-platform --namespace hello-platform
kubectl delete namespace hello-platform
```

---

## Design Decisions

### Service choices

**Flask over FastAPI or Django**
Flask was chosen for its minimal surface area. This service has no I/O, no database, and two endpoints; bringing in async machinery (FastAPI) or a full ORM framework (Django) would add complexity with no benefit. Flask's simplicity also makes the intent of the code immediately readable.

**Gunicorn as the WSGI server**
Flask's built-in development server is single-threaded and not suitable for production. Gunicorn provides synchronous multi-worker concurrency appropriate for a CPU-light, stateless API. The configuration (`--workers 2 --threads 4`) gives 8 concurrent request slots per pod without the overhead of an async event loop.

**Helm over raw YAML or Kustomize**
Helm provides parameterised templating with a first-class values override model (`-f values-prod.yaml`), which maps cleanly to GitOps workflows (Argo CD, Flux). Kustomize patches are harder to reason about at scale. Plain YAML has no environment promotion story without duplication.

**TLS at the Ingress, not in the application**
Terminating TLS in the app would require mounting cert files, managing rotation, and adding library dependencies. Delegating this to cert-manager + NGINX Ingress is the standard Kubernetes pattern: certs are renewed automatically, the application code stays simple, and the trust boundary is at the cluster edge.

**ConfigMap for environment variables**
Application configuration is injected via a Kubernetes ConfigMap rather than baked into the image or passed as raw `--set` flags. This keeps the image environment-agnostic and provides a clear audit trail of what configuration was applied to which deployment. The deployment includes a `checksum/config` annotation so pods automatically roll when the ConfigMap changes.

### Tradeoffs

| Decision | Upside | Tradeoff accepted |
|---|---|---|
| Single-stage Dockerfile | Simplicity | Slightly larger image than a multi-stage build; acceptable for a Python app with no compiled artefacts |
| `python:3.13-slim` base | Small attack surface, fast pulls | No build tools if native extensions are ever added |
| Synchronous Gunicorn workers | Easy reasoning, no async complexity | Would need to switch to Uvicorn workers if async endpoints were added |
| Let's Encrypt via cert-manager | Free, automated | Requires a public DNS record and outbound HTTP-01 challenge; not suitable for air-gapped or private clusters without DNS-01 |
| ConfigMap for all env vars | Simple, visible | Secrets (API keys, DB passwords) must use `Secret` objects with appropriate RBAC — ConfigMap is not suitable for sensitive values |

### Reusable platform capabilities

The following elements of this design are good candidates to standardize across an organization rather than repeat per service:

- **Helm chart skeleton** (`_helpers.tpl`, Ingress + cert-manager pattern, HPA, security contexts) — package this as a shared library chart (Helm `type: library`) or an internal chart template repository. Teams inherit sensible defaults and only override what differs.

- **Non-root container pattern** — the `addgroup/adduser` + `USER app` + `runAsNonRoot: true` combination should be enforced org-wide via a policy (OPA Gatekeeper or Kyverno), not left to individual teams.

- **`readOnlyRootFilesystem: true` + dropped capabilities** — same story: a platform-level PodSecurity admission policy or OPA constraint prevents teams from accidentally shipping over-privileged containers.

- **cert-manager ClusterIssuer** — provision one issuer per cluster centrally; services reference it by annotation name. Teams should never manage their own TLS certificates.

- **Health endpoint contract** — a standardized `/health` path returning `{"status":"ok"}` with HTTP 200 should be an org-wide convention. Platform tooling (Ingress defaults, Datadog synthetic monitors, GitOps health checks) can then assume this path unconditionally.

- **ConfigMap-driven configuration** — the pattern of injecting `APPLICATION_NAME`, `ENVIRONMENT`, `VERSION` from a ConfigMap built by the Helm chart gives every service a consistent metadata shape, useful for log correlation, tracing, and dashboards.

### Cost and security reasoning

**Cost**
- The default resource request (50m CPU / 64Mi memory) is intentionally conservative for a metadata API. This avoids over-provisioning cluster capacity for a low-traffic service.
- Production HPA is set to scale from 3–10 replicas at 70% CPU, meaning the cluster only pays for extra capacity under real load.
- `IfNotPresent` pull policy avoids redundant registry egress on pod restarts.

**Security**
- The container runs as a non-root system user (UID 999) with no shell, limiting blast radius if the process is compromised.
- `readOnlyRootFilesystem: true` prevents a compromised process from writing malicious files to the container filesystem.
- All Linux capabilities are dropped (`capabilities.drop: [ALL]`). This service requires none.
- `allowPrivilegeEscalation: false` closes the `setuid`/`setgid` escalation path.
- TLS is enforced end-to-end from the cluster edge; internal traffic stays on the private cluster network.
- Dependency surface is minimal: two packages (`flask`, `gunicorn`) with pinned versions reduce the supply-chain attack surface.

---

## Limitations & Future Improvements

### What would be done differently with more time

**Multi-stage Docker build**
The current Dockerfile is single-stage. A multi-stage build would separate the dependency installation step from the final runtime image, allowing the `pip install` layer to run in a build image with full tooling while the final image carries only the installed packages. This reduces image size and eliminates any build-time tools from the production artifact.

**Image scanning in CI**
There is no CI pipeline in this repository. A production setup would include a GitHub Actions (or equivalent) workflow that builds, scans the image with Trivy or Grype, and pushes to the registry only on a clean scan. The Helm chart's `image.tag` would then be updated automatically on merge to main.

**Structured logging**
The application currently relies on Flask/Gunicorn default output. In a real service, logs would be emitted as JSON (using `python-json-logger` or structlog), with `correlation_id`, `environment`, `version`, and `application` fields on every log line — making them joinable with distributed traces and queryable in a log aggregation platform (Datadog, Loki, CloudWatch).

**Distributed tracing**
Adding OpenTelemetry instrumentation (`opentelemetry-instrumentation-flask`) would produce trace spans for every request with zero application-code changes via auto-instrumentation. This is particularly valuable once this service is one of many in a service mesh.

**Request validation and versioned API paths**
The current single route at `/` has no versioning. A real API would prefix routes (`/v1/info`) so breaking changes can be introduced under a new version while clients migrate.

**Kubernetes Secrets for sensitive configuration**
The current ConfigMap approach is appropriate for non-sensitive values. If `VERSION` were replaced by a build token or the service gained a downstream API key, those values would need to live in a `Secret` (ideally managed by an external secrets operator such as External Secrets Operator backed by AWS Secrets Manager or HashiCorp Vault) rather than a ConfigMap.

**Network policy**
No `NetworkPolicy` is defined, so pods can receive traffic from any other pod in the cluster. A default-deny ingress policy scoped to only allow traffic from the NGINX Ingress controller namespace would be the minimum hardening step.

**Helm chart tests**
Helm supports `helm test` via test hook pods. A simple test that curls `/health` after deployment and asserts HTTP 200 would catch misconfigured ingress or broken image references before a release is marked stable by a GitOps controller.

**Dedicated health vs readiness logic**
Both the liveness and readiness probes currently call the same `/health` endpoint. For a service with startup dependencies (a database, a downstream API), a separate `/ready` endpoint that verifies those dependencies are reachable would prevent traffic from routing to a pod that is alive but not yet able to serve requests — without causing unnecessary restarts by making the same check influence liveness.
