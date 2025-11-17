# Quef Central Mega Moderation Bot

Quef Central is a modular **discord.py** bot focused on high-level moderation, community management, and onboarding for the Quef Central server.

The project follows the roadmap in `roadmap.md` and is organized to be easy to extend with new commands, cogs, and services.

## Features (current)

- **Moderation suite** – warn, note, timeout, mute, kick, ban, softban, purge, slowmode, lock/unlock, jail, pardon.
- **Welcome & onboarding** – basic join greetings, configurable welcome channel, JSON-backed welcome templates and previews with tokens, join-trigger auto-roles.
- **Community & command center** – verify/auto-role assignment, reaction-role syncing, announcements, and member spotlights.
- **Diagnostics & reporting** – config check, health, bot stats, audit history, member info, and CSV log export.
- **Ops & developer tools** – cog load/reload/unload, incident tracking, ticket escalation, and a restricted debug eval.
- **Shared services** – permission guard, audit logging, simple in-memory history store, auto-role and reaction-role stores, incident and ticket stores, and a scheduler for timed actions.

## Project Structure

- `main.py` – entrypoint that loads configuration and runs the bot.
- `core/`
  - `config.py` – reads `config.json` and environment variables into `BotConfig`.
  - `bot.py` – `QuefBot` class, loads cogs, error handling, shared services.
  - `views.py` – shared `ResponseView` for consistent button-based interactions.
- `cogs/`
  - `moderation/` – moderation commands and role/timeout logic.
  - `welcome/` – onboarding, welcome channel and template management, join-trigger auto-roles.
  - `community/` – verify, auto-role, reaction-role syncing, announcements, spotlights.
  - `diagnostics/` – config/health/bot stats, audit history, member info, logs export.
  - `ops/` – cog management, incidents, tickets, and debug eval.
- `services/`
  - `permissions.py` – staff/permission checks and `PermissionGuard` mixin.
  - `audit.py` – moderation action embeddings for log channels.
  - `scheduler.py` – simple time-based task scheduler.
  - `history.py` – in-memory store for punishments, notes, and jail state.
  - `auto_roles.py` – in-memory mapping of triggers (e.g. `join`, `verify`) to role IDs.
  - `reaction_roles.py` – in-memory mapping of message/emoji pairs to role IDs.
  - `incidents.py` – in-memory store for incidents.
  - `tickets.py` – in-memory store for ticket escalation state.
- `models/`
  - `punishments.py` – `PunishmentRecord`, `NoteRecord`, `JailState` models.
  - `webhook_templates.py` – simple template store for welcome payloads.
  - `webhook_manager.py` – builds tokenized welcome messages and dispatches via webhook or channel.
- `docs/`
  - `commands.md` – living command catalog.

## Requirements

- Python 3.10+
- `discord.py` (see `requirements.txt`)
- `python-dotenv` (optional but recommended for local development)
- `sqlite3` (for persistence of moderation history, incidents, tickets, auto-roles, and reaction roles)

Install dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

The bot reads configuration from **environment variables** and an optional `config.json` file next to `main.py`.

Minimum configuration:

- `DISCORD_TOKEN` (or `token` in `config.json`)

Optional fields (env or `config.json`):

- `DISCORD_GUILD_IDS` / `guild_ids` – comma-separated list of guild IDs for targeted command sync.
- `DISCORD_OWNER_IDS` / `owner_ids` – comma-separated list of owner IDs (always treated as staff).
- `DISCORD_LOG_CHANNEL_ID` / `log_channel_id` – channel ID for moderation log embeds.
- `DISCORD_WELCOME_CHANNEL_ID` / `welcome_channel_id` – channel ID for welcome messages.
- `DISCORD_WELCOME_WEBHOOK_URL` / `welcome_webhook_url` – future webhook-driven welcome payloads.
- `DISCORD_MUTE_ROLE_ID` / `default_mute_role_id` – role ID for mute/jail commands.
- `DISCORD_STAFF_ROLE_IDS` / `staff_role_ids` – comma-separated IDs of roles treated as staff.

Example `.env`:

```env
DISCORD_TOKEN=your-bot-token
DISCORD_LOG_CHANNEL_ID=123456789012345678
DISCORD_MUTE_ROLE_ID=234567890123456789
DISCORD_STAFF_ROLE_IDS=345678901234567890,456789012345678901
```

Example `config.json`:

```json
{
  "token": "your-bot-token",
  "log_channel_id": 123456789012345678,
  "welcome_channel_id": 234567890123456789,
  "default_mute_role_id": 345678901234567890,
  "staff_role_ids": [456789012345678901],
  "owner_ids": [567890123456789012]
}
```

## Running the Bot

From the project directory containing `main.py`:

```bash
python main.py
```

On first run, Discord slash commands may take a few minutes to appear globally. You can speed this up by scoping commands to specific guilds in `BotConfig` and syncing per-guild.

## Command Overview

See `docs/commands.md` for the full list. Highlights:

- Moderation: `/warn`, `/note`, `/timeout`, `/mute`, `/kick`, `/ban`, `/softban`, `/purge`, `/slowmode`, `/lock`, `/unlock`, `/jail`, `/pardon`.
- Welcome: `/welcome set-channel`, `/welcome template`, `/welcome preview`.
- Community & Command Center: `/verify`, `/auto-role set`, `/react-role sync`, `/announce`, `/spotlight`.
- Diagnostics: `/config-check`, `/health`, `/bot-stats`, `/audit-history`, `/member-info`, `/logs-export`.

## Development Notes

- Moderation history, incidents, tickets, auto-roles, and reaction-role mappings are persisted in a local SQLite database `bot.db` in the project root.
- All staff-only commands use `services.permissions.is_staff`, which checks both owner IDs and staff role IDs.
- All risky actions use `PermissionGuard.ensure_target_hierarchy` to prevent acting on higher/equal roles.

## Roadmap

See `roadmap.md` for the high-level design and future milestones, including:

- Persistent punishment history and export tools.
- Rich webhook-driven welcome/onboarding flows.
- Command center & ops tools (verify, auto-role, incidents, cog reload, etc.).

Contributions and extensions should follow the existing modular layout: add models/services first, then wire them into new cogs and keep `docs/commands.md` updated.
