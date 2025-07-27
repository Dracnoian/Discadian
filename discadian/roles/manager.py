import discord
import logging
from config import config_manager

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