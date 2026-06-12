import os
import sys
import asyncio
import discord
from discord.ext import commands
from database.connection import init_database
from config.settings import settings

# 1. Configure the structural Discord network hooks
intents = discord.Intents.default()
# Crucial: Allows the bot to read player text inputs in channels
intents.message_content = True 

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"🎲 Logged in as {bot.user.name} (ID: {bot.user.id})")
    # Setting an active D&D status activity for player scannability
    await bot.change_presence(activity=discord.Game(name="D&D 5e (2024 Rulebook)"))
    # await bot.tree.copy_global_to(guild=guild)
    # await bot.tree.sync(guild=guild)
    # await bot.tree.sync()

async def load_extensions():
    """
    Sweeps the local cogs/ folder directory and dynamically registers 
    all game engine loop cogs into the active Discord bot client namespace.
    """
    # Build absolute path to cogs folder to prevent workspace directory shift bugs
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cogs_dir = os.path.join(base_dir, "cogs")
    
    if not os.path.exists(cogs_dir):
        print(f"⚠️ Warning: Cogs folder not detected at destination: {cogs_dir}")
        return

    for filename in os.listdir(cogs_dir):
        # Explicit check for python file extensions ending in _cog
        if filename.endswith("_cog.py") and not filename.startswith("__"):
            cog_name = f"cogs.{filename[:-3]}"
            try:
                await bot.load_extension(cog_name)
                print(f"✅ Loaded Cog Module: {cog_name}")
            except Exception as e:
                print(f"❌ Failed to load extension {cog_name}: {e}", file=sys.stderr)

async def main():
    # 1. Boot up the MongoDB Motor client pool & Beanie mapping collection layers
    try:
        # Cast Pydantic's MongoDsn safely to a string for driver parsing compliance
        db_success = await init_database(str(settings.mongo_uri))
        if not db_success:
            raise ConnectionError("MongoDB initialization layer returned an unsuccessful status flag.")
    except Exception as e:
        print(f"❌ CRITICAL STORAGE BOOT FAILURE: {e}", file=sys.stderr)
        return
    
    # 2. Register all decoupled backend mechanism engine cogs
    await load_extensions()
    
    # 3. Connect to the Discord Gateway using project settings
    try:
        print("📡 Establishing secure connection link to Discord Gateway...")
        await bot.start(settings.discord_bot_token)
    except discord.LoginFailure:
        print("❌ CRITICAL AUTHENTICATION FAILURE: Provided DISCORD_BOT_TOKEN is rejected or invalid.", file=sys.stderr)
    except Exception as e:
        print(f"❌ CRITICAL CONNECTIVITY CRASH during bot initialization: {e}", file=sys.stderr)

# =========================================================================
# SYSTEM INFRASTRUCTURE: MASTER GLOBAL TREE SYNC CONTROL
# =========================================================================
@bot.command(name="sync")
@commands.is_owner() # Protects your application endpoint from malicious user execution
async def sync_application_commands(ctx: commands.Context):
    """
    Manually overrides and registers all local Cog slash commands configuration 
    matrices directly up to the global Discord Gateway server.
    """
    await ctx.send("📡 *Initiating secure application command tree verification...*")
    
    try:
        # Pushes all globally declared cog commands straight to the Discord API server
        synced = await bot.tree.sync()
        
        # Output a descriptive text receipt back to your secure developer admin console channel
        await ctx.send(
            f"✅ **Global Command Tree Sync Complete!**\n"
            f"Registered **{len(synced)} slash commands** globally across all shard profiles."
        )
        print(f"⚙️ Developer Sync Command executed manually by application owner. Synced: {len(synced)}")
        
    except discord.HTTPException as e:
        await ctx.send(f"❌ Discord Gateway rejected the structural tree payload serialization: {e}")
    except Exception as e:
        await ctx.send(f"❌ Internal orchestration exception caught during transmission: {e}")

@sync_application_commands.error
async def sync_error_handler(ctx: commands.Context, error: Exception):
    """Gracefully suppresses permission failures if non-owners try to execute the system link."""
    if isinstance(error, commands.NotOwner):
        await ctx.send("🔒 **Access Denied.** This critical configuration utility is locked to the application developer profile.", delete_after=10)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Shutdown signal intercepted. Closing all network and database connections cleanly.")
