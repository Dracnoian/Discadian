import time
import json
import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class CacheManager:
    def __init__(self, cache_file: str = "cache.json", default_ttl: int = 300):
        self.cache_file = cache_file
        self.default_ttl = default_ttl
        self.cache = self._load_cache()
    
    def _load_cache(self) -> Dict[str, Any]:
        """Load cache from JSON file"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
                logger.info(f"Cache loaded from {self.cache_file}")
                return cache
            else:
                logger.info(f"Cache file {self.cache_file} not found, starting with empty cache")
                return {}
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON cache: {e}")
            return {}
        except Exception as e:
            logger.error(f"Error loading cache: {e}")
            return {}
    
    def _save_cache(self) -> bool:
        """Save current cache to JSON file"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Error saving cache: {e}")
            return False
    
    def _is_expired(self, timestamp: float, ttl: int) -> bool:
        """Check if cache entry is expired"""
        return time.time() - timestamp > ttl
    
    def get(self, key: str, ttl: Optional[int] = None) -> Optional[Any]:
        """Get a value from cache if not expired"""
        if ttl is None:
            ttl = self.default_ttl
        
        if key in self.cache:
            entry = self.cache[key]
            if not self._is_expired(entry['timestamp'], ttl):
                logger.debug(f"Cache hit for key: {key}")
                return entry['data']
            else:
                logger.debug(f"Cache expired for key: {key}")
                del self.cache[key]
                self._save_cache()
        
        logger.debug(f"Cache miss for key: {key}")
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set a value in cache"""
        if ttl is None:
            ttl = self.default_ttl
        
        self.cache[key] = {
            'data': value,
            'timestamp': time.time(),
            'ttl': ttl
        }
        
        logger.debug(f"Cache set for key: {key}")
        return self._save_cache()
    
    def delete(self, key: str) -> bool:
        """Delete a value from cache"""
        if key in self.cache:
            del self.cache[key]
            logger.debug(f"Cache deleted for key: {key}")
            return self._save_cache()
        return False
    
    def clear(self) -> bool:
        """Clear all cache entries"""
        self.cache = {}
        logger.info("Cache cleared")
        return self._save_cache()
    
    def cleanup_expired(self) -> int:
        """Remove all expired entries from cache"""
        current_time = time.time()
        expired_keys = []
        
        for key, entry in self.cache.items():
            if self._is_expired(entry['timestamp'], entry.get('ttl', self.default_ttl)):
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.cache[key]
        
        if expired_keys:
            self._save_cache()
            logger.info(f"Cleaned up {len(expired_keys)} expired cache entries")
        
        return len(expired_keys)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        current_time = time.time()
        total_entries = len(self.cache)
        expired_entries = 0
        
        for entry in self.cache.values():
            if self._is_expired(entry['timestamp'], entry.get('ttl', self.default_ttl)):
                expired_entries += 1
        
        return {
            'total_entries': total_entries,
            'active_entries': total_entries - expired_entries,
            'expired_entries': expired_entries,
            'cache_file': self.cache_file,
            'default_ttl': self.default_ttl
        }

# Create global cache manager instance
cache_manager = CacheManager()