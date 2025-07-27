import discord
import json
import os
import logging
from typing import Dict, Any, Optional, Union

logger = logging.getLogger(__name__)

class ResponseManager:
    def __init__(self, responses_file: str = "./discadian/responses.json"):
        self.responses_file = responses_file
        self.responses = self._load_responses()
    
    def _load_responses(self) -> Dict[str, Any]:
        """Load responses from JSON file"""
        try:
            if os.path.exists(self.responses_file):
                with open(self.responses_file, 'r', encoding='utf-8') as f:
                    responses = json.load(f)
                logger.info(f"Responses loaded from {self.responses_file}")
                return responses
            else:
                logger.error(f"Responses file {self.responses_file} not found!")
                return {"embeds": {}, "messages": {}, "colors": {}, "formatting": {}}
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON responses: {e}")
            return {"embeds": {}, "messages": {}, "colors": {}, "formatting": {}}
        except Exception as e:
            logger.error(f"Error loading responses: {e}")
            return {"embeds": {}, "messages": {}, "colors": {}, "formatting": {}}
    
    def reload_responses(self):
        """Reload responses from file"""
        self.responses = self._load_responses()
    
    def get_message(self, key_path: str, **kwargs) -> str:
        """
        Get a message from the responses file
        key_path: dot-separated path like 'verification.success_base'
        """
        try:
            keys = key_path.split('.')
            current = self.responses.get("messages", {})
            
            for key in keys:
                if isinstance(current, dict) and key in current:
                    current = current[key]
                else:
                    logger.warning(f"Message key not found: {key_path}")
                    return f"[Missing: {key_path}]"
            
            if isinstance(current, str):
                return current.format(**kwargs)
            else:
                logger.warning(f"Message key is not a string: {key_path}")
                return f"[Invalid: {key_path}]"
                
        except KeyError as e:
            logger.error(f"Missing variable in message {key_path}: {e}")
            return f"[Error: {key_path} - Missing variable {e}]"
        except Exception as e:
            logger.error(f"Error getting message {key_path}: {e}")
            return f"[Error: {key_path}]"
    
    def get_color(self, color_name: str) -> int:
        """Get a color value from the responses file"""
        color_str = self.responses.get("colors", {}).get(color_name, "0x2f3136")
        try:
            return int(color_str, 16)
        except ValueError:
            logger.warning(f"Invalid color format: {color_str}")
            return 0x2f3136
    
    def get_formatting(self, key: str, **kwargs) -> str:
        """Get a formatting string"""
        format_str = self.responses.get("formatting", {}).get(key, "{key}")
        return format_str.format(**kwargs)
    
    def create_embed(self, embed_key: str, **kwargs) -> discord.Embed:
        """
        Create a Discord embed from the responses configuration
        embed_key: key in the embeds section
        **kwargs: variables to substitute in the embed
        """
        try:
            embed_config = self.responses.get("embeds", {}).get(embed_key)
            if not embed_config:
                logger.warning(f"Embed config not found: {embed_key}")
                return discord.Embed(
                    title="❌ Error",
                    description=f"Embed configuration '{embed_key}' not found",
                    color=self.get_color("error")
                )
            
            # Create base embed
            title = embed_config.get("title", "").format(**kwargs)
            description = embed_config.get("description", "").format(**kwargs)
            color = self.get_color("info")  # default
            
            # Parse color
            if "color" in embed_config:
                color_str = embed_config["color"]
                try:
                    color = int(color_str, 16)
                except ValueError:
                    logger.warning(f"Invalid color in embed {embed_key}: {color_str}")
            
            embed = discord.Embed(title=title, description=description, color=color)
            
            # Add timestamp if specified
            if embed_config.get("timestamp", False):
                embed.timestamp = discord.utils.utcnow()
            
            # Add fields
            for field_config in embed_config.get("fields", []):
                # Check if field is conditional
                if field_config.get("conditional"):
                    condition = field_config["conditional"]
                    if isinstance(condition, str):
                        # Simple boolean check
                        if not kwargs.get(condition, False):
                            continue
                    elif isinstance(condition, bool):
                        if not condition:
                            continue
                
                field_name = field_config["name"].format(**kwargs)
                field_value = field_config["value"].format(**kwargs)
                field_inline = field_config.get("inline", False)
                
                embed.add_field(name=field_name, value=field_value, inline=field_inline)
            
            # Add footer if specified
            footer_config = embed_config.get("footer")
            if footer_config:
                footer_text = footer_config.get("text", "").format(**kwargs)
                embed.set_footer(text=footer_text)
            
            return embed
            
        except KeyError as e:
            logger.error(f"Missing variable in embed {embed_key}: {e}")
            return discord.Embed(
                title="❌ Configuration Error",
                description=f"Missing variable in embed: {e}",
                color=self.get_color("error")
            )
        except Exception as e:
            logger.error(f"Error creating embed {embed_key}: {e}")
            return discord.Embed(
                title="❌ Embed Error",
                description=f"Error creating embed: {str(e)}",
                color=self.get_color("error")
            )
    
    def build_verification_message(self, ign: str, town: str, nation: str, 
                                 link_status: str, is_mayor: bool = False, 
                                 county: str = None, has_county: bool = True) -> str:
        """Build a complete verification success message"""
        message = self.get_message("verification.success_base", 
                                 ign=ign, town=town, nation=nation, link_status=link_status)
        
        if is_mayor:
            message += self.get_message("verification.success_mayor", town=town)
        
        if county:
            message += self.get_message("verification.success_county", county=county)
        elif not has_county:
            message += self.get_message("verification.success_no_county")
        
        return message

# Global response manager instance
response_manager = ResponseManager()

# Convenience functions for backwards compatibility
def create_permission_denied_embed() -> discord.Embed:
    return response_manager.create_embed("permission_denied")

def create_error_embed(title: str, description: str) -> discord.Embed:
    return response_manager.create_embed("error_generic", message=description)

def create_success_embed(title: str, description: str, user: discord.Member = None) -> discord.Embed:
    kwargs = {"message": description}
    if user:
        kwargs["user_mention"] = user.mention
    return response_manager.create_embed("success_generic", **kwargs)

def create_warning_embed(title: str, description: str) -> discord.Embed:
    return response_manager.create_embed("warning_generic", message=description)