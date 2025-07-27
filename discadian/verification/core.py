import logging
from api.earthmc import get_player_info
from verification.links import verify_discord_links
from verification.results import VerificationResult
from county.system import get_county_for_town_uuid, get_county_for_town
from config import config_manager
from utils.responses import response_manager
from utils.verification_cache import verification_cache

logger = logging.getLogger(__name__)

async def verify_player(discord_id: str, ign: str, target_nation: str = None) -> VerificationResult:
    """Main verification logic with re-verification support and multi-guild compatibility"""
    
    # Check if this is a re-verification
    existing_verification = verification_cache.get_verified_user_by_discord_id(discord_id)
    is_reverification = existing_verification is not None
    
    if is_reverification:
        logger.info(f"Re-verification detected for Discord ID {discord_id} (was: {existing_verification.get('ign')} -> now: {ign})")
    
    # Step 1: Get player info first to get UUID and nation data
    player_result = await get_player_info(ign)
    
    if not player_result["success"]:
        return VerificationResult(False, response_manager.get_message("verification.api_error", error=player_result['error']))
    
    player_data = player_result["data"]
    player_uuid = player_data.get("uuid")
    
    # Step 2: Check Discord linking
    has_contradiction, contradiction_msg, is_linked = await verify_discord_links(discord_id, ign, player_uuid)
    
    if has_contradiction:
        if contradiction_msg.startswith("Error"):
            return VerificationResult(False, contradiction_msg)
        else:
            return VerificationResult(False, response_manager.get_message("verification.contradiction_detected"), 
                                    contradiction_data=contradiction_msg)
    
    # Step 3: Check nation membership, mayor status, and county assignment
    nation_data = player_data.get("nation")
    town_data = player_data.get("town")
    status_data = player_data.get("status", {})
    
    if not nation_data:
        return VerificationResult(False, response_manager.get_message("verification.no_nation", ign=ign))
    
    nation_name = nation_data.get("name")
    nation_uuid = nation_data.get("uuid")
    town_name = town_data.get("name") if town_data else "Unknown"
    town_uuid = town_data.get("uuid") if town_data else None
    is_mayor = status_data.get("isMayor", False)
    
    # Check if target nation is specified and matches
    if target_nation and nation_name != target_nation:
        return VerificationResult(False, f"Player `{ign}` is in nation `{nation_name}`, not `{target_nation}`.")
    
    # Check if nation is approved
    approved_nations = config_manager.get_approved_nations()
    if nation_name not in approved_nations:
        return VerificationResult(False, response_manager.get_message("verification.unapproved_nation", ign=ign, nation=nation_name))
    
    # Step 4: Check county assignment using multi-guild manager
    county_name = None
    county_role_id = None
    has_county = True
    
    if town_uuid:
        # Try UUID-based lookup first
        if nation_uuid:
            county_name, county_role_id, has_county = get_county_for_town_uuid(nation_uuid, town_uuid)
        else:
            # Fallback to name-based lookup
            county_name, county_role_id, has_county = get_county_for_town(nation_name, town_uuid)
    
    # Step 5: Build success message using response manager
    link_status = "✅ Linked" if is_linked else "⚠️ Not linked"
    
    # Use different message base for re-verification
    message_base = "verification.update_success_base" if is_reverification else "verification.success_base"
    
    # Check if nation has county system enabled
    nation_config = config_manager.get_nation_config(nation_name)
    nation_has_county_system = False
    if nation_config:
        county_system = nation_config.get("county_system", {})
        nation_has_county_system = county_system.get("enabled", False)
    
    success_message = response_manager.build_verification_message(
        ign=ign,
        town=town_name,
        nation=nation_name,
        link_status=link_status,
        is_mayor=is_mayor,
        county=county_name,
        has_county=has_county and nation_has_county_system,
        message_base=message_base
    )
    
    return VerificationResult(
        True, 
        success_message, 
        nation=nation_name, 
        town=town_name, 
        is_mayor=is_mayor, 
        county=county_name, 
        has_county=has_county
    )