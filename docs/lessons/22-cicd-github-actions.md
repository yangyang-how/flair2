# 22. CI/CD: The GitHub Actions Pipeline

> CI/CD (Continuous Integration / Continuous Deployment) automates the path from code commit to running in production. This article covers Flair2's GitHub Actions pipeline and the patterns behind it.

## What CI/CD means

**Continuous Integration (CI):** every code change is automatically built, linted, and tested. If the tests fail, the change is rejected before it reaches the main branch. The goal: catch bugs early, when they're cheap to fix.

**Continuous Deployment (CD):** every change that passes CI is automatically deployed to production (or a staging environment). The goal: eliminate manual deployment steps, which are error-prone and slow.

Together, CI/CD means: push code → tests run → if green → deployed. The feedback loop is minutes, not days.

## Flair2's pipeline

Flair2's CI/CD is in `.github/workflows/`. The pipeline runs on every push to `main`:

```
Push to main
     │
     ├── Lint (ruff check .)
     │
     ├── Test (pytest)
     │
     ├── Build Docker image
     │
     ├── Push to ECR
     │
     ├── Deploy API (ECS service update)
     │
     ├── Deploy Worker (ECS service update)
     │
     ├── Frontend build (Astro)
     │
     └── Deploy frontend (S3 sync)
```

### The CI phase: lint and test

**Linting (`ruff check .`):** catches style issues, unused imports, potential bugs, and formatting inconsistencies. Runs in seconds. Fails the pipeline if any issue is found.

**Testing (`pytest`):** runs unit tests and integration tests. Unit tests use mocks and fakeredis — no external dependencies. Integration tests may use a real Redis if available.

**Why lint before test:** linting is faster and catches simpler issues. If the code has a syntax error, there's no point running tests. Fail fast on the cheap check.

### The CD phase: build and deploy

**Docker build:** creates the production image from the Dockerfile. This image contains the Python application, all dependencies, the video dataset, and the `pyproject.toml` (for pytest config — learned from PR #120).

**ECR push:** pushes the built image to AWS Elastic Container Registry (ECR). ECR is a private Docker registry — like Docker Hub, but within your AWS account.

**ECS service update:** tells ECS "use this new image." ECS performs a rolling deployment — it starts new tasks with the new image, waits for them to pass health checks, then stops the old tasks. Zero-downtime deployment.

**Frontend:** separate pipeline. Astro builds to static HTML/CSS/JS, then `aws s3 sync` uploads the files to the S3 bucket configured for static website hosting.

## The deploy-then-test pattern

Flair2 runs integration tests AFTER deployment. The workflow:

```
Deploy to AWS → Run integration tests against deployed environment → Report results
```

This is unusual. Most CI/CD pipelines test BEFORE deploying:

```
Standard: Test → Deploy (only if tests pass)
Flair2:   Deploy → Test (against the deployed environment)
```

**Why Flair2 does it this way:** the integration tests (M6 ElastiCache experiments) need a real Redis instance. Running them against ElastiCache post-deployment tests the actual production infrastructure, not a local simulation.

**The trade-off:** if integration tests fail, you've already deployed potentially broken code. In a production system, you'd deploy to a staging environment first, run tests there, and only promote to production if tests pass. For a course project, deploying to a single environment and testing is acceptable.

## GitHub Actions concepts

### Workflows, jobs, and steps

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install -r requirements.txt
      - run: ruff check .
      - run: pytest

  deploy-backend:
    needs: lint-and-test      # Only runs if lint-and-test passes
    runs-on: ubuntu-latest
    steps:
      - run: docker build -t flair2 .
      - run: docker push $ECR_URL
      - run: aws ecs update-service ...
```

**Workflow:** a YAML file in `.github/workflows/`. Triggered by events (push, pull request, schedule).
**Job:** a set of steps that run on a fresh virtual machine. Jobs can depend on each other (`needs`).
**Step:** one command or action. Steps run sequentially within a job.

### Secrets

```yaml
env:
  AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
  AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
  KIMI_API_KEY: ${{ secrets.KIMI_API_KEY }}
```

Secrets are stored in GitHub's encrypted storage and injected as environment variables. They never appear in logs. PRs #116-#119 migrated these from school credentials to personal AWS account credentials.

### Caching

```yaml
- uses: actions/cache@v4
  with:
    path: ~/.cache/pip
    key: ${{ hashFiles('requirements.txt') }}
```

Pip packages are cached between runs. If `requirements.txt` hasn't changed, dependencies are restored from cache instead of downloaded. This cuts minutes off the pipeline.

## What the pipeline catches

| Check | What it prevents |
|-------|-----------------|
| `ruff check` | Style inconsistencies, unused imports, type errors |
| `pytest` unit tests | Logic bugs in stage functions, orchestrator, models |
| `pytest` integration tests | Redis interaction bugs, multi-user concurrency issues |
| Docker build | Missing files, broken dependencies, import errors |
| ECS health check | Application crash on startup, misconfigured environment |

**What it doesn't catch:**
- Performance regressions (no load tests in CI)
- Frontend/backend integration issues (no end-to-end browser tests)
- Configuration drift (Terraform changes aren't validated in CI)
- LLM output quality changes (no quality regression tests)

## Pipeline anti-patterns to avoid

**1. Ignoring flaky tests.** If a test sometimes passes and sometimes fails, fix it — don't mark it as "known flaky." Flaky tests erode trust in the pipeline. Eventually, nobody believes the red signal.

**2. Long pipelines.** If CI takes 30 minutes, developers stop waiting for it and merge without checking results. Keep the pipeline under 10 minutes. Run slow tests (integration, load) in a separate pipeline or only on main.

**3. No rollback plan.** What happens if the deployment breaks production? Flair2's rolling deployment means the previous task definition is still in ECS history — you can roll back by updating the service to the previous image. But this isn't automated.

**4. Deploying on every commit to main.** Fine for a course project. In production, you'd deploy to staging first, run smoke tests, and promote to production manually or with a canary deployment (send 5% of traffic to the new version, watch for errors, then roll out to 100%).

## CI/CD as documentation

The workflow file tells you:
- **What languages and tools the project uses** (Python, Node.js, Docker)
- **What the test commands are** (`ruff check .`, `pytest`)
- **What the deployment target is** (ECS, S3)
- **What secrets are required** (AWS credentials, API keys)
- **What the dependency chain is** (lint → test → build → deploy)

For a new team member, the CI/CD pipeline is often the most accurate description of "how to build and deploy this project" — more reliable than README instructions, which may be outdated.

## What you should take from this

1. **CI/CD is a safety net, not overhead.** Every manual step you automate is a step that can't be forgotten, done wrong, or skipped under pressure.

2. **Fail fast, fail cheap.** Run the cheapest checks (lint) first. If the code has a syntax error, don't waste time building a Docker image.

3. **Test against real infrastructure when possible.** fakeredis is good for unit tests; ElastiCache is necessary for validating real distributed behavior. Both have a place.

4. **The pipeline IS the documentation.** It describes exactly how to build, test, and deploy. If the README disagrees with the workflow file, trust the workflow file.

5. **Secrets management is non-negotiable.** Never hardcode API keys. Use GitHub Secrets, AWS Secrets Manager, or similar. The PRs migrating credentials (#116-#119) show this being done properly.

---

***Next: [The Frontend Stack](23-the-frontend-stack.md) — Astro, React islands, and why not a full SPA.***
