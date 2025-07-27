import aiohttp
import logging
import asyncio
from typing import Dict, Any, List
from config import DISCORD_API_URL, PLAYERS_API_URL, TOWNS_API_URL, NATIONS_API_URL, API_BASE
from utils.cache import cache_manager

logger = logging.getLogger(__name__)

# Rate limiting configuration
MAX_ENTITIES_PER_REQUEST = 100
MAX_REQUESTS_PER_MINUTE = 180
REQUEST_DELAY = 60 / MAX_REQUESTS_PER_MINUTE  # ~0.33 seconds between requests

class APIBatchManager:
    def __init__(self):
        self.request_count = 0
        self.request_start_time = None
    
    async def wait_if_needed(self):
        """Wait if we're approaching rate limits"""
        import time
        current_time = time.time()
        
        if self.request_start_time is None:
            self.request_start_time = current_time
        
        # Reset counter if a minute has passed
        if current_time - self.request_start_time >= 60:
            self.request_count = 0
            self.request_start_time = current_time
        
        # If we're approaching the limit, wait
        if self.request_count >= MAX_REQUESTS_PER_MINUTE - 5:  # Leave some buffer
            wait_time = 60 - (current_time - self.request_start_time) + 1
            if wait_time > 0:
                logger.info(f"Rate limit approaching, waiting {wait_time:.1f} seconds")
                await asyncio.sleep(wait_time)
                self.request_count = 0
                self.request_start_time = time.time()
        
        self.request_count += 1

# Global batch manager instance
batch_manager = APIBatchManager()

def chunk_list(lst: List[Any], chunk_size: int) -> List[List[Any]]:
    """Split a list into chunks of specified size"""
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]

async def get_multiple_towns_info(town_queries: List[str], use_cache: bool = True) -> Dict[str, Dict[str, Any]]:
    """
    Get information for multiple towns efficiently using batching
    Returns: {town_name_or_uuid: result_data}
    """
    results = {}
    
    # Check cache first for all queries
    uncached_queries = []
    if use_cache:
        for query in town_queries:
            # Try both UUID and name-based cache keys
            cache_key_uuid = f"town_uuid:{query}"
            cache_key_name = f"town_name:{query.lower()}"
            
            cached_result = cache_manager.get(cache_key_uuid) or cache_manager.get(cache_key_name)
            if cached_result and cached_result.get("success"):
                town_data = cached_result["data"]
                town_identifier = town_data.get("name", query)
                results[town_identifier] = cached_result
                logger.info(f"Town info for '{query}' found in cache")
            else:
                uncached_queries.append(query)
    else:
        uncached_queries = town_queries
    
    if not uncached_queries:
        return results
    
    # Split into batches
    batches = chunk_list(uncached_queries, MAX_ENTITIES_PER_REQUEST)
    logger.info(f"Processing {len(uncached_queries)} towns in {len(batches)} batches")
    
    for i, batch in enumerate(batches):
        logger.info(f"Processing batch {i+1}/{len(batches)} with {len(batch)} towns")
        
        # Wait for rate limiting
        await batch_manager.wait_if_needed()
        
        try:
            payload = {
                "query": batch,
                "template": {
                    "name": True,
                    "uuid": True,
                    "coordinates": True,
                    "nation": True
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(TOWNS_API_URL, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"Batch {i+1} API response: {len(data)} towns returned")
                        
                        # Process each town in the batch
                        for j, town_data in enumerate(data):
                            if town_data and isinstance(town_data, dict):
                                town_name = town_data.get("name", f"Unknown_{j}")
                                town_uuid = town_data.get("uuid")
                                
                                if town_uuid:
                                    result = {"success": True, "data": town_data}
                                    results[town_name] = result
                                    
                                    # Cache the result using both UUID and name
                                    if use_cache:
                                        cache_manager.set(f"town_uuid:{town_uuid}", result, ttl=300)
                                        cache_manager.set(f"town_name:{town_name.lower()}", result, ttl=300)
                                else:
                                    logger.warning(f"Town data missing UUID: {town_data}")
                        
                        # Handle any failed queries in this batch
                        if len(data) < len(batch):
                            logger.warning(f"Batch {i+1}: Expected {len(batch)} results, got {len(data)}")
                    
                    else:
                        response_text = await response.text()
                        logger.error(f"Batch {i+1} API error {response.status}: {response_text}")
                        
                        # Mark all towns in this batch as failed
                        for query in batch:
                            results[query] = {
                                "success": False, 
                                "error": f"API returned status {response.status}"
                            }
        
        except Exception as e:
            logger.error(f"Exception in batch {i+1}: {e}")
            
            # Mark all towns in this batch as failed
            for query in batch:
                results[query] = {
                    "success": False, 
                    "error": str(e)
                }
        
        # Small delay between batches to be respectful
        if i < len(batches) - 1:  # Don't wait after the last batch
            await asyncio.sleep(REQUEST_DELAY)
    
    logger.info(f"Completed processing {len(town_queries)} towns, {len(results)} results")
    return results

async def get_player_info(ign: str, use_cache: bool = True) -> Dict[str, Any]:
    """Get player information from EarthMC API"""
    # Try to get from cache first using both IGN and UUID if we have it
    cache_key_ign = f"player_ign:{ign.lower()}"
    
    # Try cache first
    if use_cache:
        cached_result = cache_manager.get(cache_key_ign)
        if cached_result:
            logger.info(f"Player info for '{ign}' found in cache")
            return cached_result
    
    try:
        payload = {
            "query": [ign],
            "template": {
                "name": True,
                "uuid": True,
                "town": True,
                "nation": True,
                "status": True
            }
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(PLAYERS_API_URL, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Player API response for '{ign}': {data}")
                    if data and len(data) > 0:
                        player_data = data[0]
                        player_uuid = player_data.get("uuid")
                        if player_uuid:
                            result = {"success": True, "data": player_data}
                            # Cache successful results using both IGN and UUID
                            if use_cache:
                                cache_manager.set(cache_key_ign, result, ttl=60)  # Cache for 1 minute
                                cache_manager.set(f"player_uuid:{player_uuid}", result, ttl=60)
                            return result
                        else:
                            result = {"success": False, "error": f"Player '{ign}' found but no UUID in response"}
                    else:
                        result = {"success": False, "error": f"Player '{ign}' not found in EarthMC database"}
                else:
                    response_text = await response.text()
                    logger.error(f"Player API error {response.status}: {response_text}")
                    result = {"success": False, "error": f"API returned status {response.status}: {response_text}"}
                
                # Cache failed results for shorter time to allow retries
                if use_cache:
                    cache_manager.set(cache_key_ign, result, ttl=30)
                return result
                
    except Exception as e:
        logger.error(f"Exception in get_player_info: {e}")
        result = {"success": False, "error": str(e)}
        return result

async def get_player_info_by_uuid(player_uuid: str, use_cache: bool = True) -> Dict[str, Any]:
    """Get player information by UUID from EarthMC API"""
    cache_key_uuid = f"player_uuid:{player_uuid}"
    
    # Try cache first
    if use_cache:
        cached_result = cache_manager.get(cache_key_uuid)
        if cached_result:
            logger.info(f"Player info for UUID '{player_uuid}' found in cache")
            return cached_result
    
    try:
        payload = {
            "query": [player_uuid],
            "template": {
                "name": True,
                "uuid": True,
                "town": True,
                "nation": True,
                "status": True
            }
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(PLAYERS_API_URL, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Player API response for UUID '{player_uuid}': {data}")
                    if data and len(data) > 0:
                        player_data = data[0]
                        if player_data.get("uuid"):
                            result = {"success": True, "data": player_data}
                            # Cache successful results using both UUID and IGN
                            if use_cache:
                                cache_manager.set(cache_key_uuid, result, ttl=60)
                                player_ign = player_data.get("name")
                                if player_ign:
                                    cache_manager.set(f"player_ign:{player_ign.lower()}", result, ttl=60)
                            return result
                        else:
                            result = {"success": False, "error": f"Player with UUID '{player_uuid}' found but no UUID in response"}
                    else:
                        result = {"success": False, "error": f"Player with UUID '{player_uuid}' not found in EarthMC database"}
                else:
                    response_text = await response.text()
                    logger.error(f"Player API error {response.status}: {response_text}")
                    result = {"success": False, "error": f"API returned status {response.status}: {response_text}"}
                
                # Cache failed results for shorter time to allow retries
                if use_cache:
                    cache_manager.set(cache_key_uuid, result, ttl=30)
                return result
                
    except Exception as e:
        logger.error(f"Exception in get_player_info_by_uuid: {e}")
        result = {"success": False, "error": str(e)}
        return result

async def get_nation_info(nation_name: str, use_cache: bool = True) -> Dict[str, Any]:
    """Get nation information from EarthMC API"""
    cache_key = f"nation_name:{nation_name.lower()}"
    
    # Try cache first
    if use_cache:
        cached_result = cache_manager.get(cache_key)
        if cached_result:
            logger.info(f"Nation info for '{nation_name}' found in cache")
            return cached_result
    
    try:
        payload = {
            "query": [nation_name],
            "template": {
                "name": True,
                "uuid": True,
                "towns": True
            }
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(NATIONS_API_URL, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Nation API response for '{nation_name}': {data}")
                    if data and len(data) > 0:
                        nation_data = data[0]
                        nation_uuid = nation_data.get("uuid")
                        if nation_uuid:
                            result = {"success": True, "data": nation_data}
                            # Cache successful results using both name and UUID
                            if use_cache:
                                cache_manager.set(cache_key, result, ttl=300)  # Cache for 5 minutes
                                cache_manager.set(f"nation_uuid:{nation_uuid}", result, ttl=300)
                            return result
                        else:
                            result = {"success": False, "error": f"Nation '{nation_name}' found but no UUID in response"}
                    else:
                        result = {"success": False, "error": f"Nation '{nation_name}' not found in EarthMC database"}
                else:
                    response_text = await response.text()
                    logger.error(f"Nation API error {response.status}: {response_text}")
                    result = {"success": False, "error": f"API returned status {response.status}: {response_text}"}
                
                # Cache failed results for shorter time
                if use_cache:
                    cache_manager.set(cache_key, result, ttl=60)
                return result
                
    except Exception as e:
        logger.error(f"Exception in get_nation_info: {e}")
        result = {"success": False, "error": str(e)}
        return result

async def get_town_info(town_name: str, use_cache: bool = True) -> Dict[str, Any]:
    """Get town information from EarthMC API"""
    # Try both UUID and name-based cache keys
    cache_key_name = f"town_name:{town_name.lower()}"
    cache_key_uuid = f"town_uuid:{town_name}"  # In case town_name is actually a UUID
    
    # Try cache first
    if use_cache:
        cached_result = cache_manager.get(cache_key_name) or cache_manager.get(cache_key_uuid)
        if cached_result:
            logger.info(f"Town info for '{town_name}' found in cache")
            return cached_result
    
    try:
        payload = {
            "query": [town_name],
            "template": {
                "name": True,
                "uuid": True,
                "coordinates": True,
                "nation": True
            }
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(TOWNS_API_URL, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Town API response for '{town_name}': {data}")
                    if data and len(data) > 0:
                        town_data = data[0]
                        town_uuid = town_data.get("uuid")
                        actual_town_name = town_data.get("name")
                        if town_uuid:
                            result = {"success": True, "data": town_data}
                            # Cache successful results using both name and UUID
                            if use_cache:
                                cache_manager.set(f"town_uuid:{town_uuid}", result, ttl=300)  # Cache for 5 minutes
                                if actual_town_name:
                                    cache_manager.set(f"town_name:{actual_town_name.lower()}", result, ttl=300)
                            return result
                        else:
                            result = {"success": False, "error": f"Town '{town_name}' found but no UUID in response"}
                    else:
                        result = {"success": False, "error": f"Town '{town_name}' not found in EarthMC database"}
                else:
                    response_text = await response.text()
                    logger.error(f"Town API error {response.status}: {response_text}")
                    result = {"success": False, "error": f"API returned status {response.status}: {response_text}"}
                
                # Cache failed results for shorter time
                if use_cache:
                    cache_manager.set(cache_key_name, result, ttl=60)
                return result
                
    except Exception as e:
        logger.error(f"Exception in get_town_info: {e}")
        result = {"success": False, "error": str(e)}
        return result

async def check_discord_link(discord_id: str, player_uuid: str, use_cache: bool = True) -> Dict[str, Any]:
    """Check if Discord and player UUID are linked in EarthMC"""
    cache_key = f"discord_link:{discord_id}:{player_uuid}"
    
    # Try cache first
    if use_cache:
        cached_result = cache_manager.get(cache_key)
        if cached_result:
            logger.info(f"Discord link info found in cache")
            return cached_result
    
    try:
        logger.info(f"Checking Discord link for Discord ID: {discord_id}, UUID: {player_uuid}")

        payload = {
            "query": [
                {"type": "discord", "target": discord_id},
                {"type": "minecraft", "target": player_uuid}
            ]
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(DISCORD_API_URL, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Discord API response: {data}")
                    result = {"success": True, "data": data}
                    # Cache successful results
                    if use_cache:
                        cache_manager.set(cache_key, result, ttl=180)  # Cache for 3 minutes
                    return result
                else:
                    response_text = await response.text()
                    logger.error(f"Discord API error {response.status}: {response_text}")
                    result = {"success": False, "error": f"API returned status {response.status}: {response_text}"}
                    
                    # Cache failed results for shorter time
                    if use_cache:
                        cache_manager.set(cache_key, result, ttl=30)
                    return result
                    
    except Exception as e:
        logger.error(f"Exception in check_discord_link: {e}")
        result = {"success": False, "error": str(e)}
        return result