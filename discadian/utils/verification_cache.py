import json
import os
import time
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

class VerificationCache:
    def __init__(self, cache_file: str = "./discadian/verification_cache.json"):
        self.cache_file = cache_file
        self.cache = self._load_cache()
    
    def _load_cache(self) -> Dict[str, Any]:
        """Load verification cache from JSON file"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
                
                # Migrate old cache format if necessary
                if self._needs_migration(cache):
                    cache = self._migrate_cache_format(cache)
                
                logger.info(f"Verification cache loaded from {self.cache_file}")
                return cache
            else:
                logger.info(f"Verification cache file {self.cache_file} not found, starting with empty cache")
                return {
                    "verified_users": {},
                    "uuid_to_discord": {},  # UUID -> Discord ID mapping
                    "discord_to_uuid": {},  # Discord ID -> UUID mapping
                    "ign_to_uuid": {},      # IGN -> UUID mapping (for quick lookups)
                    "metadata": {
                        "created": time.time(), 
                        "last_updated": time.time(),
                        "version": "2.0"  # Mark as new format
                    }
                }
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON verification cache: {e}")
            return self._create_empty_cache()
        except Exception as e:
            logger.error(f"Error loading verification cache: {e}")
            return self._create_empty_cache()
    
    def _create_empty_cache(self) -> Dict[str, Any]:
        """Create an empty cache with proper structure"""
        return {
            "verified_users": {},
            "uuid_to_discord": {},
            "discord_to_uuid": {},
            "ign_to_uuid": {},
            "metadata": {
                "created": time.time(), 
                "last_updated": time.time(),
                "version": "2.0"
            }
        }
    
    def _needs_migration(self, cache: Dict[str, Any]) -> bool:
        """Check if cache needs migration from old format"""
        metadata = cache.get("metadata", {})
        version = metadata.get("version", "1.0")
        
        # Check if it's using old Discord ID-based keys
        verified_users = cache.get("verified_users", {})
        if verified_users:
            # Check if keys look like Discord IDs (all numeric)
            first_key = next(iter(verified_users.keys()), None)
            if first_key and first_key.isdigit():
                return True
        
        return version != "2.0"
    
    def _migrate_cache_format(self, old_cache: Dict[str, Any]) -> Dict[str, Any]:
        """Migrate from Discord ID-based keys to UUID-based keys"""
        logger.info("Migrating verification cache from v1.0 to v2.0 (Discord ID keys to UUID keys)")
        
        new_cache = self._create_empty_cache()
        old_verified_users = old_cache.get("verified_users", {})
        
        for discord_id, user_data in old_verified_users.items():
            player_uuid = user_data.get("player_uuid")
            if player_uuid:
                # Store under UUID
                new_cache["verified_users"][player_uuid] = user_data
                
                # Update mapping tables
                new_cache["uuid_to_discord"][player_uuid] = discord_id
                new_cache["discord_to_uuid"][discord_id] = player_uuid
                
                ign = user_data.get("ign")
                if ign:
                    new_cache["ign_to_uuid"][ign.lower()] = player_uuid
            else:
                logger.warning(f"Skipping user data without UUID during migration: {user_data}")
        
        # Preserve old metadata but update version
        if "metadata" in old_cache:
            new_cache["metadata"].update(old_cache["metadata"])
        new_cache["metadata"]["version"] = "2.0"
        new_cache["metadata"]["migrated_at"] = time.time()
        
        logger.info(f"Migration complete: {len(new_cache['verified_users'])} users migrated")
        return new_cache
    
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
    
    def _update_mappings(self, player_uuid: str, discord_id: str, ign: str):
        """Update the mapping tables"""
        # Update UUID -> Discord mapping
        self.cache["uuid_to_discord"][player_uuid] = discord_id
        
        # Update Discord -> UUID mapping
        self.cache["discord_to_uuid"][discord_id] = player_uuid
        
        # Update IGN -> UUID mapping (case insensitive)
        if ign:
            self.cache["ign_to_uuid"][ign.lower()] = player_uuid
    
    def _remove_mappings(self, player_uuid: str):
        """Remove a user from all mapping tables"""
        # Get user data to find Discord ID and IGN
        user_data = self.cache.get("verified_users", {}).get(player_uuid)
        if not user_data:
            return
        
        discord_id = user_data.get("discord_id")
        ign = user_data.get("ign")
        
        # Remove from UUID -> Discord mapping
        if player_uuid in self.cache["uuid_to_discord"]:
            del self.cache["uuid_to_discord"][player_uuid]
        
        # Remove from Discord -> UUID mapping
        if discord_id and discord_id in self.cache["discord_to_uuid"]:
            del self.cache["discord_to_uuid"][discord_id]
        
        # Remove from IGN -> UUID mapping
        if ign and ign.lower() in self.cache["ign_to_uuid"]:
            del self.cache["ign_to_uuid"][ign.lower()]
    
    def add_verified_user(self, discord_id: str, discord_username: str, ign: str, 
                         player_uuid: str, nation: str, town: str, 
                         is_mayor: bool = False, county: str = None, 
                         guild_id: str = None, verified_by: str = None,
                         town_uuid: str = None, nation_uuid: str = None) -> bool:
        """Add a verified user to the cache using UUID as primary key"""
        try:
            if not player_uuid:
                logger.error("Cannot add verified user without UUID")
                return False
            
            verification_data = {
                "discord_id": discord_id,
                "discord_username": discord_username,
                "ign": ign,
                "player_uuid": player_uuid,
                "nation": nation,
                "nation_uuid": nation_uuid,
                "town": town,
                "town_uuid": town_uuid,
                "is_mayor": is_mayor,
                "county": county,
                "guild_id": guild_id,
                "verified_by": verified_by,
                "verified_at": time.time(),
                "last_updated": time.time()
            }
            
            # Store by UUID as primary key
            self.cache["verified_users"][player_uuid] = verification_data
            
            # Update mapping tables
            self._update_mappings(player_uuid, discord_id, ign)
            
            # Save to file
            if self._save_cache():
                logger.info(f"Added verified user to cache: {ign} (UUID: {player_uuid}, Discord: {discord_username})")
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Error adding verified user to cache: {e}")
            return False
    
    def get_verified_user_by_uuid(self, player_uuid: str) -> Optional[Dict[str, Any]]:
        """Get verified user data by player UUID"""
        return self.cache.get("verified_users", {}).get(player_uuid)
    
    def get_verified_user_by_discord_id(self, discord_id: str) -> Optional[Dict[str, Any]]:
        """Get verified user data by Discord ID"""
        # Use mapping table to find UUID
        player_uuid = self.cache.get("discord_to_uuid", {}).get(discord_id)
        if player_uuid:
            return self.get_verified_user_by_uuid(player_uuid)
        return None
    
    def get_verified_user(self, discord_id: str) -> Optional[Dict[str, Any]]:
        """Get verified user data by Discord ID (backwards compatibility)"""
        return self.get_verified_user_by_discord_id(discord_id)
    
    def get_user_by_ign(self, ign: str) -> Optional[Dict[str, Any]]:
        """Get verified user data by IGN"""
        # Use mapping table to find UUID
        player_uuid = self.cache.get("ign_to_uuid", {}).get(ign.lower())
        if player_uuid:
            return self.get_verified_user_by_uuid(player_uuid)
        return None
    
    def get_user_by_uuid(self, player_uuid: str) -> Optional[Dict[str, Any]]:
        """Get verified user data by player UUID (backwards compatibility)"""
        return self.get_verified_user_by_uuid(player_uuid)
    
    def update_user_data(self, player_uuid: str, **updates) -> bool:
        """Update specific fields for a verified user by UUID"""
        try:
            if player_uuid in self.cache.get("verified_users", {}):
                old_data = self.cache["verified_users"][player_uuid].copy()
                self.cache["verified_users"][player_uuid].update(updates)
                self.cache["verified_users"][player_uuid]["last_updated"] = time.time()
                
                # Update mappings if Discord ID or IGN changed
                new_discord_id = updates.get("discord_id")
                new_ign = updates.get("ign")
                
                if new_discord_id or new_ign:
                    discord_id = new_discord_id or old_data.get("discord_id")
                    ign = new_ign or old_data.get("ign")
                    self._update_mappings(player_uuid, discord_id, ign)
                
                if self._save_cache():
                    logger.info(f"Updated verified user data for UUID: {player_uuid}")
                    return True
            else:
                logger.warning(f"Attempted to update non-existent verified user: {player_uuid}")
                return False
        except Exception as e:
            logger.error(f"Error updating verified user data: {e}")
            return False
    
    def update_user_data_by_discord_id(self, discord_id: str, **updates) -> bool:
        """Update specific fields for a verified user by Discord ID"""
        player_uuid = self.cache.get("discord_to_uuid", {}).get(discord_id)
        if player_uuid:
            return self.update_user_data(player_uuid, **updates)
        else:
            logger.warning(f"No UUID found for Discord ID: {discord_id}")
            return False
    
    def remove_verified_user_by_uuid(self, player_uuid: str) -> bool:
        """Remove a verified user from the cache by UUID"""
        try:
            if player_uuid in self.cache.get("verified_users", {}):
                user_data = self.cache["verified_users"][player_uuid]
                
                # Remove from mapping tables
                self._remove_mappings(player_uuid)
                
                # Remove main entry
                del self.cache["verified_users"][player_uuid]
                
                if self._save_cache():
                    logger.info(f"Removed verified user from cache: {user_data.get('ign', 'Unknown')} (UUID: {player_uuid})")
                    return True
            else:
                logger.warning(f"Attempted to remove non-existent verified user: {player_uuid}")
                return False
        except Exception as e:
            logger.error(f"Error removing verified user from cache: {e}")
            return False
    
    def remove_verified_user(self, discord_id: str) -> bool:
        """Remove a verified user from the cache by Discord ID (backwards compatibility)"""
        player_uuid = self.cache.get("discord_to_uuid", {}).get(discord_id)
        if player_uuid:
            return self.remove_verified_user_by_uuid(player_uuid)
        else:
            logger.warning(f"No UUID found for Discord ID: {discord_id}")
            return False
    
    def get_users_by_nation(self, nation: str) -> List[Dict[str, Any]]:
        """Get all verified users from a specific nation (backwards compatibility)"""
        users = []
        for user_data in self.cache.get("verified_users", {}).values():
            if user_data.get("nation", "").lower() == nation.lower():
                users.append(user_data)
        return users
    
    def get_users_by_county(self, nation: str, county: str) -> List[Dict[str, Any]]:
        """Get all verified users from a specific county (backwards compatibility)"""
        users = []
        for user_data in self.cache.get("verified_users", {}).values():
            if (user_data.get("nation", "").lower() == nation.lower() and 
                user_data.get("county", "").lower() == county.lower()):
                users.append(user_data)
        return users
    
    def get_users_by_nation_uuid(self, nation_uuid: str) -> List[Dict[str, Any]]:
        """Get all verified users from a specific nation using nation UUID"""
        users = []
        for user_data in self.cache.get("verified_users", {}).values():
            if user_data.get("nation_uuid") == nation_uuid:
                users.append(user_data)
        return users
    
    def get_users_by_town_uuid(self, town_uuid: str) -> List[Dict[str, Any]]:
        """Get all verified users from a specific town using town UUID"""
        users = []
        for user_data in self.cache.get("verified_users", {}).values():
            if user_data.get("town_uuid") == town_uuid:
                users.append(user_data)
        return users
    
    def get_users_by_county_uuid(self, nation_uuid: str, county: str) -> List[Dict[str, Any]]:
        """Get all verified users from a specific county using nation UUID"""
        users = []
        for user_data in self.cache.get("verified_users", {}).values():
            if (user_data.get("nation_uuid") == nation_uuid and 
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
            "cache_file": self.cache_file,
            "cache_version": metadata.get("version", "1.0"),
            "mapping_tables": {
                "uuid_to_discord": len(self.cache.get("uuid_to_discord", {})),
                "discord_to_uuid": len(self.cache.get("discord_to_uuid", {})),
                "ign_to_uuid": len(self.cache.get("ign_to_uuid", {}))
            }
        }
    
    def cleanup_old_entries(self, max_age_days: int = 30) -> int:
        """Remove verification entries older than specified days"""
        try:
            current_time = time.time()
            max_age_seconds = max_age_days * 24 * 60 * 60
            
            to_remove = []
            for player_uuid, user_data in self.cache.get("verified_users", {}).items():
                verified_at = user_data.get("verified_at", 0)
                if current_time - verified_at > max_age_seconds:
                    to_remove.append(player_uuid)
            
            for player_uuid in to_remove:
                self._remove_mappings(player_uuid)
                del self.cache["verified_users"][player_uuid]
            
            if to_remove:
                self._save_cache()
                logger.info(f"Cleaned up {len(to_remove)} old verification entries")
            
            return len(to_remove)
            
        except Exception as e:
            logger.error(f"Error cleaning up old verification entries: {e}")
            return 0
    
    def rebuild_mappings(self) -> bool:
        """Rebuild mapping tables from verified users data"""
        try:
            logger.info("Rebuilding verification cache mapping tables")
            
            # Clear existing mappings
            self.cache["uuid_to_discord"] = {}
            self.cache["discord_to_uuid"] = {}
            self.cache["ign_to_uuid"] = {}
            
            # Rebuild from verified users
            for player_uuid, user_data in self.cache.get("verified_users", {}).items():
                discord_id = user_data.get("discord_id")
                ign = user_data.get("ign")
                
                if discord_id and ign:
                    self._update_mappings(player_uuid, discord_id, ign)
            
            if self._save_cache():
                logger.info("Successfully rebuilt verification cache mapping tables")
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Error rebuilding mapping tables: {e}")
            return False
    
    def export_to_csv(self, filename: str = None) -> str:
        """Export verification cache to CSV format"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"verification_export_{timestamp}.csv"
        
        try:
            import csv
            
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = [
                    'player_uuid', 'discord_id', 'discord_username', 'ign', 
                    'nation', 'nation_uuid', 'town', 'town_uuid', 'is_mayor', 'county', 'guild_id', 
                    'verified_by', 'verified_at', 'last_updated'
                ]
                
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for player_uuid, user_data in self.cache.get("verified_users", {}).items():
                    # Convert timestamps to readable format
                    row_data = user_data.copy()
                    row_data['player_uuid'] = player_uuid  # Add UUID as first column
                    
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