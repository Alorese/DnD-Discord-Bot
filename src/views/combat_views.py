import discord
import random
from beanie import PydanticObjectId
from database.models.session import GameSession, SpeakerType, ChatMessage
from database.models.monster import Monster
from database.models.room import Room
from services.template_service import prompt_service

class PlayerCombatAttackView(discord.ui.View):
    def __init__(self, session_id: PydanticObjectId, player_user_id: str, actor_id: str, monster_instance_id: str, attack_name: str, hit_modifier: int, target_ac: int):
        super().__init__(timeout=60)
        self.session_id = session_id
        self.player_user_id = player_user_id
        self.actor_id = actor_id
        self.monster_instance_id = monster_instance_id
        self.attack_name = attack_name
        self.hit_modifier = hit_modifier
        self.target_ac = target_ac

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Enforces turn order security boundaries."""
        if str(interaction.user.id) != self.player_user_id:
            await interaction.response.send_message("❌ It is not your active turn to attack!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Roll Attack Dice", style=discord.ButtonStyle.danger, emoji="⚔️")
    async def roll_attack(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

        # 1. Automated Python Dice Roll
        d20_roll = random.randint(1, 20)
        total_hit = d20_roll + self.hit_modifier
        hit_success = total_hit >= self.target_ac

        session = await GameSession.get(self.session_id)
        actor = session.party_state.active_characters[self.actor_id]
        npc = session.npc_deltas[self.monster_instance_id]

        hit_breakdown = f"Rolled d20: {d20_roll} + Modifier: {self.hit_modifier} = **{total_hit}** vs AC {self.target_ac}"

        if not hit_success:
            # --- MELEE MISS FLOW ---
            math_payload = {
                "attacker_name": actor.name,
                "attack_name": self.attack_name,
                "hit_roll_breakdown": hit_breakdown,
                "hit_success": False,
                "damage_dealt": 0,
                "target_name": self.monster_instance_id.replace("_", " ").title(),
                "target_dead": False
            }
            # Advance loop straight to narrative rendering
            await self.view.stop()
            interaction.client.dispatch("combat_turn_resolve", self.session_id, math_payload, interaction.channel)
        else:
            # --- MELEE HIT SUCCESS FLOW ---
            # Automatically spawn the next damage roll button view for the player
            await interaction.channel.send(
                content=f"🎯 **HIT!** {hit_breakdown}. **{actor.name}**, roll your damage dice next:",
                view=PlayerCombatDamageView(
                    session_id=self.session_id,
                    player_user_id=self.player_user_id,
                    actor_id=self.actor_id,
                    monster_instance_id=self.monster_instance_id,
                    attack_name=self.attack_name,
                    hit_breakdown=hit_breakdown
                )
            )

class PlayerCombatDamageView(discord.ui.View):
    def __init__(self, session_id: PydanticObjectId, player_user_id: str, actor_id: str, monster_instance_id: str, attack_name: str, hit_breakdown: str):
        super().__init__(timeout=60)
        self.session_id = session_id
        self.player_user_id = player_user_id
        self.actor_id = actor_id
        self.monster_instance_id = monster_instance_id
        self.attack_name = attack_name
        self.hit_breakdown = hit_breakdown

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) != self.player_user_id:
            await interaction.response.send_message("❌ It is not your turn to roll damage!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Roll Damage Dice", style=discord.ButtonStyle.success, emoji="💥")
    async def roll_damage(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

        session = await GameSession.get(self.session_id)
        actor = session.party_state.active_characters[self.actor_id]
        npc = session.npc_deltas[self.monster_instance_id]

        # 2. Automated Python Damage Dice parsing (Hardcoded 1d8+3 baseline weapon proxy calculation)
        base_roll = random.randint(1, 8)
        damage_total = base_roll + 3

        # Mutate monster health directly in MongoDB session state delta
        npc.current_hp = max(0, npc.current_hp - damage_total)
        target_dead = npc.current_hp <= 0
        if target_dead:
            npc.attitude = "DEAD"

        await session.save()

        math_payload = {
            "attacker_name": actor.name,
            "attack_name": self.attack_name,
            "hit_roll_breakdown": self.hit_breakdown,
            "hit_success": True,
            "damage_dealt": damage_total,
            "target_name": self.monster_instance_id.replace("_", " ").title(),
            "target_dead": target_dead
        }

        # Dispatch finalized math packet to the NarrativeEngine listener
        interaction.client.dispatch("combat_turn_resolve", self.session_id, math_payload, interaction.channel)