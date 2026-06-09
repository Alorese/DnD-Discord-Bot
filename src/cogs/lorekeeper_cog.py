from discord.ext import commands
from google import genai
from config.settings import settings

class LorekeeperCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # The Gemini client instantly gains access to your card-authenticated token key
        self.client = genai.Client(api_key=settings.gemini_api_key)
