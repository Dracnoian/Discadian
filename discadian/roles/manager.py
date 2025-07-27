import discord
import logging
from config import config_manager
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

async def assign_roles_and_nickname(member: discord.Member, ign: str, nation: str, 
                                   is_mayor: bool = False, county: str = None, 
                                   county_role_id: int = None) -> bool:
    """Assign roles and nickname to verified member"""
    try:
        guild = member.guild
        
        # Get verified role by ID
        verified_role_id = config_manager.get("verified_role_id")
        verified_role = guild.get_role(verified_role_id) if verified_role_id else None
        if not verified_role:
            logger.warning(f"Verified role with ID {verified_role_id} not found")
        
        # Get nation-specific role by ID
        nation_roles = config_manager.get("nation_roles", {})
        nation_role = None
        if nation in nation_roles:
            nation_role = guild.get_role(nation_roles[nation])
            if not nation_role:
                logger.warning(f"Nation role with ID {nation_roles[nation]} not found")
        
        # Get mayor role if applicable
        mayor_role = None
        if is_mayor:
            mayor_role_id = config_manager.get("mayor_role_id")
            mayor_role = guild.get_role(mayor_role_id) if mayor_role_id else None
            if not mayor_role:
                logger.warning(f"Mayor role with ID {mayor_role_id} not found")
        
        # Get county role if applicable
        county_role = None
        if county_role_id:
            county_role = guild.get_role(county_role_id)
            if not county_role:
                logger.warning(f"County role with ID {county_role_id} not found")
        
        # Assign roles
        roles_to_add = []
        if verified_role:
            roles_to_add.append(verified_role)
        if nation_role:
            roles_to_add.append(nation_role)
        if mayor_role:
            roles_to_add.append(mayor_role)
        if county_role:
            roles_to_add.append(county_role)
        
        if roles_to_add:
            await member.add_roles(*roles_to_add, reason="EarthMC Verification")
        
        # Set nickname
        nickname_format = config_manager.get("nickname_format", "{ign} ({nation})")
        nickname = nickname_format.format(ign=ign, nation=nation)
        try:
            await member.edit(nick=nickname, reason="EarthMC Verification")
        except discord.Forbidden:
            logger.warning(f"Cannot change nickname for {member.display_name} - insufficient permissions")
        
        return True
    except Exception as e:
        logger.error(f"Error assigning roles/nickname: {e}")
        return False

async def handle_role_updates(member: discord.Member, ign: str, new_nation: str, 
                            is_mayor: bool = False, county: str = None, 
                            county_role_id: int = None, 
                            existing_verification: Dict[str, Any] = None) -> bool:
    """Handle role updates for re-verification using UUIDs for comparisons"""
    try:
        guild = member.guild
        
        # Get previous verification data with UUIDs
        old_nation = existing_verification.get('nation') if existing_verification else None
        old_nation_uuid = existing_verification.get('nation_uuid') if existing_verification else None
        old_town_uuid = existing_verification.get('town_uuid') if existing_verification else None
        old_county = existing_verification.get('county') if existing_verification else None
        old_is_mayor = existing_verification.get('is_mayor', False) if existing_verification else False
        
        # Get new nation UUID for comparison
        from api.earthmc import get_nation_info, get_player_info
        new_nation_uuid = None
        new_town_uuid = None
        
        # Get current player data to extract UUIDs
        player_result = await get_player_info(ign)
        if player_result["success"]:
            player_data = player_result["data"]
            nation_data = player_data.get("nation", {})
            town_data = player_data.get("town", {})
            new_nation_uuid = nation_data.get("uuid")
            new_town_uuid = town_data.get("uuid")
        
        logger.info(f"Re-verification role update: {member.display_name}")
        logger.info(f"  Old: Nation={old_nation} (UUID: {old_nation_uuid}), Town UUID: {old_town_uuid}, County={old_county}, Mayor={old_is_mayor}")
        logger.info(f"  New: Nation={new_nation} (UUID: {new_nation_uuid}), Town UUID: {new_town_uuid}, County={county}, Mayor={is_mayor}")
        
        # Determine if this is a significant change
        nation_changed = False
        if old_nation_uuid and new_nation_uuid:
            nation_changed = old_nation_uuid != new_nation_uuid
        elif old_nation and new_nation:
            nation_changed = old_nation != new_nation
        
        town_changed = old_town_uuid != new_town_uuid if old_town_uuid and new_town_uuid else False
        county_changed = old_county != county
        mayor_changed = old_is_mayor != is_mayor
        
        logger.info(f"  Changes: Nation={nation_changed}, Town={town_changed}, County={county_changed}, Mayor={mayor_changed}")
        
        # Get all relevant roles
        roles_to_add = []
        roles_to_remove = []
        
        # Verified role (should always be present)
        verified_role_id = config_manager.get("verified_role_id")
        verified_role = guild.get_role(verified_role_id) if verified_role_id else None
        if verified_role and verified_role not in member.roles:
            roles_to_add.append(verified_role)
        
        # Handle nation role changes
        nation_roles = config_manager.get("nation_roles", {})
        
        # Remove old nation role if nation changed
        if nation_changed and old_nation and old_nation in nation_roles:
            old_nation_role = guild.get_role(nation_roles[old_nation])
            if old_nation_role and old_nation_role in member.roles:
                roles_to_remove.append(old_nation_role)
                logger.info(f"  Removing old nation role: {old_nation_role.name}")
        
        # Add new nation role if not already present
        if new_nation in nation_roles:
            new_nation_role = guild.get_role(nation_roles[new_nation])
            if new_nation_role and new_nation_role not in member.roles:
                roles_to_add.append(new_nation_role)
                logger.info(f"  Adding new nation role: {new_nation_role.name}")
        
        # Handle mayor role changes
        mayor_role_id = config_manager.get("mayor_role_id")
        mayor_role = guild.get_role(mayor_role_id) if mayor_role_id else None
        
        if mayor_role:
            if is_mayor and mayor_role not in member.roles:
                roles_to_add.append(mayor_role)
                logger.info(f"  Adding mayor role: {mayor_role.name}")
            elif not is_mayor and mayor_role in member.roles:
                roles_to_remove.append(mayor_role)
                logger.info(f"  Removing mayor role: {mayor_role.name}")
        
        # Handle county role changes using UUIDs
        if nation_changed or town_changed or county_changed:
            await handle_county_role_changes(
                member, guild, new_nation_uuid, new_nation, old_county, county, 
                county_role_id, roles_to_add, roles_to_remove
            )
        
        # Handle nation departure - remove additional revocation roles
        approved_nations = config_manager.get("approved_nations", [])
        if nation_changed and old_nation and old_nation in approved_nations:
            # Check if they left an approved nation (not just switched)
            if new_nation not in approved_nations:
                revocation_roles = await get_revocation_roles(guild)
                for role in revocation_roles:
                    if role in member.roles:
                        roles_to_remove.append(role)
                        logger.info(f"  Removing revocation role: {role.name}")
        
        # Apply role changes
        if roles_to_remove:
            try:
                await member.remove_roles(*roles_to_remove, reason="EarthMC Re-verification")
                logger.info(f"Removed {len(roles_to_remove)} roles from {member.display_name}")
            except Exception as e:
                logger.error(f"Error removing roles from {member.display_name}: {e}")
        
        if roles_to_add:
            try:
                await member.add_roles(*roles_to_add, reason="EarthMC Re-verification")
                logger.info(f"Added {len(roles_to_add)} roles to {member.display_name}")
            except Exception as e:
                logger.error(f"Error adding roles to {member.display_name}: {e}")
        
        # Update nickname
        nickname_format = config_manager.get("nickname_format", "{ign} ({nation})")
        new_nickname = nickname_format.format(ign=ign, nation=new_nation)
        
        try:
            if member.nick != new_nickname:
                await member.edit(nick=new_nickname, reason="EarthMC Re-verification")
                logger.info(f"Updated nickname for {member.display_name} to {new_nickname}")
        except discord.Forbidden:
            logger.warning(f"Cannot change nickname for {member.display_name} - insufficient permissions")
        except Exception as e:
            logger.error(f"Error updating nickname for {member.display_name}: {e}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error handling role updates for {member.display_name}: {e}")
        return False

async def handle_county_role_changes(member: discord.Member, guild: discord.Guild, 
                                   new_nation_uuid: str, new_nation: str, 
                                   old_county: str, new_county: str, 
                                   new_county_role_id: int,
                                   roles_to_add: List[discord.Role], 
                                   roles_to_remove: List[discord.Role]):
    """Handle county role changes using UUID-based lookups"""
    try:
        county_system = config_manager.get("county_system", {})
        
        # Find nation counties using UUID first, fallback to name
        nation_counties = None
        if new_nation_uuid:
            for nation_name, nation_data in county_system.items():
                if nation_data.get("nation_uuid") == new_nation_uuid:
                    nation_counties = nation_data
                    break
        
        # Fallback to name-based lookup
        if not nation_counties and new_nation in county_system:
            nation_counties = county_system[new_nation]
        
        if not nation_counties:
            logger.warning(f"No county system found for nation {new_nation} (UUID: {new_nation_uuid})")
            return
        
        # Remove old county role if county changed
        if old_county and old_county != new_county:
            # Find old county role
            for county_name, county_data in nation_counties.get("counties", {}).items():
                if county_name == old_county:
                    old_county_role = guild.get_role(county_data.get("role_id"))
                    if old_county_role and old_county_role in member.roles:
                        roles_to_remove.append(old_county_role)
                        logger.info(f"  Removing old county role: {old_county_role.name}")
                    break
            
            # Also remove "no county" role if they had it
            no_county_role_id = nation_counties.get("no_county_role_id")
            if no_county_role_id:
                no_county_role = guild.get_role(no_county_role_id)
                if no_county_role and no_county_role in member.roles:
                    roles_to_remove.append(no_county_role)
                    logger.info(f"  Removing no county role: {no_county_role.name}")
        
        # Add new county role
        if new_county_role_id:
            county_role = guild.get_role(new_county_role_id)
            if county_role and county_role not in member.roles:
                roles_to_add.append(county_role)
                logger.info(f"  Adding county role: {county_role.name}")
        else:
            # Add "no county" role if no county assigned
            no_county_role_id = nation_counties.get("no_county_role_id")
            if no_county_role_id:
                no_county_role = guild.get_role(no_county_role_id)
                if no_county_role and no_county_role not in member.roles:
                    roles_to_add.append(no_county_role)
                    logger.info(f"  Adding no county role: {no_county_role.name}")
        
    except Exception as e:
        logger.error(f"Error handling county role changes: {e}")

async def revoke_nation_roles(member: discord.Member, old_nation: str) -> bool:
    """Remove nation-specific roles and revocation roles when a user leaves a nation"""
    try:
        guild = member.guild
        roles_to_remove = []
        
        # Remove nation role
        nation_roles = config_manager.get("nation_roles", {})
        if old_nation in nation_roles:
            nation_role = guild.get_role(nation_roles[old_nation])
            if nation_role and nation_role in member.roles:
                roles_to_remove.append(nation_role)
        
        # Remove county roles for that nation
        county_system = config_manager.get("county_system", {})
        if old_nation in county_system:
            nation_counties = county_system[old_nation]
            
            # Remove any county role from that nation
            for county_name, county_data in nation_counties.get("counties", {}).items():
                county_role = guild.get_role(county_data.get("role_id"))
                if county_role and county_role in member.roles:
                    roles_to_remove.append(county_role)
            
            # Remove "no county" role
            no_county_role_id = nation_counties.get("no_county_role_id")
            if no_county_role_id:
                no_county_role = guild.get_role(no_county_role_id)
                if no_county_role and no_county_role in member.roles:
                    roles_to_remove.append(no_county_role)
        
        # Remove mayor role
        mayor_role_id = config_manager.get("mayor_role_id")
        if mayor_role_id:
            mayor_role = guild.get_role(mayor_role_id)
            if mayor_role and mayor_role in member.roles:
                roles_to_remove.append(mayor_role)
        
        # Remove additional revocation roles
        revocation_roles = await get_revocation_roles(guild)
        for role in revocation_roles:
            if role in member.roles:
                roles_to_remove.append(role)
        
        # Remove verified role
        verified_role_id = config_manager.get("verified_role_id")
        if verified_role_id:
            verified_role = guild.get_role(verified_role_id)
            if verified_role and verified_role in member.roles:
                roles_to_remove.append(verified_role)
        
        # Apply removals
        if roles_to_remove:
            await member.remove_roles(*roles_to_remove, reason="EarthMC Nation Departure")
            logger.info(f"Revoked {len(roles_to_remove)} roles from {member.display_name} for leaving nation {old_nation}")
        
        # Reset nickname
        try:
            await member.edit(nick=None, reason="EarthMC Nation Departure")
        except discord.Forbidden:
            logger.warning(f"Cannot reset nickname for {member.display_name} - insufficient permissions")
        
        return True
        
    except Exception as e:
        logger.error(f"Error revoking nation roles for {member.display_name}: {e}")
        return False

async def revoke_nation_roles_by_uuid(member: discord.Member, old_nation_uuid: str, old_nation_name: str) -> bool:
    """Remove nation-specific roles and revocation roles when a user leaves a nation using UUIDs"""
    try:
        guild = member.guild
        roles_to_remove = []
        
        # Remove nation role
        nation_roles = config_manager.get("nation_roles", {})
        if old_nation_name in nation_roles:
            nation_role = guild.get_role(nation_roles[old_nation_name])
            if nation_role and nation_role in member.roles:
                roles_to_remove.append(nation_role)
        
        # Remove county roles for that nation using UUID
        county_system = config_manager.get("county_system", {})
        nation_counties = None
        
        # Find nation by UUID
        for nation_name, nation_data in county_system.items():
            if nation_data.get("nation_uuid") == old_nation_uuid:
                nation_counties = nation_data
                break
        
        # Fallback to name-based lookup
        if not nation_counties and old_nation_name in county_system:
            nation_counties = county_system[old_nation_name]
        
        if nation_counties:
            # Remove any county role from that nation
            for county_name, county_data in nation_counties.get("counties", {}).items():
                county_role = guild.get_role(county_data.get("role_id"))
                if county_role and county_role in member.roles:
                    roles_to_remove.append(county_role)
            
            # Remove "no county" role
            no_county_role_id = nation_counties.get("no_county_role_id")
            if no_county_role_id:
                no_county_role = guild.get_role(no_county_role_id)
                if no_county_role and no_county_role in member.roles:
                    roles_to_remove.append(no_county_role)
        
        # Remove mayor role
        mayor_role_id = config_manager.get("mayor_role_id")
        if mayor_role_id:
            mayor_role = guild.get_role(mayor_role_id)
            if mayor_role and mayor_role in member.roles:
                roles_to_remove.append(mayor_role)
        
        # Remove additional revocation roles
        revocation_roles = await get_revocation_roles(guild)
        for role in revocation_roles:
            if role in member.roles:
                roles_to_remove.append(role)
        
        # Remove verified role
        verified_role_id = config_manager.get("verified_role_id")
        if verified_role_id:
            verified_role = guild.get_role(verified_role_id)
            if verified_role and verified_role in member.roles:
                roles_to_remove.append(verified_role)
        
        # Apply removals
        if roles_to_remove:
            await member.remove_roles(*roles_to_remove, reason="EarthMC Nation Departure")
            logger.info(f"Revoked {len(roles_to_remove)} roles from {member.display_name} for leaving nation {old_nation_name}")
        
        # Reset nickname
        try:
            await member.edit(nick=None, reason="EarthMC Nation Departure")
        except discord.Forbidden:
            logger.warning(f"Cannot reset nickname for {member.display_name} - insufficient permissions")
        
        return True
        
    except Exception as e:
        logger.error(f"Error revoking nation roles for {member.display_name}: {e}")
        return False

async def get_revocation_roles(guild: discord.Guild) -> List[discord.Role]:
    """Get list of revocation roles that should be removed when leaving nation"""
    revocation_roles = []
    revocation_role_ids = config_manager.get("revocation_roles", [])
    
    for role_id in revocation_role_ids:
        role = guild.get_role(role_id)
        if role:
            revocation_roles.append(role)
        else:
            logger.warning(f"Revocation role with ID {role_id} not found")
    
    return revocation_roles

async def send_contradiction_report(bot, contradiction_data: str):
    """Send contradiction report to designated channel"""
    try:
        contradiction_channel_id = config_manager.get("contradiction_channel_id")
        channel = bot.get_channel(contradiction_channel_id) if contradiction_channel_id else None
        if channel:
            embed = discord.Embed(
                title="🚨 Link Contradiction Report",
                description=contradiction_data,
                color=0xff0000,
                timestamp=discord.utils.utcnow()
            )
            await channel.send(embed=embed)
        else:
            logger.error(f"Contradiction channel with ID {contradiction_channel_id} not found")
    except Exception as e:
        logger.error(f"Error sending contradiction report: {e}")