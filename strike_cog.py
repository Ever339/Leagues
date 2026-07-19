import discord
from discord.ext import commands
from discord import app_commands

from config import EMBED_COLOR, STRIKE_ROLE_NAME, STRIKES_FOR_BAN
from strike_storage import add_strikes, remove_strikes, clear_strikes, get_record, get_strikes


def get_strike_role(guild: discord.Guild) -> discord.Role | None:
    return discord.utils.find(
        lambda r: STRIKE_ROLE_NAME.lower() in r.name.lower(), guild.roles
    )


class StrikeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    strike_group = app_commands.Group(name="strike", description="Manage league host strikes.")

    @strike_group.command(name="add", description="Add strikes to a user.")
    @app_commands.describe(
        type="Type of strike",
        target="The user to strike",
        count="Number of strikes to add",
        reason="Reason for the strike",
    )
    @app_commands.choices(
        type=[
            app_commands.Choice(name="Player", value="Player"),
            app_commands.Choice(name="Host", value="Host"),
        ]
    )
    @app_commands.default_permissions(manage_roles=True)
    async def strike_add(self, interaction: discord.Interaction,
                         type: app_commands.Choice[str], target: discord.Member,
                         count: int, reason: str):
        if count < 1:
            await interaction.response.send_message("Count must be at least 1.", ephemeral=True)
            return

        new_total = add_strikes(target.id, count, type.value, reason, str(interaction.user))

        embed = discord.Embed(title="⚠️ Strike Issued", color=discord.Color.orange())
        embed.add_field(name="User", value=target.mention, inline=True)
        embed.add_field(name="Type", value=type.value, inline=True)
        embed.add_field(name="Strikes Added", value=str(count), inline=True)
        embed.add_field(name="Total Strikes", value=f"{new_total}/{STRIKES_FOR_BAN}", inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.set_footer(text=f"Issued by {interaction.user.display_name}")
        embed.timestamp = discord.utils.utcnow()

        if new_total >= STRIKES_FOR_BAN:
            role = get_strike_role(interaction.guild)
            if role and role not in target.roles:
                try:
                    await target.add_roles(role, reason=f"Reached {STRIKES_FOR_BAN} strikes: {reason}")
                    embed.description = (
                        f"🚫 {target.mention} has reached **{STRIKES_FOR_BAN} strikes** "
                        f"and has been assigned the **{STRIKE_ROLE_NAME}** role. "
                        f"They can no longer host leagues."
                    )
                except discord.Forbidden:
                    embed.description = (
                        f"⚠️ {target.mention} reached {STRIKES_FOR_BAN} strikes but I couldn't assign "
                        f"the **{STRIKE_ROLE_NAME}** role (missing permissions)."
                    )
            elif role and role in target.roles:
                embed.description = f"🚫 {target.mention} already has the **{STRIKE_ROLE_NAME}** role."

        await interaction.response.send_message(embed=embed)

    @strike_group.command(name="remove", description="Remove strikes from a user.")
    @app_commands.describe(target="The user", count="Strikes to remove", reason="Reason")
    @app_commands.default_permissions(manage_roles=True)
    async def strike_remove(self, interaction: discord.Interaction,
                            target: discord.Member, count: int, reason: str):
        if count < 1:
            await interaction.response.send_message("Count must be at least 1.", ephemeral=True)
            return

        new_total = remove_strikes(target.id, count, reason, str(interaction.user))

        embed = discord.Embed(title="✅ Strike Removed", color=discord.Color.green())
        embed.add_field(name="User", value=target.mention, inline=True)
        embed.add_field(name="Strikes Removed", value=str(count), inline=True)
        embed.add_field(name="Total Strikes", value=f"{new_total}/{STRIKES_FOR_BAN}", inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.set_footer(text=f"Removed by {interaction.user.display_name}")
        embed.timestamp = discord.utils.utcnow()

        if new_total < STRIKES_FOR_BAN:
            role = get_strike_role(interaction.guild)
            if role and role in target.roles:
                try:
                    await target.remove_roles(role, reason=f"Strikes reduced to {new_total}")
                    embed.description = f"✅ **{STRIKE_ROLE_NAME}** role removed."
                except discord.Forbidden:
                    embed.description = f"⚠️ Couldn't remove **{STRIKE_ROLE_NAME}** role (missing permissions)."

        await interaction.response.send_message(embed=embed)

    @strike_group.command(name="clear", description="Clear all strikes from a user.")
    @app_commands.describe(target="The user to clear")
    @app_commands.default_permissions(manage_roles=True)
    async def strike_clear(self, interaction: discord.Interaction, target: discord.Member):
        clear_strikes(target.id, str(interaction.user))

        role = get_strike_role(interaction.guild)
        removed_role = False
        if role and role in target.roles:
            try:
                await target.remove_roles(role, reason="All strikes cleared")
                removed_role = True
            except discord.Forbidden:
                pass

        embed = discord.Embed(
            title="🧹 Strikes Cleared",
            description=(
                f"All strikes cleared for {target.mention}."
                + (f"\n**{STRIKE_ROLE_NAME}** role removed." if removed_role else "")
            ),
            color=discord.Color.green(),
        )
        embed.set_footer(text=f"Cleared by {interaction.user.display_name}")
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.send_message(embed=embed)

    @strike_group.command(name="check", description="Check how many strikes a user has.")
    @app_commands.describe(target="The user to check")
    async def strike_check(self, interaction: discord.Interaction, target: discord.Member):
        record = get_record(target.id)
        total = record.get("total", 0)
        history = record.get("history", [])

        embed = discord.Embed(
            title=f"Strike Record — {target.display_name}",
            color=discord.Color.red() if total >= STRIKES_FOR_BAN
                  else discord.Color.orange() if total > 0
                  else discord.Color.green(),
        )
        embed.add_field(name="Total Strikes", value=f"{total}/{STRIKES_FOR_BAN}", inline=True)

        ban_role = get_strike_role(interaction.guild)
        banned = ban_role and ban_role in target.roles
        embed.add_field(name="Hosting Banned", value="🚫 Yes" if banned else "✅ No", inline=True)

        if history:
            lines = []
            for entry in reversed(history[-5:]):
                ts = entry.get("timestamp", "")[:10]
                action = entry.get("action", "")
                if action == "add":
                    lines.append(f"`+{entry['count']}` {entry['type']} — {entry['reason']} *({entry['added_by']}, {ts})*")
                elif action == "remove":
                    lines.append(f"`-{entry['count']}` removed — {entry['reason']} *({entry['removed_by']}, {ts})*")
                elif action == "clear":
                    lines.append(f"`cleared` *({entry['cleared_by']}, {ts})*")
            embed.add_field(name="Recent History", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="History", value="No strikes on record.", inline=False)

        embed.set_thumbnail(url=target.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(StrikeCog(bot))
