# account-recognition-observability Specification

## Purpose
Account recognition results must be observable even when CI secret masking replaces usernames with `***`.

## Requirements
### Requirement: Account recognition is observable
After configuration loads, the runtime SHALL emit one log line per enabled site stating how many accounts were recognized for that site, using only the count and never any credential material, so recognition remains verifiable even when CI secret masking replaces usernames with `***`.

#### Scenario: Recognized count logged at startup
- **WHEN** configuration with one site and two accounts is loaded
- **THEN** a log line contains the site name and `accounts=2 recognized`

#### Scenario: Count is mask-proof
- **WHEN** the recognized-account log line is emitted for a site whose credentials come from a CI secret
- **THEN** the line contains only the site name and the account count, with no username substring that secret masking could replace

#### Scenario: Dry-run lists masked accounts
- **WHEN** `--dry-run` validates a site with recognized accounts
- **THEN** the output shows the account count and a masked form of each username (never the full username)

### Requirement: Account identifiers are masked in logs and results
The runtime SHALL render account identifiers in logs, the rendered summary, and notifications as a masked username (first characters, `***`, last character) instead of the full username, and SHALL NOT print the full username outside internal credential handling.

#### Scenario: Per-account log line uses masked username
- **WHEN** an account finishes processing and its per-account log line is emitted
- **THEN** the log line contains the masked username (e.g. `sa***1`) and does not contain the full username

#### Scenario: Summary uses masked username
- **WHEN** the rendered summary contains an account result
- **THEN** the summary shows the masked username and not the full username

#### Scenario: Notification payload uses masked username
- **WHEN** a notification is sent with the rendered summary
- **THEN** the payload contains only masked usernames
