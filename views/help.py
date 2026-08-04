"""View trợ giúp tương tác (Select Menu theo danh mục lệnh)."""

from __future__ import annotations

import discord

# categories: {tên: (emoji, mô tả, [(lệnh, mô tả), ...])}
CategoryMap = dict[str, tuple[str, str, list[tuple[str, str]]]]


class HelpSelect(discord.ui.Select["HelpView"]):
    """Select Menu chọn danh mục lệnh để xem chi tiết."""

    def __init__(self, categories: CategoryMap) -> None:
        self.categories = categories
        options = [
            discord.SelectOption(label=name, description=summary, emoji=emoji)
            for name, (emoji, summary, _commands) in categories.items()
        ]
        super().__init__(
            placeholder="📚 Chọn danh mục...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"help_select:{id(self)}",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        name = self.values[0]
        _emoji, summary, commands = self.categories[name]
        embed = self.view.bot.embeds.base(title=f"📚 {name}", description=summary)
        for command, description in commands:
            embed.add_field(name=f"`{command}`", value=description, inline=False)
        await interaction.response.edit_message(embed=embed)


class HelpView(discord.ui.View):
    """View chứa Select Menu trợ giúp."""

    def __init__(self, bot, categories: CategoryMap) -> None:
        super().__init__(timeout=120)
        self.bot = bot
        self.add_item(HelpSelect(categories))
