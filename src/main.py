import os
import asyncio
import discord
from discord.ext import commands
from database.connection import init_database
from config.settings import settings

# Initialize the Bot client
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"🎲 Logged in as {bot.user.name} (ID: {bot.user.id})")

async def load_extensions():
    # Sweep your directory and dynamically load your cog segments
    # Path uses standard dot notation relative to the application workspace: cogs.filename
    cogs_dir = os.path.join(os.path.dirname(__file__), "cogs")
    
    for filename in os.listdir(cogs_dir):
        if filename.endswith("_cog.py"):
            cog_name = f"cogs.{filename[:-3]}"
            await bot.load_extension(cog_name)
            print(f"✅ Loaded Cog: {cog_name}")

async def main():
    # 1. Boot up the MongoDB & Beanie mapping connection layer
    await init_database(settings.mongo_uri)
    
    # 2. Register all game loop cogs
    await load_extensions()
    
    # 3. Connect to the Discord Gateway
    await bot.start(settings.discord_bot_token)

if __name__ == "__main__":
    asyncio.run(main())
