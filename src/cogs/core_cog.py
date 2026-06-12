import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from google import genai
from google.genai import types

# Import core schema documents and utilities
from services.template_service import prompt_service
from database.models.session import GameSession, PartyState, CombatState, NarrativeMemory, SessionStatus
from database.models.character import CharacterSheet
from database.models.room import Room

import discord
from discord.ext import commands
from discord import app_commands
from google import genai
from google.genai import types

from services.template_service import prompt_service
from database.models.session import GameSession, SessionStatus, SpeakerType, ChatMessage
from database.models.room import Room
from views.session_setup_views import ModuleStartView, ModuleSelectMenu, CharacterJoinView

class CoreCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ai_client = genai.Client()

    @app_commands.command(name="start_session", description="DM Only: Select a campaign module blueprint and open the player registration lobby.")
    async def start_session(self, interaction: discord.Interaction):
        """Queries unique campaign blueprints from MongoDB and prompts selection dropdown."""
        # Enforce safety check: prevent establishing multiple simultaneous running lobbies
        print(f"Checking for existing lobbies...")
        existing_lobby = await GameSession.find_one(GameSession.session_status == SessionStatus.LOBBY)
        if existing_lobby:
            return await interaction.response.send_message(
                f"❌ An open registration lobby already exists for campaign: `{existing_lobby.campaign_id}`. "
                f"Please close or launch that session before creating a new one.", habits=True, ephemeral=True
            )

        # Gather an array of all distinct campaign tags inside your rooms collection blueprint library
        room_collection = Room.get_motor_collection()
        distinct_campaigns = await room_collection.distinct("module_id")

        print(f"Checking for existing modules")
        if not distinct_campaigns:
            return await interaction.response.send_message(
                "❌ **No Ingested Modules Detected!** Your blueprint library collection is completely empty. "
                "Please run `/import_module` first.", ephemeral=True
            )

        # Create and display the dropdown menu
        print(f"Creating module select view")
        view = ModuleStartView(campaign_slugs=distinct_campaigns, dm_id=interaction.user.id)
        await interaction.response.send_message(
            content="📋 **Dungeon Master Module Selector**\nChoose which campaign configuration profile to load:",
            view=view, ephemeral=True
        )

    @app_commands.command(name="join_session", description="Browse and choose an imported character profile to join the open campaign lobby.")
    async def join_session(self, interaction: discord.Interaction):
        """Queries user sheets from MongoDB and displays the selection dropdown view."""
        # 1. Locate if there is an active running campaign registration lobby open in this guild server zone
        # (Assuming your GameSession models are active or you filter by ACTIVE status fields)
        session = await GameSession.find_one(GameSession.session_status == SessionStatus.ACTIVE)
        if not session:
            return await interaction.response.send_message("❌ No active, open campaign session lobbies found running on this server space.", ephemeral=True)

        # 2. Query all master sheets tied explicitly to this specific caller's discord user id string
        player_sheets = await CharacterSheet.find(CharacterSheet.user_id == str(interaction.user.id)).to_list()
        
        if not player_sheets:
            return await interaction.response.send_message(
                "❌ **No Character Profiles Detected!** You don't have any imported characters bound to your ID.\n"
                "Please run `/import_character <url>` first to link an adventurer to your account.", ephemeral=True
            )

        # 3. Instantiate and deploy our drop-down component view select layouts
        view = CharacterJoinView(characters=player_sheets, session_id=session.id, voter_id=interaction.user.id)
        
        await interaction.response.send_message(
            content="📋 **Character Registration Selector**\nChoose which sheet you want to load into this campaign session:",
            view=view,
            ephemeral=True # Kept hidden so other server players don't see your personal sheets choice popup dropdown menus
        )

    @app_commands.command(name="begin_campaign", description="DM Only: Closes the lobby and triggers the cinematic opening narrative.")
    async def begin_campaign(self, interaction: discord.Interaction):
        """Locks the active lobby, reads the first room, and invokes Gemini 3.1 Flash Lite."""
        # Locate the unlaunched session lobby document
        session = await GameSession.find_one(GameSession.session_status == SessionStatus.LOBBY)
        if not session:
            return await interaction.response.send_message("❌ There are no open registration lobbies awaiting commencement. Run `/start_session` first.", ephemeral=True)

        if not session.party_state.active_characters:
            return await interaction.response.send_message("❌ Cannot begin: No player characters have joined the party array yet! Run `/join_session`.", ephemeral=True)

        await interaction.response.defer(ephemeral=False)

        # 1. Pull the absolute first room blueprint from MongoDB
        starting_room_id = session.party_state.current_room_id
        starting_room = await Room.find_one(Room.room_id == starting_room_id)

        # 2. Advance the Session lifecycle status handle from LOBBY to ACTIVE
        session.session_status = SessionStatus.ACTIVE
        session.narrative_memory.campaign_summary_so_far = f"The campaign officially began in {starting_room.title}."

        # Grab the character object of the appointed party leader guide
        leader_actor = session.party_state.active_characters[str(session.party_state.party_leader_id)]

        # --- STEP 3: Compile Context and Call Gemini 3.1 Flash Lite ---
        prompt = prompt_service.render_prompt(
            "campaign_welcome.jinja",
            campaign_title=session.campaign_id.replace("_", " ").title(),
            room=starting_room,
            session=session,
            leader_name=leader_actor.name
        )

        async with interaction.channel.typing():
            response = self.ai_client.models.generate_content(
                model="gemini-3.1-flash-lite",
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.85, # Rich cinematic variance
                    thinking_level="low"
                )
            )
            story_intro = response.text

        # 4. Commit results to database history arrays
        session.narrative_memory.recent_chat_history.append(
            ChatMessage(speaker=SpeakerType.NARRATOR, text=story_intro)
        )
        await session.save()

        # 5. Broadcast the epic opening cinematic narrative to the player channel
        embed = discord.Embed(
            title=f"⚔️ Campaign Commenced: {session.campaign_id.replace('_', ' ').title()}",
            description=story_intro,
            color=discord.Color.dark_red()
        )
        embed.add_field(name="📍 Current Location", value=f"**{starting_room.title}**", inline=True)
        embed.add_field(name="👑 Party Vanguard", value=f"**{leader_actor.name}**", inline=True)
        embed.set_footer(text=f"Session Active | ID: {session.id}")
        
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="promote_leader", description="Transfers the out-of-combat navigation Lead Token to another player.")
    @app_commands.describe(member="The Discord user you want to appoint as the new party guide")
    async def promote_leader(self, interaction: discord.Interaction, member: discord.Member):
        """Mutates the party_leader_id state block to support navigation handover actions."""
        session = await GameSession.find_one({"party_state.active_characters.user_id": str(interaction.user.id)})
        if not session:
            return await interaction.response.send_message("❌ You are not currently inside an active campaign session context.", ephemeral=True)

        # Locate the specific character sheet corresponding to the target player
        target_char_id = next((c_id for c_id, c in session.party_state.active_characters.items() if c.user_id == str(member.id)), None)
        if not target_char_id:
            return await interaction.response.send_message("❌ That user does not have an active character bound to this session's party array.", ephemeral=True)

        # Apply database state transformation update
        session.party_state.party_leader_id = target_char_id
        await session.save()

        await interaction.response.send_message(
            f"👑 **Vanguard Lead Token Transferred!**\n**{session.party_state.active_characters[target_char_id].name}** ({member.mention}) is now directing party navigation inputs on the map."
        )

async def setup(bot):
    await bot.add_cog(CoreCog(bot))
