import random
import discord
from discord.ext import commands
from database.models import GameSession, CharacterSheet, ReadiedAction
from services.gemini_client import gemini_service
from beanie.operators import In

# ==============================================================================
# MASTER ENCOUNTER ROLL VIEW (Handles Group Checks, Saves, and Readied Reactions)
# ==============================================================================
class EncounterRollView(discord.ui.View):
    def __init__(self, channel_id: str, character_roster: list, mode: str, check_type: str, target_dc: int, readied_triggers: list = None):
        super().__init__(timeout=180)
        self.channel_id = channel_id
        self.mode = mode               # "INITIATIVE", "GROUP_CHECK", "SAVING_THROW", "TRIGGERED_REACTION"
        self.check_type = check_type
        self.target_dc = target_dc
        self.readied_triggers = readied_triggers or []
        
        # In-memory evaluation tracking map
        self.rolls_tracker = {}
        
        # A. Populate standard teamwide roster members
        for char in character_roster:
            p_id = str(char.player_id)
            self.rolls_tracker[p_id] = {
                "db_id": char.id,
                "name": char.character_name,
                "roll_total": None,
                "math_breakdown": "",
                "has_2024_heroic": char.vitals.has_heroic_inspiration,
                "modifier": char.base_skills.get(check_type, 0) if mode != "INITIATIVE" else char.vitals.initiative_bonus,
                "is_reaction": False,
                "action_text": f"Performs {check_type} Check"
            }

        # B. 💎 Overwrite/Inject Readied Actions into the active verification loop
        for trigger in self.readied_triggers:
            p_id = str(trigger.player_id)
            if p_id in self.rolls_tracker:
                self.rolls_tracker[p_id]["is_reaction"] = True
                self.rolls_tracker[p_id]["action_text"] = f"⚡ REACTION TRIGGERED: {trigger.held_action}"

    def _generate_status_embed(self) -> discord.Embed:
        embed = discord.Embed(title=f"🎲 ENCOUNTER EVENT: {self.mode}", color=discord.Color.dark_purple())
        text = ""
        for p_id, d in self.rolls_tracker.items():
            if d["roll_total"] is not None:
                text += f"✅ **{d['name']}**: `{d['roll_total']}` ({d['math_breakdown']})\n"
            elif d["is_reaction"]:
                text += f"⚡ **{d['name']}**: *Readied Trigger Activated!* -> `{d['action_text']}`\n"
            else:
                text += f"⏳ **{d['name']}**: *Awaiting Roll...*\n"
        embed.add_field(name="Active Resolution Queue", value=text, inline=False)
        return embed

    async def _process_roll(self, interaction: discord.Interaction, use_heroic: bool):
        user_id = str(interaction.user.id)
        data = self.rolls_tracker[user_id]
        
        d20 = random.randint(1, 20)
        total = d20 + data["modifier"]
        
        # 2024 Rule compliance hook
        if use_heroic:
            character = await CharacterSheet.find_one(CharacterSheet.id == data["db_id"])
            character.vitals.has_heroic_inspiration = False
            await character.save()
            data["has_heroic_inspiration"] = False
            breakdown = f"Heroic Reroll: {d20} + {data['modifier']}"
        else:
            breakdown = f"Rolled {d20} + {data['modifier']}"

        data["roll_total"] = total
        success_tag = "Success" if total >= self.target_dc else "Failure"
        data["math_breakdown"] = f"{success_tag} | {breakdown}"

        # Check if entire block is cleared
        all_done = all(d["roll_total"] is not None for d in self.rolls_tracker.values())
        if all_done:
            for child in self.children: child.disabled = True
            await interaction.message.edit(embed=self._generate_status_embed(), view=self)
            await self._dispatch_to_narrator(interaction)
        else:
            await interaction.message.edit(embed=self._generate_status_embed(), view=self)

    @discord.ui.button(label="🎲 ROLL", style=discord.ButtonStyle.primary, custom_id="enc_roll_btn")
    async def standard_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)
        if user_id not in self.rolls_tracker or self.rolls_tracker[user_id]["roll_total"] is not None: return
        await interaction.response.defer()
        await self._process_roll(interaction, use_heroic=False)

    async def _dispatch_to_narrator(self, interaction: discord.Interaction):
        """Compiles prompt templates and flushes readied triggers out of MongoDB post-resolution."""
        session = await GameSession.find_one(GameSession.channel_id == self.channel_id, fetch_links=True)
        
        # Build text description of what occurred
        summary = f"Encounter Context: {self.mode} ({self.check_type} DC {self.target_dc})\n"
        for d in self.rolls_tracker.values():
            summary += f"- {d['name']} {d['action_text']}: Total Result {d['roll_total']} ({d['math_breakdown']})\n"

        # 💎 Clear out spent readied actions from the database session model
        session.readied_actions = []
        await session.save()

        # Fire to Gemini long-context narrator
        client = gemini_service.get_client()
        module_file_handle = client.files.get(name=session.active_module.gemini_file_uri.split('/')[-1])
        
        prompt = f"An environmental encounter event occurred.\n{summary}\nNarrate the cinematic result."
        response = client.models.generate_content(model=gemini_service.model_name, contents=[module_file_handle, prompt])
        await interaction.followup.send(response.text)
        self.stop()


# ==============================================================================
# ENCOUNTER COG LOGIC ENTRY
# ==============================================================================
class EncounterCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="ready")
    async def ready_action_cmd(self, ctx: commands.Context, trigger: str, action: str):
        """Allows a player to store a readied trigger: !ready "if the door opens" "I shoot my bow" """
        channel_id = str(ctx.channel.id)
        player_id = str(ctx.author.id)
        
        session = await GameSession.find_one(GameSession.channel_id == channel_id)
        char = await CharacterSheet.find_one(CharacterSheet.channel_id == channel_id, CharacterSheet.player_id == player_id)
        
        if not session or not char: return

        # Append new readied trigger sub-model document natively to MongoDB
        new_trigger = ReadiedAction(
            player_id=player_id,
            character_name=char.character_name,
            trigger_condition=trigger.strip(),
            held_action=action.strip()
        )
        session.readied_actions.append(new_trigger)
        await session.save()
        
        await ctx.reply(f"🎯 **Action Readied:** {char.character_name} is holding an action: *\"{action}\"* triggered *\"{trigger}\"*.")

    @commands.command(name="event_trigger", aliases=["trigger", "ev"])
    async def trigger_event_cmd(self, ctx: commands.Context, event_description: str, check_type: str = "Perception", dc: int = 12):
        """DM command to fire an environment event, capturing all readied triggers: !ev \"The door bursts open!\" Attack 14"""
        if not ctx.author.guild_permissions.administrator: return
        channel_id = str(ctx.channel.id)
        
        session = await GameSession.find_one(GameSession.channel_id == channel_id, fetch_links=True)
        
        # 1. Pull the readied actions list. If empty, fallback to a standard teamwide group check
        active_triggers = session.readied_actions
        
        if active_triggers:
            # Gather only the specific players who had reactions readied for this encounter board
            trigger_player_ids = [t.player_id for t in active_triggers]
            roster = await CharacterSheet.find(
                CharacterSheet.channel_id == channel_id, 
                In(CharacterSheet.player_id, trigger_player_ids)
            ).to_list()
            mode = "TRIGGERED_REACTION"
        else:
            # Standard teamwide group check if no reactions are currently held in memory
            roster = await CharacterSheet.find(CharacterSheet.channel_id == channel_id).to_list()
            mode = "GROUP_CHECK"

        view = EncounterRollView(channel_id, roster, mode, check_type, dc, active_triggers)
        embed = view._generate_status_embed()
        embed.description = f"**DM Event:** \"{event_description}\"\n\n" + embed.description
        await ctx.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(EncounterCog(bot))
