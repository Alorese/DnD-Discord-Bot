# DnD Discord Dungeon Master Bot

An AI-driven Dungeon Master bot for Discord that allows players bring their own character sheets from DnD Beyond, play D&D modules, and roleplay without needing an experienced human Dungeon Master!

The bot uses a 2-model pipeline with MongoDB to track game state and Gemini 3.1 Flash Lite for context caching and swift replies.

---

## Technical Stack

- **Python & Pydantic** - Bot runner, slash commands, and data shape validation.
- **MongoDB** - Persistent game state storage
- **Open WebUI** - Hosts the LLM models and external RAG knowledge base (PHB/DMG) outside this repository.
   - **Model 1: Chat Parser Model** - Filters OOC banter and parses player actions into structured payloads. (Gemini 3.1 Flash Lite - Low Reasoning)
   - **Model 2: GM / Rule Model** - Narrator, rule arbiter, and tool orchestrator. (Gemini 3.5 Flash or 3.1 Flash Lite - Medium Reasoning)
   - **Model 3: LoreKeeper Model** - helps with onboarding by validating character sheets, modules, and other `/commands` for players. (3.1 Flash Lite)

---

## Required Environment Variables

- `DISCORD_BOT_TOKEN` - generate from Discord Developer Portal (remember to turn on Priveleged Gateway Intents ie. presence, server members, message content)
- `WHITELIST_CHANNEL_IDS` - only listens to specific channels, enter developer mode in discord and right click channel
- `MONGO_URI` - mongodb://admin_dm:super_secret_password_here@mongodb:27017/dnd_bot?authSource=admin
- `GEMINI_API_KEY` - Google AI Studio API Key
- `DND_DDB_PARSER_ID` - model id for DnD Beyond and Module Ingestion
- `DND_CHAT_PARSER_ID` - model id for your chat parser model
- `DND_RULE_ID` - model id for rule keeper model
- `DND_NARRATOR_ID` - model id for your narrator model

---

## Initialization
- `docker compose up --build` - run docker command to start bot - requires external MongoDB
 - Bot begins listening for messages on specific discord channels

---

=========================================================================================================
                      MASTER D&D DISCORD BOT FLOWCHART (MONGO + BEANIE + CACHE + JINJA2)
=========================================================================================================

  [ 1. INITIAL SESSION & CHARACTER SEEDING LOOP ]
  
     [ D&D Beyond Sheet URL ]                         [ Google Drive Campaign Module Link ]
                 │                                                      │
                 ▼                                                      ▼
       [ LLM SMART PARSER ]                                  [ GOOGLE DRIVE EXTRACTOR ]
    (Extracts JSON Object map)                             (Generates Direct PDF Stream URL)
                 │                                                      │
                 ▼                                                      ▼
     ┌───────────────────────┐                              ┌───────────────────────┐
     │  MONGODB COLLECTION:  │                              │   GEMINI FILE BUCKET  │
     │      "characters"     │                              │ (Pre-caches the 200k+ │
     │ (Saves baseline stats;│                              │  token module novel)  │
     │  clears active deltas)│                              └───────────────────────┘
     └───────────────────────┘                                          │
                 │                                                      ▼
                 │                                          ┌───────────────────────┐
                 │                                          │  MONGODB COLLECTION:  │
                 │                                          │    "room_contexts"    │
                 │                                          │  (Saves structural    │
                 │                                          │   room hazard details)│
                 └─────────────────────────┬────────────────└───────────────────────┘
                                           │
                                           ▼
                       [ /start_campaign OR /join_session COMMAND ]
                       • Activates `setup_cog.py`. Binds Discord Channel to Module URI.
                       • System initializes local room states and primes the game loops.
                                           │
                                           ▼
=========================================================================================================
  [ 2. ACTIVE RUNTIME TACTICAL LOOP ]
  
                                    [ PLAYER INPUT MESSAGE ]
                    (e.g., "Thia casts Misty Step to teleport past the pit trap")
                                           │
                                           ▼
                    ┌───────────────────────────────────────────────────────┐
                    │ 2A. MAIN APPLICATION PARSER GATEWAY                   │
                    ├───────────────────────────────────────────────────────┤
                    │ • Matches prefix (!)?  ──► Read Local MongoDB DB      │
                    │ • Matches tag (@bot)?  ──► Route to `lorekeeper_cog`  │
                    │ • In-Character Text?   ──► Route to `action_cog.py`   │
                    └───────────────────────────────────────────────────────┘
                                           │
                                           ▼ (In-Character Route)
                    ┌───────────────────────────────────────────────────────┐
                    │ 2B. RULE CHECK MODEL (Gemini 3.1 Flash-Lite + CACHE)  │
                    ├───────────────────────────────────────────────────────┤
                    │ • Input: Player Action + Character Baseline Sheet.    │
                    │ • Input: Current room hazard states from MongoDB.     │
                    │ • Note: Chat History is left out to prevent noise.    │
                    │                                                       │
                    │    ├── [REJECT] ──► "Impossible action" ──► End Loop. │
                    │    └── [APPROVE] ──► Outputs JSON:                    │
                    │                      {"valid": true, "roll": "Arcana"}│
                    └───────────────────────────────────────────────────────┘
                                           │
                                           ▼
                    ┌───────────────────────────────────────────────────────┐
                    │ 2C. BOT INTERRUPT & UI COMPONENT GENERATION           │
                    ├───────────────────────────────────────────────────────┤
                    │ • Python application freezes the active player thread.│
                    │ • Bot prints custom interactive UI block to Discord:  │
                    │   "Thia casts Misty Step! [Click to Roll Arcana]"     │
                    └───────────────────────────────────────────────────────┘
                                           │
                                           ▼ (Player physically clicks the UI Button 🔘)
                    ┌───────────────────────────────────────────────────────┐
                    │ 2D. DETERMINISTIC PYTHON RESOLUTION ENGINE            │
                    ├───────────────────────────────────────────────────────┤
                    │ • Backend server executes a secure 1d20 random roll.  │
                    │ • Automatically pulls modifier from `base_skills`.    │
                    │ • Edits Discord UI embed block showing absolute math. │
                    │ • MUTATES DELTA STATE: `await character.save()`       │
                    │   (Deducts spell slot inside MongoDB collections)     │
                    └───────────────────────────────────────────────────────┘
                                           │
                                           ▼
                    ┌───────────────────────────────────────────────────────┐
                    │ 2E. DM NARRATOR MODEL (Gemini 3.1 Flash-Lite + CACHE) │
                    ├───────────────────────────────────────────────────────┤
                    │ • Context: Loads cached module from File URI.         │
                    │ • Input: Jinja2 renders prompt file string containing │
                    │   (Action + Roll Result + Vitals Delta + Chat Window) │
                    │ • Output: Cinematic storytelling narration.           │
                    └───────────────────────────────────────────────────────┘
                                           │
                                           ▼
                              [ FINAL PRESENTATION LAYER ]
                    • Bot outputs narrator's rich narrative embed to channel.
                    • Unlocks player channel thread for the next active turn.

---

# TODOs:
[] implement In-Memory Lock/Queue system (`asyncio.Lock()`) to prevent double click errors
[] cache character sheets at start of session
[] add Discord.ui.View and discrod.ui.Button in game_loop cog