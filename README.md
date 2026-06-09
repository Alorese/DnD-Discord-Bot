# DnD Discord Dungeon Master Bot

An AI-driven Dungeon Master bot for Discord that allows players to link character sheets, play D&D modules, and roleplay without needing a book or dice.

The bot uses a 2-model pipeline with SQLite-backed persistence and Open WebUI for external model inference and RAG support.

---

## Technical Stack

- **Python & Pydantic** - Bot runner, slash commands, and data shape validation.
- **SQLite** - Persistent game state storage via `database.py`.
- **Open WebUI** - Hosts the LLM models and external RAG knowledge base (PHB/DMG) outside this repository.
   - **Model 1: Chat Parser Model** - Filters OOC banter and parses player actions into structured payloads. (Gemini 3.1 Flash Lite - Low Reasoning)
   - **Model 2: GM / Rule Model** - Narrator, rule arbiter, and tool orchestrator. (Gemini 3.5 Flash or 3.1 Flash Lite - Medium Reasoning)
   - **Model 3: LoreKeeper Model** - helps with onboarding by validating character sheets, modules, and other `/commands` for players. (3.1 Flash Lite)

---

## Required Environment Variables

- `DISCORD_BOT_TOKEN` - generate from Discord Developer Portal (remember to turn on Priveleged Gateway Intents ie. presence, server members, message contet)
- `WHITELIST_CHANNEL_IDS` - enter developer mode in discord and right click channel
- `DND_CHAT_PARSER_ID` - model id for your chat parser model
- `DND_DM_ID` - model id for your dm model

---

## Initialization
- `docker compose up --build` - run docker command to start bot and db
 - SQLite DB will create if it doesn't exist
 - Bot begins listening for messages on specific discord channel

---

┌────────────────────────────────────────────────────────────────────────┐
│                        DISCORD BOT COG LAYER                           │
└────────────────────────────────────────────────────────────────────────┘
    │           │                  │                    │
    ▼           ▼                  ▼                    ▼
┌───────────┐ ┌───────────┐ ┌──────────────┐ ┌──────────────────────────┐
│ SLASHEG   │ │ STATUSEG  │ │ ACTION COG   │ │ LOREKEEPER COG (@bot)    │
├───────────┤ ├───────────┤ ├──────────────┤ ├──────────────────────────┤
│/commands  │ │ !status   │ │ In-Character │ │ • Intercepts app mentions│
│• Join/Load│ │ • Quick DB│ │ Text Loop    │ │ • Triggers OOC pipeline  │
│• Sync DDB │ │   reads   │ │ • Runs full  │ │ • Rules/Lore context   │
│• Check in │ │ • $0 Cost │ │   multi-LLM  │ │   Q&A lookups          │
└───────────┘ └───────────┘ └──────────────┘ └──────────────────────────┘

---

How to construct Payload

[1. Your System Prompt] 
          +
[2. The Core Rulebooks (PHB/MM)] 
          +
[3. THE ACTIVE CAMPAIGN MODULE] <── Just swap this file based on the game!
          +
[4. The Chat History & Tools]

---

[ Player Inputs Action ]
            │
            ▼
┌────────────────────────────────────────────────────────┐
│ 1. PYTHON DATABASE GATEWAY (Beanie ODM)                │
├────────────────────────────────────────────────────────┤
│ • Looks up character's current 'room_id' from Session. │
│ • Pulls the strict 'RoomContext' from MongoDB.         │
└────────────────────────────────────────────────────────┘
            │
            ▼
┌────────────────────────────────────────────────────────┐
│ 2. JINJA2 PROMPT CONSTRUCT (templates/rule_check.j2)   │
├────────────────────────────────────────────────────────┤
│ • Stitches: Rulebooks + Character Sheet + Room Hazards  │
│ • Completely leaves out past chat logs.                │
└────────────────────────────────────────────────────────┘
            │
            ▼
┌────────────────────────────────────────────────────────┐
│ 3. RULE CHECK MODEL EVALUATION (Gemini 3.1 Flash-Lite)  │
├────────────────────────────────────────────────────────┤
│ • Reads: "Action: I leap the chasm."                   │
│ • Reads: "Room Hazard: 200ft wide open pit (Jump = Imp)"│
│ • Outputs: Rejection block instantly.                  │
└────────────────────────────────────────────────────────┘

---

=========================================================================================================
                        D&D DISCORD BOT: METADATA & SESSION DELTA LOOP ARCHITECTURE
=========================================================================================================

  [ 1. CHARACTER SHEET LOAD / SESSION SETUP ]
  
     [ D&D Beyond URL Link ]                          [ Google Drive Module Link ]
               │                                                    │
               ▼                                                    ▼
     [ Python HTTP Request ]                              [ Python HTTP Request ]
               │                                                    │
               ▼                                                    ▼
      [ LLM SMART PARSER ]                               [ GOOGLE DRIVE EXTRACTOR ]
     (Cleans messy nested JSON)                           (Converts PDF/Doc to Markdown)
               │                                                    │
               ▼                                                    ▼
   [ SQLite: CACHED BASELINE DATA ]                       [ GEMINI FILE API STORAGE ]
   • Overwrites: base_skills, base_ac, stats              • Uploads 200k+ token module text
   • Preserves: mid-session HP/slots deltas               • Returns a fixed 'Gemini File URI'
               │                                                    │
               └─────────────────────────┬──────────────────────────┘
                                         │
                                         ▼
                     [ /join_session OR /start_campaign COMMAND ]
                     • Binds Discord Channel ID to active Module URI.
                     • Pulls & merges local Session Deltas with Baseline sheet stats.
                     • System is now primed and ready for player turns.
                                         │
                                         ▼
=========================================================================================================
  [ 2. ACTIVE TACTICAL GAMEPLAY LOOP ]
  
                                  [ PLAYER CHAT INPUT ]
                  (e.g., "Thia casts Misty Step to teleport past the trap")
                                         │
                                         ▼
                      ┌─────────────────────────────────────────────────────┐
                      │ 2A. PYTHON REGEX & STATE PARSER                     │
                      ├─────────────────────────────────────────────────────┤
                      │ • Wrapped in ((brackets))? ──► Ignore as OOC        │
                      │ • Starts with prefix (!)?  ──► Query SQLite & Reply │
                      │ • Natural Game Action?     ──► Forward to step 2B   │
                      └─────────────────────────────────────────────────────┘
                                         │
                                         ▼
                      ┌─────────────────────────────────────────────────────┐
                      │ 2B. RULE CHECK MODEL (Gemini 3.1 Flash-Lite)        │
                      ├─────────────────────────────────────────────────────┤
                      │ • Reads: Player Action + Merged Character State     │
                      │ • Task: Enforces rules text (PHB/Monster Manual)    │
                      │                                                     │
                      │    ├── [REJECT] ──► "Out of range / slots" ──► Stop │
                      │    └── [APPROVE] ──► Output structured JSON:         │
                      │                      {"action_valid": true,         │
                      │                       "roll_type": "Spellcasting",  │
                      │                       "target_dc": 14}              │
                      └─────────────────────────────────────────────────────┘
                                         │
                                         ▼
                      ┌─────────────────────────────────────────────────────┐
                      │ 2C. BOT INTERRUPT & COMPONENT GENERATION            │
                      ├─────────────────────────────────────────────────────┤
                      │ • Python pauses the generative LLM pipeline.        │
                      │ • Locks player channel to prevent input spamming.   │
                      │ • Bot posts Discord Embed + Interactive Component:  │
                      │   "Thia casts Misty Step! [Click to Roll Arcana]"   │
                      └─────────────────────────────────────────────────────┘
                                         │
                                         ▼  ( Player physically clicks the button 🔘 )
                      ┌─────────────────────────────────────────────────────┐
                      │ 2D. DETERMINISTIC RESOLUTION ENGINE                 │
                      ├─────────────────────────────────────────────────────┤
                      │ • Python server rolls secure server-side 1d20.      │
                      │ • Fetches modifier from SQLite `base_skills_json`.  │
                      │ • Calculates: [1d20] + [Modifier] vs [Target DC].  │
                      │ • Edits Discord embed to show mathematical success. │
                      │ • MUTATES SESSION DELTA: Deducts spell slot inside  │
                      │   `session_used_slots_json` in the SQLite row.      │
                      └─────────────────────────────────────────────────────┘
                                         │
                                         ▼
                      ┌─────────────────────────────────────────────────────┐
                      │ 2E. DM NARRATOR MODEL (Gemini 3.1 Flash-Lite + CACHE)│
                      ├─────────────────────────────────────────────────────┤
                      │ • Context: Loads cached Campaign Module via File URI│
                      │ • Input Payload: Action + Roll Result + State Delta │
                      │ • Task: Extracts local room descriptions/hazards    │
                      │         from the book, weaves cinematic narrative    │
                      │         using the "Rule of Cool" framework.         │
                      └─────────────────────────────────────────────────────┘
                                         │
                                         ▼
                            [ FINAL PRESENTATION LAYER ]
                            • Bot posts narrative text block to Discord.
                            • Unlocks channel for the next player initiative.


# notes:
- implement In-Memory Lock/Queue system (`asyncio.Lock()`) to prevent double click errors
- swap SQLite to Beanie with MongoDB
- Pydantic (already using)
- cache character sheets at start of session
- add Discord.ui.View and discrod.ui.Button in game_loop cog
- use Jinja2 to pass alone old_state, new_state, and action to from python engine -> dm_narrator




File Structure

dnd-discord-bot/
├── .env                       # Local developer API keys (never commit to git)
├── .gitignore                 # Excludes node_modules, .env, __pycache__, volumes
├── docker-compose.yml         # Container configuration file
├── Dockerfile                 # Image build instructions for your Python bot
├── requirements.txt           # Pip dependencies (discord.py, beanie, motor, google-genai, jinja2)
├── README.md                  # System flowchart and documentation
│
└── src/                       # Master application directory
    ├── __init__.py
    ├── main.py                # Bot entrance file (initializes Discord, Motor, & Beanie)
    │
    ├── config/                # Environment and settings configuration
    │   ├── __init__.py
    │   └── settings.py        # Loads and validates environment variables
    │
    ├── database/              # Beanie ODM schemas & database connections
    │   ├── __init__.py
    │   ├── connection.py      # Contains the init_database() function
    │   └── models.py          # CharacterSheet, GameSession, CampaignModule schemas
    │
    ├── cogs/                  # Discord application feature separation
    │   ├── __init__.py
    │   ├── setup_cog.py       # Handles /load_module and /join_session commands
    │   ├── status_cog.py      # Handles !status and character profile display
    │   ├── action_cog.py      # Core In-Character tactical game & rolling buttons loop
    │   └── lorekeeper_cog.py  # Out-of-Character @bot mention reference assistant
    │
    ├── services/              # External heavy business logic handlers
    │   ├── __init__.py
    │   ├── ddb_parser.py      # The LLM Smart Parser script for D&D Beyond sheets and google drive modules [MarkItDown or Document Understanding API] for downloading and converting into markdown and then LLM to map out into json based of schema
    │   ├── gemini_client.py   # Handles the connection client & token cache updates
    │   └── game_engine.py     # Pure game calculation helper routines (e.g., dice rolls)
    │
    └── templates/             # Prompt engineering file directory
        ├── narrator_prompt.j2 # Jinja2 storytelling prompt template
        └── rule_check.j2      # Jinja2 tactical evaluation mechanics prompt
