import logging
from typing import Optional, Tuple
from api.earthmc import check_discord_link

logger = logging.getLogger(__name__)

def parse_link_data(link_data: list, discord_id: str, player_uuid: str) -> Tuple[Optional[dict], Optional[dict]]:
    """
    Parse Discord link data and return valid links
    Returns: (discord_link, minecraft_link)
    """
    discord_link = None
    minecraft_link = None
    
    logger.info(f"Raw link data: {link_data}")
    
    # Parse link data - only consider valid links (both id and uuid must be non-null)
    for i, entry in enumerate(link_data):
        logger.info(f"Processing entry {i}: {entry}")
        if entry is not None and isinstance(entry, dict):
            entry_id = entry.get("id")
            entry_uuid = entry.get("uuid")
            
            # Only consider it a valid link if both id and uuid are present (not None)
            if entry_id is not None and entry_uuid is not None:
                # Check if this entry matches our discord_id
                if entry_id == discord_id:
                    discord_link = entry
                    logger.info(f"Found valid Discord link: {discord_link}")
                # Check if this entry matches our player UUID
                if entry_uuid == player_uuid:
                    minecraft_link = entry
                    logger.info(f"Found valid Minecraft link: {minecraft_link}")
            else:
                logger.info(f"Skipping incomplete entry (id: {entry_id}, uuid: {entry_uuid})")
    
    logger.info(f"Final valid links - Discord: {discord_link}, Minecraft: {minecraft_link}")
    return discord_link, minecraft_link

def check_link_contradictions(discord_link: Optional[dict], minecraft_link: Optional[dict], 
                            discord_id: str, ign: str, player_uuid: str) -> Optional[str]:
    """
    Check for link contradictions and return contradiction message if found
    Returns: contradiction_message or None
    """
    if discord_link and minecraft_link:
        # Both have links - check if they match
        if discord_link.get("uuid") != player_uuid:
            return (f"**Link Contradiction Detected**\n"
                   f"Discord: <@{discord_id}>\n"
                   f"Attempted IGN: `{ign}`\n"
                   f"Issue: Discord is linked to UUID `{discord_link.get('uuid')}`, but `{ign}` has UUID `{player_uuid}`")
        
        elif minecraft_link.get("id") != discord_id:
            return (f"**Link Contradiction Detected**\n"
                    f"Discord: <@{discord_id}>\n"
                    f"Attempted IGN: `{ign}`\n"
                    f"Issue: IGN `{ign}` is linked to Discord ID `{minecraft_link.get('id')}`, not the provided Discord account")
    
    elif discord_link and not minecraft_link:
        # Discord is linked but not to this IGN
        return (f"**Link Contradiction Detected**\n"
               f"Discord: <@{discord_id}>\n"
               f"Attempted IGN: `{ign}`\n"
               f"Issue: Discord is linked to UUID `{discord_link.get('uuid')}`, not `{ign}`")
    
    elif minecraft_link and not discord_link:
        # IGN is linked but not to this Discord
        return (f"**Link Contradiction Detected**\n"
                f"Discord: <@{discord_id}>\n"
                f"Attempted IGN: `{ign}`\n"
                f"Issue: IGN `{ign}` is linked to Discord ID `{minecraft_link.get('id')}`, not the provided Discord account")
    
    return None  # No contradictions found

async def verify_discord_links(discord_id: str, ign: str, player_uuid: str) -> Tuple[bool, Optional[str], bool]:
    """
    Verify Discord links for a player
    Returns: (has_contradiction, contradiction_message, is_linked)
    """
    # Check Discord linking
    link_result = await check_discord_link(discord_id, player_uuid)
    
    if not link_result["success"]:
        return True, f"Error checking Discord link: {link_result['error']}", False
    
    # Parse link data
    discord_link, minecraft_link = parse_link_data(link_result["data"], discord_id, player_uuid)
    
    # Check for contradictions
    contradiction_msg = check_link_contradictions(discord_link, minecraft_link, discord_id, ign, player_uuid)
    
    if contradiction_msg:
        return True, contradiction_msg, False
    
    # Determine if properly linked
    is_linked = bool(discord_link and minecraft_link)
    
    logger.info("No link contradictions found, proceeding to nation check")
    return False, None, is_linked