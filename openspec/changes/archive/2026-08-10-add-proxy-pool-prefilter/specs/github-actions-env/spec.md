## MODIFIED Requirements

### Requirement: GitHub Actions env mapping covers documented CI variables
The GitHub Actions workflow SHALL map every CI environment variable marked `# @ci:secrets` or `# @ci:vars` in `.env.example` into the job `env` with the matching source, so configuration set in repository settings actually reaches the process. The reverse SHALL also hold: every `secrets.X` / `vars.X` referenced in a workflow SHALL be declared in `.env.example` with a matching marker.

#### Scenario: Proxy pool secret is mapped
- **WHEN** the job `env` of `.github/workflows/check-in.yml` is inspected
- **THEN** it contains `CHECK_IN_PROXY_POOL_URLS` sourced from `secrets` and does not reference the removed static proxy variables `CHECK_IN_PROXY_URLS` / `SITE_SIJISHE_PROXY_URLS`

#### Scenario: Missing marked variable fails coverage
- **WHEN** a variable marked `@ci:secrets` or `@ci:vars` in `.env.example` is absent from the workflow `env`
- **THEN** the env-coverage test fails with the missing variable name and expected source

#### Scenario: Local-only variables are not required in CI
- **WHEN** `.env.example` declares a variable without an `@ci` marker (e.g. `CHECK_IN_SESSION_DIR`)
- **THEN** the env-coverage test does not require it in the workflow `env`

#### Scenario: Undeclared workflow reference fails coverage
- **WHEN** a workflow `env` references `secrets.X` or `vars.X` and `X` is not declared in `.env.example` with a matching marker
- **THEN** the env-coverage test fails naming the variable and its mapped source
