---
description: Apply when creating or editing Python source files or tests. Covers runtime constraints, env var pattern, code style, type annotations, testing conventions, security, and dependency management.
globs: app/**,tests/**
---

## Runtime

- Python **3.13**. Use `X | None` over `typing.Optional`; use `list[str]` not `List[str]`.
- Flask **3.1.1** and Gunicorn **23.0.0** are the only runtime dependencies. Do not add packages to `requirements.txt` without justification.
- The app is stateless. No module-level mutable state, no disk writes, no in-process caches.

## Environment variables

Read from `os.environ.get()` with a default at **module load time** and assign to module-level constants:

```python
APPLICATION_NAME = os.environ.get("APPLICATION_NAME", "hello-platform")
```

Do not call `os.environ` inside request handlers — env vars are startup config, not per-request config.

## Code style

- Formatter: **black**, line length 88.
- Import order: **isort** with `profile = "black"`.
- Linter: **flake8** with **flake8-bugbear**.
- All tool config lives in `pyproject.toml`. Do not create `.flake8`, `setup.cfg`, or per-tool dotfiles.

## Type checking

- **mypy strict** is enforced — every function needs full annotations.
- Do not add `# type: ignore` without an inline comment explaining why.

## Testing

- Framework: **pytest** with **pytest-flask**. Do not use `unittest.TestCase`.
- Unit tests in `tests/test_unit.py`, integration tests in `tests/test_integration.py`.
- Coverage threshold: **80%** enforced via `--cov-fail-under=80` in `pyproject.toml`. Do not lower it.
- Always obtain the test client from a fixture — never instantiate `app.test_client()` inside a test body.
- To override module-level constants, use `monkeypatch.setattr(app.main, "CONSTANT", value)` — `os.environ` patching has no effect after module load.

## Security

- Do not use `subprocess`, `eval`, `exec`, or `pickle`.
- Never log request parameters or headers.
- **bandit** scans `app/` on every CI run. Config in `pyproject.toml` under `[tool.bandit]`.
- **pip-audit** scans `requirements.txt` for CVEs.

## Dependency management

- `requirements.txt` — runtime only, pinned to exact versions.
- `requirements-dev.txt` — starts with `-r requirements.txt`, then adds test/lint/type/security tools. Pin all versions.
