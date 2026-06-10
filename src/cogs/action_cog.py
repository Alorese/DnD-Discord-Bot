import asyncio
import json
import random
from collections import defaultdict
from discord.ext import commands
import discord

from config.settings import settings
from database.models import GameSession, CharacterSheet, RoomContext
from services.gemini_client import gemini_service
from google.genai import types
from jinja2 import Environment, FileSystemLoader, select_autoescape

# Setup Jinja2 template workspace parsing framework
jinja_env = Environment(
    loader=FileSystemLoader("src/templates"),
    autoescape=select_autoescape()
)

# ==============================================================================
# SINGLE PLAYER INTERACTIVE VIEW ENGINE (Multi-Stage 2024 State Machine)
# ==============================================================================
class SinglePlayerRollView(discord.ui.View):
    """
    Manages a proactive, single-player action check. 
    Implements a multi-stage 2024 state machine for Heroic Inspiration fallbacks.
    """
    def __init__(self, channel_id: str, player_id: str, roll_type: str, target_dc: int, action_text: str):
        super().__init__(timeout=120)
        self.channel_id = channel_id
        self.player_id = player_id
        self.roll_type = roll_type
        self.target_dc = target_dc
        self.action_text = action_text
        
        # Track roll steps locally in memory cache
        self.first_roll = None
        self.final_total = None

    async def _execute_narrator_handoff(self, interaction: discord.Interaction, roll_summary: str, old_vitals):
        """Compiles prompt templates and fires the long-context Gemini Narrator."""
        session = await GameSession.find_one(GameSession.channel_id == self.channel_id, fetch_links=True)
        character = await CharacterSheet.find_one(CharacterSheet.channel_id == self.channel_id, CharacterSheet.player_id == self.player_id)
        
        # Render narrative prompt parameters via Jinja2
        template = jinja_env.get_template("narrator_prompt.j2")
        rendered_prompt = template.render(
            character=character,
            session=session,
            player_action=self.action_text,
            roll_summary=roll_summary,
            old_vitals=old_vitals
        )

        # Slide the long-context window forward to protect RAM allocation limits
        gemini_service.bump_context_cache_ttl(session.active_module.gemini_file_uri)
        client = gemini_service.get_client()
        module_file_handle = client.files.get(name=session.active_module.gemini_file_uri.split('/')[-1])

        response = client.models.generate_content(
            model=gemini_service.model_name,
            contents=[module_file_handle, rendered_prompt]
        )
        
        # Dispatch final storytelling text blocks back to the Discord thread
        await interaction.followup.send(response.text)
        self.stop()

    @discord.ui.button(label="🎲 CLICK TO ROLL", style=discord.ButtonStyle.primary, custom_id="single_roll_btn")
    async def initial_roll_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.player_id:
            await interaction.response.send_message("This isn't your fate to decide, traveler!", ephemeral=True)
            return

        await interaction.response.defer()
        
        character = await CharacterSheet.find_one(CharacterSheet.channel_id == self.channel_id, CharacterSheet.player_id == self.player_id)
        modifier = character.base_skills.get(self.roll_type, 0)
        
        d20 = random.randint(1, 20)
        self.first_roll = d20
        total = d20 + modifier
        old_vitals = character.vitals.copy()

        # PATH A: SUCCESS OR NO HEROIC INSPIRATION -> Lock the turn instantly
        if total >= self.target_dc or not character.vitals.has_heroic_inspiration:
            self.final_total = total
            button.disabled = True
            await interaction.message.edit(view=self)
            
            success_tag = "SUCCESS" if total >= self.target_dc else "FAILURE"
            summary = f"{success_tag}! Rolled {d20} + {modifier} = {total} (vs DC {self.target_dc})"
            
            # Apply standard fail environmental damage delta if applicable
            if total < self.target_dc:
                current_hp = character.vitals.session_current_hp if character.vitals.session_current_hp is not None else character.vitals.base_max_hp
                character.vitals.session_current_hp = max(0, current_hp - 4)
                await character.save()
                
            await interaction.followup.send(f"**Dice Result:** {character.character_name} rolled **{total}** ({summary}). Adjudicating scene...")
            await self._execute_narrator_handoff(interaction, summary, old_vitals)
        
        # PATH B: FAILURE BUT HAS HEROIC INSPIRATION -> Morph UI View container layout to present choice
        else:
            button.disabled = True
            
            # Dynamically spawn the 2024 option button onto the active interface view
            reroll_btn = discord.ui.Button(label="⚡ ACTIVATE HEROIC REROLL", style=discord.ButtonStyle.danger, custom_id="single_heroic_btn")
            
            # Inline callback execution logic for the dynamic reroll button
            async def reroll_callback(inter: discord.Interaction):
                if str(inter.user.id) != self.player_id: 
                    return
                await inter.response.defer()
                
                # 2024 Rule Override Math Calculation
                new_d20 = random.randint(1, 20)
                new_total = new_d20 + modifier
                self.final_total = new_total
                
                # Close view layers
                reroll_btn.disabled = True
                await inter.message.edit(view=self)
                
                # Drain the 2024 Heroic Inspiration flag from MongoDB
                character.vitals.has_heroic_inspiration = False
                if new_total < self.target_dc:
                    current_hp = character.vitals.session_current_hp if character.vitals.session_current_hp is not None else character.vitals.base_max_hp
                    character.vitals.session_current_hp = max(0, current_hp - 4)
                await character.save()
                
                success_tag = "SUCCESS" if new_total >= self.target_dc else "FAILURE"
                summary = f"{success_tag}! **Heroic Reroll:** {new_d20} + {modifier} = {new_total} (vs DC {self.target_dc}, Overwrote {self.first_roll})"
                
                await inter.followup.send(f"💥 **Heroic Reroll Triggered!** New Total: **{new_total}** ({summary})")
                await self._execute_narrator_handoff(inter, summary, old_vitals)

            reroll_btn.callback = reroll_callback
            self.add_item(reroll_btn)
            
            # Update the parent message text to prompt the player for their decision
            await interaction.message.edit(
                content=f"⚠️ **Check Failed!** You rolled a total of `{total}` (vs DC {self.target_dc}). Spend your Heroic Inspiration to completely overwrite this roll?", 
                view=self
            )

# ==============================================================================
# CORE COG INTERACTION GATEWAY
# ==============================================================================
class ActionCog(commands.Cog):
    """Manages proactive, natural-language player actions and executes the Rule Check cycle."""
    def __init__(self, bot):
        self.bot = bot
        # Thread-safe asyncio lock cache queue mapping channel IDs
        self.session_locks = defaultdict(asyncio.Lock)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # 1. Pipeline Traffic Guards
        if message.author.bot:
            return
        if message.content.startswith("!") or message.content.startswith("/") or self.bot.user.mentioned_in(message):
            return
        if message.content.strip().startswith("((") and message.content.strip().endswith("))"):
            return

        channel_id = str(message.channel.id)
        player_id = str(message.author.id)

        # 2. Concurrency queue lock engagement to stamp out race conditions
        async with self.session_locks[channel_id]:
            
            # Lookup structural game session fields
            session = await GameSession.find_one(GameSession.channel_id == channel_id, fetch_links=True)
            if not session:
                return # Silence if room session hasn't been instantiated via /load_module

            character = await CharacterSheet.find_one(
                CharacterSheet.channel_id == channel_id,
                CharacterSheet.player_id == player_id
            )
            if not character:
                await message.reply("You haven't checked into this campaign yet! Use `/join_session` first.")
                return

            room = await RoomContext.find_one(
                RoomContext.module_slug == session.active_module.module_slug,
                RoomContext.room_id == session.current_room_id
            )

            # 3. Compile and dispatch the Rule Check Prompt
            rule_template = jinja_env.get_template("rule_check.j2")
            rendered_rule_prompt = rule_template.render(
                character=character,
                room=room,
                player_action=message.content
            )

            async with message.channel.typing():
                client = gemini_service.get_client()
                
                # Define constraints schema mapping parameters for Gemini 3.1 Flash-Lite
                response_schema = {
                    "type": "OBJECT",
                    "properties": {
                        "action_valid": {"type": "BOOLEAN"},
                        "rejection_reason": {"type": "STRING"},
                        "roll_required": {"type": "STRING"},
                        "target_dc": {"type": "INTEGER"}
                    },
                    "required": ["action_valid", "rejection_reason", "roll_required", "target_dc"]
                }

                rule_response = client.models.generate_content(
                    model=gemini_service.model_name,
                    contents=[rendered_rule_prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=response_schema
                        )
                )
                decision = json.loads(rule_response.text)

            # 4. Adjudicate results
            if not decision["action_valid"]:
                await message.reply(f"❌ Action Denied: {decision['rejection_reason']}")
                return
            # Action Approved: Instantiate the multi-stage single-player view state loop
            view = SinglePlayerRollView(
                channel_id=channel_id,
                player_id=player_id,
                roll_type=decision["roll_required"],
                target_dc=decision["target_dc"],
                action_text=message.content
            )
            
        await message.reply(
            f"🎲 Action Validated: {character.character_name} attempts to execute their action.\n"
            f"Requires a DC {decision['target_dc']} {decision['roll_required']} check.",
            view=view
        )
            
async def setup(bot):
    await bot.add_cog(ActionCog(bot))