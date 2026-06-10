# DnD Discord Dungeon Master Bot

An AI-driven Dungeon Master bot for Discord that allows players bring their own character sheets from DnD Beyond, play D&D modules, and roleplay without needing an experienced human Dungeon Master!

The bot uses a multi-model AI pipeline with MongoDB to track game state and Gemini 3.1 Flash Lite for context caching and swift replies.

---

## AI Model

The bot uses Google's Gemini 3.1 Flash Lite model for its AI capabilities. Currently there is no support for other models, but this may change in the future.
Only the Flash Lite model is supported due to its low cost, high speed, and most imporantly its ability to cache context for the duration of a game session.
The

---

## Technical Stack

- Language: Python 3
- Discord Framework: discord.py (utilizing the commands.Bot framework with a Cog-based modular architecture).
- Database & ODM:
  - MongoDB: NoSQL database for persistence.
  - Beanie: An asynchronous ODM (Object Document Mapper) built on top of motor and pydantic.
  - Motor: The underlying asynchronous driver for MongoDB.
- AI/LLM Integration: google-genai (Google Gemini SDK).
- Configuration & Validation: pydantic and pydantic-settings for robust environment variable management (supporting .env files).
- Templating: Jinja2 (used for dynamic prompt and response formatting).
- Runtime: asyncio for non-blocking I/O operations, which is essential for handling multiple Discord events concurrently.

---

## Dependencies
- MongoDB: Used for database operations, with pymongo and motor as drivers.
- Beanie: An asynchronous ORM for MongoDB, used in conjunction with Motor.
- Pydantic: A data validation and settings management library, used for configuration management.
- Discord.py: A Python wrapper for the Discord API, used to create a bot.
- pydantic-settings: Extends Pydantic to manage application settings from environment variables.
- google-genai: Presumably a client for Google's GenAI services.
- Jinja2: A templating engine for generating dynamic content.

## MongoDB External Container
  - `docker-compose.yml` add .env variables `MONGO_ROOT_USER=<admin>` and `MONGO_ROOT_PASS=<password>`
  ```
  services:
    mongodb:
      image: mongo:latest
      container_name: mongodb-dnd
      restart: unless-stopped
      ports:
        - "27017:27017"
      environment:
        MONGO_INITDB_ROOT_USERNAME: ${MONGO_ROOT_USER}
        MONGO_INITDB_ROOT_PASSWORD: ${MONGO_ROOT_PASS}
      networks:
        - dnd_shared_network
      volumes:
        - mongo_data:/data/db

  networks:
    dnd_shared_network:
      external: true
  volumes:
    mongo_data:
  ```

  Then run `docker-compose up --build -d`

## Required Environment Variables

- `DISCORD_BOT_TOKEN`: Your Discord bot token.
- `MONGO_URI`: The connection URI for your MongoDB database.
- `GEMINI_API_KEY`: Your Google API key for accessing GenAI services.

`.env`
```
DISCORD_BOT_TOKEN=<YOUR_TOKEN_GOES_HERE>
GEMINI_API_KEY=<YOUR_API_KEY_GOES_HERE>
MONGO_URI=mongodb://<admin>:<password>@mongodb:27017/dnd_bot?authSource=admin
```


optional:
- `WHITELIST_CHANNEL_IDS` - a comma-separated list of Discord channel IDs where the bot is allowed to operate.

---

## Quick Start
- `./deploy.sh` - deployment command, creates network between Bot container and MongoDB container

---

                      
                MASTER D&D DISCORD BOT FLOWCHART (MONGO + BEANIE + CACHE + JINJA2)
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
  ensure that the lock is **keyed to the Discord channel or User ID**. If you lock globally, you will accidentally bottleneck your entire bot to one action at a time across all servers. Use a `dict` of `asyncio.Lock()` objects:
    ```python
    self.locks = collections.defaultdict(asyncio.Lock)
    # ... inside your action handler ...
    async with self.locks[channel_id]:
        # Process turn
    ```
  disabling the button immediately upon the first interaction:
    ```python
    async def callback(self, interaction: discord.Interaction):
        self.disabled = True
        await interaction.response.edit_message(view=self)
        # Proceed with logic...

[] cache character sheets at start of session
[] implement rule of cool nat 20 success override
[] implement inspiration (gain advantage on next roll)
[] setup payment for Gemini 3.1 Flash Lite - Pay As You Go (PAYG) plan to enable Context Caching
[] setup Time-to-Live (TTL) so that it debounces for 30 minutes after every action
[] clear Time-to-Live upon /end_session