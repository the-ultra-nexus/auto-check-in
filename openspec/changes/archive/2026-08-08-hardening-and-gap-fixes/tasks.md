## 1. Notification rewrite

- [x] 1.1 Move and rewrite `notify.py` as `auto_check_in/notify.py`: channel registry, per-channel timeout, no global mutable config, no print monkeypatch, no hitokoto.
- [x] 1.2 Wrap CLI notification sending in `try/except`; add tests for exit-code isolation, no external quote, channel timeout, and multi-channel selection.

## 2. Transport abstraction

- [x] 2.1 Add `SessionProvider` to `http.py` (UA pool, timeouts, retry defaults) and switch `SijisheAdapter` to use it.
- [x] 2.2 Add a test proving sessions from the provider carry UA and timeout defaults.

## 3. Logging and summary

- [x] 3.1 Add stdlib logging with `CHECK_IN_LOG_LEVEL` / `--debug`, per-site/per-account redacted lines.
- [x] 3.2 Add `site` to `AccountResult` and group `RunSummary.render()` output by site; update tests.

## 4. Workflow operations

- [x] 4.1 Update cache restore/save keys (unique save key + restore-keys prefix).
- [x] 4.2 Add `workflow_dispatch.inputs.sites` overriding `CHECK_IN_SITES`.

## 5. Request pacing

- [x] 5.1 Add `CHECK_IN_REQUEST_DELAY` (default 3) with jitter between accounts in the runner; add tests for delay and zero-delay behavior.

## 6. Config validation and session TTL

- [x] 6.1 Add unknown-key warnings and cross-site error aggregation in `load_config`.
- [x] 6.2 Add `saved_at` to session cache and `CHECK_IN_SESSION_MAX_AGE` expiry handling; add tests.

## 7. Timing

- [x] 7.1 Record per-site elapsed time in the runner and log it.

## 8. Documentation reconciliation and verification

- [x] 8.1 Backfill `migrate-to-api-check-in` design/specs with session cache and `SITE_CONFIGS` workflow; update README and OpenSpec context.
- [x] 8.2 Run unittest, `compileall`, CLI `--dry-run`, and `openspec validate`.

## 9. Shared user-agent pool

- [x] 9.1 Restore the built-in user-agent pool in `http.py`; `SessionProvider` and `ua_headers` pick a random user agent per request and remove `CHECK_IN_USER_AGENT` / `[network] user_agent` config.
- [x] 9.2 Update `notify.py` to reuse the same user-agent pool (no hardcoded constant, no configuration parameter); CLI passes no user agent.
- [x] 9.3 Update tests and README for the pool behavior; run unittest, `compileall`, CLI `--dry-run`, and `openspec validate`.
