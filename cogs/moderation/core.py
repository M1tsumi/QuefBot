from typing import Optional

import datetime

import discord
from discord import app_commands
from discord.ext import commands

from core.bot import QuefBot
from core.views import ResponseView
from models.punishments import JailState, NoteRecord, PunishmentRecord
from services.permissions import PermissionGuard, has_guild_permissions, bot_has_guild_permissions, is_staff
from services.audit import log_moderation_action


class Moderation(commands.Cog, PermissionGuard):
    def __init__(self, bot: QuefBot) -> None:
        self.bot = bot

    def _record_punishment(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        action: str,
        reason: Optional[str] = None,
        duration_seconds: Optional[int] = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            return
        now = datetime.datetime.utcnow()
        expires_at = None
        if duration_seconds is not None:
            expires_at = now + datetime.timedelta(seconds=duration_seconds)
        record = PunishmentRecord(
            user_id=member.id,
            moderator_id=interaction.user.id if interaction.user else 0,
            action=action,
            reason=reason,
            created_at=now,
            expires_at=expires_at,
        )
        self.bot.history.add_punishment(guild.id, record)

    def _record_note(self, interaction: discord.Interaction, member: discord.Member, text: str) -> None:
        guild = interaction.guild
        if guild is None:
            return
        now = datetime.datetime.utcnow()
        record = NoteRecord(
            user_id=member.id,
            moderator_id=interaction.user.id if interaction.user else 0,
            text=text,
            created_at=now,
        )
        self.bot.history.add_note(guild.id, record)

    @app_commands.command(name="warn", description="Warn a member and log the infraction")
    @is_staff()
    @has_guild_permissions(manage_messages=True)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None) -> None:
        await self.ensure_target_hierarchy(interaction, member)
        message = f"{member.mention} has been warned."
        if reason:
            message += f" Reason: {reason}"
        await interaction.response.send_message(message, ephemeral=True, view=ResponseView())
        self._record_punishment(interaction, member, "Warn", reason=reason)
        await log_moderation_action(interaction, "Warn", target=member, reason=reason)

    @app_commands.command(name="note", description="Attach a private moderator note to a member")
    @is_staff()
    @has_guild_permissions(manage_messages=True)
    @app_commands.describe(member="Member to attach the note to", text="The note text")
    async def note(self, interaction: discord.Interaction, member: discord.Member, text: str) -> None:
        await self.ensure_target_hierarchy(interaction, member)
        self._record_note(interaction, member, text)
        await interaction.response.send_message(
            f"Note added for {member}.",
            ephemeral=True,
            view=ResponseView(),
        )
        await log_moderation_action(interaction, "Note", target=member, reason=text)

    @app_commands.command(name="timeout", description="Apply a timeout to a member")
    @is_staff()
    @has_guild_permissions(moderate_members=True)
    @bot_has_guild_permissions(moderate_members=True)
    @app_commands.describe(duration_minutes="Duration of the timeout in minutes", reason="Reason for the timeout")
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, duration_minutes: int, reason: Optional[str] = None) -> None:
        await self.ensure_target_hierarchy(interaction, member)
        if duration_minutes < 1:
            duration_minutes = 1
        delta = datetime.timedelta(minutes=duration_minutes)
        await member.timeout(delta, reason=reason)
        await interaction.response.send_message(
            f"{member.mention} has been timed out for {duration_minutes} minutes.",
            ephemeral=True,
            view=ResponseView(),
        )
        await log_moderation_action(
            interaction,
            "Timeout",
            target=member,
            reason=reason,
            duration_seconds=int(delta.total_seconds()),
        )
        self._record_punishment(
            interaction,
            member,
            "Timeout",
            reason=reason,
            duration_seconds=int(delta.total_seconds()),
        )
        scheduler = self.bot.scheduler
        if scheduler is not None:
            async def clear_timeout() -> None:
                try:
                    await member.timeout(None, reason="Timeout expired")
                except discord.HTTPException:
                    pass
            scheduler.schedule(f"timeout:{member.id}", delta.total_seconds(), clear_timeout)

    @app_commands.command(name="mute", description="Apply the configured mute role to a member")
    @is_staff()
    @has_guild_permissions(manage_roles=True)
    @bot_has_guild_permissions(manage_roles=True)
    @app_commands.describe(
        duration_minutes="Optional duration of the mute in minutes; omit for indefinite",
        reason="Reason for the mute",
    )
    async def mute(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        duration_minutes: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> None:
        await self.ensure_target_hierarchy(interaction, member)
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("This command can only be used in a guild.", ephemeral=True)
            return
        mute_role_id = self.bot.config.default_mute_role_id
        if not mute_role_id:
            await interaction.response.send_message(
                "No mute role is configured. Set `default_mute_role_id` in the config.",
                ephemeral=True,
            )
            return
        mute_role = guild.get_role(mute_role_id)
        if mute_role is None:
            await interaction.response.send_message("The configured mute role does not exist.", ephemeral=True)
            return
        await member.add_roles(mute_role, reason=reason)
        parts = [f"{member.mention} has been muted."]
        duration_seconds: Optional[int] = None
        if duration_minutes is not None and duration_minutes > 0:
            delta = datetime.timedelta(minutes=duration_minutes)
            duration_seconds = int(delta.total_seconds())
            parts.append(f" Duration: {duration_minutes} minutes.")
            scheduler = self.bot.scheduler
            if scheduler is not None:
                async def remove_mute() -> None:
                    refreshed = guild.get_member(member.id)
                    if refreshed is None:
                        return
                    role = guild.get_role(mute_role_id)
                    if role is not None and role in refreshed.roles:
                        try:
                            await refreshed.remove_roles(role, reason="Mute expired")
                        except discord.HTTPException:
                            pass
                scheduler.schedule(f"mute:{guild.id}:{member.id}", duration_seconds, remove_mute)
        await interaction.response.send_message("".join(parts), ephemeral=True, view=ResponseView())
        self._record_punishment(
            interaction,
            member,
            "Mute",
            reason=reason,
            duration_seconds=duration_seconds,
        )
        await log_moderation_action(
            interaction,
            "Mute",
            target=member,
            reason=reason,
            duration_seconds=duration_seconds if duration_seconds is not None else None,
        )

    @app_commands.command(name="kick", description="Kick a member from the server")
    @is_staff()
    @has_guild_permissions(kick_members=True)
    @bot_has_guild_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None) -> None:
        await self.ensure_target_hierarchy(interaction, member)
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("This command can only be used in a guild.", ephemeral=True)
            return
        await guild.kick(user=member, reason=reason)
        await interaction.response.send_message(
            f"{member} has been kicked.",
            ephemeral=True,
            view=ResponseView(),
        )
        self._record_punishment(interaction, member, "Kick", reason=reason)
        await log_moderation_action(interaction, "Kick", target=member, reason=reason)

    @app_commands.command(name="ban", description="Ban a member from the server")
    @is_staff()
    @has_guild_permissions(ban_members=True)
    @bot_has_guild_permissions(ban_members=True)
    @app_commands.describe(reason="Reason for the ban")
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None) -> None:
        await self.ensure_target_hierarchy(interaction, member)
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("This command can only be used in a guild.", ephemeral=True)
            return
        await guild.ban(user=member, reason=reason, delete_message_days=0)
        await interaction.response.send_message(
            f"{member} has been banned.",
            ephemeral=True,
            view=ResponseView(),
        )
        self._record_punishment(interaction, member, "Ban", reason=reason)
        await log_moderation_action(interaction, "Ban", target=member, reason=reason)

    @app_commands.command(name="softban", description="Ban and immediately unban a member to remove messages")
    @is_staff()
    @has_guild_permissions(ban_members=True)
    @bot_has_guild_permissions(ban_members=True)
    @app_commands.describe(reason="Reason for the softban")
    async def softban(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None) -> None:
        await self.ensure_target_hierarchy(interaction, member)
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("This command can only be used in a guild.", ephemeral=True)
            return
        await guild.ban(user=member, reason=reason, delete_message_days=1)
        await guild.unban(user=member, reason="Softban unban")
        await interaction.response.send_message(
            f"{member} has been softbanned.",
            ephemeral=True,
            view=ResponseView(),
        )
        self._record_punishment(interaction, member, "Softban", reason=reason)
        await log_moderation_action(interaction, "Softban", target=member, reason=reason)

    @app_commands.command(name="jail", description="Apply a jail role to a member")
    @is_staff()
    @has_guild_permissions(manage_roles=True)
    @bot_has_guild_permissions(manage_roles=True)
    @app_commands.describe(
        member="Member to jail",
        role="Optional role to apply as the jail role",
        reason="Reason for the jail",
    )
    async def jail(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        role: Optional[discord.Role] = None,
        reason: Optional[str] = None,
    ) -> None:
        await self.ensure_target_hierarchy(interaction, member)
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("This command can only be used in a guild.", ephemeral=True)
            return
        existing = self.bot.history.get_jail(guild.id, member.id)
        if existing is not None:
            await interaction.response.send_message(
                f"{member} is already jailed.",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        jail_role = role
        if jail_role is None:
            mute_role_id = self.bot.config.default_mute_role_id
            if mute_role_id:
                jail_role = guild.get_role(mute_role_id)
        if jail_role is None:
            await interaction.response.send_message(
                "You must provide a jail role or configure `default_mute_role_id`.",
                ephemeral=True,
            )
            return
        await member.add_roles(jail_role, reason=reason)
        now = datetime.datetime.utcnow()
        state = JailState(
            guild_id=guild.id,
            user_id=member.id,
            role_id=jail_role.id,
            reason=reason,
            created_at=now,
            expires_at=None,
        )
        self.bot.history.set_jail(state)
        self._record_punishment(interaction, member, "Jail", reason=reason)
        await interaction.response.send_message(
            f"{member.mention} has been jailed with role {jail_role.mention}.",
            ephemeral=True,
            view=ResponseView(),
        )
        await log_moderation_action(interaction, "Jail", target=member, reason=reason)

    @app_commands.command(name="purge", description="Bulk delete messages in the current channel")
    @is_staff()
    @has_guild_permissions(manage_messages=True)
    @bot_has_guild_permissions(manage_messages=True)
    @app_commands.describe(count="Number of messages to delete, up to 100")
    async def purge(self, interaction: discord.Interaction, count: int) -> None:
        channel = interaction.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message("This command can only be used in text channels.", ephemeral=True)
            return
        if count < 1:
            await interaction.response.send_message("Count must be at least 1.", ephemeral=True)
            return
        if count > 100:
            count = 100
        await interaction.response.defer(ephemeral=True)
        deleted = await channel.purge(limit=count + 1)
        deleted_count = max(len(deleted) - 1, 0)
        await interaction.followup.send(f"Deleted {deleted_count} messages.", ephemeral=True, view=ResponseView())
        await log_moderation_action(interaction, "Purge", target=None, reason=f"Deleted {deleted_count} messages")

    @app_commands.command(name="slowmode", description="Set slowmode for the current channel")
    @is_staff()
    @has_guild_permissions(manage_channels=True)
    @bot_has_guild_permissions(manage_channels=True)
    @app_commands.describe(seconds="Slowmode delay in seconds, 0 to disable")
    async def slowmode(self, interaction: discord.Interaction, seconds: int) -> None:
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("This command can only be used in text channels.", ephemeral=True)
            return
        if seconds < 0:
            seconds = 0
        await channel.edit(slowmode_delay=seconds)
        await interaction.response.send_message(
            f"Slowmode set to {seconds} seconds in {channel.mention}.",
            ephemeral=True,
            view=ResponseView(),
        )
        await log_moderation_action(interaction, "Slowmode", target=None, reason=f"Slowmode set to {seconds} seconds")

    @app_commands.command(name="lock", description="Lock the current channel for @everyone")
    @is_staff()
    @has_guild_permissions(manage_channels=True)
    @bot_has_guild_permissions(manage_channels=True)
    @app_commands.describe(reason="Reason for locking the channel")
    async def lock(self, interaction: discord.Interaction, reason: Optional[str] = None) -> None:
        guild = interaction.guild
        channel = interaction.channel
        if guild is None or not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("This command can only be used in text channels.", ephemeral=True)
            return
        overwrite = channel.overwrites_for(guild.default_role)
        overwrite.send_messages = False
        await channel.set_permissions(guild.default_role, overwrite=overwrite, reason=reason)
        await interaction.response.send_message(
            f"{channel.mention} has been locked.",
            ephemeral=True,
            view=ResponseView(),
        )
        await log_moderation_action(interaction, "Lock", target=None, reason=reason)

    @app_commands.command(name="unlock", description="Unlock the current channel for @everyone")
    @is_staff()
    @has_guild_permissions(manage_channels=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def unlock(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        channel = interaction.channel
        if guild is None or not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("This command can only be used in text channels.", ephemeral=True)
            return
        overwrite = channel.overwrites_for(guild.default_role)
        overwrite.send_messages = None
        await channel.set_permissions(guild.default_role, overwrite=overwrite, reason="Channel unlocked")
        await interaction.response.send_message(
            f"{channel.mention} has been unlocked.",
            ephemeral=True,
            view=ResponseView(),
        )
        await log_moderation_action(interaction, "Unlock", target=None, reason="Channel unlocked")

    @app_commands.command(name="pardon", description="Clear active mute/jail/ban state for a user")
    @is_staff()
    @has_guild_permissions(ban_members=True, manage_roles=True)
    @bot_has_guild_permissions(ban_members=True, manage_roles=True)
    @app_commands.describe(user="User to pardon", reason="Reason for the pardon")
    async def pardon(self, interaction: discord.Interaction, user: discord.User, reason: Optional[str] = None) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("This command can only be used in a guild.", ephemeral=True)
            return
        member = guild.get_member(user.id)
        actions = []
        if member is not None:
            jail_state = self.bot.history.clear_jail(guild.id, member.id)
            if jail_state is not None:
                role = guild.get_role(jail_state.role_id)
                if role is not None and role in member.roles:
                    try:
                        await member.remove_roles(role, reason=reason or "Pardon: clearing jail state")
                    except discord.HTTPException:
                        pass
                actions.append("jail")
            mute_role_id = self.bot.config.default_mute_role_id
            if mute_role_id:
                mute_role = guild.get_role(mute_role_id)
                if mute_role is not None and mute_role in member.roles:
                    try:
                        await member.remove_roles(mute_role, reason=reason or "Pardon: clearing mute")
                    except discord.HTTPException:
                        pass
                    actions.append("mute")
            timed_out = False
            if hasattr(member, "communication_disabled_until"):
                timed_out = getattr(member, "communication_disabled_until") is not None
            if getattr(member, "timed_out", False):
                timed_out = True
            if timed_out:
                try:
                    await member.timeout(None, reason=reason or "Pardon: clearing timeout")
                    actions.append("timeout")
                except discord.HTTPException:
                    pass
        banned_cleared = False
        try:
            await guild.fetch_ban(user)
        except discord.NotFound:
            banned_cleared = False
        else:
            try:
                await guild.unban(user, reason=reason or "Pardon")
                banned_cleared = True
            except discord.HTTPException:
                banned_cleared = False
        if banned_cleared:
            actions.append("ban")
        if not actions:
            await interaction.response.send_message(
                f"No active mute/jail/ban/timeout found for {user}.",
                ephemeral=True,
                view=ResponseView(),
            )
            return
        if member is not None:
            self._record_punishment(
                interaction,
                member,
                "Pardon",
                reason=reason or f"Cleared: {', '.join(actions)}",
            )
        await interaction.response.send_message(
            f"Cleared: {', '.join(actions)} for {user}.",
            ephemeral=True,
            view=ResponseView(),
        )
        await log_moderation_action(
            interaction,
            "Pardon",
            target=user,
            reason=reason or f"Cleared: {', '.join(actions)}",
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
