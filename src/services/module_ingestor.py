import os
import json
import asyncio
from google import genai
from pydantic import BaseModel, Field
from typing import List, Dict, Optional

# Import your unified Beanie initialization loop and Room Schema
from database.connection import init_database
from database.models.room import Room, Navigation, Environment, Encounters, StoryAndTriggers, RoomLLMContexts, RoomExit

# Initialize the GenAI Client
client = genai.Client()

# Create a strict Pydantic parsing structure for Gemini output validation
class IngestedRoomSchema(BaseModel):
    room_id: str
    title: str
    map_layer: str
    x_coord: int
    y_coord: int
    exits: Dict[str, Dict] # {"north": {"target_room_id": "room_2", "type": "WOODEN_DOOR"}}
    dimensions: str
    lighting: str
    read_aloud_text: str
    raw_parsed_markdown: str

class ChunkExtractionWrapper(BaseModel):
    rooms: List[IngestedRoomSchema]

async def parse_and_insert_chunk(campaign_id: str, text_chunk: str):
    """Feeds a text chunk to Gemini and commits validated results to MongoDB via Beanie."""
    
    prompt = f"""
    You are an expert TTRPG Data Engineer. Analyze the following raw Markdown data from a D&D module chunk.
    Extract every single numbered room, keyed dungeon location, or encounter space.

    RAW TEXT CHUNK:
    {text_chunk}
    """

    # Forcing Gemini 3.1 Flash Lite to return strict structured JSON matching our Pydantic spec
    response = client.models.generate_content(
        model='gemini-3.1-flash-lite',
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            system_instruction="Extract all locations into the specified JSON structure. Ensure all fields are filled accurately.",
            temperature=0.1, # High consistency, low creativity
            response_mime_type="application/json",
            response_schema=ChunkExtractionWrapper
        )
    )

    # Safely convert returned JSON string to pure data dictionaries
    data = json.loads(response.text)
    
    for r in data.get("rooms", []):
        # Translate the LLM data dictionary back into your strong-typed Beanie Document structure
        room_doc = Room(
            module_id=campaign_id,
            room_id=r["room_id"],
            title=r["title"],
            navigation=Navigation(
                map_layer=r["map_layer"],
                coordinates={"x": r["x_coord"], "y": r["y_coord"]},
                exits={dir_key: RoomExit(
                    target_room_id=ex_data["target_room_id"],
                    type=ex_data["type"]
                ) for dir_key, ex_data in r["exits"].items()}
            ),
            environment=Environment(
                dimensions=r["dimensions"],
                lighting=r["lighting"],
                hazards=[],
                interactive_objects=[]
            ),
            encounters=Encounters(combat_trigger_type="NONE", monsters=[]),
            story_and_triggers=StoryAndTriggers(required_plot_flags=[], conditional_events=[]),
            llm_contexts=RoomLLMContexts(
                read_aloud_text=r["read_aloud_text"],
                raw_parsed_markdown=r["raw_parsed_markdown"]
            )
        )
        
        # Upsert: Save to MongoDB. If room already exists, overwrite it with clean data
        await Room.find_one(Room.room_id == room_doc.room_id).upsert(
            set_on_insert=room_doc,
            on_insert=room_doc
        )
        print(f"📥 Successfully imported room document: {room_doc.room_id} -> {room_doc.title}")
