import json
import os
import time
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

class VerificationCache:
    def __init__(self, cache_file: str = "verification_cache.json"):
        self.cache_file = cache_file
        self.cache = self._load_cache()
    
    def _load_cache(self) -> Dict[str, Any]:
        """Load verification cache from JSON file"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
                logger.info(f"Verification cache loaded from {self.cache_file}")
                return cache
            else:
                logger.info(f"Verification cache file {self.cache_file} not found, starting with empty cache")
                return {"verified_users": {}, "metadata": {"created": time.time(), "last_updated": time.time()}}
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON verification cache: {e}")
            return {"verified_users": {}, "metadata": {"created": time.time(), "last_updated": time.time()}}
        except Exception as e:
            logger.error(f"Error loading verification cache: {e}")
            return {"verified_users": {}, "metadata": {"created": time.time(), "last_updated": time.time()}}
    
    def _save_cache(self) -> bool:
        """Save verification cache to JSON file"""
        try:
            # Update metadata
            self.cache["metadata"]["last_updated"] = time.time()
            
            # Create backup
            if os.path.exists(self.cache_file):
                backup_file = f"{self.cache_file}.backup"
                with open(self.cache_file, 'r', encoding='utf-8') as original:
                    with open(backup_file, 'w', encoding='utf-8') as backup:
                        backup.write(original.read())
            
            # Save new cache
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"Verification cache saved to {self.cache_file}")
            return True
        except Exception as e:
            logger.error(f"Error saving verification cache: {e}")
            return False
    
    def add_verified_user(self, discord_id: str, discord_username: str, ign: str, 
                         player_uuid: str, nation: str, town: str, 
                         is_mayor: bool = False, county: str = None, 
                         guild_id: str = None, verified_by: str = None) -> bool:
        """Add a verified user to the cache"""
        try:
            verification_data = {
                "discord_id": discord_id,
                "discord_username": discord_username,
                "ign": ign,
                "player_uuid": player_uuid,
                "nation": nation,
                "town": town,
                "is_mayor": is_mayor,
                "county": county,
                "guild_id": guild_id,
                "verified_by": verified_by,
                "verified_at": time.time(),
                "last_updated": time.time()
            }
            
            # Store by Discord ID as primary key
            self.cache["verified_users"][discord_id] = verification_data
            
            # Save to file
            if self._save_cache():
                logger.info(f"Added verified user to cache: {ign} (Discord: {discord_username})")
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Error adding verified user to cache: {e}")
            return False
    
    def get_verified_user(self, discord_id: str) -> Optional[Dict[str, Any]]:
        """Get verified user data by Discord ID"""
        return self.cache.get("verified_users", {}).get(discord_id)
    
    def get_user_by_ign(self, ign: str) -> Optional[Dict[str, Any]]:
        """Get verified user data by IGN"""
        for user_data in self.cache.get("verified_users", {}).values():
            if user_data.get("ign", "").lower() == ign.lower():
                return user_data
        return None
    
    def get_user_by_uuid(self, player_uuid: str) -> Optional[Dict[str, Any]]:
        """Get verified user data by player UUID"""
        for user_data in self.cache.get("verified_users", {}).values():
            if user_data.get("player_uuid") == player_uuid:
                return user_data
        return None
    
    def update_user_data(self, discord_id: str, **updates) -> bool:
        """Update specific fields for a verified user"""
        try:
            if discord_id in self.cache.get("verified_users", {}):
                self.cache["verified_users"][discord_id].update(updates)
                self.cache["verified_users"][discord_id]["last_updated"] = time.time()
                
                if self._save_cache():
                    logger.info(f"Updated verified user data for Discord ID: {discord_id}")
                    return True
            else:
                logger.warning(f"Attempted to update non-existent verified user: {discord_id}")
                return False
        except Exception as e:
            logger.error(f"Error updating verified user data: {e}")
            return False
    
    def remove_verified_user(self, discord_id: str) -> bool:
        """Remove a verified user from the cache"""
        try:
            if discord_id in self.cache.get("verified_users", {}):
                user_data = self.cache["verified_users"][discord_id]
                del self.cache["verified_users"][discord_id]
                
                if self._save_cache():
                    logger.info(f"Removed verified user from cache: {user_data.get('ign', 'Unknown')}")
                    return True
            else:
                logger.warning(f"Attempted to remove non-existent verified user: {discord_id}")
                return False
        except Exception as e:
            logger.error(f"Error removing verified user from cache: {e}")
            return False
    
    def get_users_by_nation(self, nation: str) -> List[Dict[str, Any]]:
        """Get all verified users from a specific nation"""
        users = []
        for user_data in self.cache.get("verified_users", {}).values():
            if user_data.get("nation", "").lower() == nation.lower():
                users.append(user_data)
        return users
    
    def get_users_by_county(self, nation: str, county: str) -> List[Dict[str, Any]]:
        """Get all verified users from a specific county"""
        users = []
        for user_data in self.cache.get("verified_users", {}).values():
            if (user_data.get("nation", "").lower() == nation.lower() and 
                user_data.get("county", "").lower() == county.lower()):
                users.append(user_data)
        return users
    
    def get_mayors(self) -> List[Dict[str, Any]]:
        """Get all verified users who are mayors"""
        mayors = []
        for user_data in self.cache.get("verified_users", {}).values():
            if user_data.get("is_mayor", False):
                mayors.append(user_data)
        return mayors
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get statistics about the verification cache"""
        verified_users = self.cache.get("verified_users", {})
        
        # Count by nation
        nations = {}
        mayors_count = 0
        counties = {}
        
        for user_data in verified_users.values():
            nation = user_data.get("nation", "Unknown")
            nations[nation] = nations.get(nation, 0) + 1
            
            if user_data.get("is_mayor", False):
                mayors_count += 1
            
            county = user_data.get("county")
            if county:
                county_key = f"{nation}:{county}"
                counties[county_key] = counties.get(county_key, 0) + 1
        
        metadata = self.cache.get("metadata", {})
        
        return {
            "total_verified_users": len(verified_users),
            "total_mayors": mayors_count,
            "nations": nations,
            "counties": counties,
            "cache_created": metadata.get("created"),
            "last_updated": metadata.get("last_updated"),
            "cache_file": self.cache_file
        }
    
    def cleanup_old_entries(self, max_age_days: int = 30) -> int:
        """Remove verification entries older than specified days"""
        try:
            current_time = time.time()
            max_age_seconds = max_age_days * 24 * 60 * 60
            
            to_remove = []
            for discord_id, user_data in self.cache.get("verified_users", {}).items():
                verified_at = user_data.get("verified_at", 0)
                if current_time - verified_at > max_age_seconds:
                    to_remove.append(discord_id)
            
            for discord_id in to_remove:
                del self.cache["verified_users"][discord_id]
            
            if to_remove:
                self._save_cache()
                logger.info(f"Cleaned up {len(to_remove)} old verification entries")
            
            return len(to_remove)
            
        except Exception as e:
            logger.error(f"Error cleaning up old verification entries: {e}")
            return 0
    
    def export_to_csv(self, filename: str = None) -> str:
        """Export verification cache to CSV format"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"verification_export_{timestamp}.csv"
        
        try:
            import csv
            
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = [
                    'discord_id', 'discord_username', 'ign', 'player_uuid', 
                    'nation', 'town', 'is_mayor', 'county', 'guild_id', 
                    'verified_by', 'verified_at', 'last_updated'
                ]
                
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for user_data in self.cache.get("verified_users", {}).values():
                    # Convert timestamps to readable format
                    row_data = user_data.copy()
                    if 'verified_at' in row_data and row_data['verified_at']:
                        row_data['verified_at'] = datetime.fromtimestamp(row_data['verified_at']).isoformat()
                    if 'last_updated' in row_data and row_data['last_updated']:
                        row_data['last_updated'] = datetime.fromtimestamp(row_data['last_updated']).isoformat()
                    
                    writer.writerow(row_data)
            
            logger.info(f"Verification cache exported to {filename}")
            return filename
            
        except Exception as e:
            logger.error(f"Error exporting verification cache: {e}")
            raise

# Global verification cache instance
verification_cache = VerificationCache()