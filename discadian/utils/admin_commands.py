embed = create_error_embed("❌ Error", "An unexpected error occurred while generating the CSV.")
            await interaction.followup.send(embed=embed)

    @bot.tree.command(name="alliance_add", description="Add a nation to the allied nations list")
    async def alliance_add_command(interaction: discord.Interaction, nation_uuid: str, nation_name: str = None):
        if not is_approved_guild(interaction.guild.id):
            return
        
        guild_nation = get_nation_for_guild(interaction.guild.id)
        if not guild_nation:
            embed = create_error_embed("❌ No Nation Configuration", "This guild is not configured for any nation.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if not has_admin_permission(interaction.user, guild_nation):
            await interaction.response.send_message(embed=create_permission_denied_embed(), ephemeral=True)
            return
        
        try:
            # Get current allied nations
            current_allies = config_manager.get_nation_setting(guild_nation, "allied_nations", [])
            
            if nation_uuid in current_allies:
                embed = create_warning_embed("⚠️ Already Allied", f"Nation UUID `{nation_uuid}` is already in the allied nations list.")
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Add to allied nations
            current_allies.append(nation_uuid)
            success = config_manager.set_nation_setting(guild_nation, "allied_nations", current_allies)
            
            if success:
                embed = create_success_embed(
                    "✅ Alliance Added", 
                    f"Added nation UUID `{nation_uuid}` to allied nations list.",
                    interaction.user
                )
                if nation_name:
                    embed.add_field(name="Nation Name", value=nation_name, inline=True)
                embed.add_field(name="Total Allies", value=len(current_allies), inline=True)
                
                # Trigger relationship updates for existing users
                await update_relationships_for_alliance_change(guild_nation, nation_uuid, 'added')
                
                await interaction.response.send_message(embed=embed)
            else:
                embed = create_error_embed("❌ Configuration Error", "Failed to save alliance configuration.")
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error in alliance_remove_command: {e}")
            embed = create_error_embed("❌ Error", "An unexpected error occurred while removing the alliance.")
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name="alliance_list", description="List all allied nations")
    async def alliance_list_command(interaction: discord.Interaction):
        if not is_approved_guild(interaction.guild.id):
            return
        
        guild_nation = get_nation_for_guild(interaction.guild.id)
        if not guild_nation:
            embed = create_error_embed("❌ No Nation Configuration", "This guild is not configured for any nation.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if not has_admin_permission(interaction.user, guild_nation):
            await interaction.response.send_message(embed=create_permission_denied_embed(), ephemeral=True)
            return
        
        try:
            allied_nations = config_manager.get_nation_setting(guild_nation, "allied_nations", [])
            
            embed = discord.Embed(
                title=f"🤝 Allied Nations for {guild_nation}",
                color=0x2f3136,
                timestamp=discord.utils.utcnow()
            )
            
            if not allied_nations:
                embed.description = "No allied nations configured."
            else:
                allies_text = "\n".join([f"• `{uuid}`" for uuid in allied_nations])
                embed.add_field(name="Allied Nation UUIDs", value=allies_text, inline=False)
                embed.add_field(name="Total Allies", value=len(allied_nations), inline=True)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in alliance_list_command: {e}")
            embed = create_error_embed("❌ Error", "An unexpected error occurred while listing alliances.")
            await interaction.response.send_message(embed=embed, ephemeral=True)

async def update_relationships_for_alliance_change(guild_nation: str, changed_nation_uuid: str, action: str):
    """Update relationship roles for all users when alliance status changes"""
    try:
        from utils.verification_cache import verification_cache
        mgm = get_multi_guild_manager()
        
        if not mgm:
            logger.error("Multi-guild manager not available for relationship updates")
            return
        
        guild = mgm.get_guild_for_nation(guild_nation)
        if not guild:
            logger.warning(f"Guild not found for nation {guild_nation}")
            return
        
        # Get all verified users
        verified_users = verification_cache.cache.get("verified_users", {})
        affected_users = []
        
        # Find users from the changed nation
        for player_uuid, user_data in verified_users.items():
            user_nation_uuid = user_data.get("nation_uuid")
            discord_id = user_data.get("discord_id")
            
            if user_nation_uuid == changed_nation_uuid and discord_id:
                member = guild.get_member(int(discord_id))
                if member:
                    affected_users.append((member, user_data))
        
        if not affected_users:
            logger.info(f"No users found to update for alliance change: {action} {changed_nation_uuid}")
            return
        
        logger.info(f"Updating {len(affected_users)} users for alliance {action}: {changed_nation_uuid}")
        
        # Update each affected user
        for member, user_data in affected_users:
            try:
                ign = user_data.get("ign", "Unknown")
                nation_name = user_data.get("nation", "Unknown")
                
                # Determine old and new relationships
                if action == 'added':
                    old_relationship = 'foreigner'
                    new_relationship = 'allied'
                else:  # removed
                    old_relationship = 'allied'
                    new_relationship = 'foreigner'
                
                logger.info(f"Updating {ign} relationship: {old_relationship} → {new_relationship}")
                
                # Remove old relationship roles
                await mgm.remove_relationship_roles(member, guild_nation, old_relationship)
                
                # Add new relationship roles
                await mgm.assign_roles_for_nation(
                    member, ign, nation_name, 
                    user_data.get("is_mayor", False),
                    None, None,  # No county roles for non-citizens
                    changed_nation_uuid, guild_nation
                )
                
            except Exception as e:
                logger.error(f"Error updating user {user_data.get('ign', 'Unknown')}: {e}")
        
        logger.info(f"Completed relationship updates for alliance {action}")
        
    except Exception as e:
        logger.error(f"Error updating relationships for alliance change: {e}") Configuration Error", "Failed to save alliance configuration.")
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
        except Exception as e:
            logger.error(f"Error in alliance_add_command: {e}")
            embed = create_error_embed("❌ Error", "An unexpected error occurred while adding the alliance.")
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name="alliance_remove", description="Remove a nation from the allied nations list")
    async def alliance_remove_command(interaction: discord.Interaction, nation_uuid: str):
        if not is_approved_guild(interaction.guild.id):
            return
        
        guild_nation = get_nation_for_guild(interaction.guild.id)
        if not guild_nation:
            embed = create_error_embed("❌ No Nation Configuration", "This guild is not configured for any nation.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if not has_admin_permission(interaction.user, guild_nation):
            await interaction.response.send_message(embed=create_permission_denied_embed(), ephemeral=True)
            return
        
        try:
            # Get current allied nations
            current_allies = config_manager.get_nation_setting(guild_nation, "allied_nations", [])
            
            if nation_uuid not in current_allies:
                embed = create_warning_embed("⚠️ Not Allied", f"Nation UUID `{nation_uuid}` is not in the allied nations list.")
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Remove from allied nations
            current_allies.remove(nation_uuid)
            success = config_manager.set_nation_setting(guild_nation, "allied_nations", current_allies)
            
            if success:
                embed = create_success_embed(
                    "✅ Alliance Removed", 
                    f"Removed nation UUID `{nation_uuid}` from allied nations list.",
                    interaction.user
                )
                embed.add_field(name="Total Allies", value=len(current_allies), inline=True)
                
                # Trigger relationship updates for existing users
                await update_relationships_for_alliance_change(guild_nation, nation_uuid, 'removed')
                
                await interaction.response.send_message(embed=embed)
            else:
                embed = create_error_embed("❌import discord
import logging
import os

from utils.permissions import has_admin_permission, is_approved_guild, get_nation_for_guild
from utils.responses import create_permission_denied_embed, create_error_embed, create_success_embed, create_warning_embed, response_manager
from roles.multi_guild_manager import get_multi_guild_manager
from api.earthmc import get_nation_info, get_town_info
from config import config_manager

logger = logging.getLogger(__name__)

def setup_admin_commands(bot):
    """Setup admin and tool commands"""
    
    @bot.tree.command(name="test", description="Test if the bot is working")
    async def test_command(interaction: discord.Interaction):
        if not is_approved_guild(interaction.guild.id):
            return
        
        guild_nation = get_nation_for_guild(interaction.guild.id)
        embed = discord.Embed(
            title="🤖 Bot Status",
            description="Bot is working correctly!",
            color=0x00ff00
        )
        embed.add_field(name="Guild Nation", value=guild_nation or "Not configured", inline=True)
        embed.add_field(name="Bot User", value=str(bot.user), inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name="config", description="Show current bot configuration for this guild's nation")
    async def config_command(interaction: discord.Interaction):
        if not is_approved_guild(interaction.guild.id):
            return
        
        guild_nation = get_nation_for_guild(interaction.guild.id)
        if not guild_nation:
            embed = create_error_embed("❌ No Nation Configuration", "This guild is not configured for any nation.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if not has_admin_permission(interaction.user, guild_nation):
            await interaction.response.send_message(embed=create_permission_denied_embed(), ephemeral=True)
            return
        
        mgm = get_multi_guild_manager()
        if not mgm:
            embed = create_error_embed("❌ System Error", "Multi-guild manager not initialized.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        nation_config = mgm.get_nation_config(guild_nation)
        if not nation_config:
            embed = create_error_embed("❌ Configuration Error", f"No configuration found for nation {guild_nation}.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"🔧 Configuration for {guild_nation}",
            color=0x2f3136,
            timestamp=discord.utils.utcnow()
        )
        
        # Basic settings
        verified_role_id = nation_config.get("verified_role_id")
        verified_role = interaction.guild.get_role(verified_role_id) if verified_role_id else None
        verified_role_name = verified_role.name if verified_role else f"Role ID: {verified_role_id} (not found)"
        
        mayor_role_id = nation_config.get("mayor_role_id")
        mayor_role = interaction.guild.get_role(mayor_role_id) if mayor_role_id else None
        mayor_role_name = mayor_role.name if mayor_role else f"Role ID: {mayor_role_id} (not found)"
        
        admin_role_ids = nation_config.get("admin_role_ids", [])
        admin_roles = []
        for role_id in admin_role_ids:
            role = interaction.guild.get_role(role_id)
            admin_roles.append(role.name if role else f"Role ID: {role_id} (not found)")
        
        settings_text = (
            f"• **Verified Role:** {verified_role_name}\n"
            f"• **Mayor Role:** {mayor_role_name}\n"
            f"• **Admin Roles:** {', '.join(admin_roles) if admin_roles else 'None configured'}\n"
            f"• **Nickname Format:** `{nation_config.get('nickname_format', '{ign} ({nation})')}`"
        )
        
        embed.add_field(name="⚙️ Basic Settings", value=settings_text, inline=False)
        
        # Allied/Foreigner roles
        allied_role_id = nation_config.get("allied_role_id")
        allied_role = interaction.guild.get_role(allied_role_id) if allied_role_id else None
        allied_role_name = allied_role.name if allied_role else "Not configured"
        
        foreigner_role_id = nation_config.get("foreigner_role_id")
        foreigner_role = interaction.guild.get_role(foreigner_role_id) if foreigner_role_id else None
        foreigner_role_name = foreigner_role.name if foreigner_role else "Not configured"
        
        relationship_text = (
            f"• **Allied Role:** {allied_role_name}\n"
            f"• **Foreigner Role:** {foreigner_role_name}"
        )
        
        embed.add_field(name="🤝 Relationship Roles", value=relationship_text, inline=False)
        
        # Allied nations
        allied_nations = nation_config.get("allied_nations", [])
        if allied_nations:
            allied_text = "\n".join([f"• `{uuid}`" for uuid in allied_nations])
            embed.add_field(name="🤝 Allied Nation UUIDs", value=allied_text, inline=False)
        else:
            embed.add_field(name="🤝 Allied Nation UUIDs", value="None configured", inline=False)
        
        # County system
        county_system = nation_config.get("county_system", {})
        if county_system.get("enabled", False):
            county_info = []
            for county_name, county_data in county_system.get("counties", {}).items():
                role = interaction.guild.get_role(county_data.get("role_id"))
                role_name = role.name if role else f"Role ID: {county_data.get('role_id')} (not found)"
                towns_count = len(county_data.get("towns", []))
                county_info.append(f"• **{county_name}:** {role_name} ({towns_count} towns)")
            
            no_county_role_id = county_system.get("no_county_role_id")
            no_county_role = interaction.guild.get_role(no_county_role_id) if no_county_role_id else None
            no_county_role_name = no_county_role.name if no_county_role else "Not configured"
            county_info.append(f"• **No County:** {no_county_role_name}")
            
            county_text = "\n".join(county_info) if county_info else "Counties configured but none defined"
            embed.add_field(name="🏛️ County System", value=county_text, inline=False)
        else:
            embed.add_field(name="🏛️ County System", value="Disabled", inline=False)
        
        # Cross-guild settings
        cross_guild_settings = []
        cross_guild_settings.append(f"• **Sync Role Updates:** {config_manager.get_cross_guild_setting('sync_role_updates', True)}")
        cross_guild_settings.append(f"• **Allow Cross-Nation Verification:** {config_manager.get_cross_guild_setting('allow_cross_nation_verification', False)}")
        
        embed.add_field(name="🌐 Cross-Guild Settings", value="\n".join(cross_guild_settings), inline=False)
        
        embed.set_footer(text=f"Guild ID: {interaction.guild.id} | Nation UUID: {nation_config.get('nation_uuid', 'Not set')}")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name="town_lookup", description="Convert between town name and UUID")
    async def town_lookup_command(interaction: discord.Interaction, query: str):
        if not is_approved_guild(interaction.guild.id):
            return
        
        guild_nation = get_nation_for_guild(interaction.guild.id)
        if not guild_nation:
            embed = create_error_embed("❌ No Nation Configuration", "This guild is not configured for any nation.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if not has_admin_permission(interaction.user, guild_nation):
            await interaction.response.send_message(embed=create_permission_denied_embed(), ephemeral=True)
            return
        
        await interaction.response.defer()
        
        try:
            town_result = await get_town_info(query)
            
            if town_result["success"]:
                town_data = town_result["data"]
                town_name = town_data.get("name")
                town_uuid = town_data.get("uuid")
                
                is_uuid_query = len(query) == 36 and query.count('-') == 4
                
                if is_uuid_query:
                    embed = response_manager.create_embed(
                        "town_lookup_result",
                        lookup_type=response_manager.get_message("town_lookup.lookup_type_uuid_to_name"),
                        input_uuid=query,
                        town_name=town_name,
                        user_mention=interaction.user.mention,
                        show_input_uuid=True,
                        show_name=True
                    )
                else:
                    embed = response_manager.create_embed(
                        "town_lookup_result",
                        lookup_type=response_manager.get_message("town_lookup.lookup_type_name_to_uuid"),
                        input_name=query,
                        exact_name=town_name,
                        town_uuid=town_uuid,
                        user_mention=interaction.user.mention,
                        show_input_name=True,
                        show_exact_name=True,
                        show_uuid=True
                    )
                
            else:
                is_uuid_query = len(query) == 36 and query.count('-') == 4
                
                if is_uuid_query:
                    error_message = response_manager.get_message("town_lookup.not_found_uuid", query=query, error=town_result['error'])
                else:
                    error_message = response_manager.get_message("town_lookup.not_found_name", query=query, error=town_result['error'])
                
                embed = response_manager.create_embed("error_generic", message=error_message)
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in town_lookup_command: {e}")
            embed = response_manager.create_embed("error_generic", message=response_manager.get_message("errors.town_lookup_error"))
            await interaction.followup.send(embed=embed)

    @bot.tree.command(name="nation_towns_csv", description="Generate CSV of all towns in a nation with UUIDs and dynmap links")
    async def nation_towns_csv_command(interaction: discord.Interaction, nation_name: str = None):
        if not is_approved_guild(interaction.guild.id):
            return
        
        guild_nation = get_nation_for_guild(interaction.guild.id)
        target_nation = nation_name or guild_nation
        
        if not target_nation:
            embed = create_error_embed("❌ No Nation Specified", "Please specify a nation or ensure this guild is configured for a specific nation.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if not has_admin_permission(interaction.user, target_nation):
            await interaction.response.send_message(embed=create_permission_denied_embed(), ephemeral=True)
            return
        
        await interaction.response.defer()
        
        try:
            nation_result = await get_nation_info(target_nation)
            
            if not nation_result["success"]:
                embed = create_error_embed("❌ Nation Not Found", f"Could not find nation `{target_nation}`: {nation_result['error']}")
                await interaction.followup.send(embed=embed)
                return
            
            nation_data = nation_result["data"]
            towns_list = nation_data.get("towns", [])
            
            if not towns_list:
                embed = create_warning_embed("⚠️ No Towns Found", f"Nation `{target_nation}` has no towns.")
                await interaction.followup.send(embed=embed)
                return
            
            town_names = [town.get("name") for town in towns_list if town.get("name")]
            
            logger.info(f"Fetching detailed info for {len(town_names)} towns using batch system")
            
            from api.earthmc import get_multiple_towns_info
            detailed_towns_dict = await get_multiple_towns_info(town_names)
            
            detailed_towns = []
            for town in towns_list:
                town_name = town.get("name")
                if town_name and town_name in detailed_towns_dict:
                    town_result = detailed_towns_dict[town_name]
                    if town_result.get("success"):
                        detailed_towns.append(town_result["data"])
                    else:
                        logger.warning(f"Failed to get details for {town_name}: {town_result.get('error')}")
                        detailed_towns.append(town)
                else:
                    detailed_towns.append(town)
            
            csv_content = generate_nation_towns_csv(target_nation, detailed_towns)
            
            filename = f"{target_nation.replace(' ', '_')}_towns.csv"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(csv_content)
            
            embed = create_success_embed("✅ CSV Generated", f"Generated CSV for nation `{target_nation}` with {len(detailed_towns)} towns.", interaction.user)
            embed.add_field(name="File", value=filename, inline=True)
            embed.add_field(name="Towns Count", value=len(detailed_towns), inline=True)
            
            file = discord.File(filename, filename=filename)
            await interaction.followup.send(embed=embed, file=file)
            
            os.remove(filename)
            
        except Exception as e:
            logger.error(f"Error in nation_towns_csv_command: {e}")
            embed = create_error_embed("❌ Error", "An unexpected error occurred while generating the CSV.")
            await interaction.followup.send(embed=embed)

def generate_nation_towns_csv(nation_name: str, towns_list: list) -> str:
    """Generate CSV content for nation towns"""
    
    csv_lines = ["Town Name,UUID,County,Homeblock X,Homeblock Z,Spawn X,Spawn Z,Dynmap Link"]
    
    mgm = get_multi_guild_manager()
    town_to_county = {}
    if mgm:
        county_system = mgm.get_county_system_for_nation(nation_name)
        for county_name, county_data in county_system.get("counties", {}).items():
            for town_uuid in county_data.get("towns", []):
                town_to_county[town_uuid] = county_name
    
    for town in towns_list:
        town_name = town.get("name", "Unknown")
        town_uuid = town.get("uuid", "Unknown")
        
        if town_uuid in town_to_county:
            county = town_to_county[town_uuid]
        else:
            if mgm and mgm.get_county_system_for_nation(nation_name).get("enabled", False):
                county = "No County"
            else:
                county = "No County System"
        
        coordinates = town.get("coordinates", {})
        homeblock = coordinates.get("homeBlock", [0, 0])
        homeblock_x = homeblock[0] if len(homeblock) >= 2 else "Unknown"
        homeblock_z = homeblock[1] if len(homeblock) >= 2 else "Unknown"
        
        spawn = coordinates.get("spawn", {})
        if spawn and isinstance(spawn, dict):
            spawn_x = spawn.get("x", 0)
            spawn_z = spawn.get("z", 0)
            
            if isinstance(spawn_x, (int, float)) and isinstance(spawn_z, (int, float)):
                spawn_x_int = int(round(spawn_x))
                spawn_z_int = int(round(spawn_z))
                dynmap_link = f"https://map.earthmc.net/?world=minecraft_overworld&zoom=3&x={spawn_x_int}&z={spawn_z_int}"
                spawn_x_display = spawn_x_int
                spawn_z_display = spawn_z_int
            else:
                spawn_x_display = "Unknown"
                spawn_z_display = "Unknown"
                dynmap_link = "https://map.earthmc.net/?world=minecraft_overworld&zoom=3&x=0&z=0"
        else:
            spawn_x_display = "Unknown"
            spawn_z_display = "Unknown"
            dynmap_link = "https://map.earthmc.net/?world=minecraft_overworld&zoom=3&x=0&z=0"
        
        town_name_escaped = f'"{town_name}"' if ',' in town_name else town_name
        county_escaped = f'"{county}"' if ',' in county else county
        
        csv_row = f"{town_name_escaped},{town_uuid},{county_escaped},{homeblock_x},{homeblock_z},{spawn_x_display},{spawn_z_display},{dynmap_link}"
        csv_lines.append(csv_row)
    
    return '\n'.join(csv_lines)