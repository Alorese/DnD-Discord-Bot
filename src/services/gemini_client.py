import os
import datetime
from google import genai
from google.genai import types
from google.genai.errors import APIError
from config.settings import settings

class GeminiService:
    """
    Central management layer for the Google Gemini API. Handles type-safe client 
    initialization and implements sliding window context caching for long modules.
    """
    def __init__(self):
        # Initialize using the official canonical SDK and validated Pydantic settings
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model_name = "gemini-3.1-flash-lite"

    def get_client(self) -> genai.Client:
        """Exposes the raw authenticated client for direct cog operations."""
        return self.client

    def bump_context_cache_ttl(self, cache_id: str, extension_minutes: int = 30) -> bool:
        """
        Dynamically pushes the expiration timestamp of a cached campaign module file
        into the future. Keeps the cache warm during active play and allows automatic 
        garbage collection when players log off.
        """
        try:
            # 1. Establish the future target time window based on current UTC clock
            future_expiry = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=extension_minutes)
            
            # 2. Format explicitly into a strict RFC 3339 string layout required by Google
            rfc3339_timestamp = future_expiry.strftime('%Y-%m-%dT%H:%M:%SZ')
            
            # 3. Fire the update pointer mutation down the cloud pipe
            self.client.caches.update(
                name=cache_id,
                config=types.UpdateCachedContentConfig(
                    expire_time=rfc3339_timestamp
                )
            )
            print(f"❄️ Context Cache '{cache_id}' extended successfully. New Expiry: {rfc3339_timestamp}")
            return True

        except APIError as e:
            # Catch API edge cases cleanly (e.g., if a cache unexpectedly expired or was dropped)
            print(f"⚠️ Failed to slide Context Cache TTL window for '{cache_id}': {e}")
            return False
        except Exception as e:
            print(f"❌ Unexpected system failure during cache TTL extension: {e}")
            return False

# Instantiate a single global instance of the service layer to share across Cogs
gemini_service = GeminiService()
