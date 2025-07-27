import discord
from typing import Optional
from config import config_manager

def get_multi_guild_manager():
    """Import function to avoid circular imports"""
    from roles.multi_guild_manager import get_multi_guild_manager
    return get_multi_guild_manager()

def has_admin_permission(user: discord.Member, nation_name: str = None) -> bool:
    """
    Check if user has admin permission for a specific nation or any nation
    
    Args:
        user: Discord member to check
        nation_name: Specific nation to check permissions for (optional)
    
    Returns:
        bool: True if user has admin permissions
    """
    if not user or not user.guild:
        return False
    
    mgm = get_multi_guild_manager()
    if not mgm:
        return False
    
    # If specific nation is provided, check only that nation
    if nation_name:
        return mgm.is_admin_in_nation(user, nation_name)
    
    # Otherwise, check if user is admin in the nation for their current guild
    nation_data = mgm.get_nation_by_guild_id(user.guild.id)
    if nation_data:
        nation_name, _ = nation_data
        return mgm.is_admin_in_nation(user, nation_name)
    
    return False

def is_approved_guild(guild_id: int) -> bool:
    """Check if guild is approved for any nation"""
    mgm = get_multi_guild_manager()
    if not mgm:
        return False
    
    approved_guilds = mgm.get_all_approved_guilds()
    return guild_id in approved_guilds

def get_nation_for_guild(guild_id: int) -> Optional[str]:
    """Get the nation name for a specific guild"""
    mgm = get_multi_guild_manager()
    if not mgm:
        return None
    
    nation_data = mgm.get_nation_by_guild_id(guild_id)
    return nation_data[0] if nation_data else None

def can_verify_for_nation(user: discord.Member, target_nation: str) -> bool:
    """
    Check if user can verify players for a specific nation
    
    Args:
        user: Discord member attempting verification
        target_nation: Nation they want to verify for
    
    Returns:
        bool: True if verification is allowed
    """
    if not user or not user.guild:
        return False
    
    mgm = get_multi_guild_manager()
    if not mgm:
        return False
    
    # Check if user has admin permissions for the target nation
    if mgm.is_admin_in_nation(user, target_nation):
        return True
    
    # Check cross-guild verification settings
    cross_guild_settings = config_manager.get("cross_guild_settings", {})
    allow_cross_nation = cross_guild_settings.get("allow_cross_nation_verification", False)
    
    if not allow_cross_nation:
        # Only allow verification if user is in the same nation's guild
        user_nation = get_nation_for_guild(user.guild.id)
        return user_nation == target_nation
    
    # If cross-nation verification is allowed, check if user is admin in any nation
    nations = config_manager.get("nations", {})
    for nation_name in nations.keys():
        if mgm.is_admin_in_nation(user, nation_name):
            return True
    
    return False

def get_user_nations(user: discord.Member) -> list:
    """Get list of nations where user has admin permissions"""
    if not user:
        return []
    
    mgm = get_multi_guild_manager()
    if not mgm:
        return []
    
    admin_nations = []
    nations = config_manager.get("nations", {})
    
    for nation_name in nations.keys():
        if mgm.is_admin_in_nation(user, nation_name):
            admin_nations.append(nation_name)
    
    return admin_nations