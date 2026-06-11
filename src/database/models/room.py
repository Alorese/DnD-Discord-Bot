from typing import List, Optional, Dict
from beanie import Document, Indexed
from pydantic import BaseModel, Field
from .enums import ExitType, LightingLevel

class RoomExit(BaseModel):
    target_room_id: str
    exit_type: ExitType = Field(alias="type")
    locked: bool = False
    lock_dc: Optional[int] = None
    perception_dc: Optional[int] = None

class Navigation(BaseModel):
    map_layer: str
    coordinates: Dict[str, int]
    exits: Dict[str, RoomExit]

class Hazard(BaseModel):
    hazard_type: str = Field(alias="type")
    name: str
    investigation_dc: int
    trigger_action: str
    effect_payload: Dict

class InteractiveObject(BaseModel):
    object_id: str
    description: str
    state: str
    lock_dc: Optional[int] = None
    loot_table_reference: Optional[str] = None

class Environment(BaseModel):
    dimensions: str
    lighting: LightingLevel
    hazards: List[Hazard] = Field(default_factory=list)
    interactive_objects: List[InteractiveObject] = Field(default_factory=list)

class MonsterSpawnTemplate(BaseModel):
    monster_id: str
    quantity: int
    is_minion: bool = False
    spawn_notes: Optional[str] = None

class Encounters(BaseModel):
    combat_trigger_type: str
    monsters: List[MonsterSpawnTemplate] = Field(default_factory=list)

class ConditionalEvent(BaseModel):
    trigger_condition: str
    fires_plot_flag_toggle: str
    xp_reward: int

class StoryAndTriggers(BaseModel):
    required_plot_flags: List[str] = Field(default_factory=list)
    conditional_events: List[ConditionalEvent] = Field(default_factory=list)

class RoomLLMContexts(BaseModel):
    read_aloud_text: str
    raw_parsed_markdown: str

class Room(Document):
    module_id: Indexed(str)
    room_id: Indexed(str, unique=True)
    title: str
    navigation: Navigation
    environment: Environment
    encounters: Encounters
    story_and_triggers: StoryAndTriggers
    llm_contexts: RoomLLMContexts

    class Settings:
        name = "rooms"
