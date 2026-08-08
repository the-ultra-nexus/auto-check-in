## ADDED Requirements

### Requirement: Default adapter fallback
The system SHALL default a site's adapter to the site name when the site's configuration omits the `adapter` field, including within `SITE_CONFIGS` JSON, so explicit `adapter` entries are only needed when the adapter name differs from the site name.

#### Scenario: Site config omits adapter
- **WHEN** `SITE_CONFIGS` defines a site whose JSON entry has no `adapter` field and no `SITE_<NAME>_ADAPTER` environment variable or TOML `adapter` overrides it
- **THEN** the site uses the adapter registered under the site name

#### Scenario: Explicit adapter still wins
- **WHEN** a site's `SITE_CONFIGS` JSON entry includes an `adapter` field
- **THEN** the configured adapter is used for that site

#### Scenario: Redundant field removed from secret
- **WHEN** the `sijishe` entry in `SITE_CONFIGS` has `adapter` removed
- **THEN** the site still resolves to the `sijishe` adapter and runs unchanged
