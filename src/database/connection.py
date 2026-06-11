import sys
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from config.settings import settings

# Explicitly import all document schemas so Beanie can register their collections
from database.models.character import CharacterSheet
from database.models.session import GameSession
from database.models.monster import Monster
from database.models.room import Room

async def init_database(mongo_uri: Optional[str] = None):
    """
    Establishes an asynchronous connection pool to the self-hosted MongoDB server
    and binds the Pydantic data schemas into high-performance Beanie document collections.
    """
    # 1. Fall back to global configuration registry if no string parameter is explicitly passed
    target_uri = str(mongo_uri if mongo_uri is not None else settings.mongo_uri)
    
    try:
        print("🔌 Launching asynchronous Motor connection pool to MongoDB...")
        # Initialize the official MongoDB Async driver connection handle
        client = AsyncIOMotorClient(target_uri)
        
        # 2. Extract the default database name directly from your connection URI layout string
        db_handle = client.get_default_database()
        
        print(f"🗃️ Target database resolved: '{db_handle.name}'. Initializing Beanie document mappings...")
        
        # 3. Synchronize Beanie Document schemas with the database server
        # This step handles creating collection indexes automatically at startup
        await init_beanie(
            database=db_handle,
            document_models=[
                CharacterSheet,  # Maps to 'characters' collection (Persistent master sheets)
                GameSession,     # Maps to 'sessions' collection (Live active delta states)
                Monster,         # Maps to 'monsters' collection (MM & Module variants)
                Room             # Maps to 'rooms' collection (Static blueprint library)
            ]
        )
        
        print("🚀 Beanie ODM mappings established. Local collection schemas matched successfully.")
        return True

    except ConnectionError as e:
        print(f"❌ DATABASE CONNECTION FAILURE: Unable to locate or authenticate with MongoDB node: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"❌ CRITICAL INFRASTRUCTURE CRASH during Beanie initialization pipeline: {e}", file=sys.stderr)
        return False
