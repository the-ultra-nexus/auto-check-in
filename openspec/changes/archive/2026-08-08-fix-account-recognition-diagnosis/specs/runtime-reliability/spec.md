## MODIFIED Requirements

### Requirement: Config validation completeness
Unknown configuration keys SHALL be reported as warnings, and required-value or type errors SHALL be aggregated across sites and reported together before any network activity. Sensitive credential keys (e.g. `accounts`) SHALL NOT be accepted inside the committed TOML site sections; when present, the loader SHALL raise a deterministic configuration error that names the offending key and points to the environment-variable or Secret alternatives.

#### Scenario: Multiple invalid sites
- **WHEN** two enabled sites both lack required values
- **THEN** startup reports both errors in a single configuration failure

#### Scenario: Unknown keys
- **WHEN** configuration contains unknown non-sensitive keys
- **THEN** the loader prints warnings and continues

#### Scenario: Credentials in TOML rejected with guidance
- **WHEN** a `[sites.<name>]` section contains an `accounts` key
- **THEN** the loader raises a configuration error naming `sites.<name>.accounts` and directing the user to `SITE_<NAME>_ACCOUNTS` or `SITE_CONFIGS`
