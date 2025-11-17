from typing import Optional

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
        trigger = (method or "verify").lower().strip()
        role_id = self.bot.auto_roles.get_role(guild.id, trigger)
        if not role_id:
            await interaction.response.send_message(
                f"No auto-role is configured for trigger '{trigger}'.",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        role = guild.get_role(role_id)
        if role is None:
            await interaction.response.send_message("The configured auto-role no longer exists.", ephemeral=True)
            return
        await member.add_roles(role, reason=f"Verified via '{trigger}'")
        await interaction.response.send_message(
            f"{member.mention} has been verified and given {role.mention}.",
            ephemeral=True,
            view=ResponseView(),
        )
        await log_moderation_action(
            interaction,
            "Verify",
            target=member,
            reason=f"Verification via '{trigger}'",
        )

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
        self.bot.reaction_roles.clear_message(guild.id, message_id)
        await interaction.response.send_message(
            "Reaction-role mappings cleared for the message.",
            ephemeral=True,
            view=ResponseView(),
        )

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
        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            await interaction.response.send_message("Message not found.", ephemeral=True)
            return
        for emoji, _role_id in mappings.items():
            if not any(str(reaction.emoji) == emoji for reaction in message.reactions):
                try:
                    await message.add_reaction(emoji)
                except discord.HTTPException:
                    continue
        await interaction.response.send_message(
            "Reaction roles synced for the message.",
            ephemeral=True,
            view=ResponseView(),
        )

    @app_commands.command(name="announce", description="Send or schedule an announcement")
    @is_staff()
    @has_guild_permissions(manage_messages=True)
    @app_commands.describe(
        channel="Channel to send the announcement in",
        message="Announcement message",
        schedule_minutes="Optional delay before sending, in minutes",
    )
    async def announce(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message: str,
        schedule_minutes: Optional[int] = None,
    ) -> None:
        guild = interaction.guild
        if guild is None or channel.guild.id != guild.id:
            await interaction.response.send_message("You must select a channel from this server.", ephemeral=True)
            return
        if schedule_minutes is None or schedule_minutes <= 0:
            await channel.send(message)
            await interaction.response.send_message(
                "Announcement sent.",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        scheduler = self.bot.scheduler
        if scheduler is None:
            await interaction.response.send_message(
                "Scheduler is not available; cannot schedule announcements.",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        delay = max(1, schedule_minutes * 60)

        async def send_later() -> None:
            try:
                await channel.send(message)
            except discord.HTTPException:
                pass

        identifier = f"announce:{guild.id}:{channel.id}:{int(time.time())}"
        scheduler.schedule(identifier, delay, send_later)
        await interaction.response.send_message(
            f"Announcement scheduled in {schedule_minutes} minutes.",
            ephemeral=True,
            view=ResponseView(),
        )

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
        await channel.send(embed=embed, view=ResponseView())
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
