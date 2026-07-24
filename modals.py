import discord
from config import EMBED_COLOR
from games import get_game, add_player, load_games, save_games


class JoinGameModal(discord.ui.Modal, title="Join Game"):
    display_name = discord.ui.TextInput(
        label="Display Name",
        placeholder="Your in-game name",
        max_length=32,
    )

    def __init__(self, game_id):
        super().__init__()
        self.game_id = game_id

    async def on_submit(self, interaction: discord.Interaction):
        game = get_game(self.game_id)

        if not game or game.get("finished"):
            await interaction.response.send_message(
                "This game is no longer available.", ephemeral=True
            )
            return

        if any(p.get("id") == interaction.user.id for p in game.get("players", [])):
            await interaction.response.send_message(
                "You've already joined this game.", ephemeral=True
            )
            return

        player = {"id": interaction.user.id, "display_name": self.display_name.value}
        add_player(self.game_id, player)
        game = get_game(self.game_id)

        thread = interaction.guild.get_thread(game["thread"])
        if thread is None:
            thread = await interaction.guild.fetch_channel(game["thread"])

        await thread.add_user(interaction.user)

        # Determine rank from tier roles
        from config import TIER_ROLES, SUPPORT_FOOTER
        member = interaction.guild.get_member(interaction.user.id)
        rank = "Unranked"
        if member:
            role_names = {r.name for r in member.roles}
            for tier in TIER_ROLES:
                if tier in role_names:
                    rank = tier
                    break

        joined_embed = discord.Embed(title="Player Joined", color=EMBED_COLOR)
        joined_embed.add_field(name="Display Name", value=player["display_name"], inline=False)
        joined_embed.add_field(name="Rank", value=rank, inline=False)
        joined_embed.set_footer(text=f"Game ID: {self.game_id} • {SUPPORT_FOOTER}")
        joined_embed.timestamp = discord.utils.utcnow()

        await thread.send(content=interaction.user.mention, embed=joined_embed)
        await interaction.response.send_message(
            "You've joined the game! Head to the thread.", ephemeral=True
        )

        remaining = game["players_needed"] - len(game["players"])
        if remaining <= 0:
            games = load_games()
            if self.game_id in games and not games[self.game_id].get("finished"):
                games[self.game_id]["finished"] = True
                games[self.game_id]["locked"] = True
                save_games(games)
                await thread.send(
                    embed=discord.Embed(
                        description="✅ This game is full. Use /endgame when the match is done.",
                        color=EMBED_COLOR,
                    )
                )
