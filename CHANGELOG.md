# Changelog

All notable changes to this project will be documented in this file.

The format is inspired by [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to semantic versioning where practical.

## [Unreleased]

- Extend welcome flow with full webhook-driven templates and tokenized embeds.
- Add verification/auto-role/incident commands and other command-center features.
- Introduce persistent storage for punishment history and export tools.

## [0.7.0] - 2025-11-16

### Added

- SQLite-backed persistence layer:
  - `Database` service managing the `bot.db` SQLite database.
  - `HistoryStore` now persists punishments, notes, and jail state to SQLite.
  - `IncidentStore` now stores incidents in SQLite with auto-increment IDs.
  - `TicketService` now stores escalated tickets in SQLite.
  - `AutoRoleStore` and `ReactionRoleStore` now persist role mappings in SQLite.

## [0.6.0] - 2025-11-16

### Added

- Webhook-driven welcome flow:
  - `WebhookManager` service for building tokenized messages from JSON templates.
  - `/welcome template` payloads now used to drive real welcome messages and previews.
  - On member join, a `default` template is used (if present) and sent via webhook when configured.

## [0.4.0] - 2025-11-16

### Added

- Community & command-center features:
  - `/verify` to approve and auto-role members using trigger-based mappings.
  - `/auto-role set` for configuring trigger -> role mappings (e.g. `verify`, `join`).
  - `/react-role sync` for ensuring message reactions match stored reaction-role mappings.
  - `/announce` for immediate or scheduled announcements using the scheduler.
  - `/spotlight` to celebrate members with a dedicated embed.
- New services:
  - `AutoRoleStore` for in-memory trigger-to-role mappings.
  - `ReactionRoleStore` for in-memory reaction-role mappings.
- Auto-role application on member join via the `join` trigger in the welcome cog.

## [0.5.0] - 2025-11-16

### Added

- Ops & developer tooling:
  - `/cog reload`, `/cog load`, `/cog unload` for runtime cog management with audit logging.
  - `/incident create` and `/incident status` backed by an in-memory `IncidentStore`.
  - `/ticket escalate` backed by an in-memory `TicketService` with priority handling.
  - `/debug-eval` owner-only evaluation command with basic AST-based safety checks.
- New services:
  - `IncidentStore` for incident tracking.
  - `TicketService` for ticket escalation state.

## [0.3.0] - 2025-11-16

### Added

- Diagnostics/reporting commands:
  - `/audit-history` for viewing punishment history (optionally filtered by user).
  - `/member-info` for summarized view of a member's infractions, notes, and roles.
  - `/logs-export` for exporting punishments and notes to a CSV file.
- Updated `docs/commands.md` to document new diagnostics commands.
- Added project `README.md` and this `CHANGELOG.md`.

## [0.2.0] - 2025-11-16

### Added

- Extended moderation suite:
  - `/note` for private moderator notes.
  - `/mute` with optional timed unmutes via the scheduler.
  - `/jail` for applying a jail role and tracking jail state.
  - `/pardon` for clearing mute/jail/timeout/ban state where applicable.
- Introduced in-memory `HistoryStore` with `PunishmentRecord`, `NoteRecord`, and `JailState` models.
- Wired moderation commands into the history store and audit logging.
- Expanded `docs/commands.md` with the new moderation commands.

## [0.1.0] - 2025-11-16

### Added

- Initial project scaffold:
  - `core/` package with `BotConfig`, `QuefBot`, and shared `ResponseView`.
  - `cogs/` package with initial moderation, welcome, and diagnostics cogs.
  - `services/` for permissions, audit logging, and scheduling.
  - `models/` for punishment and webhook template models.
  - `docs/commands.md` as the initial command catalog.
- Basic moderation commands: `/warn`, `/timeout`, `/kick`, `/ban`, `/softban`, `/purge`, `/slowmode`, `/lock`, `/unlock`.
- Basic welcome commands and diagnostics (`/config-check`, `/health`, `/bot-stats`).
