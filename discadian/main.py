import discord
from discord.ext import commands
import logging
import os
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import configuration
from config import config_manager

# Import utilities
from utils.cache import cache_manager
from utils.verification_cache import verification_cache

# Import role management
from roles.multi_guild_manager import get_multi_guild_manager

# Import command modules
from county.commands import setup_county_commands
from verification.commands import setup_verification_commands
from utils.admin_commands import setup_admin_commands

# Import periodic verification
from verification.periodic import setup_periodic_verification

class VerificationBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True
        super().__init__(command_prefix='!', intents=intents)

    async def setup_hook(self):
        # Initialize multi-guild manager
        get_multi_guild_manager(self)
        
        # Setup command modules
        setup_county_commands(self)
        setup_verification_commands(self)
        setup_admin_commands(self)
        
        # Setup periodic verification
        self.periodic_verification = setup_periodic_verification(self)
        
        # Sync slash commands
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} command(s)")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")

bot = VerificationBot()

@bot.event
async def on_ready():
    logger.info(f'{bot.user} has connected to Discord!')
    logger.info(f'Bot is ready for EarthMC verification!')
    
    # Clean up expired cache entries on startup
    expired_count = cache_manager.cleanup_expired()
    if expired_count > 0:
        logger.info(f"Cleaned up {expired_count} expired cache entries on startup")

if __name__ == "__main__":
    bot_token = config_manager.get("bot_token")
    if not bot_token or bot_token == "YOUR_BOT_TOKEN_HERE":
        logger.error("Bot token not configured! Please set your bot token in config.json")
        exit(1)
    
    logger.info("Starting Discadian bot...")
    try:
        bot.run(bot_token)
    except Exception as e:
        logger.error(f"Bot failed to start: {e}")
        import traceback
        traceback.print_exc()