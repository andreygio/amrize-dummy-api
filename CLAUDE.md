# hello-platform

Stateless Flask API that returns application metadata as JSON. Containerised with Docker, deployed to Kubernetes via ArgoCD using Helm.

## Project layout

```
app/          Flask application
tests/        pytest unit & integration tests
helm/         Helm chart (values.yaml + values-{env}.yaml overrides)
.github/      GitHub Actions workflow (code-review.yml)
```

## Key files

- [app/main.py](app/main.py) — two routes: `GET /` and `GET /health`
- [pyproject.toml](pyproject.toml) — single source of truth for all tool config
- [requirements.txt](requirements.txt) — runtime deps only
- [requirements-dev.txt](requirements-dev.txt) — adds test, lint, type, security tools
- [helm/values.yaml](helm/values.yaml) — base values; env overrides in `values-{env}.yaml`

## Language and tooling rules

Rule files live in `.claude/rules/` and are path-scoped via frontmatter globs — not loaded at session start:
- `.claude/rules/python.md` — active for `app/**` and `tests/**`
- `.claude/rules/helm.md` — active for `helm/**`
