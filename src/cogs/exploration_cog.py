import discord
from discord.ext import commands
from beanie import PydanticObjectId
from database.models.session import GameSession, SpeakerType, ChatMessage
from database.models.room import Room
from .views import ExplorationNavigationView

class ExplorationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="map")
    async def display_navigation_controls(self, ctx):
        """Queries the current room and instantiates active compass navigation buttons."""
        session = await GameSession.find_one({"party_state.active_characters.user_id": str(ctx.author.id)})
        if not session:
            return await ctx.send("❌ Active game session not found.")
        
        if session.combat_state.in_combat:
            return await ctx.send("❌ Navigation map commands are disabled while locked in combat initiative structure.")

        # Pull immutable room blueprint from MongoDB
        room = await Room.find_one(Room.room_id == session.party_state.current_room_id)
        
        # Flatten exit dictionary back to basic string IDs for the button view layout
        exit_map = {
            "north": room.navigation.exits["north"].target_room_id if "north" in room.navigation.exits else "none",
            "south": room.navigation.exits["south"].target_room_id if "south" in room.navigation.exits else "none",
            "east": room.navigation.exits["east"].target_room_id if "east" in room.navigation.exits else "none",
            "west": room.navigation.exits["west"].target_room_id if "west" in room.navigation.exits else "none",
        }

        # Query who possesses the designated Lead Token rights
        leader_id = str(session.party_state.party_leader_id)

        view = ExplorationNavigationView(
            session_id=session.id, 
            leader_user_id=leader_id, 
            available_exits=exit_map
        )
        
        await ctx.send(
            content=f"🗺️ **Current Location: {room.title}**\nUse the direction buttons below to guide the party:",
            view=view
        )

    @commands.Cog.listener()
    async def on_party_move_execute(self, session_id: PydanticObjectId, target_room_id: str, channel: discord.TextChannel):
        """Triggered when the view confirms a valid movement transition action."""
        session = await GameSession.get(session_id)
        
        # 1. Mutate the active party location tracking string in the database
        session.party_state.current_room_id = target_room_id
        
        # Setup initial room delta flag if visiting for the first time
        if target_room_id not in session.room_deltas:
            session.room_deltas[target_room_id] = {"explored": True, "cleared": False, "looted": False}
        else:
            session.room_deltas[target_room_id].explored = True

        await session.save()

        # 2. Query the new destination properties from MongoDB
        new_room = await Room.find_one(Room.room_id == target_room_id)
        
        # 3. Compile structural notification payload package straight to Narrative layer
        # This bypasses the Rules Intent parser because a directional button click has hard-coded mechanics
        payload = {
            "character_id": str(session.party_state.party_leader_id),
            "check_type": "ROOM_TRANSITION",
            "dc_target": 0,
            "final_score": 0,
            "math_breakdown": f"Party transitioned spaces to {new_room.title}",
            "outcome": "SUCCESS",
            "raw_statement": f"We walk into the room."
        }

        # Fire event hook to let NarrativeEngineCog compile prose and stream back descriptions
        self.bot.dispatch("rules_roll_complete", session_id, payload)

async def setup(bot):
    await bot.add_cog(ExplorationCog(bot))
