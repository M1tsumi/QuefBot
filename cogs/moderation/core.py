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


class LockControlView(discord.ui.View):
    def __init__(self, channel: discord.TextChannel, reason: Optional[str]) -> None:
        super().__init__(timeout=60)
        self.channel_id = channel.id
        self.guild_id = channel.guild.id
        self.reason = reason

    async def _apply_lock(self, interaction: discord.Interaction, duration_seconds: Optional[int]) -> None:
        guild = interaction.guild
        if guild is None or guild.id != self.guild_id:
            await interaction.response.edit_message(content="Could not resolve channel for lock.", view=None)
            return
        channel = guild.get_channel(self.channel_id)
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.edit_message(content="This command can only be used in text channels.", view=None)
            return
        overwrite = channel.overwrites_for(guild.default_role)
        overwrite.send_messages = False
        try:
            await channel.set_permissions(guild.default_role, overwrite=overwrite, reason=self.reason)
        except discord.HTTPException:
            await interaction.response.edit_message(content="Failed to update channel permissions.", view=None)
            return
        try:
            await channel.send("This channel has been locked by staff.")
        except discord.HTTPException:
            pass
        await log_moderation_action(interaction, "Lock", target=None, reason=self.reason)
        client = interaction.client
        if duration_seconds is not None and isinstance(client, QuefBot) and client.scheduler is not None:
            delay = max(1, duration_seconds)

            async def unlock_later() -> None:
                g = client.get_guild(self.guild_id)
                if g is None:
                    return
                c = g.get_channel(self.channel_id)
                if not isinstance(c, discord.TextChannel):
                    return
                overwrite2 = c.overwrites_for(g.default_role)
                overwrite2.send_messages = None
                try:
                    await c.set_permissions(g.default_role, overwrite=overwrite2, reason="Timed lock expired")
                except discord.HTTPException:
                    return

            client.scheduler.schedule(f"lock:{self.guild_id}:{self.channel_id}", delay, unlock_later)
        for item in self.children:
            item.disabled = True
        summary = f"{channel.mention} has been locked."
        if duration_seconds is not None:
            minutes = duration_seconds // 60
            summary = f"{channel.mention} has been locked for {minutes} minute(s)."
        await interaction.response.edit_message(content=summary, view=self)

    @discord.ui.button(label="Lock 5 minutes", style=discord.ButtonStyle.primary)
    async def lock_5_minutes(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        await self._apply_lock(interaction, 5 * 60)

    @discord.ui.button(label="Lock 1 hour", style=discord.ButtonStyle.primary)
    async def lock_1_hour(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        await self._apply_lock(interaction, 60 * 60)

    @discord.ui.button(label="Lock until unlocked", style=discord.ButtonStyle.secondary)
    async def lock_until_unlocked(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        await self._apply_lock(interaction, None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="Lock cancelled.", view=self)


class UnlockControlView(discord.ui.View):
    def __init__(self, channel: discord.TextChannel) -> None:
        super().__init__(timeout=60)
        self.channel_id = channel.id
        self.guild_id = channel.guild.id

    async def _apply_unlock(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None or guild.id != self.guild_id:
            await interaction.response.edit_message(content="Could not resolve channel for unlock.", view=None)
            return
        channel = guild.get_channel(self.channel_id)
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.edit_message(content="This command can only be used in text channels.", view=None)
            return
        overwrite = channel.overwrites_for(guild.default_role)
        overwrite.send_messages = None
        try:
            await channel.set_permissions(guild.default_role, overwrite=overwrite, reason="Channel unlocked")
        except discord.HTTPException:
            await interaction.response.edit_message(content="Failed to update channel permissions.", view=None)
            return
        try:
            await channel.send("This channel has been unlocked by staff.")
        except discord.HTTPException:
            pass
        await log_moderation_action(interaction, "Unlock", target=None, reason="Channel unlocked")
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content=f"{channel.mention} has been unlocked.", view=self)

    @discord.ui.button(label="Unlock now", style=discord.ButtonStyle.success)
    async def unlock_now(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        await self._apply_unlock(interaction)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="Unlock cancelled.", view=self)


class KickConfirmView(discord.ui.View):
    def __init__(self, cog: "Moderation", member: discord.Member, reason: Optional[str]) -> None:
        super().__init__(timeout=60)
        self.cog = cog
        self.member_id = member.id
        self.reason = reason

    @discord.ui.button(label="Confirm kick", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        guild = interaction.guild
        if guild is None:
            await interaction.response.edit_message(content="This command can only be used in a guild.", view=None)
            return
        member = guild.get_member(self.member_id)
        if member is None:
            await interaction.response.edit_message(content="Member is no longer in the guild.", view=None)
            return
        try:
            await guild.kick(user=member, reason=self.reason)
        except discord.HTTPException:
            await interaction.response.edit_message(content="Failed to kick member.", view=None)
            return
        self.cog._record_punishment(interaction, member, "Kick", reason=self.reason)
        await log_moderation_action(interaction, "Kick", target=member, reason=self.reason)
        await self.cog._send_meme_message(interaction, member, "Kick")
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content=f"{member} has been kicked.", view=self)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="Kick cancelled.", view=self)


class BanConfirmView(discord.ui.View):
    def __init__(self, cog: "Moderation", member: discord.Member, reason: Optional[str]) -> None:
        super().__init__(timeout=60)
        self.cog = cog
        self.member_id = member.id
        self.reason = reason

    @discord.ui.button(label="Confirm ban", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        guild = interaction.guild
        if guild is None:
            await interaction.response.edit_message(content="This command can only be used in a guild.", view=None)
            return
        member = guild.get_member(self.member_id)
        if member is None:
            await interaction.response.edit_message(content="Member is no longer in the guild.", view=None)
            return
        try:
            await guild.ban(user=member, reason=self.reason, delete_message_days=0)
        except discord.HTTPException:
            await interaction.response.edit_message(content="Failed to ban member.", view=None)
            return
        self.cog._record_punishment(interaction, member, "Ban", reason=self.reason)
        await log_moderation_action(interaction, "Ban", target=member, reason=self.reason)
        await self.cog._send_meme_message(interaction, member, "Ban")
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content=f"{member} has been banned.", view=self)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="Ban cancelled.", view=self)


class WarnControlView(discord.ui.View):
    def __init__(self, cog: "Moderation", member: discord.Member, base_reason: Optional[str]) -> None:
        super().__init__(timeout=60)
        self.cog = cog
        self.member_id = member.id
        self.base_reason = base_reason

    async def _apply_warn(self, interaction: discord.Interaction, severity: str) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.edit_message(content="This command can only be used in a guild.", view=None)
            return
        member = guild.get_member(self.member_id)
        if member is None:
            await interaction.response.edit_message(content="Member is no longer in the guild.", view=None)
            return
        parts = [f"[{severity}]"]
        if self.base_reason:
            parts.append(self.base_reason)
        reason = " ".join(parts).strip()
        self.cog._record_punishment(interaction, member, "Warn", reason=reason or None)
        await log_moderation_action(interaction, "Warn", target=member, reason=reason or None)
        try:
            dm_text = reason or "You have been warned by the staff."
            await member.send(f"You have been warned in {guild.name}: {dm_text}")
        except discord.HTTPException:
            pass
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"{member.mention} has been warned (severity: {severity}).",
            view=self,
        )

    @discord.ui.button(label="Info", style=discord.ButtonStyle.secondary)
    async def warn_info(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        await self._apply_warn(interaction, "Info")

    @discord.ui.button(label="Minor", style=discord.ButtonStyle.primary)
    async def warn_minor(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        await self._apply_warn(interaction, "Minor")

    @discord.ui.button(label="Major", style=discord.ButtonStyle.danger)
    async def warn_major(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        await self._apply_warn(interaction, "Major")


class TimeoutControlView(discord.ui.View):
    def __init__(self, cog: "Moderation", member: discord.Member, base_minutes: int, base_reason: Optional[str]) -> None:
        super().__init__(timeout=60)
        self.cog = cog
        self.member_id = member.id
        self.base_minutes = max(1, base_minutes)
        self.base_reason = base_reason

    async def _set_timeout(self, interaction: discord.Interaction, minutes: Optional[int]) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.edit_message(content="This command can only be used in a guild.", view=None)
            return
        member = guild.get_member(self.member_id)
        if member is None:
            await interaction.response.edit_message(content="Member is no longer in the guild.", view=None)
            return
        try:
            if minutes is None:
                await member.timeout(None, reason="Timeout cleared via control panel")
                message = f"Timeout cleared for {member.mention}."
            else:
                effective = max(1, minutes)
                delta = datetime.timedelta(minutes=effective)
                await member.timeout(delta, reason="Timeout adjusted via control panel")
                message = f"Timeout set to {effective} minute(s) for {member.mention}."
        except discord.HTTPException:
            await interaction.response.edit_message(content="Failed to update timeout.", view=None)
            return
        scheduler = self.cog.bot.scheduler
        if minutes is not None and scheduler is not None:
            delay = max(1, minutes * 60)

            async def clear_timeout() -> None:
                try:
                    await member.timeout(None, reason="Timeout expired (adjusted)")
                except discord.HTTPException:
                    pass

            scheduler.schedule(f"timeout:{member.id}", delay, clear_timeout)
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content=message, view=self)

    @discord.ui.button(label="Shorten", style=discord.ButtonStyle.secondary)
    async def shorten(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        new_minutes = max(1, self.base_minutes // 2)
        await self._set_timeout(interaction, new_minutes)

    @discord.ui.button(label="Extend +5m", style=discord.ButtonStyle.primary)
    async def extend(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        new_minutes = self.base_minutes + 5
        await self._set_timeout(interaction, new_minutes)

    @discord.ui.button(label="Clear now", style=discord.ButtonStyle.danger)
    async def clear(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        await self._set_timeout(interaction, None)


class MuteControlView(discord.ui.View):
    def __init__(
        self,
        cog: "Moderation",
        guild_id: int,
        member_id: int,
        mute_role_id: int,
        base_minutes: Optional[int],
        base_reason: Optional[str],
    ) -> None:
        super().__init__(timeout=60)
        self.cog = cog
        self.guild_id = guild_id
        self.member_id = member_id
        self.mute_role_id = mute_role_id
        self.base_minutes = base_minutes
        self.base_reason = base_reason

    async def _get_member_role(
        self,
        interaction: discord.Interaction,
    ) -> Optional[tuple[discord.Guild, discord.Member, Optional[discord.Role]]]:
        guild = interaction.guild
        if guild is None or guild.id != self.guild_id:
            await interaction.response.edit_message(content="This command can only be used in a guild.", view=None)
            return None
        member = guild.get_member(self.member_id)
        if member is None:
            await interaction.response.edit_message(content="Member is no longer in the guild.", view=None)
            return None
        role = guild.get_role(self.mute_role_id)
        return guild, member, role

    @discord.ui.button(label="Unmute now", style=discord.ButtonStyle.success)
    async def unmute_now(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        result = await self._get_member_role(interaction)
        if result is None:
            return
        guild, member, role = result
        if role is not None and role in member.roles:
            try:
                await member.remove_roles(role, reason="Mute cleared via control panel")
            except discord.HTTPException:
                await interaction.response.edit_message(content="Failed to remove mute role.", view=None)
                return
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content=f"Mute cleared for {member.mention}.", view=self)

    @discord.ui.button(label="Convert to 10m timeout", style=discord.ButtonStyle.danger)
    async def convert_to_timeout(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        result = await self._get_member_role(interaction)
        if result is None:
            return
        guild, member, role = result
        if role is not None and role in member.roles:
            try:
                await member.remove_roles(role, reason="Converted mute to timeout via control panel")
            except discord.HTTPException:
                await interaction.response.edit_message(content="Failed to remove mute role.", view=None)
                return
        try:
            delta = datetime.timedelta(minutes=10)
            await member.timeout(delta, reason="Converted mute to timeout via control panel")
        except discord.HTTPException:
            await interaction.response.edit_message(content="Failed to apply timeout.", view=None)
            return
        scheduler = self.cog.bot.scheduler
        if scheduler is not None:
            async def clear_timeout() -> None:
                try:
                    await member.timeout(None, reason="Timeout expired (from mute conversion)")
                except discord.HTTPException:
                    pass

            scheduler.schedule(f"timeout:{member.id}", 10 * 60, clear_timeout)
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"Converted mute to a 10 minute timeout for {member.mention}.",
            view=self,
        )


class JailControlView(discord.ui.View):
    def __init__(self, cog: "Moderation", guild_id: int, user_id: int, role_id: int) -> None:
        super().__init__(timeout=60)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
        self.role_id = role_id

    @discord.ui.button(label="Pardon now", style=discord.ButtonStyle.success)
    async def pardon_now(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        guild = interaction.guild
        if guild is None or guild.id != self.guild_id:
            await interaction.response.edit_message(content="This command can only be used in a guild.", view=None)
            return
        member = guild.get_member(self.user_id)
        role = guild.get_role(self.role_id)
        if member is not None and role is not None and role in member.roles:
            try:
                await member.remove_roles(role, reason="Pardon: clearing jail state via control panel")
            except discord.HTTPException:
                await interaction.response.edit_message(content="Failed to remove jail role.", view=None)
                return
        # Clear jail state in history if present
        self.cog.bot.history.clear_jail(guild.id, self.user_id)
        if member is not None:
            self.cog._record_punishment(
                interaction,
                member,
                "Pardon",
                reason="Cleared jail via control panel",
            )
        await log_moderation_action(
            interaction,
            "Pardon",
            target=member if member is not None else None,
            reason="Cleared jail via control panel",
        )
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content="Jail state cleared for the user.",
            view=self,
        )


class Moderation(commands.Cog, PermissionGuard):
    def __init__(self, bot: QuefBot) -> None:
        self.bot = bot

    async def _send_meme_message(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        action: str,
        duration_minutes: Optional[int] = None,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            return
        get_log_channel = getattr(self.bot, "get_log_channel", None)
        if get_log_channel is None:
            return
        channel = get_log_channel(guild)
        if channel is None:
            return
        if action == "Ban":
            text = f"Get pwned, {member.mention}!"
        elif action == "Mute":
            text = f"{member.mention} has been silenced. (Muted)"
        elif action == "Kick":
            text = f"{member.mention} just got kicked out of the server."
        elif action == "Timeout":
            if duration_minutes is not None and duration_minutes > 0:
                text = f"{member.mention} has been put in timeout for {duration_minutes} minute(s)."
            else:
                text = f"{member.mention} has been put in timeout."
        elif action == "Jail":
            text = f"{member.mention} has been thrown in jail."
        else:
            text = f"{member.mention} has received action: {action}."
        try:
            await channel.send(text)
        except discord.HTTPException:
            return

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
        message = f"Preparing to warn {member.mention}."
        if reason:
            message += f" Proposed reason: {reason}"
        message += " Choose a severity below to confirm."
        view = WarnControlView(self, member, reason)
        await interaction.response.send_message(message, ephemeral=True, view=view)

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
        view = TimeoutControlView(self, member, duration_minutes, reason)
        await interaction.response.send_message(
            f"{member.mention} has been timed out for {duration_minutes} minutes. Use the buttons below to adjust or clear the timeout.",
            ephemeral=True,
            view=view,
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
        await self._send_meme_message(interaction, member, "Timeout", duration_minutes=duration_minutes)
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
        view = MuteControlView(self, guild.id, member.id, mute_role_id, duration_minutes, reason)
        await interaction.response.send_message("".join(parts), ephemeral=True, view=view)
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
        await self._send_meme_message(interaction, member, "Mute", duration_minutes=duration_minutes)

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
        view = KickConfirmView(self, member, reason)
        text = f"Are you sure you want to kick {member.mention}?"
        if reason:
            text += f" Reason: {reason}"
        await interaction.response.send_message(text, ephemeral=True, view=view)

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
        view = BanConfirmView(self, member, reason)
        text = f"Are you sure you want to ban {member.mention}?"
        if reason:
            text += f" Reason: {reason}"
        await interaction.response.send_message(text, ephemeral=True, view=view)

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
        view = JailControlView(self, guild.id, member.id, jail_role.id)
        await interaction.response.send_message(
            f"{member.mention} has been jailed with role {jail_role.mention}. Use the button below to quickly pardon if needed.",
            ephemeral=True,
            view=view,
        )
        await log_moderation_action(interaction, "Jail", target=member, reason=reason)
        await self._send_meme_message(interaction, member, "Jail")

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
        view = LockControlView(channel, reason)
        await interaction.response.send_message(
            f"Configure lock duration for {channel.mention}.",
            ephemeral=True,
            view=view,
        )

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
        view = UnlockControlView(channel)
        await interaction.response.send_message(
            f"Confirm unlocking {channel.mention}.",
            ephemeral=True,
            view=view,
        )

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
