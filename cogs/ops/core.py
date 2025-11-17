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
        incident = self.bot.incidents.create_incident(title, description, interaction.user.id)
        embed = discord.Embed(
            title=f"Incident #{incident.id}: {incident.title}",
            description=incident.description,
            colour=discord.Colour.red(),
            timestamp=incident.created_at,
        )
        embed.add_field(name="Status", value=incident.status, inline=True)
        embed.add_field(name="Created By", value=f"<@{incident.created_by}>", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True, view=ResponseView())

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
        embed = discord.Embed(
            title=f"Incident #{incident.id}: {incident.title}",
            description=incident.description,
            colour=discord.Colour.red(),
            timestamp=incident.updated_at,
        )
        embed.add_field(name="Status", value=incident.status, inline=True)
        embed.add_field(name="Created By", value=f"<@{incident.created_by}>", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True, view=ResponseView())

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
        effective_priority = priority or "medium"
        ticket = self.bot.tickets.escalate_ticket(ticket_id, effective_priority, interaction.user.id)
        await interaction.response.send_message(
            f"Ticket #{ticket.id} escalated with priority '{ticket.priority}'.",
            ephemeral=True,
            view=ResponseView(),
        )

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
        await interaction.response.send_message(
            f"Ticket category set to {category.mention}.",
            ephemeral=True,
            view=ResponseView(),
        )

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
        await interaction.response.send_message(
            f"Result: {result!r}",
            ephemeral=True,
            view=ResponseView(),
        )


async def setup(bot: commands.Bot) -> None:
    if isinstance(bot, QuefBot):
        bot.add_view(TicketOpenView())
    await bot.add_cog(Ops(bot))  # type: ignore[arg-type]
