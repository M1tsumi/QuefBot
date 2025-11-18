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

## Command Rework Roadmap (Components v2)

The list below covers **all current slash commands**, ordered from **highest** to **lowest** rework priority. Each entry has:

- **Logic** – what the command does now/should do.
- **Components v2 idea** – how we want to use modern Discord components (buttons, selects, modals, etc.), **not embeds**, to make the UX smoother.

### High Priority

- **`/lock`**
  - **Logic:** Lock the current text channel by preventing `@everyone` from sending messages, while keeping staff roles able to talk, and log the action.
  - **Components v2 idea:** Ephemeral confirmation panel with buttons like **"Lock for 5 min / 1 h / Until unlocked"**, plus a dropdown to choose which non-staff role groups lose send permissions. A toggle-style component can opt into sending a visible "channel locked" notice.

- **`/unlock`**
  - **Logic:** Revert the channel’s `@everyone` overwrite so normal users can speak again and log the unlock.
  - **Components v2 idea:** Follow-up panel with **"Unlock now"** and **"Schedule unlock"** buttons, plus an optional modal to add a short unlock message that will be posted into the channel.

- **`/jail`**
  - **Logic:** Apply a jail role to a member (configured or provided) so they only see a restricted channel, store jail state, and log the punishment.
  - **Components v2 idea:** After jailing, show an ephemeral control view with buttons for **"Adjust duration"**, **"Move to another jail channel"**, and **"Pardon"**, and a select menu to quickly switch between existing jail roles.

- **`/mute`**
  - **Logic:** Apply the configured mute role, optionally set up auto-unmute using the scheduler, record the punishment, and log the moderation action.
  - **Components v2 idea:** Use a modal to collect duration + reason instead of raw text arguments, and provide preset duration buttons (5m, 1h, 24h). Add a button **"Convert to timeout"** to swap to Discord’s native timeout.

- **`/timeout`**
  - **Logic:** Apply a Discord communication timeout for a duration, record and schedule clearing of the timeout, and log.
  - **Components v2 idea:** Show a Components v2 time picker / select for common durations and a button row: **"Shorten"**, **"Extend"**, **"Clear now"** that can be pressed later from the same ephemeral interaction.

- **`/warn`**
  - **Logic:** Warn a member, store a punishment record, log the action, optionally including a reason, and optionally send a meme message in the log channel.
  - **Components v2 idea:** Ephemeral warning composer: severity buttons (Info / Minor / Major), a modal to capture a structured reason, and a toggle to decide whether to ping the member via DM.

- **`/kick`**
  - **Logic:** Kick a member from the guild, record a punishment entry, and log the moderation event.
  - **Components v2 idea:** Confirmation dialog using buttons **"Confirm kick"** / **"Cancel"**, with a modal to optionally DM a pre-filled template reason to the target before executing the kick.

- **`/ban`**
  - **Logic:** Ban a member with optional reason, record the ban, and log.
  - **Components v2 idea:** Use buttons to select ban type (Permanent / 7d / 30d) and checkboxes/toggles for "Delete last 24h of messages". A modal lets staff customize an appeal link that’s recorded alongside the ban.

- **`/softban`**
  - **Logic:** Ban and immediately unban a member to clear recent messages while not keeping them banned, plus log the action.
  - **Components v2 idea:** Buttons for **"Softban 24h history"** vs **"Softban 7d history"** (deletion window presets), and a confirmation row to avoid accidental presses.

- **`/pardon`**
  - **Logic:** Clear active jail state, mute role, timeout, and any active ban for the user, then log a "Pardon" record.
  - **Components v2 idea:** Show a Components v2 checklist (multi-select) for which states to clear (jail, mute, timeout, ban) before executing. A button **"Undo"** can schedule a quick re-apply within a short grace window.

- **`/purge`**
  - **Logic:** Bulk delete up to 100 recent messages and report how many were removed, then log the purge.
  - **Components v2 idea:** Ephemeral control panel with a slider/select for count, and toggles for filters such as "Only from this user" or "Only with attachments". A confirmation button starts the purge and a secondary button **"Preview"** shows a lightweight summary count (no embeds) before deletion.

- **`/slowmode`**
  - **Logic:** Set or clear the slowmode delay for the current text channel and log the change.
  - **Components v2 idea:** Use a Components v2 slider or select for delay (0, 5, 10, 30, 60s, etc.) and a button **"Apply to all channels in category"** that triggers a confirmation modal.

- **`/audit-history`**
  - **Logic:** Fetch punishment history for the guild (optionally filtered to a user) with a cap on number of entries.
  - **Components v2 idea:** Ephemeral history browser with a select component to filter by action type (Warn/Mute/Ban/etc.) and navigation buttons **"Prev" / "Next"** to page through entries without re-running the command.

- **`/member-info`**
  - **Logic:** Show a member’s moderation summary: infractions, notes, roles, and recent history.
  - **Components v2 idea:** Panel with tabs implemented via buttons (Overview / Infractions / Notes). Each button press swaps the displayed info using followup edits, plus a button **"Open case"** that opens a modal for starting an incident tied to that member.

- **`/config-check`**
  - **Logic:** Display sanitized configuration key-value pairs for the bot.
  - **Components v2 idea:** Use a select menu to choose which config section to view (Auth, Logging, Roles, Tickets, etc.) and a search box modal opened by a **"Search key"** button to filter down to a particular setting.

- **`/health`**
  - **Logic:** Report basic bot health (latency, guild count, uptime, etc.).
  - **Components v2 idea:** Buttons to run targeted health checks (Gateway, Database, Webhooks) and show pass/fail states inline using text + status icons, plus a **"Run all checks"** button that refreshes values.

- **`/bot-stats`**
  - **Logic:** Show runtime stats like uptime, shards, guild count, and possibly other metrics.
  - **Components v2 idea:** Components row with buttons for **"Shard breakdown"**, **"Top guilds"**, **"Memory"**, each triggering a followup message or edit with the requested subset in plain text.

- **`/logs-export`**
  - **Logic:** Export recent punishments and notes as CSV and send as a file.
  - **Components v2 idea:** Modal with fields for date range and record types, and buttons **"Export CSV"** / **"Export JSON"**. A Components v2 file-upload input could optionally accept an existing filter config file.

- **`/incident create`**
  - **Logic:** Create a new incident with title, description, and creator ID, storing it in the incident store.
  - **Components v2 idea:** Incident creation modal with separate text inputs for title, impact, and steps taken, plus buttons **"Mark as critical"** and **"Auto-follow"** that subscribe the executor to updates.

- **`/incident status`**
  - **Logic:** Look up an incident by ID and present its current status and details.
  - **Components v2 idea:** Buttons to change status (Open / Investigating / Resolved), and a select for assigning a "lead" from recent staff members, all applied without re-running the command.

- **`/incident delete`**
  - **Logic:** Delete an incident from the incident store when no longer needed.
  - **Components v2 idea:** Danger-styled **"Confirm delete"** button with an additional confirmation modal requiring the user to type the incident ID before deletion.

- **`/ticket config`**
  - **Logic:** Configure which category tickets are created in for a guild.
  - **Components v2 idea:** Dropdown showing all categories in the server, plus a **"Test creation"** button that spins up a dummy ticket channel to verify permissions.

- **`/ticket panel`**
  - **Logic:** Send a "Support Tickets" panel with an "Open Ticket" button in a chosen channel.
  - **Components v2 idea:** Use Components v2 to let staff configure the panel layout inline: toggles for "Allow attachments", "Require category selection", and a dropdown for which queue label to attach to new tickets.

- **`/ticket escalate`**
  - **Logic:** Update a ticket’s priority and record who escalated it.
  - **Components v2 idea:** Priority selector (Low/Medium/High/Critical) implemented as a segmented control, plus a **"Ping on-call"** button that sends a followup mentioning a configured on-call role.

- **`/debug-eval`**
  - **Logic:** Owner-only evaluation of a restricted Python expression with strict AST checks and limited locals.
  - **Components v2 idea:** A small evaluation console with a text-input component for the expression, preset buttons for common snippets (e.g., `len(bot.guilds)`), and a **"Re-run"** button on the last expression.

### Medium Priority

- **`/warn`**, **`/note`**, **`/timeout`**, **`/mute`**, **`/kick`**, **`/ban`**, **`/softban`**, **`/pardon`** (moderation flows already functional but can gain richer Components v2 panels as described above).

- **`/verify`**
  - **Logic:** Approve a member and assign a preconfigured auto-role, logging a verification action.
  - **Components v2 idea:** Verification panel with buttons for common methods (ID check, quiz passed, manual approval) and a dropdown to override which role is assigned for this one interaction.

- **`/auto-role set`** and **`/auto-role list`**
  - **Logic:** Configure and list trigger→role mappings for auto-role assignment.
  - **Components v2 idea:** Use a table-like view rendered in text plus a Components v2 multi-select to toggle which triggers are active; a **"Add mapping"** button opens a modal to map trigger string to a role.

- **`/react-role set`**, **`/react-role clear`**, **`/react-role sync`**
  - **Logic:** Manage reaction-role mappings and ensure message reactions line up with stored state.
  - **Components v2 idea:** Components view that lists existing mappings with remove buttons and a **"Sync now"** button, plus a modal for adding a new emoji→role mapping without retyping IDs.

- **`/announce`**
  - **Logic:** Send or schedule announcements to a target channel, optionally using JSON-defined payloads.
  - **Components v2 idea:** Scheduling UI with a date/time picker, a checkbox for "Ping @everyone" or specific roles, and a **"Preview message"** button that shows the final formatted message text-only.

- **`/spotlight`**
  - **Logic:** Post a spotlight celebration for a member in an appropriate channel and log the event.
  - **Components v2 idea:** Buttons for "Add kudos", "Nominate again later", and a select menu to tag what the spotlight is for (Support, Events, Contributions), all reflected in the message content.

- **`/welcome set-channel`**, **`/welcome template`**, **`/welcome preview`**
  - **Logic:** Configure the welcome channel, store JSON templates, and preview the welcome output.
  - **Components v2 idea:** Template manager view with a dropdown of template names, buttons to duplicate or delete templates, and a file-upload component to import/export templates as JSON.

### Low Priority

- **`/note`**
  - **Logic:** Attach a private moderator note to a member and store it in history.
  - **Components v2 idea:** Simple modal with a multi-line text field and a toggle for "Mark as important" to surface in member summaries.

- **`/react-role clear`**, **`/react-role sync`** (already functional; additional components mainly for convenience as above).

- **`/slowmode`**, **`/unlock`**, **`/kick`**, **`/softban`**, **`/purge`** (core behavior is solid; Components v2 usage is primarily to add presets, confirmations, and quality-of-life controls rather than change logic).
