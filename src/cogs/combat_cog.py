import discord
from discord.ext import commands
from discord import app_commands
from google import genai
from google.genai import types
import random
from database.models.session import GameSession, CombatState, InitiativeTurn, SpeakerType, ChatMessage
from database.models.room import Room
from database.models.monster import Monster
from services.template_service import prompt_service
from views.combat_views import PlayerCombatAttackView

class CombatCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ai_client = genai.Client()

    @app_commands.command(name="initiate_combat", description="DM Only: Freezes normal exploration and rolls initiative order values.")
    async def initiate_combat(self, ctx):
        """Builds combat sequence loops out of active room blueprint contents."""
        session = await GameSession.find_one({"party_state.active_characters.user_id": str(ctx.user.id)})
        if not session or session.combat_state.in_combat:
            return await ctx.response.send_message("❌ Combat is either already running or session lobby is unavailable.", ephemeral=True)

        await ctx.response.defer()
        room = await Room.find_one(Room.room_id == session.party_state.current_room_id)

        initiative_list = []

        # 1. Roll automated true random initiative for players
        for char_id, actor in session.party_state.active_characters.items():
            roll = random.randint(1, 20) + actor.initiative_modifier
            initiative_list.append(InitiativeTurn(entity_id=char_id, entity_type="PLAYER", roll_total=roll))

        # 2. Spawn monster instance references and roll NPC initiative values
        for idx, m_template in enumerate(room.encounters.monsters):
            monster_blueprint = await Monster.find_one(Monster.monster_id == m_template.monster_id)
            
            for qty in range(1, m_template.quantity + 1):
                instance_slug = f"{m_template.monster_id}_{qty}"
                
                # Setup live instance health tracking array mapping records
                from models.session import NpcDelta
                session.npc_deltas[instance_slug] = NpcDelta(
                    current_hp=monster_blueprint.defenses.hit_points.average,
                    max_hp=monster_blueprint.defenses.hit_points.average,
                    attitude="HOSTILE"
                )
                
                roll = random.randint(1, 20) + monster_blueprint.mobility_and_senses.passive_perception # Initiative proxy modifier
                initiative_list.append(InitiativeTurn(entity_id=instance_slug, entity_type="NPC", roll_total=roll))

        # Sort the turn array descending based on total roll scores
        initiative_list.sort(key=lambda x: x.roll_total, reverse=True)

        # Commit initial structural combat settings to MongoDB via Beanie
        session.combat_state = CombatState(
            in_combat=True,
            current_round=1,
            active_turn_index=0,
            initiative_order=initiative_list
        )
        await session.save()

        # Build clean visual output board layout representation
        order_board = "\n".join([f"**{idx+1}.** {turn.entity_id.replace('_',' ').title()} *(Roll: {turn.roll_total})*" for idx, turn in enumerate(initiative_list)])
        
        embed = discord.Embed(title="⚔️ Initiative Combat Roll Commenced!", description=f"The environment tightens as weapons are drawn!\n\n{order_board}", color=discord.Color.red())
        await ctx.followup.send(embed=embed)

        # Trigger initial turn allocation sequence
        await self.process_active_combat_turn(ctx.channel, session)

    async def process_active_combat_turn(self, channel, session: GameSession):
        """Orchestrates turn handovers based on active queue properties."""
        active_turn = session.combat_state.initiative_order[session.combat_state.active_turn_index]

        # --- BRANCH A: AUTOMATED NPC ENEMY AI MONSTER BRAIN TURN ---
        if active_turn.entity_type == "NPC":
            npc_delta = session.npc_deltas.get(active_turn.entity_id)
            if npc_delta.attitude == "DEAD":
                return await self.advance_combat_queue(channel, session) # Automatically skip dead monsters

            await channel.send(f"🤖 *{active_turn.entity_id.replace('_',' ').title()} compiles hostile tactical actions...*")
            # (Runs automated rules model calculation script we built earlier inside step 2)
            # For simplicity in testing, we assume monster executes a standard attack roll via code tools...
            await self.execute_automated_npc_turn(channel, session, active_turn.entity_id)

        # --- BRANCH B: PLAYER CHARACTER STRIPPED BUTTON ACTION PROMPT ---
        else:
            actor = session.party_state.active_characters[active_turn.entity_id]
            # Hardcoded target monster example selector lookup for template testing
            first_live_npc = next((k for k, v in session.npc_deltas.items() if v.attitude != "DEAD"), None)
            
            if not first_live_npc:
                # Combat victory condition caught!
                session.combat_state.in_combat = False
                await session.save()
                return await channel.send("🎉 **Victory! All hostiles inside the location have been completely neutralized!**")

            # Initialize your simple button roll view passing calculated database parameters
            view = PlayerCombatAttackView(
                session_id=session.id,
                player_user_id=actor.user_id,
                actor_id=active_turn.entity_id,
                monster_instance_id=first_live_npc,
                attack_name="Longsword strike",
                hit_modifier=4, # Hardcoded baseline attribute proxy modifier adjustment
                target_ac=15 # Monster Armor Class reference
            )

            await channel.send(
                content=f"🟢 <@{actor.user_id}>, it is your turn! **{actor.name}** targets **{first_live_npc.replace('_',' ').title()}**.\n"
                        f"Click the interactive button below to resolve your attack options:",
                view=view
            )

    @commands.Cog.listener()
    async def on_combat_turn_resolve(self, session_id, math_payload: dict, channel: discord.TextChannel):
        """Listener hook that picks up finalized math results and streams storytelling entries."""
        session = await GameSession.get(session_id)
        room = await Room.find_one(Room.room_id == session.party_state.current_room_id)

        # Render Jinja2 template file layout
        prompt = prompt_service.render_prompt("narrator_attack_block.jinja", room=room, payload=math_payload)

        async with channel.typing():
            response = self.ai_client.models.generate_content(
                model="gemini-3.1-flash-lite", contents=prompt,
                config=types.GenerateContentConfig(temperature=0.8)
            )
            story_output = response.text

        # Record updates to history ledger arrays
        session.narrative_memory.recent_chat_history.append(ChatMessage(speaker=SpeakerType.NARRATOR, text=story_output))
        await session.save()

        embed = discord.Embed(title="💥 Combat Action Sequence Resolves", description=story_output, color=discord.Color.dark_orange())
        embed.set_footer(text=math_payload["hit_roll_breakdown"])
        await channel.send(embed=embed)

        # Progress the active pointer to the next entity slot
        await self.advance_combat_queue(channel, session)

    async def advance_combat_queue(self, channel, session: GameSession):
        session.combat_state.active_turn_index += 1
        if session.combat_state.active_turn_index >= len(session.combat_state.initiative_order):
            session.combat_state.active_turn_index = 0
            session.combat_state.current_round += 1
            await channel.send(f"🛡️ **Combat Round {session.combat_state.current_round} begins!**")

        await session.save()
        await self.process_active_combat_turn(channel, session)

    async def execute_automated_npc_turn(self, channel, session: GameSession, npc_instance_id: str):
        """Executes a 100% automated monster calculation turn loop in pure Python."""
        # Simple random targeting logic for testing
        random_player_key = random.choice(list(session.party_state.active_characters.keys()))
        player = session.party_state.active_characters[random_player_key]

        d20_roll = random.randint(1, 20)
        total_hit = d20_roll + 3 # Baseline monster hit modifier proxy
        hit_success = total_hit >= player.armor_class

        damage = 0
        if hit_success:
            damage = random.randint(1, 6) + 1
            player.current_hp = max(0, player.current_hp - damage)

        await session.save()

        math_payload = {
            "attacker_name": npc_instance_id.replace("_", " ").title(),
            "attack_name": "Claw swipe",
            "hit_roll_breakdown": f"NPC rolled {d20_roll} + 3 = **{total_hit}** vs Player AC {player.armor_class}",
            "hit_success": hit_success,
            "damage_dealt": damage,
            "target_name": player.name,
            "target_dead": player.current_hp <= 0
        }

        self.bot.dispatch("combat_turn_resolve", session.id, math_payload, channel)

async def setup(bot):
    await bot.add_cog(CombatCog(bot))