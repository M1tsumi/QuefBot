import csv
import io
import time
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from core.bot import QuefBot
from core.views import ResponseView
from services.permissions import is_staff


class Diagnostics(commands.Cog):
    def __init__(self, bot: QuefBot) -> None:
        self.bot = bot
        self.process_start = time.time()

    @app_commands.command(name="config-check", description="Show resolved configuration with secrets redacted")
    @is_staff()
    async def config_check(self, interaction: discord.Interaction) -> None:
        config = self.bot.config
        data = config.sanitize()
        lines = []
        for key, value in data.items():
            lines.append(f"{key}: {value}")
        description = "```ini\n" + "\n".join(lines) + "\n```"
        embed = discord.Embed(
            title="Resolved configuration",
            description=description,
            colour=discord.Colour.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True, view=ResponseView())

    @app_commands.command(name="health", description="Show basic bot health information")
    @is_staff()
    async def health(self, interaction: discord.Interaction) -> None:
        latency_ms = round(self.bot.latency * 1000)
        guild_count = len(self.bot.guilds)
        uptime_seconds = int(time.time() - self.process_start)
        embed = discord.Embed(
            title="Bot health",
            colour=discord.Colour.green(),
        )
        embed.add_field(name="Latency", value=f"{latency_ms} ms", inline=True)
        embed.add_field(name="Guilds", value=str(guild_count), inline=True)
        embed.add_field(name="Uptime", value=f"{uptime_seconds} seconds", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True, view=ResponseView())

    @app_commands.command(name="bot-stats", description="Show runtime statistics for the bot")
    @is_staff()
    async def runtime_stats(self, interaction: discord.Interaction) -> None:
        uptime_seconds = int(time.time() - self.process_start)
        shard_count = self.bot.shard_count or 1
        guild_count = len(self.bot.guilds)
        latency_ms = round(self.bot.latency * 1000)
        embed = discord.Embed(
            title="Bot statistics",
            colour=discord.Colour.blurple(),
        )
        embed.add_field(name="Uptime", value=f"{uptime_seconds} seconds", inline=True)
        embed.add_field(name="Shards", value=str(shard_count), inline=True)
        embed.add_field(name="Guilds", value=str(guild_count), inline=True)
        embed.add_field(name="Latency", value=f"{latency_ms} ms", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True, view=ResponseView())

    @app_commands.command(name="audit-history", description="Show punishment history for a user")
    @is_staff()
    @app_commands.describe(user="User to show history for", limit="Maximum number of entries to show")
    async def audit_history(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.User] = None,
        limit: int = 10,
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("This command can only be used in a guild.", ephemeral=True)
            return
        if limit < 1:
            limit = 1
        if limit > 50:
            limit = 50
        records = self.bot.history.get_punishments(guild.id)
        if user is not None:
            records = [record for record in records if record.user_id == user.id]
        records = sorted(records, key=lambda r: r.created_at, reverse=True)[:limit]
        if not records:
            await interaction.response.send_message("No history found.", ephemeral=True, view=ResponseView())
            return
        embed = discord.Embed(
            title="Audit history",
            colour=discord.Colour.blurple(),
        )
        if user is None:
            target_label = "All users"
        else:
            target_label = f"User: {user} ({user.id})"
        lines = []
        for record in records:
            reason = record.reason or "None"
            lines.append(
                f"{record.created_at:%Y-%m-%d %H:%M} - {record.action} | user={record.user_id} | "
                f"moderator={record.moderator_id} | reason={reason}"
            )
        embed.description = "\n".join(lines)
        count = len(records)
        plural = "entry" if count == 1 else "entries"
        embed.set_footer(text=f"{target_label} | Showing {count} {plural}")
        await interaction.response.send_message(embed=embed, ephemeral=True, view=ResponseView())

    @app_commands.command(name="member-info", description="Show moderation summary for a member")
    @is_staff()
    @app_commands.describe(member="Member to inspect")
    async def member_info(self, interaction: discord.Interaction, member: discord.Member) -> None:
        guild = interaction.guild
        if guild is None or member.guild.id != guild.id:
            await interaction.response.send_message("Select a member from this server.", ephemeral=True)
            return
        punishments = self.bot.history.get_punishments_for_user(guild.id, member.id)
        notes = self.bot.history.get_notes_for_user(guild.id, member.id)
        embed = discord.Embed(
            title=f"Member info: {member}",
            colour=discord.Colour.blurple(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="User ID", value=str(member.id), inline=True)
        embed.add_field(name="Infractions", value=str(len(punishments)), inline=True)
        embed.add_field(name="Notes", value=str(len(notes)), inline=True)
        created_at = getattr(member, "created_at", None)
        joined_at = getattr(member, "joined_at", None)
        if created_at is not None:
            embed.add_field(name="Account created", value=created_at.strftime("%Y-%m-%d"), inline=True)
        if joined_at is not None:
            embed.add_field(name="Joined server", value=joined_at.strftime("%Y-%m-%d"), inline=True)
        roles = [role.mention for role in member.roles if role.name != "@everyone"]
        embed.add_field(name="Roles", value=" ".join(roles) or "None", inline=False)
        punishments_preview = punishments[-3:]
        if punishments_preview:
            lines = []
            for record in punishments_preview:
                lines.append(f"{record.created_at.date()} – {record.action} ({record.reason or 'No reason'})")
            embed.add_field(name="Recent actions", value="\n".join(lines), inline=False)
        notes_preview = notes[-3:]
        if notes_preview:
            lines = []
            for note in notes_preview:
                lines.append(f"{note.created_at.date()} – {note.text}")
            embed.add_field(name="Recent notes", value="\n".join(lines), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True, view=ResponseView())

    @app_commands.command(name="logs-export", description="Export moderation logs as a CSV file")
    @is_staff()
    @app_commands.describe(limit="Maximum number of records to export")
    async def logs_export(self, interaction: discord.Interaction, limit: int = 100) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("This command can only be used in a guild.", ephemeral=True)
            return
        if limit < 1:
            limit = 1
        if limit > 500:
            limit = 500
        punishments = sorted(
            self.bot.history.get_punishments(guild.id),
            key=lambda r: r.created_at,
            reverse=True,
        )[:limit]
        notes = sorted(
            self.bot.history.get_notes(guild.id),
            key=lambda r: r.created_at,
            reverse=True,
        )[:limit]
        if not punishments and not notes:
            await interaction.response.send_message("No logs available to export.", ephemeral=True, view=ResponseView())
            return
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["type", "user_id", "moderator_id", "action_or_text", "created_at", "expires_at"])
        for record in punishments:
            writer.writerow([
                "punishment",
                record.user_id,
                record.moderator_id,
                f"{record.action}: {record.reason or ''}",
                record.created_at.isoformat(),
                record.expires_at.isoformat() if record.expires_at else "",
            ])
        for note in notes:
            writer.writerow([
                "note",
                note.user_id,
                note.moderator_id,
                note.text,
                note.created_at.isoformat(),
                "",
            ])
        buffer.seek(0)
        file = discord.File(fp=io.BytesIO(buffer.getvalue().encode("utf-8")), filename="moderation_logs.csv")
        punishments_count = len(punishments)
        notes_count = len(notes)
        embed = discord.Embed(
            title="Moderation logs export",
            description=(
                f"Exported {punishments_count} punishment record(s) "
                f"and {notes_count} note(s) to CSV."
            ),
            colour=discord.Colour.blurple(),
        )
        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
            file=file,
            view=ResponseView(),
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Diagnostics(bot))
