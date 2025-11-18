from __future__ import annotations

from typing import Optional

import ast
import io

import discord
from discord import app_commands
from discord.ext import commands

from core.bot import QuefBot
from core.views import ResponseView
from services.audit import log_moderation_action
from services.permissions import is_staff


DEV_ADMIN_IDS = {1051142172130422884}


class TicketControlsView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, custom_id="ticket_close")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "This button can only be used in a server.",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        client = interaction.client
        if not isinstance(client, QuefBot):
            await interaction.response.send_message(
                "Ticket system is not available for this bot.",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "This button can only be used in a ticket text channel.",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        ticket = client.tickets.get_ticket_by_channel(guild.id, channel.id)
        if ticket is None:
            await interaction.response.send_message(
                "No ticket is associated with this channel.",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message(
                "Could not resolve member for this interaction.",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        is_reporter = ticket.reporter_id == member.id
        is_staff_like = (
            member.guild_permissions.manage_channels
            or member.guild_permissions.manage_messages
            or member.guild_permissions.administrator
        )
        if not (is_reporter or is_staff_like):
            await interaction.response.send_message(
                "Only the ticket opener or staff can close this ticket.",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        transcript_channel_id = client.tickets.get_transcript_channel(guild.id)
        transcript_channel: Optional[discord.TextChannel] = None
        if transcript_channel_id is not None:
            target = guild.get_channel(transcript_channel_id)
            if isinstance(target, discord.TextChannel):
                transcript_channel = target
        if transcript_channel is not None:
            lines = []
            async for msg in channel.history(limit=None, oldest_first=True):
                ts = msg.created_at.isoformat()
                author = f"{msg.author} ({msg.author.id})"
                content = msg.content or ""\
                
                if msg.attachments:
                    attachment_info = " ".join(a.url for a in msg.attachments)
                    if content:
                        content = f"{content} [Attachments: {attachment_info}]"
                    else:
                        content = f"[Attachments: {attachment_info}]"
                lines.append(f"[{ts}] {author}: {content}")
            text = "\n".join(lines) or "No messages."
            buffer = io.BytesIO(text.encode("utf-8"))
            file = discord.File(fp=buffer, filename=f"ticket-{ticket.id}.txt")
            embed = discord.Embed(
                title=f"Ticket #{ticket.id} closed",
                description=(
                    f"Reporter: <@{ticket.reporter_id}>\n"
                    f"Closed by: {interaction.user.mention}"
                ),
                colour=discord.Colour.dark_gray(),
            )
            try:
                await transcript_channel.send(embed=embed, file=file, view=ResponseView())
            except discord.HTTPException:
                pass
        client.tickets.close_ticket(ticket.id)
        try:
            await interaction.response.send_message(
                "Closing ticket...",
                ephemeral=True,
                view=ResponseView(),
            )
        except discord.HTTPException:
            pass
        try:
            await channel.delete(reason=f"Ticket #{ticket.id} closed by {interaction.user}")
        except discord.HTTPException:
            pass


class TicketOpenView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.primary, custom_id="ticket_open")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Tickets can only be opened in a server.",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        client = interaction.client
        if not isinstance(client, QuefBot):
            await interaction.response.send_message(
                "Ticket system is not available for this bot.",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message(
                "Could not resolve member for this interaction.",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        tickets = client.tickets
        category_id = tickets.get_category(guild.id)
        if category_id is None:
            await interaction.response.send_message(
                "Ticket system is not configured yet. Ask staff to run `/ticket config`.",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        existing = tickets.get_open_ticket_for_user(guild.id, member.id)
        if existing is not None:
            channel_id = tickets.get_channel_for_ticket(existing.id)
            channel = guild.get_channel(channel_id) if channel_id else None
            if isinstance(channel, (discord.TextChannel, discord.Thread)):
                await interaction.response.send_message(
                    f"You already have an open ticket in {channel.mention}.",
                    ephemeral=True,
                    view=ResponseView(),
                )
            else:
                await interaction.response.send_message(
                    "You already have an open ticket.",
                    ephemeral=True,
                    view=ResponseView(),
                )
            return
        category = guild.get_channel(category_id)
        if not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message(
                "Ticket category is misconfigured. Ask staff to run `/ticket config` again.",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        ticket = tickets.create_ticket(member.id, priority="medium")
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            ),
        }
        config = client.config
        for role_id in getattr(config, "staff_role_ids", []) or []:
            role = guild.get_role(role_id)
            if role is not None:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_messages=True,
                )
        channel_name = f"ticket-{member.name}-{ticket.id}".replace(" ", "-")
        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"Ticket #{ticket.id} for {member} ({member.id})",
                reason="Support ticket opened",
            )
        except discord.HTTPException:
            await interaction.response.send_message(
                "Failed to create a ticket channel. Please contact staff.",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        tickets.link_channel(ticket.id, guild.id, channel.id)
        await channel.send(
            f"{member.mention} opened a ticket. Staff will be with you shortly.",
            view=ResponseView(),
        )
        await interaction.response.send_message(
            f"Your ticket has been created in {channel.mention}.",
            ephemeral=True,
            view=ResponseView(),
        )


class IncidentCreateView(discord.ui.View):
    def __init__(self, cog: "Ops", title: str, description: str) -> None:
        super().__init__(timeout=120)
        self.cog = cog
        self.title = title
        self.description = description

    @discord.ui.button(label="Create incident", style=discord.ButtonStyle.primary)
    async def create_incident(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        incident = self.cog.bot.incidents.create_incident(self.title, self.description, interaction.user.id)
        lines = [
            f"Incident #{incident.id} created.",
            f"Title: {incident.title}",
            f"Description: {incident.description}",
            f"Status: {incident.status}",
            f"Created by: <@{incident.created_by}>",
            f"Created at: {incident.created_at:%Y-%m-%d %H:%M UTC}",
        ]
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="\n".join(lines), view=self)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="Incident creation cancelled.", view=self)


class IncidentStatusView(discord.ui.View):
    def __init__(self, cog: "Ops", incident_id: int) -> None:
        super().__init__(timeout=120)
        self.cog = cog
        self.incident_id = incident_id

    def _format_incident(self, incident) -> str:
        return "\n".join(
            [
                f"Incident #{incident.id}",
                f"Title: {incident.title}",
                f"Description: {incident.description}",
                f"Status: {incident.status}",
                f"Created by: <@{incident.created_by}>",
                f"Created at: {incident.created_at:%Y-%m-%d %H:%M UTC}",
                f"Last updated: {incident.updated_at:%Y-%m-%d %H:%M UTC}",
            ]
        )

    async def _set_status(self, interaction: discord.Interaction, status: str) -> None:
        updated = self.cog.bot.incidents.set_status(self.incident_id, status)
        if updated is None:
            await interaction.response.edit_message(content="Incident not found.", view=None)
            return
        for item in self.children:
            item.disabled = False
        await interaction.response.edit_message(content=self._format_incident(updated), view=self)

    @discord.ui.button(label="Open", style=discord.ButtonStyle.secondary)
    async def set_open(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        await self._set_status(interaction, "open")

    @discord.ui.button(label="Investigating", style=discord.ButtonStyle.primary)
    async def set_investigating(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        await self._set_status(interaction, "investigating")

    @discord.ui.button(label="Resolved", style=discord.ButtonStyle.success)
    async def set_resolved(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        await self._set_status(interaction, "resolved")


class IncidentDeleteView(discord.ui.View):
    def __init__(self, cog: "Ops", incident_id: int, title: str) -> None:
        super().__init__(timeout=60)
        self.cog = cog
        self.incident_id = incident_id
        self.title = title

    @discord.ui.button(label="Confirm delete", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        deleted = self.cog.bot.incidents.delete_incident(self.incident_id)
        if not deleted:
            await interaction.response.edit_message(content="Incident could not be deleted (it may have been removed already).", view=None)
            return
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"Incident #{self.incident_id} ('{self.title}') deleted.",
            view=self,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="Incident deletion cancelled.", view=self)


class TicketEscalateView(discord.ui.View):
    def __init__(self, cog: "Ops", ticket_id: int, current_priority: str) -> None:
        super().__init__(timeout=60)
        self.cog = cog
        self.ticket_id = ticket_id
        self.current_priority = current_priority

    async def _apply_priority(self, interaction: discord.Interaction, priority: str) -> None:
        ticket = self.cog.bot.tickets.get_ticket(self.ticket_id)
        if ticket is None:
            await interaction.response.edit_message(content="Ticket not found.", view=None)
            return
        ticket = self.cog.bot.tickets.escalate_ticket(self.ticket_id, priority, interaction.user.id)
        await log_moderation_action(
            interaction,
            "Ticket Escalate",
            target=None,
            reason=f"Escalated ticket #{ticket.id} to priority '{ticket.priority}'",
        )
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"Ticket #{ticket.id} escalated to '{ticket.priority}'.",
            view=self,
        )

    @discord.ui.button(label="Low", style=discord.ButtonStyle.secondary)
    async def set_low(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        await self._apply_priority(interaction, "low")

    @discord.ui.button(label="Medium", style=discord.ButtonStyle.primary)
    async def set_medium(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        await self._apply_priority(interaction, "medium")

    @discord.ui.button(label="High", style=discord.ButtonStyle.primary)
    async def set_high(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        await self._apply_priority(interaction, "high")

    @discord.ui.button(label="Critical", style=discord.ButtonStyle.danger)
    async def set_critical(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        await self._apply_priority(interaction, "critical")


class TicketConfigView(discord.ui.View):
    def __init__(self, bot: QuefBot, guild_id: int, category_id: int) -> None:
        super().__init__(timeout=60)
        self.bot = bot
        self.guild_id = guild_id
        self.category_id = category_id

    @discord.ui.button(label="Send test ticket panel here", style=discord.ButtonStyle.primary)
    async def send_test_panel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        guild = interaction.guild
        channel = interaction.channel
        if guild is None or guild.id != self.guild_id or not isinstance(channel, discord.TextChannel):
            await interaction.response.edit_message(
                content="This button can only be used in a text channel in the configured guild.",
                view=None,
            )
            return
        category = guild.get_channel(self.category_id)
        if not isinstance(category, discord.CategoryChannel):
            await interaction.response.edit_message(
                content="Ticket category is misconfigured. Run `/ticket config` again.",
                view=None,
            )
            return
        embed = discord.Embed(
            title="Support Tickets",
            description="Click **Open Ticket** to create a private channel with the staff team.",
            colour=discord.Colour.blurple(),
        )
        embed.set_footer(text="Use this for support, appeals, or other private matters.")
        view = TicketOpenView()
        try:
            await channel.send(embed=embed, view=view)
        except discord.HTTPException:
            await interaction.response.edit_message(content="Failed to send test ticket panel.", view=None)
            return
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content=f"Test ticket panel sent in {channel.mention}.", view=self)


def _resolve_extension_name(name: str) -> str:
    name = name.strip()
    if not name:
        return name
    if name.startswith("cogs."):
        return name
    if "." not in name:
        return f"cogs.{name}.core"
    return name


class Ops(commands.Cog):
    def __init__(self, bot: QuefBot) -> None:
        self.bot = bot

    def _is_owner(self, user: discord.abc.User) -> bool:
        owner_ids = self.bot.config.owner_ids or []
        return user.id in owner_ids

    ops_cog_group = app_commands.Group(name="cog", description="Cog management commands")

    @ops_cog_group.command(name="reload", description="Reload a cog extension")
    @is_staff()
    @app_commands.describe(name="Name of the cog to reload (e.g. 'moderation', 'cogs.moderation.core')")
    async def reload_cog(self, interaction: discord.Interaction, name: str) -> None:
        ext = _resolve_extension_name(name)
        try:
            await self.bot.reload_extension(ext)
        except Exception as exc:
            await interaction.response.send_message(
                f"Failed to reload extension '{ext}': {exc}",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        await interaction.response.send_message(
            f"Reloaded extension `{ext}`.",
            ephemeral=True,
            view=ResponseView(),
        )
        await log_moderation_action(
            interaction,
            "Cog Reload",
            target=None,
            reason=f"Reloaded {ext}",
        )

    @ops_cog_group.command(name="load", description="Load a cog extension")
    @is_staff()
    @app_commands.describe(name="Name of the cog to load (e.g. 'moderation', 'cogs.moderation.core')")
    async def load_cog(self, interaction: discord.Interaction, name: str) -> None:
        ext = _resolve_extension_name(name)
        try:
            await self.bot.load_extension(ext)
        except Exception as exc:
            await interaction.response.send_message(
                f"Failed to load extension '{ext}': {exc}",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        await interaction.response.send_message(
            f"Loaded extension `{ext}`.",
            ephemeral=True,
            view=ResponseView(),
        )
        await log_moderation_action(
            interaction,
            "Cog Load",
            target=None,
            reason=f"Loaded {ext}",
        )

    @ops_cog_group.command(name="unload", description="Unload a cog extension")
    @is_staff()
    @app_commands.describe(name="Name of the cog to unload (e.g. 'moderation', 'cogs.moderation.core')")
    async def unload_cog(self, interaction: discord.Interaction, name: str) -> None:
        ext = _resolve_extension_name(name)
        try:
            await self.bot.unload_extension(ext)
        except Exception as exc:
            await interaction.response.send_message(
                f"Failed to unload extension '{ext}': {exc}",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        await interaction.response.send_message(
            f"Unloaded extension `{ext}`.",
            ephemeral=True,
            view=ResponseView(),
        )
        await log_moderation_action(
            interaction,
            "Cog Unload",
            target=None,
            reason=f"Unloaded {ext}",
        )

    incident_group = app_commands.Group(name="incident", description="Incident tracking commands")

    @incident_group.command(name="create", description="Create a new incident")
    @is_staff()
    @app_commands.describe(title="Short title for the incident", description="Detailed description of the incident")
    async def incident_create(self, interaction: discord.Interaction, title: str, description: str) -> None:
        lines = [
            "Previewing new incident:",
            f"Title: {title}",
            f"Description: {description}",
            f"Requested by: {interaction.user.mention}",
            "",
            "Use the buttons below to create or cancel.",
        ]
        view = IncidentCreateView(self, title, description)
        await interaction.response.send_message("\n".join(lines), ephemeral=True, view=view)

    @incident_group.command(name="status", description="Get the status of an incident")
    @is_staff()
    @app_commands.describe(incident_id="ID of the incident to look up")
    async def incident_status(self, interaction: discord.Interaction, incident_id: int) -> None:
        incident = self.bot.incidents.get_incident(incident_id)
        if incident is None:
            await interaction.response.send_message(
                "Incident not found.",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        lines = [
            f"Incident #{incident.id}",
            f"Title: {incident.title}",
            f"Description: {incident.description}",
            f"Status: {incident.status}",
            f"Created by: <@{incident.created_by}>",
            f"Created at: {incident.created_at:%Y-%m-%d %H:%M UTC}",
            f"Last updated: {incident.updated_at:%Y-%m-%d %H:%M UTC}",
        ]
        view = IncidentStatusView(self, incident.id)
        await interaction.response.send_message("\n".join(lines), ephemeral=True, view=view)

    @incident_group.command(name="delete", description="Delete an existing incident")
    @is_staff()
    @app_commands.describe(incident_id="ID of the incident to delete")
    async def incident_delete(self, interaction: discord.Interaction, incident_id: int) -> None:
        incident = self.bot.incidents.get_incident(incident_id)
        if incident is None:
            await interaction.response.send_message(
                "Incident not found.",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        content = (
            f"Are you sure you want to delete Incident #{incident.id}: '{incident.title}'? "
            "This cannot be undone."
        )
        view = IncidentDeleteView(self, incident.id, incident.title)
        await interaction.response.send_message(content, ephemeral=True, view=view)

    ticket_group = app_commands.Group(name="ticket", description="Ticket queue commands")

    @ticket_group.command(name="escalate", description="Escalate a ticket to the staff queue")
    @is_staff()
    @app_commands.describe(ticket_id="Ticket identifier", priority="Priority level (low/medium/high/critical)")
    async def ticket_escalate(
        self,
        interaction: discord.Interaction,
        ticket_id: int,
        priority: Optional[str] = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "This command can only be used in a guild.",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        ticket = self.bot.tickets.get_ticket(ticket_id)
        if ticket is None:
            await interaction.response.send_message(
                "Ticket not found.",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        content = (
            f"Ticket #{ticket.id} (status: {ticket.status}, priority: {ticket.priority}). "
            "Choose a new priority below to escalate."
        )
        view = TicketEscalateView(self, ticket.id, ticket.priority)
        await interaction.response.send_message(content, ephemeral=True, view=view)

    @ticket_group.command(name="config", description="Configure where ticket channels are created")
    @is_staff()
    @app_commands.describe(category="Category to create ticket channels in")
    async def ticket_config(self, interaction: discord.Interaction, category: discord.CategoryChannel) -> None:
        guild = interaction.guild
        if guild is None or category.guild.id != guild.id:
            await interaction.response.send_message(
                "You must choose a category from this server.",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        self.bot.tickets.set_category(guild.id, category.id)
        content = (
            f"Ticket category set to {category.mention}. "
            "Use the button below to send a test ticket panel in this channel."
        )
        view = TicketConfigView(self.bot, guild.id, category.id)
        await interaction.response.send_message(content, ephemeral=True, view=view)

    @ticket_group.command(name="panel", description="Send a ticket panel with an Open Ticket button")
    @is_staff()
    @app_commands.describe(channel="Channel to send the ticket panel in (defaults to current channel)")
    async def ticket_panel(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "This command can only be used in a guild.",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel) or target.guild.id != guild.id:
            await interaction.response.send_message(
                "You must choose a text channel from this server.",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        category_id = self.bot.tickets.get_category(guild.id)
        if category_id is None:
            await interaction.response.send_message(
                "Ticket system is not configured yet. Use `/ticket config` first.",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        embed = discord.Embed(
            title="Support Tickets",
            description="Click **Open Ticket** to create a private channel with the staff team.",
            colour=discord.Colour.blurple(),
        )
        embed.set_footer(text="Use this for support, appeals, or other private matters.")
        view = TicketOpenView()
        await target.send(embed=embed, view=view)
        await interaction.response.send_message(
            f"Ticket panel sent in {target.mention}.",
            ephemeral=True,
            view=ResponseView(),
        )

    @app_commands.command(name="debug-eval", description="Owner-only emergency evaluation tool")
    @app_commands.describe(expression="Python expression to evaluate (owner only)")
    async def debug_eval(self, interaction: discord.Interaction, expression: str) -> None:
        if not self._is_owner(interaction.user):
            raise app_commands.CheckFailure("Only bot owners may use this command.")
        if len(expression) > 200:
            await interaction.response.send_message(
                "Expression is too long.",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        try:
            parsed = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            await interaction.response.send_message(
                f"Syntax error: {exc}",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        for node in ast.walk(parsed):
            if isinstance(node, (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal, ast.Lambda)):
                await interaction.response.send_message(
                    "Disallowed syntax in expression.",
                    ephemeral=True,
                    view=ResponseView(),
                )
                return
        allowed_globals = {"__builtins__": {}}
        allowed_locals = {
            "bot": self.bot,
            "discord": discord,
            "interaction": interaction,
        }
        try:
            result = eval(compile(parsed, "<debug-eval>", "eval"), allowed_globals, allowed_locals)
        except Exception as exc:
            await interaction.response.send_message(
                f"Evaluation error: {exc}",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        result_repr = repr(result)
        if len(result_repr) > 1000:
            result_repr = result_repr[:1000] + "...(truncated)"
        expression_block = f"```py\n{expression}\n```"
        result_block = f"```py\n{result_repr}\n```"
        embed = discord.Embed(
            title="Debug eval result",
            colour=discord.Colour.blurple(),
        )
        embed.add_field(name="Expression", value=expression_block, inline=False)
        embed.add_field(name="Result", value=result_block, inline=False)
        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
            view=ResponseView(),
        )


async def setup(bot: commands.Bot) -> None:
    if isinstance(bot, QuefBot):
        bot.add_view(TicketOpenView())
    await bot.add_cog(Ops(bot))  # type: ignore[arg-type]
