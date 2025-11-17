from typing import Any, Dict, List, Optional, Tuple

import json

import aiohttp
import discord


class WebhookManager:
    def __init__(self, bot: discord.Client) -> None:
        self.bot = bot

    def _token_values(self, member: discord.Member, guild: discord.Guild) -> Dict[str, str]:
        return {
            "member": str(member),
            "member_name": member.display_name,
            "member_mention": member.mention,
            "member_id": str(member.id),
            "guild_name": guild.name,
            "guild_id": str(guild.id),
        }

    def _apply_tokens(self, value: Any, member: discord.Member, guild: discord.Guild) -> Any:
        if not isinstance(value, str):
            return value
        mapping = self._token_values(member, guild)
        try:
            return value.format(**mapping)
        except KeyError:
            return value

    def build_message(
        self,
        template_payload: str,
        member: discord.Member,
        guild: discord.Guild,
    ) -> Tuple[Optional[str], List[discord.Embed]]:
        data = json.loads(template_payload)
        content_raw = data.get("content")
        content = None
        if isinstance(content_raw, str):
            content = self._apply_tokens(content_raw, member, guild)
        embeds: List[discord.Embed] = []
        embeds_data = data.get("embeds")
        if isinstance(embeds_data, list):
            for item in embeds_data:
                if not isinstance(item, dict):
                    continue
                embed = discord.Embed()
                title = item.get("title")
                description = item.get("description")
                color = item.get("color")
                if isinstance(title, str):
                    embed.title = self._apply_tokens(title, member, guild)
                if isinstance(description, str):
                    embed.description = self._apply_tokens(description, member, guild)
                if isinstance(color, int):
                    embed.colour = discord.Colour(color)
                fields = item.get("fields")
                if isinstance(fields, list):
                    for field in fields:
                        if not isinstance(field, dict):
                            continue
                        name = field.get("name")
                        value = field.get("value")
                        inline = field.get("inline", True)
                        if isinstance(name, str) and isinstance(value, str):
                            name_t = self._apply_tokens(name, member, guild)
                            value_t = self._apply_tokens(value, member, guild)
                            if not name_t:
                                name_t = "\u200b"
                            if not value_t:
                                value_t = "\u200b"
                            embed.add_field(name=name_t, value=value_t, inline=bool(inline))
                embeds.append(embed)
        return content, embeds

    async def send_welcome(
        self,
        channel: discord.TextChannel,
        member: discord.Member,
        template_payload: str,
        webhook_url: Optional[str],
    ) -> None:
        guild = channel.guild
        content, embeds = self.build_message(template_payload, member, guild)
        if webhook_url:
            async with aiohttp.ClientSession() as session:
                webhook = discord.Webhook.from_url(webhook_url, session=session)
                username = None
                avatar_url = None
                me = guild.me
                if me is not None:
                    username = me.display_name
                    try:
                        avatar_url = me.display_avatar.url
                    except AttributeError:
                        avatar_url = None
                await webhook.send(
                    content=content,
                    embeds=embeds or None,
                    username=username,
                    avatar_url=avatar_url,
                )
        else:
            await channel.send(content=content, embeds=embeds or None)
