import os
import random
import discord
from discord.ext import commands
from jinja2 import Environment, FileSystemLoader
from google import genai
from google.genai import types
# Import your strong-typed Beanie schemas
from database.models.session import GameSession, SpeakerType, ChatMessage
from database.models.room import Room
from database.models.monster import Monster

class CombatCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # 1. Initialize Jinja2 environment looking inside the templates folder
        self.jinja_env = Environment(loader=FileSystemLoader("templates"))
        # 2. Initialize Google GenAI Client for Gemini 3.1 Flash Lite
        self.ai_client = genai.Client()

    async def execute_monster_turn(self, ctx, session: GameSession, monster_instance_id: str):
        """Programmatically executes an active monster's complete turn cycle."""
        await ctx.send(f"📖 *{monster_instance_id.replace('_', ' ').title()} is calculating tactical movement...*")

        # Extract base monster identity slug from instance tracking string (e.g. "goblin_sentry_1" -> "goblin_sentry")
        monster_base_slug = "_".join(monster_instance_id.split("_")[:-1])
        
        # Pull required DB records concurrently
        room = await Room.find_one(Room.room_id == session.party_state.current_room_id)
        monster_blueprint = await Monster.find_one(Monster.monster_id == monster_base_slug)
        
        if not room or not monster_blueprint:
            return await ctx.send("❌ Error: Missing mechanical room/monster assets in database.")

        # --- STEP 1: Jinja2 Injection for Rules Engine Choice ---
        rules_template = self.jinja_env.get_template("rules_monster_brain.jinja")
        rules_prompt = rules_template.render(room=room, session=session, monster=monster_blueprint)

        # Call Gemini 3.1 Flash Lite configured as the strict JSON rules brain
        rules_response = self.ai_client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=rules_prompt,
            config=types.GenerateContentConfig(
                temperature=0.1, # High determinism for logic engine
                response_mime_type="application/json"
            )
        )
        
        # Safely extract decision metrics out of model JSON string
        import json
        decision = json.loads(rules_response.text)
        action_name = decision["action_name"]
        target_id = decision["target_character_id"]

        # --- STEP 2: Pure Python Tool Evaluation (The Math Layer) ---
        attack = next(a for a in monster_blueprint.actions if a.name == action_name)
        player_target = session.party_state.active_characters[target_id]

        d20_roll = random.randint(1, 20)
        total_hit = d20_roll + attack.hit_modifier
        hit_success = total_hit >= player_target.armor_class
        
        damage_dealt = 0
        if hit_success:
            # Basic parsing of standard formula syntax like "1d6 + 2"
            # (In production, replace with a secure regex dice-roller helper)
            dice_count, dice_faces = map(int, attack.damage_formula.split("+")[0].strip().split("d"))
            base_damage = sum(random.randint(1, dice_faces) for _ in range(dice_count))
            flat_bonus = int(attack.damage_formula.split("+")[1].strip()) if "+" in attack.damage_formula else 0
            damage_dealt = base_damage + flat_bonus
            
            # Reduce health safely in the active memory footprint
            player_target.current_hp = max(0, player_target.current_hp - damage_dealt)

        # Build structural validation package
        math_payload = {
            "monster_name": monster_blueprint.name,
            "attack_name": action_name,
            "hit_roll_breakdown": f"Rolled {d20_roll} + {attack.hit_modifier} = {total_hit} vs AC {player_target.armor_class}",
            "hit_success": hit_success,
            "damage_dealt": damage_dealt,
            "target_name": player_target.name,
            "player_dead": player_target.current_hp <= 0
        }

        # --- STEP 3: Jinja2 Injection for Narrative Generation ---
        narrator_template = self.jinja_env.get_template("narrator_combat_block.jinja")
        narrator_prompt = narrator_template.render(room=room, payload=math_payload)

        # Call Gemini 3.1 Flash Lite as the creative DM voice (Explicit caching prefix sits here)
        narrator_response = self.ai_client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=narrator_prompt,
            config=types.GenerateContentConfig(
                temperature=0.85, # Rich linguistic variety
            )
        )

        # --- STEP 4: Session Memory & DB Save Commitment ---
        story_output = narrator_response.text
        
        # Append transactional log items back to your running MongoDB session history
        session.narrative_memory.recent_chat_history.append(
            ChatMessage(speaker=SpeakerType.RULES_ENGINE, text=f"{monster_instance_id} attacks {player_target.name}: {math_payload['hit_roll_breakdown']} (Dealt {damage_dealt} DMG)")
        )
        session.narrative_memory.recent_chat_history.append(
            ChatMessage(speaker=SpeakerType.NARRATOR, text=story_output)
        )
        
        # Commit all mutations to MongoDB via Beanie
        await session.save()

        # Send finalized immersive story layout blocks back to the chat channel
        embed = discord.Embed(
            title=f"⚔️ Encounter Combat Tracker: {monster_blueprint.name}'s Action",
            description=story_output,
            color=discord.Color.red() if hit_success else discord.Color.blue()
        )
        embed.set_footer(text=math_payload["hit_roll_breakdown"])
        await ctx.send(embed=embed)
        
        # Automatically advance turn index pipeline forward
        await self.rotate_turn_queue(ctx, session)

    async def rotate_turn_queue(self, ctx, session: GameSession):
        """Advances initiative pointer slots and updates combat rounds."""
        session.combat_state.active_turn_index += 1
        
        # Check if rotation round cycle completed
        if session.combat_state.active_turn_index >= len(session.combat_state.initiative_order):
            session.combat_state.active_turn_index = 0
            session.combat_state.current_round += 1
            await ctx.send(f"🛡️ **Round {session.combat_state.current_round} has begun!**")

        await session.save()
        
        # Evaluate entity properties of the next active slot
        next_entity = session.combat_state.initiative_order[session.combat_state.active_turn_index]
        
        if next_entity.entity_type == "NPC":
            # Recurse down the execution pipeline automatically
            await self.execute_monster_turn(ctx, session, next_entity.entity_id)
        else:
            await ctx.send(f"🟢 It is now your turn to act, **{next_entity.entity_id}**! Submit your tactical action.")

    @commands.command(name="next_turn")
    async def command_next_turn(self, ctx):
        """Manual command to advance out of a player turn choice slot."""
        # Find active session tracking user
        session = await GameSession.find_one({"party_state.active_characters.user_id": str(ctx.author.id)})
        if not session or not session.combat_state.in_combat:
            return await ctx.send("Your party is not currently locked in initiative combat structures.")
            
        await self.rotate_turn_queue(ctx, session)

async def setup(bot):
    await bot.add_cog(CombatCog(bot))
