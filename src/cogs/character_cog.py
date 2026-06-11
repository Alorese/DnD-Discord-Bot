import discord
from discord.ext import commands
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from google import genai
from google.genai import types

from database.models.session import GameSession, SpeakerType, ChatMessage
from database.models.character import CharacterSheet
from database.models.room import Room

class CharacterManagerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.jinja_env = Environment(loader=FileSystemLoader("templates"))
        self.ai_client = genai.Client()

    @commands.command(name="long_rest")
    async def long_rest(self, ctx):
        """Executes a full D&D 2024 Long Rest mechanics sequence for the active session."""
        session = await GameSession.find_one({"party_state.active_characters.user_id": str(ctx.author.id)})
        if not session:
            return await ctx.send("❌ You are not currently in an active game session.")
        
        if session.combat_state.in_combat:
            return await ctx.send("❌ You cannot take a long rest while locked in active combat initiative!")

        await ctx.send("⏳ *The party prepares to hunkers down for an 8-hour Long Rest...*")

        resting_characters_data = []

        # 1. Loop through and programmatically restore all active character states
        for char_id, actor in list(session.party_state.active_characters.items()):
            # Fetch persistent master sheet to grab maximum hit points and reference data
            master_sheet = await CharacterSheet.get(actor.character_id)
            if not master_sheet:
                continue

            # Apply 2024 Long Rest Rule mutations to the active instance state
            actor.current_hp = master_sheet.vitals.max_hp
            actor.temporary_hp = 0
            actor.active_conditions = [c for c in actor.active_conditions if c.value != "EXHAUSTION"] # Clear status conditions
            actor.active_buffs_and_debuffs = [] # Clear temporary spell buffs
            
            # 2. Sync values back down to the persistent Master Document
            master_sheet.vitals.current_hp = master_sheet.vitals.max_hp
            master_sheet.status_conditions = actor.active_conditions
            
            # Reset Spell Slots on master sheet
            if master_sheet.spell_slots:
                if "level_1" in master_sheet.spell_slots.level_1: master_sheet.spell_slots.level_1["used"] = 0
                if "level_2" in master_sheet.spell_slots.level_2: master_sheet.spell_slots.level_2["used"] = 0
                if "level_3" in master_sheet.spell_slots.level_3: master_sheet.spell_slots.level_3["used"] = 0
            
            master_sheet.updated_at = datetime.utcnow()
            await master_sheet.save()
            
            resting_characters_data.append({"name": actor.name})

        # --- STEP 3: Invoke Jinja2 & Gemini to Describe the Camp Sequence ---
        room = await Room.find_one(Room.room_id == session.party_state.current_room_id)
        template = self.jinja_env.get_template("rest_narrative.jinja")
        prompt = template.render(room=room, rest_type="LONG_REST", characters=resting_characters_data, slots_reset=True)

        response = self.ai_client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.7)
        )

        story_text = response.text
        session.narrative_memory.recent_chat_history.append(ChatMessage(speaker=SpeakerType.NARRATOR, text=story_text))
        await session.save()

        embed = discord.Embed(
            title="💤 Long Rest Complete",
            description=f"{story_text}\n\n✨ **All Hit Points restored. All Spell Slots recovered. Exhaustion cleared.**",
            color=discord.Color.purple()
        )
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(CharacterManagerCog(bot))
