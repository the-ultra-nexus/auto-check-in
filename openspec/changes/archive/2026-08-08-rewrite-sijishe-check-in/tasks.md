## 1. Runtime foundation

- [x] 1.1 Create the `auto_check_in` package with typed account, configuration, result, and adapter protocol models.
- [x] 1.2 Implement layered TOML/environment configuration loading, validation, secret redaction, and account payload parsing.
- [x] 1.3 Implement bounded HTTP and Selenium browser session helpers with deterministic cleanup and optional debug artifact capture.

## 2. Driver社 adapter and runner

- [x] 2.1 Move release-page discovery and candidate URL validation into `SijisheAdapter` with configurable direct URL override and retries.
- [x] 2.2 Move formhash/cookie extraction, CAPTCHA OCR/check, login, sign-in, and profile/statistics extraction into adapter-scoped methods using the shared session.
- [x] 2.3 Implement adapter registry, multi-account runner, stable result statuses, sanitized aggregation, and exit-code behavior.
- [x] 2.4 Keep `sijishe.py` and `handler(event, context)` as thin compatibility entry points and route notifications through the existing `notify.send` API.

## 3. Configuration and scheduled execution

- [x] 3.1 Add a documented non-secret `config/check-in.toml` template and update ignore rules for runtime artifacts and local secret files.
- [x] 3.2 Add a GitHub Actions workflow with daily cron, manual dispatch, locked Python dependencies, Chrome setup, read-only permissions, and Secrets-to-environment wiring.
- [x] 3.3 Document local setup, GitHub repository Secrets, supported environment variables, dry-run behavior, and manual integration verification.

## 4. Verification

- [x] 4.1 Add unit tests for account parsing, configuration precedence/validation, URL discovery parsing, result aggregation, and secret redaction without network or browser access.
- [x] 4.2 Run formatting/static checks, unit tests, `python -m compileall`, and OpenSpec validation.
- [ ] 4.3 Perform one manual integration run with test credentials, verify sign-in and notification output, then confirm no sensitive artifacts are tracked.
