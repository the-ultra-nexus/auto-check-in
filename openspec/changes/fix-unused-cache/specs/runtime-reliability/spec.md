## MODIFIED Requirements

### Requirement: Workflow session cache correctness
The workflow SHALL restore the latest session cache and save a fresh entry without same-key collisions, SHALL skip saving when the session directory holds no session files, and SHALL surface a restored-but-unused cache: when a cache was restored yet the runtime reported zero restored sessions or zero newly saved sessions, the workflow SHALL emit a warning in the run log instead of passing silently.

#### Scenario: Consecutive daily runs
- **WHEN** a second daily run restores the previous cache
- **THEN** it saves the updated cache under a new unique key and does not fail the job

#### Scenario: Empty session directory skips save
- **WHEN** `.runtime/sessions` contains no session files after the check-in step
- **THEN** the workflow skips the cache-save step and does not create a new cache entry

#### Scenario: Restored cache content is reported
- **WHEN** the cache restore step extracts a previous cache
- **THEN** the run log lists the number and total size of the restored session files before the check-in step

#### Scenario: Unused cache is surfaced
- **WHEN** the cache restore step reports a hit but the runtime reports zero restored sessions or zero newly saved sessions
- **THEN** the workflow emits a warning naming the cache key and the observed counters
