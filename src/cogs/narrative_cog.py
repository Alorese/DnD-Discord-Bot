import discord
from discord.ext import commands
from jinja2 import Environment, FileSystemLoader
from google import genai
from google.genai import types

from database.models.session import GameSession, SpeakerType, ChatMessage
from database.models.room import Room

class NarrativeEngineCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # 1. Load the Jinja2 file environment
        self.jinja_env = Environment(loader=FileSystemLoader("templates"))
        # 2. Instantiate the Google GenAI Client
        self.ai_client = genai.Client()

    @commands.Cog.listener()
    async def on_rules_roll_complete(self, session_id, payload: dict):
        """
        Triggered automatically whenever a player's dice roll sequence resolves.
        Stitches database context and requests descriptive prose from Gemini.
        """
        # 1. Fetch active session state from MongoDB via Beanie
        session = await GameSession.get(session_id)
        if not session:
            return

        # 2. Fetch immutable structural details of the current room
        room = await Room.find_one(Room.room_id == session.party_state.current_room_id)
        
        # 3. Locate the specific character name
        actor_id = payload["character_id"]
        actor = session.party_state.active_characters[str(actor_id)]
        
        # Locate target channel from the active bot cache
        # (In production, store a target 'channel_id' inside your GameSession schema)
        channel = self.bot.get_channel(int(actor.user_id)) 
        if not channel:
            # Fallback to searching active channel structures if user matching fails
            for guild in self.bot.guilds:
                for ch in guild.text_channels:
                    if ch.permissions_for(guild.me).send_messages:
                        channel = ch
                        break

        # --- STEP 1: Render Immersive Narrative Prompt Stack ---
        template = self.jinja_env.get_template("narrator_player_action.jinja")
        narrator_prompt = template.render(
            room=room, 
            session=session, 
            payload=payload, 
            actor_name=actor.name
        )

        # Send a typing indicator to simulate the DM describing the scene
        async with channel.typing():
            # --- STEP 2: Invoke Gemini 3.1 Flash Lite Prose Generator ---
            # (Note: Explicit context caching would hook onto this specific prompt prefix)
            response = self.ai_client.models.generate_content(
                model="gemini-3.1-flash-lite",
                contents=narrator_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.8,  # Higher temperature allows for colorful, creative prose descriptions
                )
            )
            
            story_text = response.text

        # --- STEP 3: Append Transactional Records to History Logs ---
        if payload["check_type"] != "FLAVOR_ACTION":
            session.narrative_memory.recent_chat_history.append(
                ChatMessage(speaker=SpeakerType.RULES_ENGINE, text=f"{actor.name}: {payload['math_breakdown']} -> {payload['outcome']}")
            )
        session.narrative_memory.recent_chat_history.append(
            ChatMessage(speaker=SpeakerType.NARRATOR, text=story_text)
        )
        
        # Commit running log updates securely to MongoDB
        await session.save()

        # --- STEP 4: Post the Final Immersive Embed block ---
        embed = discord.Embed(
            title=f"📖 {actor.name}'s Action Resolves",
            description=story_text,
            color=discord.Color.gold() if payload["outcome"] == "SUCCESS" else discord.Color.dark_grey()
        )
        if payload["check_type"] != "FLAVOR_ACTION":
            embed.set_footer(text=f"Math Ledger: {payload['math_breakdown']} (vs DC {payload['dc_target']})")
            
        await channel.send(embed=embed)

async def setup(bot):
    await bot.add_cog(NarrativeEngineCog(bot))
