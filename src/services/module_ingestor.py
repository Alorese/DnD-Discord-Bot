import os
import re
import pydantic
from typing import List, Dict
from google import genai
from google.genai import types
from config.settings import settings
from database.models import CampaignModule, RoomContext

# Reuse the Pydantic schemas from your previous ingestion layout
class ParsedRoom(pydantic.BaseModel):
    room_id: str
    room_title: str
    environmental_hazards: List[str]
    mechanics_override_json: Dict[str, str]
    flavor_text: str

class ParsedModuleSchema(pydantic.BaseModel):
    module_name: str
    rooms: List[ParsedRoom]

def extract_google_drive_id(url: str) -> str:
    """Regex helper to instantly parse the File ID out of a messy GDrive link."""
    match = re.search(r'(?:id=|/d/|/file/d/)([\w_-]{25,})', url)
    if not match:
        raise ValueError("Invalid Google Drive Link format.")
    return match.group(1)

async def stream_and_structure_module(module_slug: str, gdrive_url: str):
    client = genai.Client(api_key=settings.gemini_api_key)
    
    # 1. Strip out the file ID from the player's link
    file_id = extract_google_drive_id(gdrive_url)
    
    # 2. Construct the direct PDF Export URL stream endpoint
    # This instructs Google Drive to convert the file to a standard PDF byte stream on the fly.
    export_stream_url = f"https://google.com{file_id}&exportFormat=pdf"
    
    # 3. Tell Gemini to fetch and parse the file directly from the URL stream
    # No local server files are created or written to your Docker disk.
    extraction_prompt = (
        "Analyze this adventure module via its remote stream. Break the map down room-by-room. "
        "Extract all mechanical environmental hazards and narrative descriptions."
    )
    
    print(f"Streaming module directly from Google Cloud space...")
    response = client.models.generate_content(
        model='gemini-3.1-flash-lite',
        # We pass the raw export URL string directly as content instead of a local file path!
        contents=[export_stream_url, extraction_prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ParsedModuleSchema,
        ),
    )
    
    # 4. Map the resulting string data directly into your self-hosted MongoDB
    structured_data = ParsedModuleSchema.model_validate_json(response.text)
    
    # Write Master Module Pointer Record
    campaign = CampaignModule(
        module_slug=module_slug,
        module_name=structured_data.module_name,
        gemini_file_uri=export_stream_url # Keep the remote streaming link as your permanent cache pointer!
    )
    await campaign.insert()
    
    # Map rooms natively to database collections
    for parsed_room in structured_data.rooms:
        room_doc = RoomContext(
            module_slug=module_slug,
            room_id=parsed_room.room_id,
            room_title=parsed_room.room_title,
            environmental_hazards=parsed_room.environmental_hazards,
            mechanics_override_json=parsed_room.mechanics_override_json,
            flavor_text=parsed_room.flavor_text
        )
        await room_doc.insert()
        
    print(f"✅ Successfully ingested {len(structured_data.rooms)} rooms with zero local server downloads!")
