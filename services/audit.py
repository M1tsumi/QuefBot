from dataclasses import dataclass
from typing import Optional

import datetime
import discord


@dataclass
class AuditEvent:
    action: str
    executor_id: int
    target_id: Optional[int]
    reason: Optional[str]
    duration: Optional[int]
    created_at: datetime.datetime


async def log_moderation_action(
    interaction: discord.Interaction,
    action: str,
    target: Optional[discord.abc.Snowflake] = None,
    reason: Optional[str] = None,
    duration_seconds: Optional[int] = None,
) -> None:
    executor_id = interaction.user.id if interaction.user else 0
    target_id = target.id if target is not None else None
    event = AuditEvent(
        action=action,
        executor_id=executor_id,
        target_id=target_id,
        reason=reason,
        duration=duration_seconds,
        created_at=datetime.datetime.utcnow(),
    )
    client = interaction.client
    guild = interaction.guild
    if guild is None:
        print(event)
        return
    config = getattr(client, "config", None)
    channel = None
    if config is not None and getattr(config, "log_channel_id", None):
        candidate = guild.get_channel(config.log_channel_id)
        if isinstance(candidate, discord.TextChannel):
            channel = candidate
    embed = discord.Embed(
        title=event.action,
        colour=discord.Colour.blurple(),
        timestamp=event.created_at,
    )
    embed.add_field(name="Executor", value=f"<@{event.executor_id}>", inline=True)
    if event.target_id is not None:
        embed.add_field(name="Target", value=f"<@{event.target_id}>", inline=True)
    if event.reason:
        embed.add_field(name="Reason", value=event.reason, inline=False)
    if event.duration is not None:
        embed.add_field(name="Duration (seconds)", value=str(event.duration), inline=True)
    if channel is not None:
        await channel.send(embed=embed)
    else:
        print(event)
