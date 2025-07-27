from typing import Tuple, Optional
from config import config_manager

async def validate_town_nation(town_uuid: str, expected_nation_uuid: str) -> Tuple[bool, str, str]:
    """
    Validate that a town belongs to the specified nation using UUIDs
    Returns: (is_valid, actual_nation_uuid_or_error, nation_name_for_display)
    """
    try:
        from api.earthmc import get_town_info
        
        # Get town details using UUID - make sure to get nation data
        town_result = await get_town_info(town_uuid, use_cache=False)  # Don't use cache for validation
        
        if not town_result["success"]:
            return False, f"Could not validate town: {town_result['error']}", ""
        
        town_data = town_result["data"]
        town_name = town_data.get("name", "Unknown")
        nation_data = town_data.get("nation")
        
        # Debug logging
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Validating town {town_name} (UUID: {town_uuid})")
        logger.info(f"Town data keys: {list(town_data.keys())}")
        logger.info(f"Nation data: {nation_data}")
        
        if not nation_data:
            return False, f"Town '{town_name}' is not in any nation", ""
        
        actual_nation_uuid = nation_data.get("uuid")
        actual_nation_name = nation_data.get("name", "Unknown")
        
        if not actual_nation_uuid:
            return False, f"Town '{town_name}' has invalid nation data", ""
        
        if actual_nation_uuid != expected_nation_uuid:
            return False, f"Town '{town_name}' belongs to different nation (UUID: {actual_nation_uuid})", actual_nation_name
        
        return True, actual_nation_uuid, actual_nation_name
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Exception in validate_town_nation: {e}")
        return False, f"Error validating town nation: {str(e)}", ""

def get_county_for_town_uuid(nation_uuid: str, town_uuid: str) -> Tuple[Optional[str], Optional[int], bool]:
    """
    Get county information for a town UUID in a nation UUID
    Returns: (county_name, county_role_id, has_county)
    """
    county_system = config_manager.get("county_system", {})
    
    # Find nation by UUID in county system
    nation_counties = None
    for nation_name, nation_data in county_system.items():
        # Get nation UUID from config or lookup
        stored_nation_uuid = nation_data.get("nation_uuid")
        if stored_nation_uuid == nation_uuid:
            nation_counties = nation_data
            break
    
    if not nation_counties:
        return None, None, True  # Nation doesn't use county system
    
    # Check if town UUID is in any county
    for county_name, county_data in nation_counties.get("counties", {}).items():
        if town_uuid in county_data.get("towns", []):
            return county_name, county_data.get("role_id"), True
    
    # Town not in any county
    no_county_role_id = nation_counties.get("no_county_role_id")
    return None, no_county_role_id, False

def get_county_for_town(nation_name: str, town_uuid: str) -> Tuple[Optional[str], Optional[int], bool]:
    """
    Get county information for a town UUID in a nation (backwards compatibility)
    Returns: (county_name, county_role_id, has_county)
    """
    county_system = config_manager.get("county_system", {})
    
    if nation_name not in county_system:
        return None, None, True  # Nation doesn't use county system
    
    nation_counties = county_system[nation_name]
    
    # Check if town UUID is in any county
    for county_name, county_data in nation_counties.get("counties", {}).items():
        if town_uuid in county_data.get("towns", []):
            return county_name, county_data.get("role_id"), True
    
    # Town not in any county
    no_county_role_id = nation_counties.get("no_county_role_id")
    return None, no_county_role_id, False

async def add_town_to_county_by_uuid(nation_uuid: str, county: str, town_uuid: str) -> Tuple[bool, str]:
    """
    Add a town UUID to a county using nation UUID (with nation validation)
    Returns: (success, message)
    """
    # First validate that the town belongs to the specified nation
    is_valid, validation_result, nation_name = await validate_town_nation(town_uuid, nation_uuid)
    
    if not is_valid:
        return False, f"❌ **Nation Validation Failed**: {validation_result}"
    
    county_system = config_manager.get("county_system", {})
    
    # Find nation by UUID or create entry
    nation_config = None
    nation_key = None
    
    for nation_name_key, nation_data in county_system.items():
        stored_nation_uuid = nation_data.get("nation_uuid")
        if stored_nation_uuid == nation_uuid:
            nation_config = nation_data
            nation_key = nation_name_key
            break
    
    # If nation not found, create new entry using nation name
    if not nation_config:
        nation_key = nation_name
        county_system[nation_key] = {
            "nation_uuid": nation_uuid,
            "counties": {}, 
            "no_county_role_id": None
        }
        nation_config = county_system[nation_key]
        config_manager.set("county_system", county_system)
    
    # Check if county exists
    if county not in nation_config.get("counties", {}):
        return False, f"County `{county}` does not exist in nation `{nation_name}`. Create it first."
    
    # Check if town is already in this county
    current_towns = nation_config["counties"][county].get("towns", [])
    if town_uuid in current_towns:
        return False, f"Town is already in county `{county}`."
    
    # Remove town from other counties in this nation if it exists
    old_county = None
    for other_county, county_data in nation_config["counties"].items():
        if town_uuid in county_data.get("towns", []):
            county_data["towns"].remove(town_uuid)
            old_county = other_county
            break
    
    # Add town to county
    nation_config["counties"][county]["towns"].append(town_uuid)
    
    # Save configuration
    if config_manager.set("county_system", county_system):
        # Update verification cache if town moved counties
        if old_county:
            await update_verification_cache_county_by_uuid(nation_uuid, town_uuid, old_county, county)
        else:
            await update_verification_cache_county_by_uuid(nation_uuid, town_uuid, None, county)
        
        return True, f"✅ Successfully added town to county `{county}` in nation `{nation_name}`. Validated: Town belongs to {nation_name}."
    else:
        return False, "Failed to save configuration changes."

async def add_town_to_county(nation: str, county: str, town_uuid: str) -> Tuple[bool, str]:
    """
    Add a town UUID to a county (backwards compatibility with nation name)
    Returns: (success, message)
    """
    # Get nation UUID from name
    from api.earthmc import get_nation_info
    nation_result = await get_nation_info(nation)
    
    if not nation_result["success"]:
        return False, f"Could not find nation '{nation}': {nation_result['error']}"
    
    nation_uuid = nation_result["data"].get("uuid")
    if not nation_uuid:
        return False, f"Nation '{nation}' missing UUID in API response"
    
    return await add_town_to_county_by_uuid(nation_uuid, county, town_uuid)

def remove_town_from_county_by_uuid(nation_uuid: str, town_uuid: str) -> Tuple[bool, str, Optional[str]]:
    """
    Remove a town UUID from its county using nation UUID
    Returns: (success, message, removed_from_county)
    """
    county_system = config_manager.get("county_system", {})
    
    # Find nation by UUID
    nation_config = None
    nation_name = None
    
    for nation_name_key, nation_data in county_system.items():
        stored_nation_uuid = nation_data.get("nation_uuid")
        if stored_nation_uuid == nation_uuid:
            nation_config = nation_data
            nation_name = nation_name_key
            break
    
    if not nation_config:
        return False, f"Nation with UUID `{nation_uuid}` does not have a county system configured.", None
    
    # Find and remove town from its county
    removed_from_county = None
    for county_name, county_data in nation_config.get("counties", {}).items():
        if town_uuid in county_data.get("towns", []):
            county_data["towns"].remove(town_uuid)
            removed_from_county = county_name
            break
    
    if removed_from_county:
        # Save configuration
        if config_manager.set("county_system", county_system):
            # Update verification cache to remove county assignment
            import asyncio
            asyncio.create_task(update_verification_cache_county_by_uuid(nation_uuid, town_uuid, removed_from_county, None))
            
            return True, f"Successfully removed town from county `{removed_from_county}` in nation `{nation_name}`.", removed_from_county
        else:
            return False, "Failed to save configuration changes.", None
    else:
        return False, f"Town is not currently assigned to any county in nation `{nation_name}`.", None

def remove_town_from_county(nation: str, town_uuid: str) -> Tuple[bool, str, Optional[str]]:
    """
    Remove a town UUID from its county (backwards compatibility with nation name)
    Returns: (success, message, removed_from_county)
    """
    county_system = config_manager.get("county_system", {})
    
    # Check if nation exists in county system
    if nation not in county_system:
        return False, f"Nation `{nation}` does not have a county system configured.", None
    
    # Find and remove town from its county
    removed_from_county = None
    for county_name, county_data in county_system[nation].get("counties", {}).items():
        if town_uuid in county_data.get("towns", []):
            county_data["towns"].remove(town_uuid)
            removed_from_county = county_name
            break
    
    if removed_from_county:
        # Save configuration
        if config_manager.set("county_system", county_system):
            # Update verification cache to remove county assignment
            nation_uuid = county_system[nation].get("nation_uuid")
            if nation_uuid:
                import asyncio
                asyncio.create_task(update_verification_cache_county_by_uuid(nation_uuid, town_uuid, removed_from_county, None))
            
            return True, f"Successfully removed town from county `{removed_from_county}` in nation `{nation}`.", removed_from_county
        else:
            return False, "Failed to save configuration changes.", None
    else:
        return False, f"Town is not currently assigned to any county in nation `{nation}`.", None

def rename_county_by_uuid(nation_uuid: str, old_county_name: str, new_county_name: str) -> Tuple[bool, str, int]:
    """
    Rename a county using nation UUID and update verification cache
    Returns: (success, message, towns_count)
    """
    county_system = config_manager.get("county_system", {})
    
    # Find nation by UUID
    nation_config = None
    nation_name = None
    
    for nation_name_key, nation_data in county_system.items():
        stored_nation_uuid = nation_data.get("nation_uuid")
        if stored_nation_uuid == nation_uuid:
            nation_config = nation_data
            nation_name = nation_name_key
            break
    
    if not nation_config:
        return False, f"Nation with UUID `{nation_uuid}` does not have a county system configured.", 0
    
    counties = nation_config.get("counties", {})
    
    # Check if old county exists
    if old_county_name not in counties:
        return False, f"County `{old_county_name}` does not exist in nation `{nation_name}`.", 0
    
    # Check if new county name already exists
    if new_county_name in counties:
        return False, f"County `{new_county_name}` already exists in nation `{nation_name}`.", 0
    
    # Rename county
    county_data = counties[old_county_name]
    counties[new_county_name] = county_data
    del counties[old_county_name]
    
    # Update the county system
    nation_config["counties"] = counties
    
    towns_count = len(county_data.get("towns", []))
    
    # Save configuration
    if config_manager.set("county_system", county_system):
        # Update verification cache for all users in this county
        import asyncio
        asyncio.create_task(update_verification_cache_county_rename_by_uuid(nation_uuid, old_county_name, new_county_name))
        
        return True, f"Successfully renamed county `{old_county_name}` to `{new_county_name}` in nation `{nation_name}`.", towns_count
    else:
        return False, "Failed to save configuration changes.", 0

def rename_county(nation: str, old_county_name: str, new_county_name: str) -> Tuple[bool, str, int]:
    """
    Rename a county (backwards compatibility with nation name)
    Returns: (success, message, towns_count)
    """
    county_system = config_manager.get("county_system", {})
    
    # Check if nation exists in county system
    if nation not in county_system:
        return False, f"Nation `{nation}` does not have a county system configured.", 0
    
    counties = county_system[nation].get("counties", {})
    
    # Check if old county exists
    if old_county_name not in counties:
        return False, f"County `{old_county_name}` does not exist in nation `{nation}`.", 0
    
    # Check if new county name already exists
    if new_county_name in counties:
        return False, f"County `{new_county_name}` already exists in nation `{nation}`.", 0
    
    # Rename county
    county_data = counties[old_county_name]
    counties[new_county_name] = county_data
    del counties[old_county_name]
    
    # Update the county system
    county_system[nation]["counties"] = counties
    
    towns_count = len(county_data.get("towns", []))
    
    # Save configuration
    if config_manager.set("county_system", county_system):
        # Update verification cache for all users in this county
        nation_uuid = county_system[nation].get("nation_uuid")
        if nation_uuid:
            import asyncio
            asyncio.create_task(update_verification_cache_county_rename_by_uuid(nation_uuid, old_county_name, new_county_name))
        
        return True, f"Successfully renamed county `{old_county_name}` to `{new_county_name}` in nation `{nation}`.", towns_count
    else:
        return False, "Failed to save configuration changes.", 0

async def update_verification_cache_county_by_uuid(nation_uuid: str, town_uuid: str, old_county: Optional[str], new_county: Optional[str]):
    """Update verification cache when a town's county assignment changes using UUIDs"""
    try:
        from utils.verification_cache import verification_cache
        import logging
        
        logger = logging.getLogger(__name__)
        logger.info(f"Updating verification cache for town UUID {town_uuid}: {old_county} -> {new_county}")
        
        # Find all users in this town and update their county
        updated_count = 0
        verified_users = verification_cache.cache.get("verified_users", {})
        
        for player_uuid, user_data in verified_users.items():
            if (user_data.get("nation_uuid") == nation_uuid and 
                user_data.get("town_uuid") == town_uuid):
                
                # Update the county for this user
                verification_cache.update_user_data(
                    player_uuid=player_uuid,
                    county=new_county
                )
                updated_count += 1
                logger.info(f"Updated county for user {user_data.get('ign', 'Unknown')} from {old_county} to {new_county}")
        
        if updated_count > 0:
            logger.info(f"Updated county assignment for {updated_count} users in town UUID {town_uuid}")
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error updating verification cache for county change: {e}")

async def update_verification_cache_county_rename_by_uuid(nation_uuid: str, old_county_name: str, new_county_name: str):
    """Update verification cache when a county is renamed using nation UUID"""
    try:
        from utils.verification_cache import verification_cache
        import logging
        
        logger = logging.getLogger(__name__)
        logger.info(f"Updating verification cache for county rename in nation UUID {nation_uuid}: {old_county_name} -> {new_county_name}")
        
        # Find all users in this county and update their county name
        updated_count = 0
        verified_users = verification_cache.cache.get("verified_users", {})
        
        for player_uuid, user_data in verified_users.items():
            if (user_data.get("nation_uuid") == nation_uuid and 
                user_data.get("county") == old_county_name):
                
                # Update the county name for this user
                verification_cache.update_user_data(
                    player_uuid=player_uuid,
                    county=new_county_name
                )
                updated_count += 1
                logger.info(f"Updated county name for user {user_data.get('ign', 'Unknown')} from {old_county_name} to {new_county_name}")
        
        if updated_count > 0:
            logger.info(f"Updated county name for {updated_count} users from {old_county_name} to {new_county_name}")
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error updating verification cache for county rename: {e}")

# Legacy compatibility functions
async def update_verification_cache_county(nation: str, town_uuid: str, old_county: Optional[str], new_county: Optional[str]):
    """Legacy function - tries to find nation UUID and delegate to UUID-based function"""
    try:
        # Try to get nation UUID from county system
        county_system = config_manager.get("county_system", {})
        nation_uuid = None
        
        if nation in county_system:
            nation_uuid = county_system[nation].get("nation_uuid")
        
        if nation_uuid:
            await update_verification_cache_county_by_uuid(nation_uuid, town_uuid, old_county, new_county)
        else:
            # Fallback to name-based search (less reliable)
            from utils.verification_cache import verification_cache
            import logging
            
            logger = logging.getLogger(__name__)
            logger.warning(f"No nation UUID found for {nation}, using name-based fallback")
            
            updated_count = 0
            verified_users = verification_cache.cache.get("verified_users", {})
            
            for player_uuid, user_data in verified_users.items():
                if (user_data.get("nation") == nation and 
                    user_data.get("town_uuid") == town_uuid):
                    
                    verification_cache.update_user_data(
                        player_uuid=player_uuid,
                        county=new_county
                    )
                    updated_count += 1
            
            if updated_count > 0:
                logger.info(f"Updated county assignment for {updated_count} users in town UUID {town_uuid} (name-based fallback)")
                
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in legacy county update: {e}")

async def update_verification_cache_county_rename(nation: str, old_county_name: str, new_county_name: str):
    """Legacy function - tries to find nation UUID and delegate to UUID-based function"""
    try:
        # Try to get nation UUID from county system
        county_system = config_manager.get("county_system", {})
        nation_uuid = None
        
        if nation in county_system:
            nation_uuid = county_system[nation].get("nation_uuid")
        
        if nation_uuid:
            await update_verification_cache_county_rename_by_uuid(nation_uuid, old_county_name, new_county_name)
        else:
            # Fallback to name-based search (less reliable)
            from utils.verification_cache import verification_cache
            import logging
            
            logger = logging.getLogger(__name__)
            logger.warning(f"No nation UUID found for {nation}, using name-based fallback")
            
            updated_count = 0
            verified_users = verification_cache.cache.get("verified_users", {})
            
            for player_uuid, user_data in verified_users.items():
                if (user_data.get("nation") == nation and 
                    user_data.get("county") == old_county_name):
                    
                    verification_cache.update_user_data(
                        player_uuid=player_uuid,
                        county=new_county_name
                    )
                    updated_count += 1
            
            if updated_count > 0:
                logger.info(f"Updated county name for {updated_count} users (name-based fallback)")
                
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in legacy county rename: {e}")