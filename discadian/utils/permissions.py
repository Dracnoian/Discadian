import discord
from config import config_manager

def has_admin_permission(user: discord.Member) -> bool:
    """Check if user has admin permission"""
    admin_role_ids = config_manager.get("admin_role_ids", [])
    return any(role.id in admin_role_ids for role in user.roles)

def is_approved_guild(guild_id: int) -> bool:
    """Check if guild is approved"""
    approved_guilds = config_manager.get("approved_guilds", [])
    return guild_id in approved_guilds