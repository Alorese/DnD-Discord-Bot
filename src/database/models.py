from datetime import datetime
from typing import Dict, List, Optional
from beanie import Document, Link
from pydantic import BaseModel, Field

# ==============================================================================
# 1. PYDANTIC SUB-STRUCTURES (Reusable embedded data blocks)
# ==============================================================================

class CharacterVitals(BaseModel):
    """Tracks active, runtime combat health parameters during a play session."""
    # Current session health. If NULL, code defaults to base_max_hp
    session_current_hp: Optional[int] = None
    base_max_hp: int
    temp_hp: int = 0
    base_ac: int
    speed: int = 30
    initiative_bonus: int = 0
    active_conditions: List[str] = Field(default_factory=list) # ["Poisoned", "Prone"]

class SpellSlots(BaseModel):
    """Tracks character spell slots. Maps slot tier to current allocation count."""
    max_slots: Dict[str, int] = Field(default_factory=dict)   # {"1st": 4, "2nd": 2}
    used_slots: Dict[str, int] = Field(default_factory=dict)  # {"1st": 1, "2nd": 0}

class InventoryItem(BaseModel):
    """Structures inventory tracking for baseline gear and mid-session loot shifts."""
    name: str
    quantity: int = 1
    weight: float = 0.0
    is_loot_found_mid_session: bool = False

# ==============================================================================
# 2. GLOBAL DATABASE DOCUMENTS (Beanie MongoDB Collection Sheets)
# ==============================================================================

class CampaignModule(Document):
    """Stores metadata pointer configurations for long-context campaign modules."""
    module_slug: str = Field(unique=True)     # Unique look-up shorthand (e.g., "lost_mine")
    module_name: str                         # Human-readable title ("Lost Mine of Phandelver")
    gemini_file_uri: str                     # The permanent Google Cloud Stream export URL
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "campaign_modules"            # Target collection name inside MongoDB

class RoomContext(Document):
    """Holds discrete tactical boundaries and rules overrides for unique map zones."""
    module_slug: str                         # Links back to parent CampaignModule
    room_id: str                             # Alpha-numeric lookup key (e.g., "room_04_chasm")
    room_title: str                          # Formal room title ("The Fractured Abyss")
    
    # Strict variables processed by the Rule Check Model
    environmental_hazards: List[str] = Field(default_factory=list) # ["200ft open chasm"]
    mechanics_override_json: Dict[str, str] = Field(default_factory=dict) # {"jump": "impossible"}
    
    # Story text blocks reserved strictly for the DM Narrator Model
    flavor_text: str
    
    class Settings:
        name = "room_contexts"
        # Index on both fields for ultra-fast lookup times inside your action cogs
        indexes = [
            [("module_slug", 1), ("room_id", 1)]
        ]

class CharacterProficiencies(BaseModel):
    """Tracks explicit training states for automatic game mechanic scaling."""
    # Saving Throws: {"STR": true, "DEX": false, ...}
    saving_throws: Dict[str, bool] = Field(default_factory=dict)
    
    # Skills maps to tier flags: 0 = None, 1 = Proficient, 2 = Expertise
    skills: Dict[str, int] = Field(default_factory=dict) 
    
    # Static tags parsed from D&D Beyond
    tools: List[str] = Field(default_factory=list)      # ["Thieves' Tools", "Alchemist's Supplies"]
    languages: List[str] = Field(default_factory=list)  # ["Common", "Elvish"]
    armor: List[str] = Field(default_factory=list)      # ["Light Armor", "Shields"]
    weapons: List[str] = Field(default_factory=list)    # ["Simple Weapons", "Longsword"]

class CharacterSheet(Document):
    channel_id: str                          
    player_id: str                           
    ddb_character_id: str                    
    character_name: str                      
    class_and_level: str                     
    
    # Base Vitals & Level Trackers
    level: int = 1                           # ⚠️ NEW: Vital for calculating scaling mechanics
    proficiency_bonus: int = 2               # ⚠️ NEW: Base standard stat mapping
    vitals: CharacterVitals
    
    # Stats & Calculated Modifier Arrays
    stats: Dict[str, int]                    # Raw scores: {"strength": 14}
    base_skills: Dict[str, int]              # Final computed values for easy Jinja2 rendering

    # 💎 THE FIXED COUPLING: Native System Proficiencies
    proficiencies: CharacterProficiencies    # Injects tool, language, and weapon permissions
    
    features: Dict[str, str]                 
    spellcasting: Optional[SpellSlots] = None
    inventory: List[InventoryItem] = Field(default_factory=list)

    class Settings:
        name = "characters"
        indexes = [[("channel_id", 1), ("player_id", 1)]]
        ]

class GameSession(Document):
    """Maintains the active runtime, turn structures, and state flags for a game thread."""
    channel_id: str = Field(unique=True)     # Primary Key mapping directly to the Discord Channel
    current_room_id: str                     # Tracks character location map keys (matches RoomContext.room_id)
    combat_active: bool = False              # Structural game engine state toggle
    initiative_order: List[str] = Field(default_factory=list) # Session turn sequence tracking
    current_turn_index: int = 0
    last_activity: datetime = Field(default_factory=datetime.utcnow)
    
    # Creates a type-safe relational lazy-link to the parent CampaignModule collection document
    active_module: Link[CampaignModule]

    class Settings:
        name = "game_sessions"
