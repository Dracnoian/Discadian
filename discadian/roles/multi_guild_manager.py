import discord
import logging
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger(__name__)

class MultiGuildManager:
    def __init__(self, bot):
        self.bot = bot
        # Import config_manager here to avoid circular imports
        from config import config_manager
        self.config_manager = config_manager
    
    def get_nation_config(self, nation_name: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific nation"""
        return self.config_manager.get_nation_config(nation_name)
    
    def get_nation_by_guild_id(self, guild_id: int) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Find nation configuration by guild ID"""
        return self.config_manager.get_nation_by_guild_id(guild_id)
    
    def get_guild_for_nation(self, nation_name: str) -> Optional[discord.Guild]:
        """Get Discord guild for a nation"""
        nation_config = self.get_nation_config(nation_name)
        if not nation_config:
            return None
        
        guild_id = nation_config.get("guild_id")
        if guild_id:
            return self.bot.get_guild(guild_id)
        return None
    
    def is_admin_in_nation(self, user: discord.Member, nation_name: str) -> bool:
        """Check if user has admin permissions for a specific nation"""
        nation_config = self.get_nation_config(nation_name)
        if not nation_config:
            return False
        
        admin_role_ids = nation_config.get("admin_role_ids", [])
        return any(role.id in admin_role_ids for role in user.roles)
    
    def is_approved_guild_for_nation(self, guild_id: int, nation_name: str) -> bool:
        """Check if guild is the approved guild for a nation"""
        nation_config = self.get_nation_config(nation_name)
        if not nation_config:
            return False
        return nation_config.get("guild_id") == guild_id
    
    def get_all_approved_guilds(self) -> List[int]:
        """Get all approved guild IDs"""
        return self.config_manager.get_all_approved_guilds()
    
    def get_approved_nations(self) -> List[str]:
        """Get list of all approved nations"""
        return self.config_manager.get_approved_nations()
    
    async def assign_roles_for_nation(self, member: discord.Member, ign: str, nation_name: str,
                                    is_mayor: bool = False, county: str = None, 
                                    county_role_id: int = None) -> bool:
        """Assign roles for a specific nation in its guild"""
        try:
            nation_config = self.get_nation_config(nation_name)
            if not nation_config:
                logger.error(f"No configuration found for nation: {nation_name}")
                return False
            
            guild = member.guild
            roles_to_add = []
            
            # Verified role
            verified_role_id = nation_config.get("verified_role_id")
            if verified_role_id:
                verified_role = guild.get_role(verified_role_id)
                if verified_role and verified_role not in member.roles:
                    roles_to_add.append(verified_role)
            
            # Mayor role
            if is_mayor:
                mayor_role_id = nation_config.get("mayor_role_id")
                if mayor_role_id:
                    mayor_role = guild.get_role(mayor_role_id)
                    if mayor_role and mayor_role not in member.roles:
                        roles_to_add.append(mayor_role)
            
            # County role
            if county_role_id:
                county_role = guild.get_role(county_role_id)
                if county_role and county_role not in member.roles:
                    roles_to_add.append(county_role)
            elif county is None:
                # Assign "no county" role if applicable
                county_system = nation_config.get("county_system", {})
                if county_system.get("enabled", False):
                    no_county_role_id = county_system.get("no_county_role_id")
                    if no_county_role_id:
                        no_county_role = guild.get_role(no_county_role_id)
                        if no_county_role and no_county_role not in member.roles:
                            roles_to_add.append(no_county_role)
            
            # Add roles
            if roles_to_add:
                await member.add_roles(*roles_to_add, reason=f"EarthMC Verification - {nation_name}")
                logger.info(f"Added {len(roles_to_add)} roles to {member.display_name} in {guild.name}")
            
            # Set nickname
            nickname_format = nation_config.get("nickname_format", "{ign} ({nation})")
            nickname = nickname_format.format(ign=ign, nation=nation_name)
            try:
                if member.nick != nickname:
                    await member.edit(nick=nickname, reason=f"EarthMC Verification - {nation_name}")
            except discord.Forbidden:
                logger.warning(f"Cannot change nickname for {member.display_name} - insufficient permissions")
            
            return True
            
        except Exception as e:
            logger.error(f"Error assigning roles for nation {nation_name}: {e}")
            return False
    
    async def revoke_nation_roles(self, member: discord.Member, nation_name: str) -> bool:
        """Revoke all nation-specific roles from a member"""
        try:
            nation_config = self.get_nation_config(nation_name)
            if not nation_config:
                return False
            
            guild = member.guild
            roles_to_remove = []
            
            # Verified role
            verified_role_id = nation_config.get("verified_role_id")
            if verified_role_id:
                verified_role = guild.get_role(verified_role_id)
                if verified_role and verified_role in member.roles:
                    roles_to_remove.append(verified_role)
            
            # Mayor role
            mayor_role_id = nation_config.get("mayor_role_id")
            if mayor_role_id:
                mayor_role = guild.get_role(mayor_role_id)
                if mayor_role and mayor_role in member.roles:
                    roles_to_remove.append(mayor_role)
            
            # County roles
            county_system = nation_config.get("county_system", {})
            if county_system.get("enabled", False):
                # Remove all county roles
                for county_data in county_system.get("counties", {}).values():
                    county_role_id = county_data.get("role_id")
                    if county_role_id:
                        county_role = guild.get_role(county_role_id)
                        if county_role and county_role in member.roles:
                            roles_to_remove.append(county_role)
                
                # Remove "no county" role
                no_county_role_id = county_system.get("no_county_role_id")
                if no_county_role_id:
                    no_county_role = guild.get_role(no_county_role_id)
                    if no_county_role and no_county_role in member.roles:
                        roles_to_remove.append(no_county_role)
            
            # Revocation roles
            revocation_role_ids = nation_config.get("revocation_roles", [])
            for role_id in revocation_role_ids:
                role = guild.get_role(role_id)
                if role and role in member.roles:
                    roles_to_remove.append(role)
            
            # Remove roles
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason=f"EarthMC Nation Departure - {nation_name}")
                logger.info(f"Removed {len(roles_to_remove)} roles from {member.display_name} in {guild.name}")
            
            # Reset nickname
            try:
                await member.edit(nick=None, reason=f"EarthMC Nation Departure - {nation_name}")
            except discord.Forbidden:
                logger.warning(f"Cannot reset nickname for {member.display_name} - insufficient permissions")
            
            return True
            
        except Exception as e:
            logger.error(f"Error revoking nation roles for {nation_name}: {e}")
            return False
    
    async def sync_user_across_guilds(self, discord_id: str, ign: str, new_nation: str,
                                    old_nation: str = None, is_mayor: bool = False,
                                    county: str = None, county_role_id: int = None):
        """Synchronize user roles across all relevant guilds"""
        try:
            if not self.config_manager.get_cross_guild_setting("sync_role_updates", True):
                logger.debug("Cross-guild role sync disabled")
                return
            
            discord_user_id = int(discord_id)
            
            # Remove from old nation's guild if different
            if old_nation and old_nation != new_nation:
                old_guild = self.get_guild_for_nation(old_nation)
                if old_guild:
                    old_member = old_guild.get_member(discord_user_id)
                    if old_member:
                        await self.revoke_nation_roles(old_member, old_nation)
                        logger.info(f"Revoked {old_nation} roles from {ign} in {old_guild.name}")
            
            # Add to new nation's guild
            new_guild = self.get_guild_for_nation(new_nation)
            if new_guild:
                new_member = new_guild.get_member(discord_user_id)
                if new_member:
                    await self.assign_roles_for_nation(
                        new_member, ign, new_nation, is_mayor, county, county_role_id
                    )
                    logger.info(f"Assigned {new_nation} roles to {ign} in {new_guild.name}")
                else:
                    logger.debug(f"User {ign} not found in {new_nation} guild {new_guild.name}")
            
        except Exception as e:
            logger.error(f"Error syncing user across guilds: {e}")
    
    async def handle_role_updates_multi_guild(self, member: discord.Member, ign: str, new_nation: str,
                                            is_mayor: bool = False, county: str = None,
                                            county_role_id: int = None,
                                            existing_verification: Dict[str, Any] = None) -> bool:
        """Handle role updates with multi-guild support and allied/foreigner role transitions"""
        try:
            # Get current guild's nation
            guild_nation_data = self.get_nation_by_guild_id(member.guild.id)
            if not guild_nation_data:
                logger.error(f"No nation configuration found for guild {member.guild.id}")
                return False
            
            guild_nation, _ = guild_nation_data
            
            # Get player's new nation UUID
            from api.earthmc import get_player_info
            player_result = await get_player_info(ign)
            new_nation_uuid = None
            
            if player_result["success"]:
                player_data = player_result["data"]
                nation_data = player_data.get("nation", {})
                new_nation_uuid = nation_data.get("uuid")
            
            # Get old relationship status
            old_nation_uuid = existing_verification.get('nation_uuid') if existing_verification else None
            old_relationship = self.determine_relationship_status(guild_nation, old_nation_uuid) if old_nation_uuid else 'foreigner'
            
            # Get new relationship status
            new_relationship = self.determine_relationship_status(guild_nation, new_nation_uuid) if new_nation_uuid else 'foreigner'
            
            logger.info(f"Role update for {ign}: {old_relationship} → {new_relationship} in guild {guild_nation}")
            
            # Remove old relationship-specific roles if relationship changed
            if old_relationship != new_relationship:
                await self.remove_relationship_roles(member, guild_nation, old_relationship)
            
            # Assign new roles based on new relationship
            success = await self.assign_roles_for_nation(
                member, ign, new_nation, is_mayor, county, county_role_id,
                new_nation_uuid, guild_nation
            )
            
            # Sync across other guilds if enabled
            if success and existing_verification:
                old_nation = existing_verification.get('nation')
                await self.sync_user_across_guilds(
                    str(member.id), ign, new_nation, old_nation, is_mayor, county, county_role_id
                )
            
            return success
            
        except Exception as e:
            logger.error(f"Error handling multi-guild role updates for {ign}: {e}")
            return False

    async def remove_relationship_roles(self, member: discord.Member, nation_name: str, relationship: str):
        """Remove relationship-specific roles (allied, foreigner, citizen-only roles)"""
        try:
            nation_config = self.get_nation_config(nation_name)
            if not nation_config:
                return
            
            guild = member.guild
            roles_to_remove = []
            
            if relationship == 'allied':
                # Remove allied role
                allied_role_id = nation_config.get("allied_role_id")
                if allied_role_id:
                    allied_role = guild.get_role(allied_role_id)
                    if allied_role and allied_role in member.roles:
                        roles_to_remove.append(allied_role)
                        
            elif relationship == 'foreigner':
                # Remove foreigner role
                foreigner_role_id = nation_config.get("foreigner_role_id")
                if foreigner_role_id:
                    foreigner_role = guild.get_role(foreigner_role_id)
                    if foreigner_role and foreigner_role in member.roles:
                        roles_to_remove.append(foreigner_role)
                        
            elif relationship == 'citizen':
                # Remove citizen-only roles (mayor, county roles)
                mayor_role_id = nation_config.get("mayor_role_id")
                if mayor_role_id:
                    mayor_role = guild.get_role(mayor_role_id)
                    if mayor_role and mayor_role in member.roles:
                        roles_to_remove.append(mayor_role)
                
                # Remove county roles
                county_system = nation_config.get("county_system", {})
                if county_system.get("enabled", False):
                    for county_data in county_system.get("counties", {}).values():
                        county_role_id = county_data.get("role_id")
                        if county_role_id:
                            county_role = guild.get_role(county_role_id)
                            if county_role and county_role in member.roles:
                                roles_to_remove.append(county_role)
                    
                    # Remove "no county" role
                    no_county_role_id = county_system.get("no_county_role_id")
                    if no_county_role_id:
                        no_county_role = guild.get_role(no_county_role_id)
                        if no_county_role and no_county_role in member.roles:
                            roles_to_remove.append(no_county_role)
            
            # Remove the roles
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason=f"EarthMC Relationship Change - {nation_name}")
                logger.info(f"Removed {len(roles_to_remove)} old relationship roles from {member.display_name}")
                
        except Exception as e:
            logger.error(f"Error removing relationship roles: {e}")

    async def update_user_relationship_across_guilds(self, discord_id: str, ign: str, new_nation_uuid: str, new_nation_name: str):
        """Update user's relationship status across all guilds where they're verified"""
        try:
            if not self.config_manager.get_cross_guild_setting("sync_role_updates", True):
                logger.debug("Cross-guild role sync disabled")
                return
            
            discord_user_id = int(discord_id)
            updated_guilds = []
            
            # Check all nation guilds
            nations = self.config_manager.get("nations", {})
            for guild_nation_name, nation_config in nations.items():
                guild_id = nation_config.get("guild_id")
                if not guild_id:
                    continue
                
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    continue
                
                member = guild.get_member(discord_user_id)
                if not member:
                    continue
                
                # Check if member has verified role in this guild
                verified_role_id = nation_config.get("verified_role_id")
                verified_role = guild.get_role(verified_role_id) if verified_role_id else None
                
                if not verified_role or verified_role not in member.roles:
                    continue  # User not verified in this guild
                
                # Determine new relationship
                new_relationship = self.determine_relationship_status(guild_nation_name, new_nation_uuid)
                
                # Get current relationship by checking existing roles
                current_relationship = self.get_current_relationship(member, nation_config)
                
                if current_relationship != new_relationship:
                    logger.info(f"Updating relationship for {ign} in {guild_nation_name}: {current_relationship} → {new_relationship}")
                    
                    # Remove old relationship roles
                    await self.remove_relationship_roles(member, guild_nation_name, current_relationship)
                    
                    # Add new relationship roles (determine county for citizens)
                    county_name = None
                    county_role_id = None
                    is_mayor = False  # We'll need to get this from verification cache
                    
                    # Get verification data for mayor status
                    from utils.verification_cache import verification_cache
                    user_data = verification_cache.get_verified_user_by_discord_id(discord_id)
                    if user_data:
                        is_mayor = user_data.get('is_mayor', False)
                        if new_relationship == 'citizen':
                            county_name = user_data.get('county')
                            # Get county role ID
                            if county_name:
                                county_system = nation_config.get("county_system", {})
                                county_data = county_system.get("counties", {}).get(county_name)
                                if county_data:
                                    county_role_id = county_data.get("role_id")
                    
                    # Assign new roles
                    await self.assign_roles_for_nation(
                        member, ign, new_nation_name, is_mayor, county_name, county_role_id,
                        new_nation_uuid, guild_nation_name
                    )
                    
                    updated_guilds.append(guild_nation_name)
            
            if updated_guilds:
                logger.info(f"Updated relationship for {ign} across {len(updated_guilds)} guilds: {updated_guilds}")
                
        except Exception as e:
            logger.error(f"Error updating user relationship across guilds: {e}")

    def get_current_relationship(self, member: discord.Member, nation_config: Dict[str, Any]) -> str:
        """Determine current relationship status by checking member's roles"""
        try:
            # Check for allied role
            allied_role_id = nation_config.get("allied_role_id")
            if allied_role_id:
                allied_role = member.guild.get_role(allied_role_id)
                if allied_role and allied_role in member.roles:
                    return 'allied'
            
            # Check for foreigner role
            foreigner_role_id = nation_config.get("foreigner_role_id")
            if foreigner_role_id:
                foreigner_role = member.guild.get_role(foreigner_role_id)
                if foreigner_role and foreigner_role in member.roles:
                    return 'foreigner'
            
            # Check for citizen-specific roles (mayor or county roles)
            mayor_role_id = nation_config.get("mayor_role_id")
            if mayor_role_id:
                mayor_role = member.guild.get_role(mayor_role_id)
                if mayor_role and mayor_role in member.roles:
                    return 'citizen'
            
            # Check county roles
            county_system = nation_config.get("county_system", {})
            if county_system.get("enabled", False):
                for county_data in county_system.get("counties", {}).values():
                    county_role_id = county_data.get("role_id")
                    if county_role_id:
                        county_role = member.guild.get_role(county_role_id)
                        if county_role and county_role in member.roles:
                            return 'citizen'
                
                # Check "no county" role
                no_county_role_id = county_system.get("no_county_role_id")
                if no_county_role_id:
                    no_county_role = member.guild.get_role(no_county_role_id)
                    if no_county_role and no_county_role in member.roles:
                        return 'citizen'
            
            # Default to citizen if they have verified role but no specific relationship role
            return 'citizen'
            
        except Exception as e:
            logger.error(f"Error determining current relationship: {e}")
            return 'citizen'
    
    async def send_contradiction_report(self, nation_name: str, contradiction_data: str):
        """Send contradiction report to nation-specific channel"""
        try:
            nation_config = self.get_nation_config(nation_name)
            if not nation_config:
                # Fallback to global channel
                global_channel_id = self.config_manager.get_global_setting("contradiction_channel_id")
                channel = self.bot.get_channel(global_channel_id) if global_channel_id else None
            else:
                contradiction_channel_id = nation_config.get("contradiction_channel_id")
                channel = self.bot.get_channel(contradiction_channel_id) if contradiction_channel_id else None
            
            if channel:
                embed = discord.Embed(
                    title="🚨 Link Contradiction Report",
                    description=contradiction_data,
                    color=0xff0000,
                    timestamp=discord.utils.utcnow()
                )
                embed.add_field(name="Nation", value=nation_name, inline=True)
                await channel.send(embed=embed)
            else:
                logger.error(f"No contradiction channel configured for nation {nation_name}")
                
        except Exception as e:
            logger.error(f"Error sending contradiction report for {nation_name}: {e}")
    
    def get_county_system_for_nation(self, nation_name: str) -> Dict[str, Any]:
        """Get county system configuration for a nation"""
        nation_config = self.get_nation_config(nation_name)
        if not nation_config:
            return {}
        return nation_config.get("county_system", {})
    
    def get_county_for_town_in_nation(self, nation_name: str, town_uuid: str) -> Tuple[Optional[str], Optional[int], bool]:
        """Get county information for a town UUID in a specific nation"""
        county_system = self.get_county_system_for_nation(nation_name)
        
        if not county_system.get("enabled", False):
            return None, None, True  # Nation doesn't use county system
        
        # Check if town UUID is in any county
        for county_name, county_data in county_system.get("counties", {}).items():
            if town_uuid in county_data.get("towns", []):
                return county_name, county_data.get("role_id"), True
        
        # Town not in any county
        no_county_role_id = county_system.get("no_county_role_id")
        return None, no_county_role_id, False

# Global instance
multi_guild_manager = None

def get_multi_guild_manager(bot=None):
    """Get or create the multi-guild manager instance"""
    global multi_guild_manager
    if multi_guild_manager is None and bot:
        multi_guild_manager = MultiGuildManager(bot)
    return multi_guild_manager