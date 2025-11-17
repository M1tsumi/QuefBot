from typing import Optional

import json

import discord
from discord import app_commands
from discord.ext import commands

from core.bot import QuefBot
from core.views import ResponseView
from models.webhook_templates import TemplateStore
from services.permissions import is_staff


class Welcome(commands.Cog):
    def __init__(self, bot: QuefBot) -> None:
        self.bot = bot
        self.templates = TemplateStore()
        self.welcome_channel_id = bot.config.welcome_channel_id

    def resolve_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        if self.welcome_channel_id:
            channel = guild.get_channel(self.welcome_channel_id)
            if isinstance(channel, discord.TextChannel):
                return channel
        if guild.system_channel and isinstance(guild.system_channel, discord.TextChannel):
            return guild.system_channel
        return None

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        guild = member.guild
        channel = self.resolve_channel(guild)
        if channel is None:
            return
        manager = getattr(self.bot, "webhook_manager", None)
        template = self.templates.get_template("default")
        if manager is not None and template is not None:
            try:
                await manager.send_welcome(
                    channel,
                    member,
                    template.json_payload,
                    self.bot.config.welcome_webhook_url,
                )
            except Exception:
                embed = discord.Embed(
                    title="Welcome",
                    description=f"{member.mention}, welcome to {guild.name}.",
                    colour=discord.Colour.green(),
                )
                await channel.send(embed=embed, view=ResponseView())
        else:
            embed = discord.Embed(
                title="Welcome",
                description=f"{member.mention}, welcome to {guild.name}.",
                colour=discord.Colour.green(),
            )
            await channel.send(embed=embed, view=ResponseView())
        auto_roles = getattr(self.bot, "auto_roles", None)
        if auto_roles is not None:
            role_id = auto_roles.get_role(guild.id, "join")
            if role_id:
                role = guild.get_role(role_id)
                if role is not None:
                    try:
                        await member.add_roles(role, reason="Auto-role on join (trigger 'join')")
                    except discord.HTTPException:
                        pass

    group = app_commands.Group(name="welcome", description="Onboarding and welcome configuration")

    @group.command(name="set-channel", description="Set the channel used for welcome messages")
    @is_staff()
    @app_commands.describe(channel="Channel that will receive welcome messages")
    async def set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        guild = interaction.guild
        if guild is None or channel.guild.id != guild.id:
            await interaction.response.send_message("You must select a channel from this server.", ephemeral=True)
            return
        self.welcome_channel_id = channel.id
        await interaction.response.send_message(
            f"Welcome channel set to {channel.mention}.",
            ephemeral=True,
            view=ResponseView(),
        )

    @group.command(name="template", description="Store a JSON template for welcome payloads")
    @is_staff()
    @app_commands.describe(name="Template name", json_payload="JSON payload that defines the welcome message")
    async def template(self, interaction: discord.Interaction, name: str, json_payload: str) -> None:
        try:
            json.loads(json_payload)
        except json.JSONDecodeError:
            await interaction.response.send_message("The JSON payload is invalid.", ephemeral=True)
            return
        self.templates.set_template(name, json_payload)
        await interaction.response.send_message(
            f"Template '{name}' has been stored.",
            ephemeral=True,
            view=ResponseView(),
        )

    @group.command(name="preview", description="Preview the configured welcome message")
    @is_staff()
    @app_commands.describe(template="Optional template name", member="Member to preview the message for")
    async def preview(self, interaction: discord.Interaction, template: Optional[str] = None, member: Optional[discord.Member] = None) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("This command can only be used in a guild.", ephemeral=True)
            return
        if member is None:
            if isinstance(interaction.user, discord.Member):
                member = interaction.user
            else:
                await interaction.response.send_message("Select a member to preview.", ephemeral=True)
                return
        manager = getattr(self.bot, "webhook_manager", None)
        stored = None
        if template:
            stored = self.templates.get_template(template)
            if stored is None:
                await interaction.response.send_message("Template not found.", ephemeral=True)
                return
        else:
            stored = self.templates.get_template("default")
        if manager is not None and stored is not None:
            try:
                content, embeds = manager.build_message(stored.json_payload, member, guild)
                await interaction.response.send_message(
                    content=content or None,
                    embeds=embeds or None,
                    ephemeral=True,
                    view=ResponseView(),
                )
                return
            except Exception:
                pass
        description = f"{member.mention}, welcome to {guild.name}."
        embed = discord.Embed(
            title="Welcome Preview",
            description=description,
            colour=discord.Colour.green(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True, view=ResponseView())


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Welcome(bot))
