from datetime import datetime
from typing import List, Optional, Dict
from beanie import Document, Indexed, PydanticObjectId
from pydantic import BaseModel, Field
from .enums import SessionStatus, SpeakerType, ConditionType, EffectDuration

class ActiveModifier(BaseModel):
    name: str
    source: str
    target_stat: str
    value_formula: str
    duration_type: EffectDuration
    rounds_remaining: Optional[int] = None

class ActiveCharacterState(BaseModel):
    character_id: PydanticObjectId
    user_id: str
    name: str
    class_and_level: str
    current_hp: int
    temporary_hp: int = 0
    armor_class: int
    speed_ft: int
    initiative_modifier: int
    passive_perception: int
    proficiency_bonus: int
    saving_throw_modifiers: Dict[str, int]
    skill_modifiers: Dict[str, int]
    has_regular_inspiration: bool = False
    has_heroic_inspiration: bool = False
    reaction_used_this_round: bool = False
    active_conditions: List[ConditionType] = Field(default_factory=list)
    active_buffs_and_debuffs: List[ActiveModifier] = Field(default_factory=list)

class PartyState(BaseModel):
    current_region_id: str
    current_room_id: str
    party_leader_id: PydanticObjectId
    active_characters: Dict[str, ActiveCharacterState] = Field(default_factory=dict)

class InitiativeTurn(BaseModel):
    entity_id: str
    entity_type: str
    roll_total: int

class CombatState(BaseModel):
    in_combat: bool = False
    current_round: int = 0
    active_turn_index: int = 0
    initiative_order: List[InitiativeTurn] = Field(default_factory=list)

class RoomDelta(BaseModel):
    explored: bool = False
    cleared: bool = False
    looted: bool = False
    traps_triggered: List[str] = Field(default_factory=list)
    interactive_object_states: Dict[str, str] = Field(default_factory=dict)
    custom_notes: Optional[str] = None

class NpcDelta(BaseModel):
    current_hp: int
    max_hp: int
    status_conditions: List[ConditionType] = Field(default_factory=list)
    attitude: str
    location_override: Optional[str] = None

class ChatMessage(BaseModel):
    speaker: SpeakerType
    sender_name: Optional[str] = None
    text: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class NarrativeMemory(BaseModel):
    summary_token_count: int = 0
    campaign_summary_so_far: str = "The campaign has just begun."
    recent_chat_history: List[ChatMessage] = Field(default_factory=list)

class GameSession(Document):
    campaign_id: str
    session_status: SessionStatus = SessionStatus.ACTIVE
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    party_state: PartyState
    combat_state: CombatState
    room_deltas: Dict[str, RoomDelta] = Field(default_factory=dict)
    npc_deltas: Dict[str, NpcDelta] = Field(default_factory=dict)
    plot_flags: Dict[str, bool] = Field(default_factory=dict)
    narrative_memory: NarrativeMemory

    class Settings:
        name = "sessions"
