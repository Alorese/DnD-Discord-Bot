import os
import re
import json
import aiohttp
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from google import genai
from google.genai import types
from pydantic import BaseModel
from beanie import WriteRules
from beanie.odm.operators.update.general import Set
# Import core system helper utilities and Beanie document schemas
from services.template_service import prompt_service
from database.models.ingestion import CharacterSheetIngestionSchema
from database.models.character import CharacterSheet
from database.models.room import Room, Navigation, Environment, Encounters, StoryAndTriggers, RoomLLMContexts

class ImportCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # 1. Instantiate the Google GenAI Client
        self.ai_client = genai.Client()
        self.tmp_dir = "tmp_downloads"
        os.makedirs(self.tmp_dir, exist_ok=True)

        # RegEx Patterns for Link Group Validation
        self.ddb_pattern = re.compile(r"dndbeyond\.com/(?:characters|profile/[^/]+/characters)/(\d+)")
        self.gdrive_pattern = re.compile(r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)")

    async def download_file_async(self, url: str, destination: str) -> bool:
        """Asynchronously streams remote files down to local disk space safely."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        return False
                    with open(destination, "wb") as f:
                        while True:
                            chunk = await response.content.read(1024 * 1024) # 1MB chunks
                            if not chunk:
                                break
                            f.write(chunk)
            return True
        except Exception:
            return False

    # =========================================================================
    # CHARACTER IMPORT: D&D BEYOND + JINJA TRANSFORM ROUTINE
    # =========================================================================
    @app_commands.command(name="import_character", description="Imports a character sheet using a public D&D Beyond URL link.")
    @app_commands.describe(url="The public share link to your character sheet")
    async def import_character(self, interaction: discord.Interaction, url: str):
        match = self.ddb_pattern.search(url)
        if not match:
            return await interaction.response.send_message(
                "❌ **Invalid Link format!** Please provide a valid D&D Beyond character URL.", ephemeral=True
            )

        character_id = match.group(1)
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send("⚡ *Connecting to D&D Beyond API proxy endpoints...*")

        proxy_url = f"https://character-service.dndbeyond.com/character/v5/character/{character_id}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(proxy_url) as response:
                    if response.status != 200:
                        print(f"Response status: {response.status}")
                        return await interaction.followup.send("❌ Data fetch failure. Ensure your character visibility is set to **Public**.")
                    raw_json_data = await response.json()
            
            await interaction.followup.send("🧠 *Data buffered! Compiling Jinja2 mapping schema for Gemini 3.1...*")

            # --- STEP 1: Render JSON Context Using TemplateService ---
            prompt = prompt_service.render_prompt(
                "ddb_character_mapper.jinja",
                raw_json_data=json.dumps(raw_json_data.get('data', {}))
            )

            schema = CharacterSheetIngestionSchema.model_json_schema()

            def remove_additional_properties(schema_dict):
                """Recursively remove 'additionalProperties': False from dict."""
                if isinstance(schema_dict, dict):
                    schema_dict.pop("additionalProperties", None)
                    for value in schema_dict.values():
                        remove_additional_properties(value)
                elif isinstance(schema_dict, list):
                    for item in schema_dict:
                        remove_additional_properties(item)
                return schema_dict

            clean_schema = remove_additional_properties(schema)

            # --- STEP 2: Call Gemini 3.1 Flash Lite For Pydantic Structural Extraction ---
            ai_response = self.ai_client.models.generate_content(
                model="gemini-3.1-flash-lite",
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                    # Swap the Beanie document out for the pure Pydantic schema
                    response_schema=clean_schema
                )
            )

            # --- STEP 3: Map the dict directly to your Beanie Document ---
            sheet_dict = prompt_service.clean_json_response(ai_response.text)
            sheet_dict["user_id"] = str(interaction.user.id) # Inject active user owner link
            
            # This safely instantiates your Beanie Document and generates a fresh ObjectId automatically!
            character_doc = CharacterSheet(**sheet_dict)
            update_character_doc = character_doc.model_dump(exclude={"id"})

            # Perform upsert safely into MongoDB via Beanie
            await CharacterSheet.find_one(
                CharacterSheet.user_id == character_doc.user_id, 
                CharacterSheet.name == character_doc.name
            ).upsert(
                Set(update_character_doc),
                on_insert=character_doc
            )

            await interaction.followup.send(f"✅ **Import Successful!** Character **{character_doc.name}** (Level {character_doc.level}) has been successfully mapped to your Discord account!")

        except Exception as e:
            await interaction.followup.send(f"❌ Critical exception during character document creation: {e}")

    # =========================================================================
    # MODULE IMPORT: MULTIMODAL GOOGLE DRIVE + JINJA REFACTOR ROUTINE
    # =========================================================================
    @app_commands.command(name="import_module", description="Parses and indexes an adventure PDF module via shareable Google Drive Link.")
    @app_commands.describe(campaign_id="The unique reference slug identifier for this module", url="Google Drive share link")
    async def import_module(self, interaction: discord.Interaction, campaign_id: str, url: str):
        match = self.gdrive_pattern.search(url)
        if not match:
            return await interaction.response.send_message(
                "❌ **Invalid Link format!** Please provide a valid, shareable Google Drive File URL.", ephemeral=True
            )

        file_id = match.group(1)
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send("📥 *Buffering campaign document payload from Google Drive...*")

        download_url = f"https://google.com{file_id}"
        temp_filepath = os.path.join(self.tmp_dir, f"{campaign_id}_temp.pdf")

        

        success = await self.download_file_async(download_url, temp_filepath)
        if not success or not os.path.exists(temp_filepath):
            return await interaction.followup.send("❌ Download failure. Ensure your file access is set to **'Anyone with the link can view'**.")

        await interaction.followup.send("🛡️ *File buffered! Uploading asset directly into Gemini files infrastructure...*")

        try:
            # --- STEP 1: Push file directly to Google File API Workspace ---
            uploaded_file_info = self.ai_client.files.upload(file=temp_filepath)
            
            # Sleep 3 seconds to let remote virus scan pipelines resolve cleanly
            await asyncio.sleep(3)

            await interaction.followup.send("⚙️ *Asset registered! Compiling room parsing instructions...*")

            # Create list wrapping schema for Gemini 3.1 structured validation arrays
            class ModuleImportWrapper(BaseModel):
                model_config = ConfigDict(extra="allow")
                rooms: list[dict]

            # --- STEP 2: Compile Context and Call Gemini with Multimodal Reference ---
            # Render the prompt template passing your campaign ID slug and the raw text file chunk
            prompt = prompt_service.render_prompt(
                "module_ingestor.jinja",
                campaign_id=campaign_id,
                text_chunk=prompt_service.render_prompt("module_ingestor.jinja", campaign_id=campaign_id) 
            )

            # Define your API payload script instructions 
            ai_response = self.ai_client.models.generate_content(
                model="gemini-3.5-flash", # Or gemini-3.1-flash-lite with thinking_level="high"
                contents=[uploaded_file_info, prompt],
                config=types.GenerateContentConfig(
                    temperature=0.1, # Enforce heavy structure consistency
                    response_mime_type="application/json",
                    response_schema=ModuleImportWrapper
                )
            )

            # --- STEP 3: Iterate JSON Array and Construct Beanie Models Natively ---
            parsed_data = prompt_service.clean_json_response(ai_response.text)
            rooms_list = parsed_data.get("rooms", [])

            for idx, r in enumerate(rooms_list):
                try:
                    # Dynamically instantiate matching sub-document structures
                    room_doc = Room(
                        module_id=campaign_id,
                        room_id=r["room_id"],
                        title=r["title"],
                        navigation=Navigation(**r["navigation"]),
                        environment=Environment(**r["environment"]),
                        encounters=Encounters(**r["encounters"]),
                        story_and_triggers=StoryAndTriggers(**r["story_and_triggers"]),
                        llm_contexts=RoomLLMContexts(**r["llm_contexts"])
                    )

                    # Update data for upsert
                    update_room_doc = room_doc.model_dump(exclude={"id"}) # shouldn't need this because should check if campaign id exists already, and if so then dont just return

                    # Perform upsert safely into MongoDB via Beanie
                    await Room.find_one(
                        Room.room_id == room_doc.room_id
                    ).upsert(
                        Set(update_room_doc),
                        on_insert=room_doc
                    )
                except Exception as inner_err:
                    print(f"Skipped malformed block index {idx} during import loop: {inner_err}")

            await interaction.followup.send(f"✅ **Ingestion Complete!** Successfully mapped **{len(rooms_list)} room documents** to module identifier slug: `{campaign_id}`.")

        except Exception as e:
            await interaction.followup.send(f"❌ Critical pipeline exception during multi-page layout analysis: {e}")

        finally:
            # --- STEP 4: Enforce absolute local temp storage cleanup ---
            if os.path.exists(temp_filepath):os.remove(temp_filepath)
            print(f"🧹 Cleaned up temporary local download asset artifact: {temp_filepath}")
            
async def setup(bot):
    await bot.add_cog(ImportCog(bot))