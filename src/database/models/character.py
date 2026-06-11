from datetime import datetime
from typing import List, Dict
from beanie import Document, Indexed
from pydantic import BaseModel, Field
from .enums import ConditionType

class AttributeScore(BaseModel):
    score: int
    modifier: int

class CharacterAttributes(BaseModel):
    str: AttributeScore
    dex: AttributeScore
    con: AttributeScore
    int: AttributeScore
    wis: AttributeScore
    cha: AttributeScore

class CharacterVitals(BaseModel):
    current_hp: int
    max_hp: int
    temporary_hp: int = 0
    armor_class: int
    initiative_modifier: int
    passive_perception: int
    speed_ft: int

class Item(BaseModel):
    item_id: str
    name: str
    quantity: int
    weight_lbs: float
    is_equipped: bool = False
    properties: Dict = Field(default_factory=dict)

class SpellSlotTracker(BaseModel):
    level_1: Dict[str, int] = {"max": 0, "used": 0}
    level_2: Dict[str, int] = {"max": 0, "used": 0}
    level_3: Dict[str, int] = {"max": 0, "used": 0}

class CharacterSheet(Document):
    user_id: Indexed(str)
    name: str
    character_class: str = Field(alias="class")
    level: int = 1
    race: str
    background: str
    alignment: str
    experience_points: int = 0
    
    attributes: CharacterAttributes
    vitals: CharacterVitals
    
    proficiencies: List[str] = Field(default_factory=list)
    status_conditions: List[ConditionType] = Field(default_factory=list)
    features_and_traits: Dict[str, str] = Field(default_factory=dict)
    
    inventory: List[Item] = Field(default_factory=list)
    gold_pieces: int = 0
    
    known_spells: List[str] = Field(default_factory=list)
    spell_slots: SpellSlotTracker = Field(default_factory=SpellSlotTracker)
    
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "characters"
