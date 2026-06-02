# hello-platform

A minimal, stateless Flask API that returns application metadata as JSON. Built to demonstrate a production-ready containerized service with a full CI/CD pipeline and GitOps-compatible Helm packaging.

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
| PR pipeline | GitHub Actions (`code-review.yml`) | Linting, type checking, tests, security scans, Helm validation |
| Build pipeline | GitHub Actions (`build.yml`) | Image build, push to GHCR, automated Helm values update |

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

## CI/CD Pipelines

### PR pipeline — `code-review.yml`

Triggered on every pull request to `main` or `develop`. All jobs run in parallel; `all-checks-pass` is the single required status check to register in branch protection.

| Job | Tools | Fails on |
|---|---|---|
| `secret-detection` | Gitleaks (full history scan) | Any credential in the diff |
| `lint` | black · isort · flake8-bugbear | Style or import order violations |
| `type-check` | mypy (strict) | Missing annotations or type errors |
| `static-analysis` | Bandit + pip-audit | Security findings (SARIF → GitHub Security tab) |
| `test` | pytest + pytest-cov | Test failures or coverage < 80% |
| `build` | Docker Buildx + Trivy | CRITICAL/HIGH CVEs in the image |
| `helm-validate` | helm lint × 3 + kubeconform | Invalid chart or manifests against K8s 1.28 schema |
| `argocd-diff` | argocd app diff | Informational only — posts diff to job summary |

### Build pipeline — `build.yml`

Triggered on every push to `main` (i.e. merged PR). Runs two sequential jobs:

```
merge to main
     │
     ▼
build-push
  • logs in to ghcr.io with GITHUB_TOKEN
  • tags image: sha-<7chars>  +  latest
  • builds with GHA layer cache, pushes to GHCR
     │
     ▼
update-helm
  • updates image.repository and image.tag in helm/values.yaml
  • commits back to main (GITHUB_TOKEN commits don't re-trigger workflows)
  • ArgoCD detects the diff and syncs the cluster
```

The image is published to `ghcr.io/<owner>/hello-platform`.

---

## Setup Instructions

### Prerequisites

| Tool | Minimum version | Notes |
|---|---|---|
| Python | 3.13 | Local development and testing |
| Docker | 24+ | Image build and local testing |
| kubectl | 1.28+ | Cluster interaction |
| Helm | 3.12+ | Chart rendering and deployment |
| A Kubernetes cluster | 1.28+ | EKS / GKE / AKS / local (kind/k3d) |
| NGINX Ingress Controller | any | `helm install ingress-nginx ingress-nginx/ingress-nginx` |
| cert-manager | 1.14+ | `helm install cert-manager jetstack/cert-manager --set installCRDs=true` |

### Local development

```bash
# Install dev dependencies (includes Flask, pytest, black, mypy, bandit, etc.)
pip install -r requirements-dev.txt

# Run the app directly
python -m app.main

# Run tests with coverage
pytest -v

# Format and lint
black app/ tests/ && isort app/ tests/
flake8 app/ tests/
mypy app/
```

### Local development (Docker)

```bash
# Copy and adjust env vars
cp .env.example .env

# Build
docker build -t hello-platform:dev .

# Run
docker run --rm -p 8080:8080 --env-file .env hello-platform:dev

# Verify
curl http://localhost:8080/
curl http://localhost:8080/health
```

### Kubernetes deployment

Image builds and `helm/values.yaml` updates are automated by the build pipeline on every merge to `main`. Manual steps are only needed for first-time cluster setup.

**1. Create a cert-manager ClusterIssuer** (once per cluster)

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

**2. Deploy**

```bash
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

After first deploy, ArgoCD takes over — subsequent image updates are applied automatically when the build pipeline commits a new `image.tag` to `helm/values.yaml`.

**3. Verify the deployment**

```bash
kubectl -n hello-platform-prod get pods,svc,ingress

# Once the Ingress has an address and the TLS cert is Ready:
curl https://hello-platform.example.com/
curl https://hello-platform.example.com/health
```

### Cleanup

```bash
helm uninstall hello-platform --namespace hello-platform-prod
kubectl delete namespace hello-platform-prod
```

---

## Design Decisions

### Service choices

**Flask over FastAPI or Django**
Flask was chosen for its minimal surface area. This service has no I/O, no database, and two endpoints; bringing in async machinery (FastAPI) or a full ORM framework (Django) would add complexity with no benefit. Flask's simplicity also makes the intent of the code immediately readable.

**Gunicorn as the WSGI server**
Flask's built-in development server is single-threaded and not suitable for production. Gunicorn provides synchronous multi-worker concurrency appropriate for a CPU-light, stateless API. The configuration (`--workers 2 --threads 4`) gives 8 concurrent request slots per pod without the overhead of an async event loop.

**Helm over raw YAML or Kustomize**
Helm provides parameterised templating with a first-class values override model (`-f values-prod.yaml`), which maps cleanly to GitOps workflows (ArgoCD, Flux). Kustomize patches are harder to reason about at scale. Plain YAML has no environment promotion story without duplication.

**TLS at the Ingress, not in the application**
Terminating TLS in the app would require mounting cert files, managing rotation, and adding library dependencies. Delegating this to cert-manager + NGINX Ingress is the standard Kubernetes pattern: certs are renewed automatically, the application code stays simple, and the trust boundary is at the cluster edge.

**ConfigMap for environment variables**
Application configuration is injected via a Kubernetes ConfigMap rather than baked into the image or passed as raw `--set` flags. This keeps the image environment-agnostic and provides a clear audit trail of what configuration was applied to which deployment. The deployment includes a `checksum/config` annotation so pods automatically roll when the ConfigMap changes.

**GHCR as the container registry**
GitHub Container Registry requires no additional secrets — `GITHUB_TOKEN` is sufficient and is automatically scoped to the repository. The build pipeline uses a short-SHA tag (`sha-<7chars>`) for immutable traceability and a `latest` tag for convenience. The SHA tag is written back to `helm/values.yaml` by the build pipeline so ArgoCD always deploys the exact commit that triggered the build.

**Single-repo GitOps**
The Helm chart and application code live in the same repository. The build pipeline commits updated image tags directly to `main`. This is simpler than a two-repo setup (app repo + gitops repo) and appropriate for a single service. At scale, separating the gitops repo prevents the app history from being polluted with automated tag-bump commits.

### Tradeoffs

| Decision | Upside | Tradeoff accepted |
|---|---|---|
| Single-stage Dockerfile | Simplicity | Slightly larger image than a multi-stage build; acceptable for a Python app with no compiled artefacts |
| `python:3.13-slim` base | Small attack surface, fast pulls | No build tools if native extensions are ever added |
| Synchronous Gunicorn workers | Easy reasoning, no async complexity | Would need to switch to Uvicorn workers if async endpoints were added |
| Let's Encrypt via cert-manager | Free, automated | Requires a public DNS record and outbound HTTP-01 challenge; not suitable for air-gapped clusters without DNS-01 |
| ConfigMap for all env vars | Simple, visible | Secrets (API keys, DB passwords) must use `Secret` objects — ConfigMap is not suitable for sensitive values |
| Single-repo GitOps | Less operational overhead | Automated tag-bump commits appear in app git history |

### Reusable platform capabilities

The following elements are good candidates to standardize across an organization:

- **Helm chart skeleton** (`_helpers.tpl`, Ingress + cert-manager pattern, HPA, security contexts) — package as a shared library chart (Helm `type: library`) or an internal chart template repository. Teams inherit sensible defaults and only override what differs.

- **CI/CD pipeline templates** — the two GitHub Actions workflows (PR checks and build-push) are generic enough to be shared as reusable workflows (`workflow_call`). Teams reference them by version rather than copying YAML.

- **Non-root container pattern** — the `addgroup/adduser` + `USER app` + `runAsNonRoot: true` combination should be enforced org-wide via OPA Gatekeeper or Kyverno, not left to individual teams.

- **`readOnlyRootFilesystem: true` + dropped capabilities** — a platform-level PodSecurity admission policy prevents teams from accidentally shipping over-privileged containers.

- **cert-manager ClusterIssuer** — provision one issuer per cluster centrally; services reference it by annotation name. Teams should never manage their own TLS certificates.

- **Health endpoint contract** — a standardized `/health` path returning `{"status":"ok"}` with HTTP 200 should be an org-wide convention. Platform tooling (Ingress defaults, synthetic monitors, GitOps health checks) can then assume this path unconditionally.

- **ConfigMap-driven service identity** — injecting `APPLICATION_NAME`, `ENVIRONMENT`, `VERSION` from a ConfigMap gives every service a consistent metadata shape, useful for log correlation, tracing, and dashboards.

### Cost and security reasoning

**Cost**
- The default resource request (50m CPU / 64Mi memory) is intentionally conservative for a metadata API. This avoids over-provisioning cluster capacity for a low-traffic service.
- Production HPA scales from 3–10 replicas at 70% CPU, meaning the cluster only pays for extra capacity under real load.
- `IfNotPresent` pull policy avoids redundant registry egress on pod restarts.
- GHA layer caching (`type=gha`) significantly reduces build times for repeated merges.

**Security**
- The container runs as a non-root system user (UID 999) with no shell, limiting blast radius if the process is compromised.
- `readOnlyRootFilesystem: true` prevents a compromised process from writing malicious files to the container filesystem.
- All Linux capabilities are dropped (`capabilities.drop: [ALL]`). This service requires none.
- `allowPrivilegeEscalation: false` closes the `setuid`/`setgid` escalation path.
- TLS is enforced end-to-end from the cluster edge; internal traffic stays on the private cluster network.
- Dependency surface is minimal: two runtime packages (`flask`, `gunicorn`) with pinned versions reduce the supply-chain attack surface.
- Gitleaks scans the full commit history on every PR; Bandit and Trivy results are uploaded to the GitHub Security tab.

---

## Limitations & Future Improvements

**Multi-stage Docker build**
The current Dockerfile is single-stage. A multi-stage build would separate the `pip install` layer from the final runtime image, producing a smaller artifact with no build tooling present in production.

**Structured logging**
The application relies on Flask/Gunicorn default output. In a real service, logs would be emitted as JSON (using `python-json-logger` or structlog), with `correlation_id`, `environment`, `version`, and `application` fields on every line — making them joinable with distributed traces and queryable in a log aggregation platform.

**Distributed tracing**
Adding OpenTelemetry instrumentation (`opentelemetry-instrumentation-flask`) would produce trace spans for every request with zero application-code changes via auto-instrumentation.

**Versioned API paths**
The current route at `/` has no versioning. A real API would prefix routes (`/v1/info`) so breaking changes can be introduced under a new version while clients migrate.

**Kubernetes Secrets for sensitive configuration**
The ConfigMap approach is appropriate for non-sensitive values. Any downstream API keys or tokens would need to live in a `Secret` managed by an external secrets operator (External Secrets Operator backed by AWS Secrets Manager or HashiCorp Vault).

**Network policy**
No `NetworkPolicy` is defined. A default-deny ingress policy scoped to only allow traffic from the NGINX Ingress controller namespace would be the minimum hardening step.

**Helm chart tests**
Helm supports `helm test` via test hook pods. A simple test that curls `/health` after deployment and asserts HTTP 200 would catch misconfigured ingress or broken image references before ArgoCD marks a sync as healthy.

**Dedicated readiness vs liveness logic**
Both probes call the same `/health` endpoint. For a service with startup dependencies, a separate `/ready` endpoint that verifies those dependencies are reachable would prevent traffic from routing to a pod that is alive but not yet able to serve requests.

**Two-repo GitOps**
For a fleet of services, separating the application repository from the GitOps repository (which holds only Helm values and image tags) keeps deployment history clean and allows platform teams to manage rollouts independently of application releases.
