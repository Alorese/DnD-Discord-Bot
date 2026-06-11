import discord
from beanie import PydanticObjectId
from database.models.session import GameSession
from .views import HeroicInspirationDecisionView  # Imports your post-roll reroll button layout

async def handle_initial_roll_result(ctx, session_id: PydanticObjectId, character_id: str, stat_name: str, target_dc: int, modifier: int, rolled_d20: int, math_desc: str, client: discord.Client):
    """
    Evaluates numeric outcomes. Intercepts failures to spawn the reactive 
    Heroic Inspiration view, or routes success data straight to the Narrator.
    """
    total = rolled_d20 + modifier
    success = total >= target_dc
    
    # Fetch live session metadata state
    session = await GameSession.get(session_id)
    actor = session.party_state.active_characters[character_id]

    # --- REACTIVE INTERCEPTION: Check 2024 Heroic Inspiration ---
    if not success and actor.has_heroic_inspiration:
        # Halt normal flow! Spawn decision prompt to let player decide to burn resource
        view = HeroicInspirationDecisionView(
            session_id=session_id,
            character_id=character_id,
            stat_name=stat_name,
            target_dc=target_dc,
            modifier=modifier,
            original_d20=rolled_d20
        )
        
        return await ctx.send(
            content=f"📉 **Roll Failure!** Total was a **{total} vs DC {target_dc}**.\n"
                    f"**{actor.name}**, would you like to spend your **Heroic Inspiration** to discard that roll and completely reroll?",
            view=view
        )

    # --- NORMAL RESOLUTION FLOW ---
    outcome = "SUCCESS" if success else "FAILURE"
    
    # 2024 Rule Rulebook Integration: Rolling a natural 20 awards a free Regular Inspiration charge
    awarded_inspiration_note = ""
    if rolled_d20 == 20:
        actor.has_regular_inspiration = True
        await session.save()
        awarded_inspiration_note = "\n✨ *Natural 20! Regular Inspiration has been awarded to your character!*"

    # Construct the definitive validation block payload
    payload = {
        "character_id": character_id,
        "check_type": stat_name.upper(),
        "dc_target": target_dc,
        "final_score": total,
        "math_breakdown": f"{math_desc} + Modifier: {modifier}",
        "outcome": outcome
    }

    # Dispatch data package directly to the NarrativeEngine listener
    client.dispatch("rules_roll_complete", session_id, payload)
    
    if awarded_inspiration_note:
        await ctx.send(content=awarded_inspiration_note)
