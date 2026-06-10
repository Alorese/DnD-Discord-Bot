import sys
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from config.settings import settings

# Explicitly import all document schemas so Beanie can register their collections
from database.models import CampaignModule, RoomContext, CharacterSheet, GameSession

async def init_database(mongo_uri: str):
    """
    Establishes an asynchronous connection pool to the self-hosted MongoDB server
    and binds the Pydantic data schemas into high-performance Beanie document collections.
    """
    # 1. Fall back to global configuration registry if no string parameter is explicitly passed
    target_uri = str(mongo_uri or settings.mongo_uri)
    
    try:
        print("🔌 Launching asynchronous Motor connection pool to MongoDB...")
        # Initialize the official MongoDB Async driver connection handle
        # client = motor.motor_asyncio.AsyncIOMotorClient(target_uri)
        client = AsyncIOMotorClient(target_uri)
        
        # 2. Extract the default database name directly from your connection URI layout string
        # e.g., '...:27017/dnd_bot?...' will naturally resolve and track data inside 'dnd_bot'
        db_handle = client.get_default_database()
        
        print(f"🗃️ Target database resolved: '{db_handle.name}'. Initializing Beanie document mappings...")
        
        # 3. Synchronize Beanie Document schemas with the database server
        # This step handles creating collection indexes (such as your single-session constraint) on the fly
        await init_beanie(
            database=db_handle,
            document_models=[
                CampaignModule,
                RoomContext,
                CharacterSheet,
                GameSession
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

