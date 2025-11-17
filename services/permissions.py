from typing import Any, Dict

import discord
from discord import app_commands


DEV_ADMIN_IDS = {1051142172130422884}


def has_guild_permissions(**perms: bool):
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            raise app_commands.CheckFailure("Command can only be used in a guild")
        member = interaction.user
        if not isinstance(member, discord.Member):
            raise app_commands.CheckFailure("Invalid member")
        if member.guild_permissions.administrator or member.id in DEV_ADMIN_IDS:
            return True
        missing = []
        for name, value in perms.items():
            if getattr(member.guild_permissions, name, False) != value:
                missing.append(name)
        if missing:
            joined = ", ".join(missing)
            raise app_commands.CheckFailure(f"Missing required permissions: {joined}")
        return True

    return app_commands.check(predicate)


def bot_has_guild_permissions(**perms: bool):
    async def predicate(interaction: discord.Interaction) -> bool:
        guild = interaction.guild
        if guild is None:
            raise app_commands.CheckFailure("Command can only be used in a guild")
        me = guild.me
        if me is None:
            raise app_commands.CheckFailure("Bot member not found")
        if me.guild_permissions.administrator:
            return True
        missing = []
        for name, value in perms.items():
            if getattr(me.guild_permissions, name, False) != value:
                missing.append(name)
        if missing:
            joined = ", ".join(missing)
            raise app_commands.CheckFailure(f"Bot is missing required permissions: {joined}")
        return True

    return app_commands.check(predicate)


def is_staff():
    async def predicate(interaction: discord.Interaction) -> bool:
        guild = interaction.guild
        if guild is None:
            raise app_commands.CheckFailure("Command can only be used in a guild")
        member = interaction.user
        if not isinstance(member, discord.Member):
            raise app_commands.CheckFailure("Invalid member")
        if member.id in DEV_ADMIN_IDS:
            return True
        if guild.owner_id == member.id or member.guild_permissions.administrator:
            return True
        client = interaction.client
        config = getattr(client, "config", None)
        if config is not None:
            if config.owner_ids and member.id in config.owner_ids:
                return True
            if config.staff_role_ids:
                member_role_ids = {role.id for role in member.roles}
                for required_id in config.staff_role_ids:
                    if required_id in member_role_ids:
                        return True
        db = getattr(client, "db", None)
        if db is not None:
            try:
                row = db.query_one("SELECT level FROM staff_whitelist WHERE user_id = ?", (member.id,))
            except Exception:
                row = None
            if row is not None:
                return True
        raise app_commands.CheckFailure("You do not have permission to use this command")

    return app_commands.check(predicate)


class PermissionGuard:
    async def ensure_target_hierarchy(self, interaction: discord.Interaction, target: discord.Member) -> None:
        guild = interaction.guild
        if guild is None:
            raise app_commands.CheckFailure("Command can only be used in a guild")
        actor = interaction.user
        if not isinstance(actor, discord.Member):
            raise app_commands.CheckFailure("Invalid member")
        if actor.id == target.id:
            raise app_commands.CheckFailure("You cannot target yourself")
        if guild.owner_id != actor.id and target.top_role >= actor.top_role:
            raise app_commands.CheckFailure("The target member has a higher or equal role")
        me = guild.me
        if me is not None and target.top_role >= me.top_role:
            raise app_commands.CheckFailure("The target member has a higher or equal role to the bot")
