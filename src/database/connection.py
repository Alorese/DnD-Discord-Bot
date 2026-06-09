import os
import motor.motor_asyncio
from beanie import init_beanie

async def init_database():
    # Read the connection URI directly from the container environment variables
    mongo_uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    
    client = motor.motor_asyncio.AsyncIOMotorClient(mongo_uri)
    
    # Initialize Beanie Documents
    await init_beanie(
        database=client.get_default_database(), # Grabs the database name specified in the URI path
        document_models=[CampaignModule, CharacterSheet, GameSession]
    )
    print("🤖 Production MongoDB Link Established via Docker Network Node.")
