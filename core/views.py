from typing import Optional

import discord


class _DismissButton(discord.ui.Button):
    def __init__(self, label: str) -> None:
        super().__init__(label=label, style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction) -> None:  # type: ignore[override]
        if self.view is not None:
            for item in self.view.children:
                item.disabled = True
            await interaction.response.edit_message(view=self.view)


class ResponseView(discord.ui.View):
    def __init__(self, *, label: str = "Dismiss", timeout: Optional[float] = 60.0) -> None:
        super().__init__(timeout=timeout)
        self.add_item(_DismissButton(label))
