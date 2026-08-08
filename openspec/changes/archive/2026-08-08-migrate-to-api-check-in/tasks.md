## 1. Login + sign-in adapter

- [x] 1.1 Rewrite `SijisheAdapter` to perform HTTP login via the login dialog form (no CAPTCHA, password submitted as MD5 digest) and sign-in only (no statistics) using `requests.Session` + lxml with a required `base_url`.
- [x] 1.2 Implement the response classifier for XML CDATA (`今日已签` / empty), `Discuz! System Error` HTML, and retry-once with a refreshed formhash.
- [x] 1.3 Delete the obsolete transport-layer implementation, remove dependencies no longer required by the dialog login flow (including OCR packages), and sync dependency files, README, and workflow.

## 2. Multi-site parallel orchestration

- [x] 2.1 Update `runner.py` to read `CHECK_IN_SITES`, execute enabled sites concurrently with `ThreadPoolExecutor`, honor `CHECK_IN_MAX_WORKERS`, and aggregate results with exit codes 0/1/2.
- [x] 2.2 Update configuration to require per-site `base_url` and support `SITE_<NAME>_BASE_URL` / `SITE_<NAME>_ACCOUNTS`; remove unused keys.
- [x] 2.3 Add a redaction helper and apply it to results, logs, and notifications.
- [x] 2.4 Update the GitHub Actions workflow and README for single-job multi-site parallel execution with per-site secrets.

## 3. Verification

- [x] 3.1 Add unit tests with HTML/XML fixtures for the login sequence, sign-in classification, parallel multi-site orchestration, exit codes, redaction, and no-obsolete-dependency checks.
- [x] 3.2 Run unittest, `compileall`, CLI `--dry-run`, and `openspec validate`.
- [ ] 3.3 Perform one real API login and sign-in with test credentials over HTTP only.

## 4. Extension scaffolding

- [x] 4.1 Add a registry unit test using a stub adapter to prove a new site needs no runner, result-model, notification, or CLI changes.
- [x] 4.2 Add an adapter extension guide covering the module, registration, `SITE_<NAME>_*` environment isolation, and fixture-test steps.

## 5. Cleanup and notification title

- [x] 5.1 Remove the obsolete root-level `sijishe.py` compatibility entry and update README/OpenSpec context references.
- [x] 5.2 Make the notification title specific (`每日自动签到结果` + run date) in defaults, template, and CLI notification.

## 6. Session cache

- [x] 6.1 Add a per-site/per-account cookie cache under `.runtime/sessions` with 0600 permissions and gitignore coverage.
- [x] 6.2 Reuse valid cached sessions, skip login, and automatically re-login when sign-in reports `login-failed`.
- [x] 6.3 Add GitHub Actions cache restore/save steps and document `CHECK_IN_SESSION_CACHE` / `CHECK_IN_SESSION_DIR`.

## 7. Shared helpers and documentation

- [x] 7.1 Extract generic HTTP UA helpers, Discuz parsing/response classification, and adapter error types into shared modules.
- [x] 7.2 Document the run flowchart and shared helper modules in README.

## 8. Test organization

- [x] 8.1 Split tests by site adapter and shared/common categories (`tests/test_sijishe.py`, `tests/test_common.py`).
- [x] 8.2 Extract reusable fixtures and helpers into `tests/helpers.py` for future site tests.

## 9. Multi-site workflow

- [x] 9.1 Make the GitHub Actions workflow site-agnostic with `CHECK_IN_SITES` variable and `SITE_CONFIGS` JSON secret.
- [x] 9.2 Support `SITE_CONFIGS` in config loading with per-site env/TOML fallback and enabled-site derivation.
- [x] 9.3 Document the multi-site GitHub configuration in README and add config tests.
