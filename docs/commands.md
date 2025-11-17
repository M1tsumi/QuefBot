# Quef Central Bot Command Reference

## Moderation

- `/warn user reason` 
- `/note user text`
- `/timeout user duration_minutes reason`
- `/mute user [duration_minutes] [reason]`
- `/kick user reason`
- `/ban user reason`
- `/softban user reason`
- `/purge count`
- `/slowmode seconds`
- `/lock reason`
- `/unlock`
- `/jail user [role] [reason]`
- `/pardon user [reason]`

## Welcome

- `/welcome set-channel channel`
- `/welcome template name json_payload`
- `/welcome preview [template] [member]`

Welcome templates use JSON with optional `content` and `embeds` fields. Strings may include tokens such as `{member_mention}`, `{member_name}`, and `{guild_name}` which are resolved at send time.

## Diagnostics

- `/config-check`
- `/health`
- `/bot-stats`
- `/audit-history [user] [limit]`
- `/member-info user`
- `/logs-export [limit]`

## Community & Command Center

- `/verify member [method]`
- `/auto-role set role [trigger]`
- `/react-role set channel message_id emoji role`
- `/react-role clear channel message_id`
- `/react-role sync channel message_id`
- `/announce channel message [schedule_minutes]`
- `/spotlight member [reason]`

## Ops & Developer Tools

- `/cog reload name`
- `/cog load name`
- `/cog unload name`
- `/incident create title description`
- `/incident status incident_id`
- `/ticket escalate ticket_id [priority]`
- `/ticket config category`
- `/ticket panel [channel]`
- `/debug-eval expression` (owner only)
