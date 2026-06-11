import json
import discord
from discord.ext import commands
from jinja2 import Environment, FileSystemLoader
from google import genai
from google.genai import types
from database.models.session import GameSession
from cogs.views import InitialDiceRollView

class RulesEngineCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # 1. Bind the unified Jinja2 parsing environment
        self.jinja_env = Environment(loader=FileSystemLoader("templates"))
        # 2. Instantiate the Google GenAI connection client
        self.ai_client = genai.Client()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Listens to game channels to intercept raw text statements
        and process them through the mechanical intent parser loop.
        """
        # Prevent the bot from parsing its own text or processing non-game commands
        if message.author.bot or message.content.startswith("!"):
            return

        # Find if this specific user has an active, running game session thread
        session = await GameSession.find_one({"party_state.active_characters.user_id": str(message.author.id)})
        if not session:
            return

        # Block casual inputs during combat to protect initiative sequence stability
        if session.combat_state.in_combat:
            # Locate whose active entity slot it currently is
            active_turn = session.combat_state.initiative_order[session.combat_state.active_turn_index]
            if active_turn.entity_id != str(message.author.id):
                return await message.channel.send(f"❌ Hold on, it is currently **{active_turn.entity_id}**'s turn to act!")

        # Process the input statement
        await self.adjudicate_player_action(message.channel, session, str(message.author.id), message.content)

    async def adjudicate_player_action(self, channel, session: GameSession, user_id: str, player_input: str):
        """Processes intent parsing and launches tactical roll prompts."""
        # Find the specific actor sub-document corresponding to this user
        character_id = next(c_id for c_id, c in session.party_state.active_characters.items() if c.user_id == user_id)
        actor = session.party_state.active_characters[character_id]

        # --- STEP 1: Compile Context and Call Gemini Intent Brain ---
        template = self.jinja_env.get_template("rules_intent_parser.jinja")
        prompt = template.render(actor=actor, player_input=player_input)

        response = self.ai_client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,  # Strict mechanical classification consistency
                response_mime_type="application/json"
            )
        )

        # Parse structural target rules parameters out of the JSON response payload
        intent = json.loads(response.text)

        # --- STEP 2: Branch Execution Based on Intent Requirements ---
        if not intent.get("requires_roll"):
            # If no mechanical stakes exist, route data straight to the Narrator layer
            payload = {
                "character_id": character_id,
                "check_type": "FLAVOR_ACTION",
                "outcome": "SUCCESS",
                "math_breakdown": "No roll required.",
                "raw_statement": player_input
            }
            self.bot.dispatch("rules_roll_complete", session.id, payload)
            return

        # --- STEP 3: Spawn Interactive Dice Button Prompts ---
        stat_name = intent["stat_to_use"]
        target_dc = intent["target_dc"]
        modifier = intent["modifier_value"]

        # Instantiate our dynamic multi-die split selection view
        view = InitialDiceRollView(
            session_id=session.id,
            character_id=character_id,
            stat_name=stat_name,
            target_dc=target_dc,
            modifier=modifier,
            can_use_inspiration=actor.has_regular_inspiration
        )

        await channel.send(
            content=f"🎲 **{actor.name}** attempts to act! *({intent['reasoning']})*\n"
                    f"**{stat_name.replace('_', ' ').title()} check forced.** Target DC: **{target_dc}**",
            view=view
        )

async def setup(bot):
    await bot.add_cog(RulesEngineCog(bot))
