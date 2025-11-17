# Quef Central Mega Moderation Bot Roadmap

## Vision
Build a professional, modular Discord.py bot focused on high-level moderation, community management, and onboarding for the Quef Central server. The bot should combine strict permission handling, auditable actions, and welcoming experiences delivered via webhook-driven templates.

## Architectural Principles
1. **Modular Packages**
   - `core/` – bootstraps the bot, loads cogs, manages configuration, and exposes shared utilities.
   - `cogs/moderation/` – contains cog classes for moderation abstractions (mute, kick, ban, timeout, jail) with shared helper services for permission checks and audit logging.
   - `cogs/welcome/` – handles onboarding workflows, webhook formatting, and greeting components.
   - `services/` – reusable services like role resolver, punishment scheduler, webhook manager, and database or config adapters.
   - `models/` – dataclasses for structured command payloads, webhook templates, and timeout/jail state.
   - `docs/` – living command reference with detailed usage + permissions.

2. **Components v2 for Interaction Quality**
   - Use `discord.ui.View` with buttons/dropdowns for moderation decisions and configuration.
   - Provide a standardized `ResponseView` that reuses button styles and accessibility labels.

3. **Command & Permission Strategy**
   - Each command defines required Discord permissions, minimum role, and fallback messaging.
   - Implement a `PermissionGuard` mixin ensuring commands verify bot permissions before execution.
   - Record action metadata (executor, target, reason, duration) for audit logging.

4. **Webhook-Driven Welcome Flow**
   - Welcome cog dispatches JSON payloads to configurable webhooks.
   - Payload includes embedded callouts, role instructions, and a component-based quick-start view.
   - Support dynamic tokens (member mention, server info) for reuse.

5. **Future-Proofing**
   - Plan for data persistence (JSON, SQLite, or ORM) for punishment history.
   - Provide CLI or script to export logs for moderation teams.

## Milestones
1. **Structure Setup (Phase 1)** – establish package layout, base bot loader, config parsing (`.env`/`config.json`).
2. **Moderation Cog Suite (Phase 2)** – implement mute, timeout, jail, kick, ban with role assignment logic and Components v2 confirmations.
3. **Welcome & Webhooks (Phase 3)** – webhook manager, templated welcome payload, and importable components.
4. **Documentation & Deployment (Phase 4)** – comprehensive command docs, setup guide, and runtime checks for production readiness.

## Next Steps
1. Create skeleton directories and `__init__` files to satisfy Python package requirements.
2. Implement base bot loader that discovers cogs and reads configuration.
3. Build moderation commands with strict role/permission resolution.
4. Add webhook-based welcome system with JSON formatting and component views.
5. Document every command, role requirement, and webhook payload in `docs/commands.md`.

## Command Catalog & Logic

The catalog prioritizes modular command definitions, each pairing intent with documentation and infrastructure logic so new commands can be wired into the `PermissionGuard`, `Scheduler`, and `AuditEvent` ecosystems with minimal friction. Every command references `docs/commands.md` for usage, permission matrices, and payload samples.

1. **Moderation Control Commands (12)** – strict, auditable interventions.
   - **`/warn [user] [reason] [severity?]`** – logs infractions with optional escalation. Use case: visible trail before escalating. Docs: link to `PunishmentLog` schema. Logic: append to `models/BehaviorRecord`, emit staff embed.
   - **`/note [user] [text]`** – persist private moderator notes. Use case: context on recurring issues. Docs: retention rules, redactable fields. Logic: encrypt with rotating key, surface in `/audit history`.
   - **`/mute [user] [duration?] [reason?]`** – mute in text channels. Use case: calm heated debates. Logic: integrates with `scheduler.AutoActionService` for auto-unmute and logs start/end.
   - **`/timeout [user] [duration] [reason]`** – Discord timeout for multi-channel cooldown. Logic: track `timeoutExpiresAt`, send actionable staff summary.
   - **`/slowmode [channel] [seconds]`** – throttle send rate across high-traffic rooms. Docs: mention persistence to revert. Logic: adjust rate, log change.
   - **`/lock [channel] [reason?]` / `/unlock [channel]`** – emergency send-permission toggles. Use case: halt spam. Logic: set `@everyone` overwrite, queue check for role-based overrides.
   - **`/kick [user] [reason?]`** – remove with dignity. Logic: hierarchy guard, DM fallback, `AuditEvent` emission.
   - **`/ban [user] [duration?] [reason?]`** – ban with optional timed release. Logic: persists `banDuration`, schedules auto-unban, includes appeal link in webhook.
   - **`/softban [user] [reason?]`** – purge messages via ban/unban. Use case: spam removal without lasting punishment. Logic: reuses ban path while skipping retention.
   - **`/pardon [user] [reason?]`** – clear ban/jail state. Logic: removes roles, clears records, logs reversal.
   - **`/jail [user] [role?] [reason?]`** – isolate with restricted role set. Logic: ensures idempotency, watches for jail-role removal.
   - **`/purge [channel] [count] [filter?]`** – bulk delete with filters (user, content). Logic: batched `bulk_delete`, logs cleanup summary.

2. **Command Center & Community Experience (8)** – essential for onboarding and visibility.
   - **`/welcome set-channel [channel]`** – anchor onboarding webhook. Logic: validate webhook perms, persist `WebhookConfig`.
   - **`/welcome template [name] [json]`** – provision structured onboarding templates. Logic: JSON schema validation, template versioning.
   - **`/welcome preview [template] [member?]`** – QA welcome output. Logic: optionally anonymize mentions, render component view.
   - **`/verify [member] [method?]`** – approve and auto-role users. Use case: gating entry. Logic: ties into `services/RoleResolver`, logs in `VerificationLog`.
   - **`/auto-role set [role] [trigger?]`** – assign roles via join/verify trigger. Logic: updates `RoleMatcher`, refreshes cached mapping.
   - **`/react-role sync [message]`** – ensure reaction-role mapping matches stored state. Use case: persistent opt-in groups. Logic: re-sync emoji-role map, repair missing reacts.
   - **`/announce [channel] [message] [schedule?]`** – multi-channel announcements. Use case: maintenance alerts. Logic: uses scheduler, supports template tokens.
   - **`/spotlight [member] [reason?]`** – celebrate contributors via webhook. Logic: templated embed + component buttons for kudos.

3. **Diagnostics, Reporting & Member Insights (6)** – indispensable for accountability.
   - **`/config check`** – shows resolved config with redacted secrets. Logic: `core.Config.sanitize()` + ACL check before display.
   - **`/health`** – summarizes gateway latency, DB, webhook health, cog status. Logic: aggregate async heartbeats into single view.
   - **`/logs export [team?] [range?]`** – extract audit slices (JSON/CSV). Logic: paginated query, rate-limited download link.
   - **`/audit history [user?] [limit?]`** – fetch action history for appeals. Logic: join `PunishmentRecord`, `AuditEvent`, `notes`.
   - **`/member info [user]`** – aggregated view of roles, infractions, welcome state. Logic: pulls from caches and persistence.
   - **`/role sync [role]`** – compare Discord state vs config (e.g., for onboarding). Logic: cross-check `services/RoleResolver` with Discord API, report deltas.

4. **Ops, Developer & Safety Tooling (6)** – can’t live without when maintaining uptime.
   - **`/cog reload [cog]`**, **`/cog unload [cog]`**, **`/cog load [cog]`** – runtime control with validation. Logic: ensures atoms unload safely, emits `AuditEvent`.
   - **`/incident create [title] [description]`** – log major incidents for post-mortems. Logic: persists to `services/IncidentStore`, links to relevant actions.
   - **`/incident status [id]`** – fetch live incident status and responders. Logic: queries store, surfaces assigned team.
   - **`/ticket escalate [id] [priority?]`** – elevate reporter cases to staff queue. Logic: updates `TicketService`, tags roles, reroutes to webhook.
   - **`/bot stats`** – core metrics (shards, memory, DB latency). Use case: quick health triage. Logic: gathers from `core.Metrics`, formats view.
   - **`/debug eval [expression]`** – owner's emergency inspect tool. Use case: debug nil pointer in production. Logic: AST-limited, logs instrumentation.

Modularity note: every command shares helpers (`PermissionGuard`, `ResponseView`, `services/Scheduler`), so new entries automatically inherit validation, logging, and documentation hooks; the catalog in `docs/commands.md` mirrors this structure for seamless expansion.
