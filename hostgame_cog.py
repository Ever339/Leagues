import discord
from discord.ext import commands
from discord import app_commands
import random
import string

from config import (
    GAME_TYPES, MATCH_TYPES, REGIONS, THREAD_NAME, EMBED_COLOR,
    PING_ROLE_NAME, SUPPORT_FOOTER, TIER_ROLES, STRIKE_ROLE_NAME,
)
from game_storage import (
    create_game, delete_game, get_game, add_player, remove_player,
    get_game_by_thread, load_games, save_games,
)
from views import JoinButton


def generate_game_id(length=6):
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def is_host_or_staff(interaction: discord.Interaction, game: dict) -> bool:
    if interaction.user.id == game.get("host_id"):
        return True
    member = interaction.user
    if isinstance(member, discord.Member):
        perms = interaction.channel.permissions_for(member)
        if perms.manage_threads or perms.administrator:
            return True
    return False


def get_player_tier(guild: discord.Guild, user_id: int) -> str | None:
    member = guild.get_member(user_id)
    if not member:
        return None
    role_names = [r.name for r in member.roles]
    for tier in TIER_ROLES:
        if any(tier in name for name in role_names):
            return tier
    return None


def resolve_game(interaction: discord.Interaction):
    channel = interaction.channel
    if not isinstance(channel, discord.Thread):
        return None, None
    game_id, game = get_game_by_thread(channel.id)
    return game_id, game


async def get_thread(interaction: discord.Interaction, game: dict) -> discord.Thread:
    thread = interaction.guild.get_thread(game["thread"])
    if thread is None:
        thread = await interaction.guild.fetch_channel(game["thread"])
    return thread


class HostGameCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ─── /hostgame ────────────────────────────────────────────────────────────

    @app_commands.command(name="hostgame", description="Host a game.")
    @app_commands.describe(
        gametype="Game Type", matchtype="Match Type",
        region="Region", vipserver="VIP Server Link",
    )
    @app_commands.choices(
        gametype=[app_commands.Choice(name=g, value=g) for g in GAME_TYPES],
        matchtype=[app_commands.Choice(name=m, value=m) for m in MATCH_TYPES],
        region=[app_commands.Choice(name=r, value=r) for r in REGIONS],
    )
    async def hostgame(self, interaction: discord.Interaction,
                       gametype: app_commands.Choice[str],
                       matchtype: app_commands.Choice[str],
                       region: app_commands.Choice[str],
                       vipserver: str):
        # Block users with the strike ban role
        strike_role = discord.utils.find(
            lambda r: r.name.lower() == STRIKE_ROLE_NAME.lower(),
            interaction.guild.roles,
        )
        if strike_role and strike_role in interaction.user.roles:
            await interaction.response.send_message(
                f"🚫 You have the **{STRIKE_ROLE_NAME}** role and cannot host leagues.",
                ephemeral=True,
            )
            return

        game_id = generate_game_id()

        players_map = {"1s": 1, "2s": 3, "3s": 5, "4s": 7}
        players_needed = players_map.get(gametype.value, 1)

        ping_role = discord.utils.find(
            lambda r: PING_ROLE_NAME in r.name, interaction.guild.roles
        )
        ping_mention = ping_role.mention if ping_role else f"@{PING_ROLE_NAME}"

        embed = discord.Embed(
            title=f"Hosting a {matchtype.value} Match ({region.value})",
            description=(
                f"Hosting a **{gametype.value}** game! Need **{players_needed}** more players to join.\n"
                f"Hosted by: `{interaction.user.display_name}`"
            ),
            color=EMBED_COLOR,
        )
        embed.set_footer(text=f"{SUPPORT_FOOTER}")
        embed.timestamp = discord.utils.utcnow()

        view = JoinButton(game_id)

        # Temporarily make role mentionable so the ping notifies members
        try:
            if ping_role and not ping_role.mentionable:
                await ping_role.edit(mentionable=True)
                print("[DEBUG] Made role mentionable")
            await interaction.response.send_message(
                content=ping_mention,
                embed=embed,
                view=view,
                allowed_mentions=discord.AllowedMentions(roles=True),
            )
            if ping_role and not ping_role.mentionable:
                await ping_role.edit(mentionable=False)
        except Exception as e:
            print(f"[DEBUG] Error during ping: {e}")
            await interaction.response.send_message(
                content=ping_mention,
                embed=embed,
                view=view,
                allowed_mentions=discord.AllowedMentions(roles=True),
            )

        message = await interaction.original_response()

        thread_name = THREAD_NAME.format(
            match=gametype.value, gametype=matchtype.value, gameid=game_id
        )
        # Private thread — invisible in the channel, only added members see it
        thread = await interaction.channel.create_thread(
            name=thread_name,
            type=discord.ChannelType.private_thread,
            invitable=False,
        )

        create_game(
            game_id=game_id,
            host_id=interaction.user.id,
            host_name=interaction.user.display_name,
            gametype=gametype.value,
            matchtype=matchtype.value,
            region=region.value,
            vip=vipserver,
            thread_id=thread.id,
            message_id=message.id,
            players_needed=players_needed,
            channel_id=interaction.channel_id,
        )

        await thread.add_user(interaction.user)

        welcome_embed = discord.Embed(
            title=f"{interaction.user.display_name}'s Game",
            description=(
                f"VIP Server Link: [Join here!]({vipserver})\n"
                f"• Please wait for players to join and then you can start your match."
            ),
            color=EMBED_COLOR,
        )
        welcome_embed.set_footer(text=f"Game ID: {game_id}")
        welcome_embed.timestamp = discord.utils.utcnow()
        await thread.send(embed=welcome_embed)

    # ─── /endgame ─────────────────────────────────────────────────────────────

    @app_commands.command(name="endgame", description="End the current game.")
    async def endgame(self, interaction: discord.Interaction):
        gameid, game = resolve_game(interaction)
        if not game:
            await interaction.response.send_message(
                "This command only works inside a game thread.", ephemeral=True
            )
            return

        if not is_host_or_staff(interaction, game):
            await interaction.response.send_message("Only the host can end the game.", ephemeral=True)
            return

        # Check if game is already finished
        if game.get("finished") or game.get("locked"):
            await interaction.response.send_message(
                "This game has already been ended.", ephemeral=True
            )
            return

        # Mark game as finished and locked to prevent duplicate end calls
        games = load_games()
        if gameid in games:
            games[gameid]["finished"] = True
            games[gameid]["locked"] = True
            save_games(games)

        delete_game(gameid)
        thread = await get_thread(interaction, game)

        await interaction.response.send_message("Game ended.", ephemeral=True)
        await thread.delete()

    # ─── /createteams ─────────────────────────────────────────────────────────

    @app_commands.command(name="createteams", description="Randomly split players into two balanced teams.")
    async def createteams(self, interaction: discord.Interaction):
        gameid, game = resolve_game(interaction)
        if not game:
            await interaction.response.send_message(
                "This command only works inside a game thread.", ephemeral=True
            )
            return

        if not is_host_or_staff(interaction, game):
            await interaction.response.send_message("Only the host can create teams.", ephemeral=True)
            return

        players = list(game["players"])

        if not any(p["id"] == game["host_id"] for p in players):
            host_member = interaction.guild.get_member(game["host_id"])
            host_name = host_member.display_name if host_member else game["host_name"]
            players.append({"id": game["host_id"], "display_name": host_name})

        if len(players) < 2:
            await interaction.response.send_message("Not enough players have joined yet.", ephemeral=True)
            return

        # Assign each player a numeric tier rank (higher = better)
        tier_rank = {t: len(TIER_ROLES) - i for i, t in enumerate(TIER_ROLES)}

        ranked = []
        for p in players:
            tier = get_player_tier(interaction.guild, p["id"])
            ranked.append((p, tier, tier_rank.get(tier, 0)))

        # Shuffle within same rank so equal-tier players are randomly ordered
        random.shuffle(ranked)
        ranked.sort(key=lambda x: x[2], reverse=True)

        # Snake draft: A, B, B, A, A, B, B, A …
        # Ensures no team ever stacks with the odd player out from any tier
        team_a, team_b = [], []
        for i, (p, tier, _) in enumerate(ranked):
            pair = i // 2
            goes_to_a = (pair % 2 == 0 and i % 2 == 0) or (pair % 2 == 1 and i % 2 == 1)
            if goes_to_a:
                team_a.append((p, tier))
            else:
                team_b.append((p, tier))

        def fmt(entry):
            p, tier = entry
            label = tier if tier else "Unranked"
            return f"• <@{p['id']}> — {label}"

        embed = discord.Embed(
            title="⚔️ Teams Are In!",
            description="Balanced by skill tier. Good luck, have fun. 🎮",
            color=EMBED_COLOR,
        )
        embed.add_field(name=f"Team 1 ({len(team_a)})", value="\n".join(fmt(e) for e in team_a) or "—", inline=True)
        embed.add_field(name=f"Team 2 ({len(team_b)})", value="\n".join(fmt(e) for e in team_b) or "—", inline=True)
        embed.timestamp = discord.utils.utcnow()
        embed.set_footer(text=f"Game ID: {gameid}")

        thread = await get_thread(interaction, game)
        await thread.send(embed=embed)
        await interaction.response.send_message("Teams created in the thread.", ephemeral=True)

    # ─── /add ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="add", description="Manually add a member to the game.")
    @app_commands.describe(player="The member to add to the game")
    async def add(self, interaction: discord.Interaction, player: discord.Member):
        gameid, game = resolve_game(interaction)
        if not game:
            await interaction.response.send_message(
                "This command only works inside a game's thread.", ephemeral=True
            )
            return

        if not is_host_or_staff(interaction, game):
            await interaction.response.send_message("Only the host can add players.", ephemeral=True)
            return

        if any(p.get("id") == player.id for p in game.get("players", [])):
            await interaction.response.send_message(f"{player.mention} is already in this game.", ephemeral=True)
            return

        spots_remaining = game.get("players_needed", 0) - len(game.get("players", []))
        if spots_remaining <= 0:
            await interaction.response.send_message("This game is already full.", ephemeral=True)
            return

        add_player(gameid, {"id": player.id, "display_name": player.display_name})
        game = get_game(gameid)

        thread = await get_thread(interaction, game)
        await thread.add_user(player)
        await thread.send(
            embed=discord.Embed(
                title="Player Added",
                description=f"{player.mention} was added by {interaction.user.mention}.",
                color=EMBED_COLOR,
            )
        )

        if len(game.get("players", [])) >= game.get("players_needed", 0):
            games = load_games()
            if gameid in games and not games[gameid].get("finished"):
                games[gameid]["finished"] = True
                games[gameid]["locked"] = True
                save_games(games)
                await thread.send(
                    embed=discord.Embed(description="✅ This game is now full!", color=EMBED_COLOR)
                )

        await interaction.response.send_message(f"Added {player.mention} to the game.", ephemeral=True)

    # ─── /sub ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="sub", description="Announce that you need a substitute for the game.")
    async def sub(self, interaction: discord.Interaction):
        gameid, game = resolve_game(interaction)
        if not game:
            await interaction.response.send_message(
                "This command only works inside a game thread.", ephemeral=True
            )
            return

        if not is_host_or_staff(interaction, game):
            await interaction.response.send_message("Only the host can call for a sub.", ephemeral=True)
            return

        spots_remaining = game.get("players_needed", 0) - len(game.get("players", []))
        if spots_remaining < 1:
            spots_remaining = 1

        ping_role = discord.utils.find(
            lambda r: PING_ROLE_NAME in r.name, interaction.guild.roles
        )
        ping_mention = ping_role.mention if ping_role else f"@{PING_ROLE_NAME}"

        sub_embed = discord.Embed(
            title=f"Looking for {spots_remaining} Sub{'s' if spots_remaining > 1 else ''}",
            description=(
                f"{interaction.user.mention} is looking for **{spots_remaining}** substitute player(s).\n"
                "Join using the **Join Game** button above."
            ),
            color=EMBED_COLOR,
        )
        sub_embed.set_footer(text=f"Game ID: {gameid}")
        sub_embed.timestamp = discord.utils.utcnow()

        thread = await get_thread(interaction, game)
        await thread.send(content=ping_mention, embed=sub_embed, allowed_mentions=discord.AllowedMentions(roles=True))
        await interaction.response.send_message("Sub announcement posted.", ephemeral=True)

    # ─── /remove ──────────────────────────────────────────────────────────────

    @app_commands.command(name="remove", description="Remove a player from the game.")
    @app_commands.describe(player="The player to remove", reason="Reason for removal")
    async def remove(self, interaction: discord.Interaction,
                     player: discord.Member, reason: str = "No reason given"):
        gameid, game = resolve_game(interaction)
        if not game:
            await interaction.response.send_message(
                "This command only works inside a game thread.", ephemeral=True
            )
            return

        if not is_host_or_staff(interaction, game):
            await interaction.response.send_message("Only the host can remove players.", ephemeral=True)
            return

        if not any(p.get("id") == player.id for p in game.get("players", [])):
            await interaction.response.send_message(f"{player.mention} is not in this game.", ephemeral=True)
            return

        remove_player(gameid, player.id)

        thread = await get_thread(interaction, game)
        await thread.remove_user(player)
        await thread.send(
            embed=discord.Embed(
                title="Player Removed",
                description=f"{player.mention} was removed. Reason: {reason}",
                color=EMBED_COLOR,
            )
        )

        games = load_games()
        if gameid in games:
            games[gameid]["finished"] = False
            games[gameid]["locked"] = False
            save_games(games)

        await interaction.response.send_message(f"Removed {player.mention}.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(HostGameCog(bot))

