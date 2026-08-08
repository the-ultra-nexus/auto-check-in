## 1. Credential-safe username helper

- [x] 1.1 Add `mask_username(username)` to `auto_check_in/security.py`: length ≤1 → `*`; ≤4 → first char + `***`; else → first 2 chars + `***` + last char
- [x] 1.2 Add unit tests for `mask_username` covering length boundaries, empty input, and asserting the output never contains the full username

## 2. Account recognition observability

- [x] 2.1 In `load_config`, after building the site list, emit `logger.info("site=%s accounts=%d recognized", ...)` per site using only the parsed account count
- [x] 2.2 Update `--dry-run` output to print the account count and the masked username list per site
- [x] 2.3 Add tests: `assertLogs` verifies the recognized-count log line; dry-run output shows masked usernames only

## 3. Login-blocked status

- [x] 3.1 Add `CheckInStatus.LOGIN_BLOCKED = "login-blocked"` with label `登录被拦截` in `auto_check_in/models.py`
- [x] 3.2 Add `LoginBlockedError(LoginError)` in `auto_check_in/errors.py`
- [x] 3.3 In `adapters/sijishe.py`, make `_post_login` raise `LoginBlockedError` with status + actionable hint on HTTP 4xx (e.g. 403), and `run()` map it to `LOGIN_BLOCKED`; keep non-login HTTP failures mapped to `site-unavailable`
- [x] 3.4 Add adapter tests with a fake session: HTTP 403 on the login POST → result `login-blocked` with hint message; HTTP 503 on the sign-in request → result `site-unavailable`
- [x] 3.5 Add debug-level logging in `_login`/`_post_login` recording the failed step (dialog fetch / login submit / sign-in) and confirming login form fields are filled using field names only (never values); add a test asserting the log contains field names and no credential values

## 4. Masked identifiers in logs, summary, and notifications

- [x] 4.1 Update `runner.py` per-account log to include an account ordinal and the masked username (e.g. `account=1 username=sa***1`)
- [x] 4.2 Update `adapters/sijishe.py` warning logs to use the masked username
- [x] 4.3 Update `models.py` `summary_line` and `cli.py` output to render the masked username
- [x] 4.4 Add tests asserting logs, rendered summary, and notification payload contain masked usernames and never the full username

## 5. Config credential-key guard

- [x] 5.1 In `load_config`, detect `accounts` (and password-like keys) inside `[sites.<name>]` and raise `ConfigError` naming `sites.<name>.accounts` and pointing to `SITE_<NAME>_ACCOUNTS` / `SITE_CONFIGS`
- [x] 5.2 Add a config test asserting the TOML `accounts` key raises a configuration error with the guidance message
- [x] 5.3 Update `config/check-in.toml` comments to state credentials must not be written to the file

## 6. Documentation

- [x] 6.1 Update `README.md`: explain CI `***` is GitHub Secret masking (not unrecognized accounts), how to verify recognition via `--dry-run` and the `accounts=N recognized` log, and how to troubleshoot `登录被拦截`

## 7. Repo credential hygiene

- [x] 7.1 Replace real identifiers in planning artifacts and docs with placeholders (e.g. `alice&secret`); confirm neither the real username nor the real password from the user's `SITE_CONFIGS` report remains anywhere in the workspace
- [x] 7.2 Sweep all tracked files and git history for real credentials (`git grep` + `git log -p`) and confirm only placeholder values remain
- [x] 7.3 Confirm `.gitignore` still covers `.runtime/`, `.env*`, `config/*.secret.toml`, and captcha image files
- [x] 7.4 Add a README note that docs, examples, and planning artifacts must use placeholder accounts (e.g. `alice&secret`), never real ones

## 8. Verification

- [x] 8.1 Run the full automated suite: `uv run python -m unittest discover -s tests -v`
- [x] 8.2 Manual integration: local `--dry-run` with a placeholder `SITE_CONFIGS` shows the recognized count and masked usernames; if real credentials are available, run once locally and confirm the status mapping; trigger a GitHub Actions `workflow_dispatch` and confirm the recognized log line and `login-blocked`/success outcome
