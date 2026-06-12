import discord
import random
from beanie import PydanticObjectId
from typing import List
from database.models.character import CharacterSheet
from database.models.session import GameSession, SessionStatus, PartyState, CombatState, NarrativeMemory, ActiveCharacterState

class ModuleSelectMenu(discord.ui.Select):
    def __init__(self, campaign_slugs: List[str], dm_id: int):
        self.dm_id = dm_id
        options = [
            discord.SelectOption(
                label=slug.replace("_", " ").title(),
                description=f"Initialize lobby with layout blueprint: {slug}",
                value=slug,
                emoji="📖"
            ) for slug in campaign_slugs
        ]
        super().__init__(
            placeholder="Select a campaign module to initialize the lobby...",
            min_values=1, max_values=1, options=options
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)

        selected_campaign_id = self.values

        # 1. Instantiate the live GameSession document inside MongoDB right here
        new_session = GameSession(
            campaign_id=selected_campaign_id,
            session_status=SessionStatus.LOBBY, # Set to LOBBY so players can join
            party_state=PartyState(
                current_region_id=selected_campaign_id,
                current_room_id=f"{selected_campaign_id}_lvl1_room_01", # Target starting room pointer
                party_leader_id=None, # Assigned dynamically when players register
                active_characters={}
            ),
            combat_state=CombatState(in_combat=False),
            narrative_memory=NarrativeMemory(campaign_summary_so_far="Lobby initialized. Waiting for players.")
        )
        
        await new_session.insert()

        self.view.stop()
        await interaction.edit_original_response(content=f"✅ **Lobby Created!** Campaign set to `{selected_campaign_id}`.", view=None)

        # 2. Broadcast public invitation embed out to the channel chat space
        embed = discord.Embed(
            title=f"🏰 Campaign Lobby Opened: {selected_campaign_id.replace('_', ' ').title()}",
            description="The Dungeon Master has established an active game server workspace!\n\n"
                        "👉 **Step 1: Players Join**\nEveryone playing tonight must type the command:\n`/join_session`\n\n"
                        "🏁 **Step 2: DM Begins Game**\nOnce all heroes have selected their sheets, the DM can kick off the story by typing:\n`/begin_campaign`",
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Database Session ID: {new_session.id}")
        await interaction.channel.send(embed=embed)

class CharacterJoinView(discord.ui.View):
    def __init__(self, characters: List[CharacterSheet], session_id: PydanticObjectId, voter_id: int):
        super().__init__(timeout=60)
        self.voter_id = voter_id
        # Append the dropdown select component list to the active view pane
        self.add_item(CharacterSelectMenu(characters, session_id))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Enforces execution checks so only the calling command user can select their sheet choice."""
        if interaction.user.id != self.voter_id:
            await interaction.response.send_message("❌ Run `/join_session` on your own profile to pick your adventurer choice!", ephemeral=True)
            return False
        return True

class ModuleStartView(discord.ui.View):
    def __init__(self, campaign_slugs: List[str], dm_id: int):
        super().__init__(timeout=60)
        self.add_item(ModuleSelectMenu(campaign_slugs, dm_id))