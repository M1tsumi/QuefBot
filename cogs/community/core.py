from typing import Optional

import json
import time

import discord
from discord import app_commands
from discord.ext import commands

from core.bot import QuefBot
from core.views import ResponseView
from services.audit import log_moderation_action
from services.permissions import (
    PermissionGuard,
    bot_has_guild_permissions,
    has_guild_permissions,
    is_staff,
)


class AutoRoleManageSelect(discord.ui.Select["AutoRoleManageView"]):
    def __init__(self, view: "AutoRoleManageView") -> None:
        options: list[discord.SelectOption] = []
        guild = view.guild
        for trigger, role_id in sorted(view.mappings.items()):
            role = guild.get_role(role_id)
            label = trigger
            description = role.mention if role is not None else f"Missing role ID {role_id}"
            options.append(discord.SelectOption(label=label, description=description, value=trigger))
        if not options:
            options.append(discord.SelectOption(label="(no triggers)", value="__none__", default=True))
        super().__init__(
            placeholder="Select trigger(s) to remove",
            min_values=0,
            max_values=len(options),
            options=options,
        )
        self._parent_view = view

    async def callback(self, interaction: discord.Interaction) -> None:  # type: ignore[override]
        self._parent_view.selected_triggers = [v for v in self.values if v != "__none__"]
        await interaction.response.defer()


class AutoRoleManageView(discord.ui.View):
    def __init__(self, cog: "Community", guild: discord.Guild, mappings: dict[str, int]) -> None:
        super().__init__(timeout=120)
        self.cog = cog
        self.guild = guild
        self.mappings = mappings
        self.selected_triggers: list[str] = []
        self.add_item(AutoRoleManageSelect(self))

    def _render_content(self) -> str:
        if not self.mappings:
            return "No auto-roles configured for this server."
        lines: list[str] = ["Configured auto-roles:"]
        for trigger, role_id in sorted(self.mappings.items()):
            role = self.guild.get_role(role_id)
            if role is not None:
                lines.append(f"- {trigger}: {role.mention}")
            else:
                lines.append(f"- {trigger}: <@&{role_id}> (role not found)")
        if self.selected_triggers:
            lines.append("")
            lines.append("Selected for removal: " + ", ".join(self.selected_triggers))
        return "\n".join(lines)

    @discord.ui.button(label="Remove selected", style=discord.ButtonStyle.danger)
    async def remove_selected(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        if not self.selected_triggers:
            await interaction.response.edit_message(content=self._render_content(), view=self)
            return
        for trigger in self.selected_triggers:
            self.cog.bot.auto_roles.clear_trigger(self.guild.id, trigger)
        self.mappings = self.cog.bot.auto_roles.all_triggers(self.guild.id)
        self.selected_triggers = []
        # Rebuild the select with updated mappings
        for child in list(self.children):
            if isinstance(child, AutoRoleManageSelect):
                self.remove_item(child)
        self.add_item(AutoRoleManageSelect(self))
        await interaction.response.edit_message(content=self._render_content(), view=self)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.secondary)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="Auto-role manager closed.", view=self)


class VerifyControlView(discord.ui.View):
    def __init__(self, cog: "Community", guild: discord.Guild, member: discord.Member, trigger_roles: dict[str, int], default_trigger: str) -> None:
        super().__init__(timeout=60)
        self.cog = cog
        self.guild = guild
        self.member_id = member.id
        self.trigger_roles = trigger_roles
        self.selected_trigger = default_trigger
        # Build a select for triggers → roles
        options: list[discord.SelectOption] = []
        for trigger, role_id in sorted(trigger_roles.items()):
            role = guild.get_role(role_id)
            label = trigger
            description = role.mention if role is not None else f"Missing role ID {role_id}"
            options.append(discord.SelectOption(label=label, description=description, value=trigger, default=(trigger == default_trigger)))
        if not options:
            options.append(discord.SelectOption(label="(no triggers)", value="__none__", default=True))
        select = discord.ui.Select(placeholder="Choose trigger / role", min_values=1, max_values=1, options=options)

        async def select_callback(interaction: discord.Interaction) -> None:
            value = select.values[0]
            if value == "__none__":
                self.selected_trigger = ""
            else:
                self.selected_trigger = value
            await interaction.response.defer()

        select.callback = select_callback  # type: ignore[assignment]
        self.add_item(select)

    async def _verify_with_method(self, interaction: discord.Interaction, method_label: str) -> None:
        guild = interaction.guild
        if guild is None or guild.id != self.guild.id:
            await interaction.response.edit_message(content="You must run this in the same server.", view=None)
            return
        member = guild.get_member(self.member_id)
        if member is None:
            await interaction.response.edit_message(content="Member is no longer in the server.", view=None)
            return
        trigger = (self.selected_trigger or "verify").lower().strip()
        role_id = self.cog.bot.auto_roles.get_role(guild.id, trigger)
        if not role_id:
            await interaction.response.edit_message(
                content=f"No auto-role is configured for trigger '{trigger}'.",
                view=None,
            )
            return
        role = guild.get_role(role_id)
        if role is None:
            await interaction.response.edit_message(
                content="The configured auto-role no longer exists.",
                view=None,
            )
            return
        try:
            await member.add_roles(role, reason=f"Verified via {method_label} ('{trigger}')")
        except discord.HTTPException:
            await interaction.response.edit_message(content="Failed to assign the verification role.", view=None)
            return
        await log_moderation_action(
            interaction,
            "Verify",
            target=member,
            reason=f"Verification ({method_label}) via '{trigger}'",
        )
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=(
                f"{member.mention} has been verified by {interaction.user.mention} "
                f"using method '{method_label}' and given {role.mention}."
            ),
            view=self,
        )

    @discord.ui.button(label="ID check", style=discord.ButtonStyle.primary)
    async def id_check(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        await self._verify_with_method(interaction, "ID check")

    @discord.ui.button(label="Quiz passed", style=discord.ButtonStyle.success)
    async def quiz_passed(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        await self._verify_with_method(interaction, "Quiz passed")

    @discord.ui.button(label="Manual approval", style=discord.ButtonStyle.secondary)
    async def manual_approval(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        await self._verify_with_method(interaction, "Manual approval")


class ReactionRoleSelect(discord.ui.Select["ReactionRoleManageView"]):
    def __init__(self, view: "ReactionRoleManageView") -> None:
        options: list[discord.SelectOption] = []
        guild = view.guild
        for emoji, role_id in sorted(view.mappings.items()):
            role = guild.get_role(role_id)
            label = emoji
            description = role.mention if role is not None else f"Missing role ID {role_id}"
            options.append(discord.SelectOption(label=label, description=description, value=emoji))
        if not options:
            options.append(discord.SelectOption(label="(no mappings)", value="__none__", default=True))
        super().__init__(
            placeholder="Select emoji mapping(s) to remove",
            min_values=0,
            max_values=len(options),
            options=options,
        )
        self._parent_view = view

    async def callback(self, interaction: discord.Interaction) -> None:  # type: ignore[override]
        self._parent_view.selected_emojis = [v for v in self.values if v != "__none__"]
        await interaction.response.defer()


class ReactionRoleManageView(discord.ui.View):
    def __init__(
        self,
        cog: "Community",
        guild: discord.Guild,
        channel: discord.TextChannel,
        message_id: int,
        mappings: dict[str, int],
    ) -> None:
        super().__init__(timeout=120)
        self.cog = cog
        self.guild = guild
        self.channel_id = channel.id
        self.message_id = message_id
        self.mappings = mappings
        self.selected_emojis: list[str] = []
        self.add_item(ReactionRoleSelect(self))

    def _render_content(self) -> str:
        channel = self.guild.get_channel(self.channel_id)
        if not self.mappings:
            return "No reaction-role mappings are configured for this message."
        header = "Reaction-role mappings for message `{}`".format(self.message_id)
        if isinstance(channel, discord.TextChannel):
            header += f" in {channel.mention}:"
        else:
            header += ":"
        lines: list[str] = [header]
        for emoji, role_id in sorted(self.mappings.items()):
            role = self.guild.get_role(role_id)
            if role is not None:
                lines.append(f"- {emoji} → {role.mention}")
            else:
                lines.append(f"- {emoji} → <@&{role_id}> (role not found)")
        if self.selected_emojis:
            lines.append("")
            lines.append("Selected for removal: " + ", ".join(self.selected_emojis))
        return "\n".join(lines)

    async def _sync_reactions(self, interaction: discord.Interaction) -> None:
        channel = self.guild.get_channel(self.channel_id)
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.edit_message(
                content="Channel no longer exists or is not a text channel.",
                view=None,
            )
            return
        try:
            message = await channel.fetch_message(self.message_id)
        except discord.NotFound:
            await interaction.response.edit_message(
                content="Message not found; cannot sync reaction roles.",
                view=None,
            )
            return
        for emoji, _role_id in self.mappings.items():
            if not any(str(reaction.emoji) == emoji for reaction in message.reactions):
                try:
                    await message.add_reaction(emoji)
                except discord.HTTPException:
                    continue
        await interaction.response.edit_message(
            content="Reaction roles synced for the message.",
            view=self,
        )

    @discord.ui.button(label="Sync now", style=discord.ButtonStyle.primary)
    async def sync_now(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        if not self.mappings:
            await interaction.response.edit_message(content=self._render_content(), view=self)
            return
        await self._sync_reactions(interaction)

    @discord.ui.button(label="Remove selected", style=discord.ButtonStyle.danger)
    async def remove_selected(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        if not self.selected_emojis:
            await interaction.response.edit_message(content=self._render_content(), view=self)
            return
        for emoji in self.selected_emojis:
            self.cog.bot.reaction_roles.clear_mapping(self.guild.id, self.message_id, emoji)
        self.mappings = self.cog.bot.reaction_roles.get_mappings_for_message(self.guild.id, self.message_id)
        self.selected_emojis = []
        # Rebuild select with updated mappings
        for child in list(self.children):
            if isinstance(child, ReactionRoleSelect):
                self.remove_item(child)
        if self.mappings:
            self.add_item(ReactionRoleSelect(self))
        await interaction.response.edit_message(content=self._render_content(), view=self)

    @discord.ui.button(label="Clear all", style=discord.ButtonStyle.danger)
    async def clear_all(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        if not self.mappings:
            await interaction.response.edit_message(content=self._render_content(), view=self)
            return
        self.cog.bot.reaction_roles.clear_message(self.guild.id, self.message_id)
        self.mappings = {}
        self.selected_emojis = []
        # Remove select since there are no mappings left
        for child in list(self.children):
            if isinstance(child, ReactionRoleSelect):
                self.remove_item(child)
        await interaction.response.edit_message(
            content="Reaction-role mappings cleared for the message.",
            view=self,
        )

    @discord.ui.button(label="Close", style=discord.ButtonStyle.secondary)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="Reaction-role manager closed.", view=self)


class AnnouncementControlView(discord.ui.View):
    def __init__(
        self,
        bot: QuefBot,
        channel_id: int,
        content: Optional[str],
        embeds: list[discord.Embed],
        default_delay_minutes: Optional[int] = None,
    ) -> None:
        super().__init__(timeout=120)
        self.bot = bot
        self.channel_id = channel_id
        self.content = content
        self.embeds = embeds
        self.default_delay_minutes = default_delay_minutes if default_delay_minutes and default_delay_minutes > 0 else None

    def _get_channel(self) -> Optional[discord.TextChannel]:
        channel = self.bot.get_channel(self.channel_id)
        if isinstance(channel, discord.TextChannel):
            return channel
        return None

    async def _send_now(self, interaction: discord.Interaction) -> None:
        channel = self._get_channel()
        if channel is None:
            await interaction.response.edit_message(
                content="Announcement channel is no longer available.",
                view=None,
            )
            return
        try:
            await channel.send(content=self.content or None, embeds=self.embeds or None)
        except discord.HTTPException:
            await interaction.response.edit_message(
                content="Failed to send the announcement.",
                view=None,
            )
            return
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"Announcement sent in {channel.mention}.",
            view=self,
        )

    async def _schedule(self, interaction: discord.Interaction, minutes: int) -> None:
        channel = self._get_channel()
        if channel is None:
            await interaction.response.edit_message(
                content="Announcement channel is no longer available.",
                view=None,
            )
            return
        scheduler = self.bot.scheduler
        if scheduler is None:
            await interaction.response.edit_message(
                content="Scheduler is not available; cannot schedule announcements.",
                view=None,
            )
            return
        delay = max(1, minutes * 60)

        async def send_later() -> None:
            try:
                await channel.send(content=self.content or None, embeds=self.embeds or None)
            except discord.HTTPException:
                pass

        identifier = f"announce:{channel.guild.id}:{channel.id}:{int(time.time())}"
        scheduler.schedule(identifier, delay, send_later)
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"Announcement scheduled in {minutes} minute(s) for {channel.mention}.",
            view=self,
        )

    @discord.ui.button(label="Send now", style=discord.ButtonStyle.primary)
    async def send_now(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        await self._send_now(interaction)

    @discord.ui.button(label="Schedule (default)", style=discord.ButtonStyle.secondary)
    async def schedule_default(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        minutes = self.default_delay_minutes if self.default_delay_minutes is not None else 10
        await self._schedule(interaction, minutes)


class SpotlightControlView(discord.ui.View):
    def __init__(self, member: discord.Member, base_description: str) -> None:
        super().__init__(timeout=300)
        self.member_id = member.id
        self.base_description = base_description
        self.category: Optional[str] = None
        self.kudos: int = 0

        options = [
            discord.SelectOption(label="None", value="", description="No specific category", default=True),
            discord.SelectOption(label="Support", value="Support"),
            discord.SelectOption(label="Events", value="Events"),
            discord.SelectOption(label="Contributions", value="Contributions"),
        ]
        select = discord.ui.Select(placeholder="Tag what this spotlight is for", min_values=1, max_values=1, options=options)

        async def select_callback(interaction: discord.Interaction) -> None:
            value = select.values[0]
            self.category = value or None
            await self._update_embed(interaction)

        select.callback = select_callback  # type: ignore[assignment]
        self.add_item(select)

    def _build_description(self) -> str:
        parts: list[str] = []
        if self.category:
            parts.append(f"[{self.category}]")
        parts.append(self.base_description)
        if self.kudos > 0:
            parts.append(f"\n\nKudos: {self.kudos}")
        return " ".join(parts)

    async def _update_embed(self, interaction: discord.Interaction) -> None:
        message = interaction.message
        if message is None or not message.embeds:
            await interaction.response.send_message("Unable to update spotlight message.", ephemeral=True, view=ResponseView())
            return
        embed = message.embeds[0]
        embed.description = self._build_description()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Add kudos", style=discord.ButtonStyle.success)
    async def add_kudos(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        self.kudos += 1
        await self._update_embed(interaction)

    @discord.ui.button(label="Nominate again later", style=discord.ButtonStyle.secondary)
    async def nominate_again(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        self.kudos += 1
        await self._update_embed(interaction)

    @discord.ui.button(label="Close controls", style=discord.ButtonStyle.danger)
    async def close_controls(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)


class Community(commands.Cog, PermissionGuard):
    def __init__(self, bot: QuefBot) -> None:
        self.bot = bot

    @app_commands.command(name="verify", description="Approve and auto-role a member")
    @is_staff()
    @has_guild_permissions(manage_roles=True)
    @bot_has_guild_permissions(manage_roles=True)
    @app_commands.describe(member="Member to verify", method="Verification method/trigger name")
    async def verify(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        method: Optional[str] = None,
    ) -> None:
        await self.ensure_target_hierarchy(interaction, member)
        guild = interaction.guild
        if guild is None or member.guild.id != guild.id:
            await interaction.response.send_message("You must select a member from this server.", ephemeral=True)
            return
        trigger_roles = self.bot.auto_roles.all_triggers(guild.id)
        if not trigger_roles:
            await interaction.response.send_message(
                "No auto-roles are configured for this server.",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        default_trigger = (method or "verify").lower().strip()
        if default_trigger not in trigger_roles:
            # Fallback to an arbitrary configured trigger
            default_trigger = next(iter(trigger_roles.keys()))
        lines = [
            f"Verification panel for {member.mention}.",
            "Choose a trigger/role from the dropdown, then a verification method.",
        ]
        view = VerifyControlView(self, guild, member, trigger_roles, default_trigger)
        await interaction.response.send_message("\n".join(lines), ephemeral=True, view=view)

    auto_role_group = app_commands.Group(name="auto-role", description="Auto-role configuration")

    @auto_role_group.command(name="set", description="Set an auto-role for a trigger")
    @is_staff()
    @has_guild_permissions(manage_roles=True)
    @bot_has_guild_permissions(manage_roles=True)
    @app_commands.describe(
        role="Role to assign",
        trigger="Trigger name (e.g. 'verify', 'join')",
    )
    async def auto_role_set(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        trigger: Optional[str] = None,
    ) -> None:
        guild = interaction.guild
        if guild is None or role.guild.id != guild.id:
            await interaction.response.send_message("You must select a role from this server.", ephemeral=True)
            return
        trigger_name = (trigger or "verify").lower().strip()
        self.bot.auto_roles.set_role(guild.id, trigger_name, role.id)
        await interaction.response.send_message(
            f"Auto-role set: trigger '{trigger_name}' -> {role.mention}.",
            ephemeral=True,
            view=ResponseView(),
        )

    @auto_role_group.command(name="list", description="List auto-role triggers for this server")
    @is_staff()
    @has_guild_permissions(manage_roles=True)
    @bot_has_guild_permissions(manage_roles=True)
    async def auto_role_list(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "This command can only be used in a guild.",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        mappings = self.bot.auto_roles.all_triggers(guild.id)
        if not mappings:
            await interaction.response.send_message(
                "No auto-roles configured for this server.",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        view = AutoRoleManageView(self, guild, mappings)
        content = view._render_content()
        await interaction.response.send_message(content, ephemeral=True, view=view)

    react_role_group = app_commands.Group(name="react-role", description="Reaction-role configuration")

    @react_role_group.command(name="set", description="Configure a reaction-role mapping for a message")
    @is_staff()
    @has_guild_permissions(manage_roles=True)
    @bot_has_guild_permissions(manage_roles=True)
    @app_commands.describe(
        channel="Channel containing the message",
        message_id="ID of the message to attach the reaction-role to",
        emoji="Emoji to use for the reaction",
        role="Role to assign when the emoji is used",
    )
    async def react_role_set(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message_id: int,
        emoji: str,
        role: discord.Role,
    ) -> None:
        guild = interaction.guild
        if guild is None or channel.guild.id != guild.id or role.guild.id != guild.id:
            await interaction.response.send_message("You must select resources from this server.", ephemeral=True)
            return
        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            await interaction.response.send_message("Message not found.", ephemeral=True)
            return
        emoji_str = emoji
        self.bot.reaction_roles.set_mapping(guild.id, message.id, emoji_str, role.id)
        try:
            await message.add_reaction(emoji_str)
        except discord.HTTPException:
            pass
        await interaction.response.send_message(
            f"Reaction role set on message `{message.id}`: {emoji_str} -> {role.mention}.",
            ephemeral=True,
            view=ResponseView(),
        )

    @react_role_group.command(name="clear", description="Clear all reaction-role mappings for a message")
    @is_staff()
    @has_guild_permissions(manage_roles=True)
    @bot_has_guild_permissions(manage_roles=True)
    @app_commands.describe(
        channel="Channel containing the message",
        message_id="ID of the message to clear reaction-roles from",
    )
    async def react_role_clear(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message_id: int,
    ) -> None:
        guild = interaction.guild
        if guild is None or channel.guild.id != guild.id:
            await interaction.response.send_message("You must select a channel from this server.", ephemeral=True)
            return
        existing = self.bot.reaction_roles.get_mappings_for_message(guild.id, message_id)
        if not existing:
            await interaction.response.send_message(
                "No reaction-role mappings are configured for this message.",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        view = ReactionRoleManageView(self, guild, channel, message_id, existing)
        content = view._render_content()
        await interaction.response.send_message(content, ephemeral=True, view=view)

    @react_role_group.command(name="sync", description="Ensure reaction-role mappings match stored state")
    @is_staff()
    @has_guild_permissions(manage_roles=True)
    @bot_has_guild_permissions(manage_roles=True)
    @app_commands.describe(
        channel="Channel containing the message",
        message_id="ID of the message to sync reactions on",
    )
    async def react_role_sync(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message_id: int,
    ) -> None:
        guild = interaction.guild
        if guild is None or channel.guild.id != guild.id:
            await interaction.response.send_message("You must select a channel from this server.", ephemeral=True)
            return
        mappings = self.bot.reaction_roles.get_mappings_for_message(guild.id, message_id)
        if not mappings:
            await interaction.response.send_message(
                "No reaction-role mappings are configured for this message.",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        view = ReactionRoleManageView(self, guild, channel, message_id, mappings)
        content = view._render_content()
        await interaction.response.send_message(content, ephemeral=True, view=view)

    @app_commands.command(name="announce", description="Send or schedule an announcement")
    @is_staff()
    @has_guild_permissions(manage_messages=True)
    @app_commands.describe(
        channel="Channel to send the announcement in",
        message="Announcement message (ignored if embed_json is provided)",
        schedule_minutes="Optional delay before sending, in minutes",
        embed_json="Optional JSON payload defining content/embeds for the announcement",
    )
    async def announce(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message: str,
        schedule_minutes: Optional[int] = None,
        embed_json: Optional[str] = None,
    ) -> None:
        guild = interaction.guild
        if guild is None or channel.guild.id != guild.id:
            await interaction.response.send_message("You must select a channel from this server.", ephemeral=True)
            return
        content: Optional[str] = None
        embeds: list[discord.Embed] = []
        if embed_json:
            try:
                data = json.loads(embed_json)
            except json.JSONDecodeError:
                await interaction.response.send_message(
                    "The JSON payload is invalid.",
                    ephemeral=True,
                    view=ResponseView(),
                )
                return
            raw_content = data.get("content")
            if isinstance(raw_content, str):
                content = raw_content
            embeds_data = data.get("embeds")
            if isinstance(embeds_data, list):
                for item in embeds_data:
                    if isinstance(item, dict):
                        embeds.append(discord.Embed.from_dict(item))
        else:
            content = message
        lines = [
            f"Announcement preview for {channel.mention}:",
        ]
        if content:
            lines.append("")
            lines.append(content)
        if not content and not embeds:
            lines.append("")
            lines.append("(no message content)")
        lines.append("")
        if schedule_minutes is not None and schedule_minutes > 0:
            lines.append(
                f"Default schedule: {schedule_minutes} minute(s). Use the buttons below to send or schedule."
            )
        else:
            lines.append("Use the buttons below to send now or schedule.")
        view = AnnouncementControlView(self.bot, channel.id, content, embeds, schedule_minutes)
        await interaction.response.send_message("\n".join(lines), ephemeral=True, view=view)

    @app_commands.command(name="spotlight", description="Celebrate a member with a spotlight message")
    @is_staff()
    @has_guild_permissions(manage_messages=True)
    @app_commands.describe(member="Member to spotlight", reason="Reason for the spotlight")
    async def spotlight(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: Optional[str] = None,
    ) -> None:
        guild = interaction.guild
        if guild is None or member.guild.id != guild.id:
            await interaction.response.send_message("You must select a member from this server.", ephemeral=True)
            return
        channel: Optional[discord.TextChannel]
        if isinstance(interaction.channel, discord.TextChannel):
            channel = interaction.channel
        else:
            channel = guild.system_channel or self.bot.get_log_channel(guild)
        if channel is None:
            await interaction.response.send_message(
                "No suitable channel found to send the spotlight.",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        description = f"{member.mention} is in the spotlight!"
        if reason:
            description += f"\n\nReason: {reason}"
        embed = discord.Embed(
            title="Community Spotlight",
            description=description,
            colour=discord.Colour.gold(),
        )
        embed.set_footer(text=f"Nominated by {interaction.user}")
        spotlight_view = SpotlightControlView(member, description)
        await channel.send(embed=embed, view=spotlight_view)
        await interaction.response.send_message(
            f"Spotlight posted for {member.mention} in {channel.mention}.",
            ephemeral=True,
            view=ResponseView(),
        )
        await log_moderation_action(
            interaction,
            "Spotlight",
            target=member,
            reason=reason,
        )

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None or payload.user_id == getattr(self.bot.user, "id", None):
            return
        guild_id = payload.guild_id
        mappings = self.bot.reaction_roles.get_mappings_for_message(guild_id, payload.message_id)
        if not mappings:
            return
        emoji_str = str(payload.emoji)
        role_id = mappings.get(emoji_str)
        if not role_id:
            return
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return
        role = guild.get_role(role_id)
        if role is None:
            return
        member = payload.member or guild.get_member(payload.user_id)
        if member is None:
            return
        try:
            await member.add_roles(role, reason="Reaction role opt-in")
        except discord.HTTPException:
            return

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        if payload.guild_id is None or payload.user_id == getattr(self.bot.user, "id", None):
            return
        guild_id = payload.guild_id
        mappings = self.bot.reaction_roles.get_mappings_for_message(guild_id, payload.message_id)
        if not mappings:
            return
        emoji_str = str(payload.emoji)
        role_id = mappings.get(emoji_str)
        if not role_id:
            return
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return
        role = guild.get_role(role_id)
        if role is None:
            return
        member = guild.get_member(payload.user_id)
        if member is None:
            return
        try:
            await member.remove_roles(role, reason="Reaction role removal")
        except discord.HTTPException:
            return


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Community(bot))
