import discord
import random
from beanie import PydanticObjectId
from typing import List
from database.models.character import CharacterSheet
from database.models.session import GameSession, SessionStatus, PartyState, CombatState, NarrativeMemory, ActiveCharacterState

class ExplorationNavigationView(discord.ui.View):
    def __init__(self, session_id: PydanticObjectId, leader_user_id: str, available_exits: dict):
        super().__init__(timeout=180)
        self.session_id = session_id
        self.leader_user_id = leader_user_id
        self.available_exits = available_exits

        # Dynamically disable button pointers if no valid room connection exists
        if available_exits.get("north", "none") == "none": self.go_north.disabled = True
        if available_exits.get("south", "none") == "none": self.go_south.disabled = True
        if available_exits.get("east", "none") == "none": self.go_east.disabled = True
        if available_exits.get("west", "none") == "none": self.go_west.disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Enforces Lead Token rules: Only the party leader can advance the map."""
        if str(interaction.user.id) != self.leader_user_id:
            await interaction.response.send_message("❌ Only the appointed Party Leader can navigate the map layout.", ephemeral=True)
            return False
        return True

    async def execute_move(self, interaction: discord.Interaction, direction: str):
        """Processes room transition state updates natively in Python code."""
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

        target_room_id = self.available_exits[direction]
        
        # Dispatch move event over to the ExplorationCog namespace loop
        interaction.client.dispatch("party_move_execute", self.session_id, target_room_id, interaction.channel)

    @discord.ui.button(label="North", style=discord.ButtonStyle.primary, emoji="⬆️", row=0)
    async def go_north(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.execute_move(interaction, "north")

    @discord.ui.button(label="West", style=discord.ButtonStyle.primary, emoji="⬅️", row=1)
    async def go_west(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.execute_move(interaction, "west")

    @discord.ui.button(label="South", style=discord.ButtonStyle.primary, emoji="⬇️", row=1)
    async def go_south(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.execute_move(interaction, "south")

    @discord.ui.button(label="East", style=discord.ButtonStyle.primary, emoji="➡️", row=1)
    async def go_east(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.execute_move(interaction, "east")

class InitialDiceRollView(discord.ui.View):
    def __init__(self, session_id: PydanticObjectId, character_id: str, stat_name: str, target_dc: int, modifier: int, can_use_inspiration: bool):
        super().__init__(timeout=120)
        self.session_id = session_id
        self.character_id = character_id
        self.stat_name = stat_name
        self.target_dc = target_dc
        self.modifier = modifier
        
        # If the player doesn't have regular inspiration, gray out the advantage button instantly
        if not can_use_inspiration:
            self.inspiration_advantage_roll.disabled = True
            self.inspiration_advantage_roll.style = discord.ButtonStyle.secondary

    async def process_initial_roll(self, interaction: discord.Interaction, mode: str):
        """Processes the primary d20 roll mechanics securely in Python."""
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

        roll1 = random.randint(1, 20)
        roll2 = random.randint(1, 20)

        if mode == "INSPIRATION_ADVANTAGE":
            # 1. Consume the resource in MongoDB via Beanie
            session = await GameSession.find_one({"_id": self.session_id})
            actor = session.party_state.active_characters[self.character_id]
            actor.has_regular_inspiration = False
            await session.save()

            final_d20 = max(roll1, roll2)
            math_desc = f"Rolled with Inspiration (Advantage): [d20: {roll1}, {roll2}] -> took **{final_d20}**"
        else:
            final_d20 = roll1
            math_desc = f"Rolled normal d20: **{final_d20}**"

        # Pass the verified numeric result to your two-stage evaluator function
        # This function determines whether to display the reactive Heroic Inspiration view or finalize
        from .utils import handle_initial_roll_result
        await handle_initial_roll_result(
            ctx=interaction.channel,
            session_id=self.session_id,
            character_id=self.character_id,
            stat_name=self.stat_name,
            target_dc=self.target_dc,
            modifier=self.modifier,
            rolled_d20=final_d20,
            math_desc=math_desc,
            client=interaction.client
        )

    # --- Button Layout Configuration ---
    
    @discord.ui.button(label="Normal Roll", style=discord.ButtonStyle.primary, emoji="🎲", row=0)
    async def normal_roll(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_initial_roll(interaction, "NORMAL")

    @discord.ui.button(label="Spend Inspiration (Advantage)", style=discord.ButtonStyle.success, emoji="✨", row=0)
    async def inspiration_advantage_roll(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_initial_roll(interaction, "INSPIRATION_ADVANTAGE")