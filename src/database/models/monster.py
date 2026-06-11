from typing import List, Optional, Dict
from beanie import Document, Indexed
from pydantic import BaseModel, Field
from .enums import CreatureSize, AttackType

class MonsterMeta(BaseModel):
    size: CreatureSize
    creature_type: str = Field(alias="type")
    subtype: Optional[str] = None
    alignment: str
    challenge_rating: float
    xp_value: int

class AttributeScore(BaseModel):
    score: int
    modifier: int

class Attributes(BaseModel):
    str: AttributeScore
    dex: AttributeScore
    con: AttributeScore
    int: AttributeScore
    wis: AttributeScore
    cha: AttributeScore

class HitPoints(BaseModel):
    average: int
    hit_dice_formula: str

class Defenses(BaseModel):
    armor_class: int
    armor_type: str
    hit_points: HitPoints
    saving_throws: Dict[str, int] = Field(default_factory=dict)
    damage_immunities: List[str] = Field(default_factory=list)
    damage_resistances: List[str] = Field(default_factory=list)
    condition_immunities: List[str] = Field(default_factory=list)
    vulnerabilities: List[str] = Field(default_factory=list)

class MobilityAndSenses(BaseModel):
    speed: Dict[str, int]
    darkvision_ft: int = 0
    passive_perception: int

class Trait(BaseModel):
    name: str
    description: str

class MonsterAction(BaseModel):
    name: str
    type: AttackType
    hit_modifier: int
    range_ft: int
    max_range_ft: Optional[int] = None
    targets: str
    damage_formula: str
    damage_type: str

class LLMContexts(BaseModel):
    narrative_description: str
    rules_engine_markdown: str

class Monster(Document):
    monster_id: Indexed(str, unique=True)
    name: str
    source_book: str
    meta: MonsterMeta
    attributes: Attributes
    defenses: Defenses
    mobility_and_senses: MobilityAndSenses
    skills: Dict[str, int] = Field(default_factory=dict)
    languages: List[str] = Field(default_factory=list)
    traits: List[Trait] = Field(default_factory=list)
    actions: List[MonsterAction] = Field(default_factory=list)
    llm_contexts: LLMContexts

    class Settings:
        name = "monsters"
