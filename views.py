import discord
from modals import JoinGameModal
from games import get_game


class JoinButton(discord.ui.View):
    def __init__(self, game_id):
        super().__init__(timeout=None)
        self.game_id = game_id

    @discord.ui.button(
        label="Join Game",
        emoji="🎮",
        style=discord.ButtonStyle.primary,
        custom_id="join_game",
    )
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = get_game(self.game_id)

        allowed_roles = {"LXY", "LXY+"}

        if not any(role.name in allowed_roles for role in interaction.user.roles):
            await interaction.response.send_message(
                "❌ You must have the **LXY** or **LXY+** role to join League games.",
                ephemeral=True,
            )
            return

        if not game:
            await interaction.response.send_message("This game has ended.", ephemeral=True)
            return

        if game.get("finished"):
            await interaction.response.send_message("This game has ended.", ephemeral=True)
            return

        if any(p["id"] == interaction.user.id for p in game["players"]):
            await interaction.response.send_message("You've already joined this game.", ephemeral=True)
            return

        if len(game["players"]) >= game["players_needed"]:
            await interaction.response.send_message("This game is full!", ephemeral=True)
            return

        await interaction.response.send_modal(JoinGameModal(self.game_id))
