import discord
from discord.ext import commands
import os
import asyncio

intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(e)


async def load():
    await bot.load_extension("hostgame_cog")
    await bot.load_extension("strike_cog")


async def main():
    token = os.getenv("DISCORD_TOKEN") or os.getenv("TOKEN")
    if not token:
        raise RuntimeError("No bot token found. Set DISCORD_TOKEN in Replit Secrets.")

    async with bot:
        await load()
        await bot.start(token)


asyncio.run(main())
