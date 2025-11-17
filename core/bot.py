from typing import Optional

from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from core.config import BotConfig
from services.auto_roles import AutoRoleStore
from services.database import Database
from services.history import HistoryStore
from services.incidents import IncidentStore
from services.reaction_roles import ReactionRoleStore
from services.scheduler import Scheduler
from services.tickets import TicketService
from services.webhook_manager import WebhookManager


COG_EXTENSIONS = [
    "cogs.moderation.core",
    "cogs.welcome.core",
    "cogs.community.core",
    "cogs.ops.core",
    "cogs.diagnostics.core",
]


class QuefBot(commands.Bot):
    def __init__(self, config: BotConfig) -> None:
        intents = discord.Intents.default()
        intents.members = True
        intents.guilds = True
        intents.message_content = True
        super().__init__(
            command_prefix=commands.when_mentioned_or("!"),
            intents=intents,
        )
        self.config = config
        base_dir = Path(__file__).resolve().parents[1]
        self.db = Database(base_dir / "bot.db")
        self.scheduler: Optional[Scheduler] = Scheduler(self)
        self.auto_roles = AutoRoleStore(self.db)
        self.history = HistoryStore(self.db)
        self.incidents = IncidentStore(self.db)
        self.reaction_roles = ReactionRoleStore(self.db)
        self.tickets = TicketService(self.db)
        self.webhook_manager = WebhookManager(self)

    async def setup_hook(self) -> None:
        for ext in COG_EXTENSIONS:
            await self.load_extension(ext)
        await self.tree.sync()

    async def on_ready(self) -> None:
        if self.user is None:
            return
        print(f"Logged in as {self.user} ({self.user.id})")

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if interaction.response.is_done():
            sender = interaction.followup
        else:
            sender = interaction.response
        if isinstance(error, app_commands.CheckFailure):
            message = str(error) or "You do not have permission to use this command."
            try:
                await sender.send(message, ephemeral=True)
            except discord.HTTPException:
                pass
        else:
            print(f"Unhandled app command error: {error}")
            try:
                await sender.send("An error occurred while executing this command.", ephemeral=True)
            except discord.HTTPException:
                pass

    def get_log_channel(self, guild: Optional[discord.Guild]) -> Optional[discord.TextChannel]:
        if guild is None:
            return None
        if not self.config.log_channel_id:
            return None
        channel = guild.get_channel(self.config.log_channel_id)
        if isinstance(channel, discord.TextChannel):
            return channel
        return None
