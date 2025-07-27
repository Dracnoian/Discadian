import discord
from discord.ext import commands
import logging
import os
from datetime import datetime

# Import configuration
from config import config_manager

# Import utilities
from utils.permissions import has_admin_permission, is_approved_guild
from utils.responses import response_manager, create_permission_denied_embed, create_error_embed, create_success_embed, create_warning_embed
from utils.cache import cache_manager
from utils.verification_cache import verification_cache

# Import verification system
from verification.core import verify_player
from api.earthmc import get_player_info, get_nation_info

# Import role management
from roles.manager import assign_roles_and_nickname, send_contradiction_report, handle_role_updates

# Import county system
from county.system import get_county_for_town
from county.commands import setup_county_commands

# Import periodic verification
from verification.periodic import setup_periodic_verification

from discord import app_commands

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VerificationBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True
        super().__init__(command_prefix='!', intents=intents)

    async def setup_hook(self):
        # Setup county commands
        setup_county_commands(self)
        
        # Setup periodic verification
        self.periodic_verification = setup_periodic_verification(self)
        
        # Sync slash commands
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} command(s)")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")

bot = VerificationBot()

@bot.event
async def on_ready():
    logger.info(f'{bot.user} has connected to Discord!')
    logger.info(f'Bot is ready for EarthMC verification!')
    
    # Clean up expired cache entries on startup
    expired_count = cache_manager.cleanup_expired()
    if expired_count > 0:
        logger.info(f"Cleaned up {expired_count} expired cache entries on startup")

@bot.tree.command(name="verify", description="Verify a player's EarthMC nation membership")
async def verify_command(interaction: discord.Interaction, member: discord.Member, ign: str):
    # Check if guild is approved
    if not is_approved_guild(interaction.guild.id):
        return  # Silently ignore if not in approved guild
    
    # Check if user has admin permission
    if not has_admin_permission(interaction.user):
        await interaction.response.send_message(embed=create_permission_denied_embed(), ephemeral=True)
        return
    
    await interaction.response.defer()
    
    try:
        # Check if user is already verified
        existing_verification = verification_cache.get_verified_user_by_discord_id(str(member.id))
        is_reverification = existing_verification is not None
        
        # Perform verification
        result = await verify_player(str(member.id), ign)
        
        if result.success:
            # Get player info to extract UUIDs
            player_result = await get_player_info(ign)
            town_uuid = None
            nation_uuid = None
            
            if player_result["success"]:
                player_data = player_result["data"]
                town_data = player_data.get("town", {})
                nation_data = player_data.get("nation", {})
                town_uuid = town_data.get("uuid") if town_data else None
                nation_uuid = nation_data.get("uuid") if nation_data else None
            
            # Get county role info using UUIDs when possible
            if nation_uuid and town_uuid:
                from county.system import get_county_for_town_uuid
                county_name, county_role_id, has_county = get_county_for_town_uuid(nation_uuid, town_uuid)
            else:
                # Fallback to name-based lookup
                county_name, county_role_id, has_county = get_county_for_town(result.nation, town_uuid) if town_uuid else (None, None, True)
            
            # Handle role updates for re-verification or initial verification
            if is_reverification:
                roles_updated = await handle_role_updates(
                    member, ign, result.nation, result.is_mayor, county_name, county_role_id,
                    existing_verification
                )
            else:
                roles_updated = await assign_roles_and_nickname(
                    member, ign, result.nation, result.is_mayor, county_name, county_role_id
                )
            
            if roles_updated:
                # Save/update verification data in cache
                player_result = await get_player_info(ign)
                if player_result["success"]:
                    player_data = player_result["data"]
                    player_uuid = player_data.get("uuid")
                    
                    # Extract UUIDs for town and nation
                    town_data = player_data.get("town", {})
                    nation_data = player_data.get("nation", {})
                    town_uuid = town_data.get("uuid") if town_data else None
                    nation_uuid = nation_data.get("uuid") if nation_data else None
                    
                    if is_reverification:
                        # Update existing verification
                        verification_cache.update_user_data_by_discord_id(
                            discord_id=str(member.id),
                            ign=ign,
                            nation=result.nation,
                            nation_uuid=nation_uuid,
                            town=result.town,
                            town_uuid=town_uuid,
                            is_mayor=result.is_mayor,
                            county=county_name,
                            last_verified_by=str(interaction.user.id),
                            last_verified_at=datetime.utcnow().timestamp()
                        )
                    else:
                        # Add new verification
                        verification_cache.add_verified_user(
                            discord_id=str(member.id),
                            discord_username=f"{member.name}#{member.discriminator}" if member.discriminator != "0" else member.name,
                            ign=ign,
                            player_uuid=player_uuid,
                            nation=result.nation,
                            nation_uuid=nation_uuid,
                            town=result.town,
                            town_uuid=town_uuid,
                            is_mayor=result.is_mayor,
                            county=county_name,
                            guild_id=str(interaction.guild.id),
                            verified_by=str(interaction.user.id)
                        )
                
                # Create appropriate embed based on verification type
                if is_reverification:
                    embed_key = "verification_update_success"
                    embed = response_manager.create_embed(
                        embed_key,
                        message=result.message,
                        user_mention=member.mention,
                        admin_mention=interaction.user.mention,
                        old_nation=existing_verification.get('nation', 'Unknown'),
                        new_nation=result.nation,
                        old_town=existing_verification.get('town', 'Unknown'),
                        new_town=result.town
                    )
                else:
                    embed = response_manager.create_embed(
                        "verification_success",
                        message=result.message,
                        user_mention=member.mention,
                        admin_mention=interaction.user.mention
                    )
                
                # Add special message for towns not in counties
                county_system = config_manager.get("county_system", {})
                if not has_county and result.nation in county_system:
                    county_notice_embed = response_manager.create_embed(
                        "verification_county_notice",
                        town=result.town,
                        nation=result.nation
                    )
                    # Add as a field to the main embed
                    embed.add_field(
                        name=county_notice_embed.title,
                        value=county_notice_embed.description,
                        inline=False
                    )
            else:
                embed_key = "verification_update_partial" if is_reverification else "verification_partial"
                embed = response_manager.create_embed(
                    embed_key,
                    message=result.message,
                    user_mention=member.mention,
                    admin_mention=interaction.user.mention
                )
            
            await interaction.followup.send(embed=embed)
        else:
            # Handle contradiction reports
            if result.contradiction_data:
                await send_contradiction_report(bot, result.contradiction_data)
            
            # Send simple failure message without embed
            await interaction.followup.send(result.message)
            
    except Exception as e:
        logger.error(f"Error in verify command: {e}")
        embed = response_manager.create_embed("error_generic", message=response_manager.get_message("errors.verification_error"))
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="config", description="Show current bot configuration")
async def config_command(interaction: discord.Interaction):
    # Check if guild is approved
    if not is_approved_guild(interaction.guild.id):
        return  # Silently ignore if not in approved guild
    
    # Check if user has admin permission
    if not has_admin_permission(interaction.user):
        await interaction.response.send_message(embed=create_permission_denied_embed(), ephemeral=True)
        return
    
    # Build configuration data
    approved_nations = config_manager.get("approved_nations", [])
    nations_list = "\n".join([f"• {nation}" for nation in approved_nations])
    if not nations_list:
        nations_list = response_manager.get_formatting("none_configured")
    
    # Role Mapping
    nation_roles = config_manager.get("nation_roles", {})
    role_mappings = []
    for nation, role_id in nation_roles.items():
        role = interaction.guild.get_role(role_id)
        role_name = role.name if role else response_manager.get_formatting("role_not_found", role_id=role_id)
        role_mappings.append(f"• {nation} → {role_name}")
    
    role_mappings_text = "\n".join(role_mappings) if role_mappings else response_manager.get_formatting("none_configured")
    
    # County Systems
    county_system = config_manager.get("county_system", {})
    county_info = []
    for nation, county_data in county_system.items():
        county_list = []
        for county_name, county_details in county_data.get("counties", {}).items():
            role = interaction.guild.get_role(county_details.get("role_id"))
            role_name = role.name if role else response_manager.get_formatting("role_not_found", role_id=county_details.get('role_id'))
            towns_count = len(county_details.get("towns", []))
            county_list.append(f"    • {county_name} → {role_name} ({towns_count} towns)")
        
        no_county_role_id = county_data.get("no_county_role_id")
        no_county_role = interaction.guild.get_role(no_county_role_id) if no_county_role_id else None
        no_county_role_name = no_county_role.name if no_county_role else response_manager.get_formatting("role_not_found", role_id=no_county_role_id)
        
        county_info.append(f"**{nation}:**\n" + "\n".join(county_list) + f"\n    • No County → {no_county_role_name}")
    
    county_info_text = "\n\n".join(county_info) if county_info else response_manager.get_formatting("none_configured")
    
    # Settings
    verified_role_id = config_manager.get("verified_role_id")
    verified_role = interaction.guild.get_role(verified_role_id) if verified_role_id else None
    verified_role_name = verified_role.name if verified_role else response_manager.get_formatting("role_not_found", role_id=verified_role_id)
    
    mayor_role_id = config_manager.get("mayor_role_id")
    mayor_role = interaction.guild.get_role(mayor_role_id) if mayor_role_id else None
    mayor_role_name = mayor_role.name if mayor_role else response_manager.get_formatting("role_not_found", role_id=mayor_role_id)
    
    admin_role_ids = config_manager.get("admin_role_ids", [])
    admin_roles = []
    for role_id in admin_role_ids:
        role = interaction.guild.get_role(role_id)
        admin_roles.append(role.name if role else response_manager.get_formatting("role_not_found", role_id=role_id))
    
    contradiction_channel_id = config_manager.get("contradiction_channel_id")
    contradiction_channel = bot.get_channel(contradiction_channel_id) if contradiction_channel_id else None
    contradiction_channel_name = contradiction_channel.name if contradiction_channel else response_manager.get_formatting("channel_not_found", channel_id=contradiction_channel_id)
    
    nickname_format = config_manager.get("nickname_format", "{ign} ({nation})")
    
    # Revocation roles
    revocation_roles = config_manager.get("revocation_roles", [])
    revocation_role_names = []
    for role_id in revocation_roles:
        role = interaction.guild.get_role(role_id)
        revocation_role_names.append(role.name if role else response_manager.get_formatting("role_not_found", role_id=role_id))
    
    settings_info = (
        f"• **Verified Role:** {verified_role_name}\n"
        f"• **Mayor Role:** {mayor_role_name}\n"
        f"• **Admin Roles:** {', '.join(admin_roles)}\n"
        f"• **Contradiction Channel:** #{contradiction_channel_name}\n"
        f"• **Nickname Format:** `{nickname_format}`\n"
        f"• **Revocation Roles:** {', '.join(revocation_role_names) if revocation_role_names else response_manager.get_formatting('none_configured')}"
    )
    
    embed = response_manager.create_embed(
        "config_display",
        nations_list=nations_list,
        role_mappings=role_mappings_text,
        county_info=county_info_text,
        settings_info=settings_info,
        guild_id=interaction.guild.id
    )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="verification_stats", description="Show verification cache statistics")
async def verification_stats_command(interaction: discord.Interaction):
    # Check if guild is approved
    if not is_approved_guild(interaction.guild.id):
        return
    
    # Check if user has admin permission
    if not has_admin_permission(interaction.user):
        await interaction.response.send_message(embed=create_permission_denied_embed(), ephemeral=True)
        return
    
    stats = verification_cache.get_cache_stats()
    
    embed = discord.Embed(
        title="📊 Verification Statistics",
        color=response_manager.get_color("info"),
        timestamp=discord.utils.utcnow()
    )
    
    embed.add_field(name="Total Verified Users", value=stats['total_verified_users'], inline=True)
    embed.add_field(name="Total Mayors", value=stats['total_mayors'], inline=True)
    embed.add_field(name="Cache Version", value=stats.get('cache_version', '1.0'), inline=True)
    
    # Nations breakdown
    if stats['nations']:
        nations_text = "\n".join([f"• {nation}: {count} users" for nation, count in stats['nations'].items()])
        embed.add_field(name="👥 Users by Nation", value=nations_text, inline=False)
    
    # Counties breakdown (top 10)
    if stats['counties']:
        sorted_counties = sorted(stats['counties'].items(), key=lambda x: x[1], reverse=True)[:10]
        counties_text = "\n".join([f"• {county.replace(':', ' - ')}: {count} users" for county, count in sorted_counties])
        embed.add_field(name="🏛️ Top Counties", value=counties_text, inline=False)
    
    # Mapping table stats
    mapping_stats = stats.get('mapping_tables', {})
    if mapping_stats:
        mapping_text = "\n".join([f"• {name}: {count} entries" for name, count in mapping_stats.items()])
        embed.add_field(name="🗂️ Mapping Tables", value=mapping_text, inline=False)
    
    # Timestamps
    if stats.get('cache_created'):
        created_time = datetime.fromtimestamp(stats['cache_created'])
        embed.add_field(name="Cache Created", value=created_time.strftime("%Y-%m-%d %H:%M"), inline=True)
    
    if stats.get('last_updated'):
        updated_time = datetime.fromtimestamp(stats['last_updated'])
        embed.add_field(name="Last Updated", value=updated_time.strftime("%Y-%m-%d %H:%M"), inline=True)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="lookup_verified_user", description="Look up a verified user by Discord mention or IGN")
async def lookup_verified_user_command(interaction: discord.Interaction, query: str):
    # Check if guild is approved
    if not is_approved_guild(interaction.guild.id):
        return
    
    # Check if user has admin permission
    if not has_admin_permission(interaction.user):
        await interaction.response.send_message(embed=create_permission_denied_embed(), ephemeral=True)
        return
    
    # Try to extract Discord ID from mention or use as IGN
    discord_id = None
    if query.startswith('<@') and query.endswith('>'):
        # Extract Discord ID from mention
        discord_id = query.strip('<@!>')
    
    # Search verification cache
    user_data = None
    search_type = ""
    
    if discord_id:
        user_data = verification_cache.get_verified_user(discord_id)
        search_type = "Discord mention"
    else:
        # Search by IGN
        user_data = verification_cache.get_user_by_ign(query)
        search_type = "IGN"
    
    if user_data:
        embed = discord.Embed(
            title="👤 Verified User Found",
            color=response_manager.get_color("success"),
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(name="🎮 IGN", value=f"`{user_data.get('ign', 'Unknown')}`", inline=True)
        embed.add_field(name="💬 Discord", value=f"<@{user_data.get('discord_id')}>", inline=True)
        embed.add_field(name="🏴 Nation", value=user_data.get('nation', 'Unknown'), inline=True)
        
        embed.add_field(name="🏘️ Town", value=user_data.get('town', 'Unknown'), inline=True)
        
        # Add town UUID if available
        town_uuid = user_data.get('town_uuid')
        if town_uuid:
            embed.add_field(name="🏘️ Town UUID", value=f"`{town_uuid}`", inline=True)
        
        if user_data.get('county'):
            embed.add_field(name="🏛️ County", value=user_data.get('county'), inline=True)
        
        if user_data.get('is_mayor'):
            embed.add_field(name="👑 Status", value="Mayor", inline=True)
        
        # Add nation UUID if available
        nation_uuid = user_data.get('nation_uuid')
        if nation_uuid:
            embed.add_field(name="🏴 Nation UUID", value=f"`{nation_uuid}`", inline=False)
        
        embed.add_field(name="🆔 Player UUID", value=f"`{user_data.get('player_uuid', 'Unknown')}`", inline=False)
        
        # Verification details
        verified_at = user_data.get('verified_at')
        if verified_at:
            verified_time = datetime.fromtimestamp(verified_at)
            embed.add_field(name="✅ Verified", value=verified_time.strftime("%Y-%m-%d %H:%M"), inline=True)
        
        if user_data.get('verified_by'):
            embed.add_field(name="Verified By", value=f"<@{user_data.get('verified_by')}>", inline=True)
        
        # Re-verification details
        last_verified_at = user_data.get('last_verified_at')
        if last_verified_at and last_verified_at != verified_at:
            last_verified_time = datetime.fromtimestamp(last_verified_at)
            embed.add_field(name="🔄 Last Re-verified", value=last_verified_time.strftime("%Y-%m-%d %H:%M"), inline=True)
        
        if user_data.get('last_verified_by') and user_data.get('last_verified_by') != user_data.get('verified_by'):
            embed.add_field(name="Last Verified By", value=f"<@{user_data.get('last_verified_by')}>", inline=True)
        
        embed.add_field(name="Search Type", value=search_type, inline=True)
        
    else:
        embed = response_manager.create_embed(
            "error_generic", 
            message=f"No verified user found for {search_type.lower()}: `{query}`"
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="export_verification_data", description="Export verification data to CSV")
async def export_verification_data_command(interaction: discord.Interaction):
    # Check if guild is approved
    if not is_approved_guild(interaction.guild.id):
        return
    
    # Check if user has admin permission
    if not has_admin_permission(interaction.user):
        await interaction.response.send_message(embed=create_permission_denied_embed(), ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        # Export to CSV
        filename = verification_cache.export_to_csv()
        
        # Send the file
        embed = response_manager.create_embed(
            "success_generic",
            message=f"Exported verification data to CSV: {filename}",
            user_mention=interaction.user.mention
        )
        
        file = discord.File(filename, filename=filename)
        await interaction.followup.send(embed=embed, file=file)
        
        # Clean up the file
        os.remove(filename)
        
    except Exception as e:
        logger.error(f"Error in export_verification_data_command: {e}")
        embed = response_manager.create_embed("error_generic", message="Failed to export verification data.")
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="town_lookup", description="Convert between town name and UUID")
async def town_lookup_command(interaction: discord.Interaction, query: str):
    # Check if guild is approved
    if not is_approved_guild(interaction.guild.id):
        return
    
    # Check if user has admin permission
    if not has_admin_permission(interaction.user):
        await interaction.response.send_message(embed=create_permission_denied_embed(), ephemeral=True)
        return
    
    await interaction.response.defer()
    
    try:
        from api.earthmc import get_town_info
        
        # The API accepts both names and UUIDs, so we can use the same function
        town_result = await get_town_info(query)
        
        if town_result["success"]:
            town_data = town_result["data"]
            town_name = town_data.get("name")
            town_uuid = town_data.get("uuid")
            
            # Check if query looks like a UUID to determine the lookup direction
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
            # Determine if it was a UUID or name query for better error message
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
async def nation_towns_csv_command(interaction: discord.Interaction, nation_name: str):
    # Check if guild is approved
    if not is_approved_guild(interaction.guild.id):
        return
    
    # Check if user has admin permission
    if not has_admin_permission(interaction.user):
        await interaction.response.send_message(embed=create_permission_denied_embed(), ephemeral=True)
        return
    
    await interaction.response.defer()
    
    try:
        # Get nation info first to get all towns
        nation_result = await get_nation_info(nation_name)
        
        if not nation_result["success"]:
            embed = create_error_embed(
                "❌ Nation Not Found",
                f"Could not find nation `{nation_name}`: {nation_result['error']}"
            )
            await interaction.followup.send(embed=embed)
            return
        
        nation_data = nation_result["data"]
        towns_list = nation_data.get("towns", [])
        
        if not towns_list:
            embed = create_warning_embed(
                "⚠️ No Towns Found",
                f"Nation `{nation_name}` has no towns."
            )
            await interaction.followup.send(embed=embed)
            return
        
        # Get detailed info for each town to get homeblock coordinates
        town_names = [town.get("name") for town in towns_list if town.get("name")]
        
        logger.info(f"Fetching detailed info for {len(town_names)} towns using batch system")
        
        # Use the new batching system for efficient API calls
        from api.earthmc import get_multiple_towns_info
        detailed_towns_dict = await get_multiple_towns_info(town_names)
        
        # Convert back to list format, maintaining order and handling failures
        detailed_towns = []
        for town in towns_list:
            town_name = town.get("name")
            if town_name and town_name in detailed_towns_dict:
                town_result = detailed_towns_dict[town_name]
                if town_result.get("success"):
                    detailed_towns.append(town_result["data"])
                else:
                    logger.warning(f"Failed to get details for {town_name}: {town_result.get('error')}")
                    detailed_towns.append(town)  # Use basic info as fallback
            else:
                detailed_towns.append(town)  # Use basic info as fallback
        # Create CSV content
        csv_content = generate_nation_towns_csv(nation_name, detailed_towns)
        
        # Save CSV to file
        filename = f"{nation_name.replace(' ', '_')}_towns.csv"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(csv_content)
        
        # Send the file
        embed = create_success_embed(
            "✅ CSV Generated",
            f"Generated CSV for nation `{nation_name}` with {len(detailed_towns)} towns.",
            interaction.user
        )
        embed.add_field(name="File", value=filename, inline=True)
        embed.add_field(name="Towns Count", value=len(detailed_towns), inline=True)
        
        file = discord.File(filename, filename=filename)
        await interaction.followup.send(embed=embed, file=file)
        
        # Clean up the file
        os.remove(filename)
        
    except Exception as e:
        logger.error(f"Error in nation_towns_csv_command: {e}")
        embed = create_error_embed(
            "❌ Error",
            "An unexpected error occurred while generating the CSV."
        )
        await interaction.followup.send(embed=embed)

def generate_nation_towns_csv(nation_name: str, towns_list: list) -> str:
    """Generate CSV content for nation towns"""
    
    # CSV headers
    csv_lines = [
        "Town Name,UUID,County,Homeblock X,Homeblock Z,Spawn X,Spawn Z,Dynmap Link"
    ]
    
    # Get county system for this nation
    county_system = config_manager.get("county_system", {})
    nation_counties = county_system.get(nation_name, {})
    
    # Create a lookup dictionary: town_uuid -> county_name
    town_to_county = {}
    for county_name, county_data in nation_counties.get("counties", {}).items():
        for town_uuid in county_data.get("towns", []):
            town_to_county[town_uuid] = county_name
    
    # Add each town
    for town in towns_list:
        town_name = town.get("name", "Unknown")
        town_uuid = town.get("uuid", "Unknown")
        
        # Determine county for this town
        if town_uuid in town_to_county:
            county = town_to_county[town_uuid]
        else:
            # Check if this nation has a county system
            if nation_name in county_system:
                county = "No County"
            else:
                county = "No County System"
        
        # Get coordinates from the town data
        coordinates = town.get("coordinates", {})
        
        # Get homeblock coordinates (chunk coordinates)
        homeblock = coordinates.get("homeBlock", [0, 0])
        homeblock_x = homeblock[0] if len(homeblock) >= 2 else "Unknown"
        homeblock_z = homeblock[1] if len(homeblock) >= 2 else "Unknown"
        
        # Get spawn coordinates (actual world coordinates)
        spawn = coordinates.get("spawn", {})
        if spawn and isinstance(spawn, dict):
            spawn_x = spawn.get("x", 0)
            spawn_z = spawn.get("z", 0)
            
            # Round to integers for cleaner display and ensure they're numbers
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
        
        # Escape commas in town names and county names by wrapping in quotes
        town_name_escaped = f'"{town_name}"' if ',' in town_name else town_name
        county_escaped = f'"{county}"' if ',' in county else county
        
        # Add CSV row
        csv_row = f"{town_name_escaped},{town_uuid},{county_escaped},{homeblock_x},{homeblock_z},{spawn_x_display},{spawn_z_display},{dynmap_link}"
        csv_lines.append(csv_row)
    
    return '\n'.join(csv_lines)

@bot.tree.command(name="cache_stats", description="Show cache statistics")
async def cache_stats_command(interaction: discord.Interaction):
    # Check if guild is approved
    if not is_approved_guild(interaction.guild.id):
        return
    
    # Check if user has admin permission
    if not has_admin_permission(interaction.user):
        await interaction.response.send_message(embed=create_permission_denied_embed(), ephemeral=True)
        return
    
    stats = cache_manager.get_stats()
    
    embed = discord.Embed(
        title="📊 Cache Statistics",
        color=0x2f3136,
        timestamp=discord.utils.utcnow()
    )
    
    embed.add_field(name="Total Entries", value=stats['total_entries'], inline=True)
    embed.add_field(name="Active Entries", value=stats['active_entries'], inline=True)
    embed.add_field(name="Expired Entries", value=stats['expired_entries'], inline=True)
    embed.add_field(name="Default TTL", value=f"{stats['default_ttl']} seconds", inline=True)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="periodic_verification_status", description="Show periodic verification status and statistics")
async def periodic_verification_status_command(interaction: discord.Interaction):
    # Check if guild is approved
    if not is_approved_guild(interaction.guild.id):
        return
    
    # Check if user has admin permission
    if not has_admin_permission(interaction.user):
        await interaction.response.send_message(embed=create_permission_denied_embed(), ephemeral=True)
        return
    
    status = bot.periodic_verification.get_status()
    
    embed = discord.Embed(
        title="🔄 Periodic Verification Status",
        color=0x00ff00 if not status["is_running"] else 0xffaa00,
        timestamp=discord.utils.utcnow()
    )
    
    # Current state
    state = "🔄 Running" if status["is_running"] else "⏸️ Idle"
    embed.add_field(name="Status", value=state, inline=True)
    
    enabled = config_manager.get("periodic_verification_enabled", False)
    embed.add_field(name="Enabled", value="✅ Yes" if enabled else "❌ No", inline=True)
    
    interval = config_manager.get("periodic_verification_interval_hours", 24)
    embed.add_field(name="Interval", value=f"{interval} hours", inline=True)
    
    # Current run info (if running)
    if status["is_running"]:
        embed.add_field(name="Current Batch", value=f"{status['current_batch']}", inline=True)
        embed.add_field(name="Processed", value=f"{status['processed_users']}/{status['total_users']}", inline=True)
        embed.add_field(name="Updated", value=str(status['updated_users']), inline=True)
    
    # Last run statistics
    stats = status["stats"]
    if stats["total_runs"] > 0:
        embed.add_field(name="Total Runs", value=str(stats['total_runs']), inline=True)
        embed.add_field(name="Last Run Users", value=str(stats['last_run_users']), inline=True)
        embed.add_field(name="Last Run Updates", value=str(stats['last_run_updates']), inline=True)
        embed.add_field(name="Last Run Duration", value=f"{stats['last_run_duration']:.1f}s", inline=True)
        embed.add_field(name="Avg Duration", value=f"{stats['average_processing_time']:.1f}s", inline=True)
        embed.add_field(name="Last Run Failures", value=str(stats['last_run_failures']), inline=True)
    
    # Next run time
    if status["last_run_time"] and enabled:
        from datetime import datetime, timedelta
        last_run = datetime.fromisoformat(status["last_run_time"])
        next_run = last_run + timedelta(hours=interval)
        embed.add_field(
            name="Next Run", 
            value=f"<t:{int(next_run.timestamp())}:R>", 
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="periodic_verification_control", description="Start or stop periodic verification")
@app_commands.describe(action="Choose action: start, stop, enable, or disable")
@app_commands.choices(action=[
    app_commands.Choice(name="Start", value="start"),
    app_commands.Choice(name="Stop", value="stop"), 
    app_commands.Choice(name="Enable", value="enable"),
    app_commands.Choice(name="Disable", value="disable")
])
async def periodic_verification_control_command(interaction: discord.Interaction, action: app_commands.Choice[str]):
    # Check if guild is approved
    if not is_approved_guild(interaction.guild.id):
        return
    
    # Check if user has admin permission
    if not has_admin_permission(interaction.user):
        await interaction.response.send_message(embed=create_permission_denied_embed(), ephemeral=True)
        return
    
    if action.value.lower() not in ["start", "stop", "enable", "disable"]:
        embed = create_error_embed(
            "❌ Invalid Action",
            "Action must be one of: start, stop, enable, disable"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    try:
        if action.value.lower() == "start":
            bot.periodic_verification.start_periodic_verification()
            config_manager.set("periodic_verification_enabled", True)
            embed = create_success_embed(
                "✅ Periodic Verification Started",
                "Periodic verification has been enabled and started.",
                interaction.user
            )
        
        elif action.lower() == "stop":
            bot.periodic_verification.stop_periodic_verification()
            embed = create_success_embed(
                "⏹️ Periodic Verification Stopped",
                "Periodic verification has been stopped (but remains enabled).",
                interaction.user
            )
        
        elif action.lower() == "enable":
            config_manager.set("periodic_verification_enabled", True)
            bot.periodic_verification.start_periodic_verification()
            embed = create_success_embed(
                "✅ Periodic Verification Enabled",
                "Periodic verification has been enabled and will start automatically.",
                interaction.user
            )
        
        elif action.lower() == "disable":
            config_manager.set("periodic_verification_enabled", False)
            bot.periodic_verification.stop_periodic_verification()
            embed = create_success_embed(
                "❌ Periodic Verification Disabled",
                "Periodic verification has been disabled and stopped.",
                interaction.user
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        logger.error(f"Error in periodic verification control: {e}")
        embed = create_error_embed(
            "❌ Error",
            f"Failed to {action} periodic verification: {str(e)}"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="periodic_verification_run", description="Manually trigger a periodic verification run")
async def periodic_verification_run_command(interaction: discord.Interaction):
    # Check if guild is approved
    if not is_approved_guild(interaction.guild.id):
        return
    
    # Check if user has admin permission
    if not has_admin_permission(interaction.user):
        await interaction.response.send_message(embed=create_permission_denied_embed(), ephemeral=True)
        return
    
    if bot.periodic_verification.is_running:
        embed = create_warning_embed(
            "⚠️ Already Running",
            "Periodic verification is already running. Please wait for it to complete."
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        # Start manual run in background
        import asyncio
        asyncio.create_task(bot.periodic_verification.run_verification_update())
        
        embed = create_success_embed(
            "🔄 Manual Run Started",
            "Periodic verification has been manually triggered and is running in the background.",
            interaction.user
        )
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        logger.error(f"Error starting manual verification run: {e}")
        embed = create_error_embed(
            "❌ Error",
            f"Failed to start manual verification run: {str(e)}"
        )
        await interaction.followup.send(embed=embed)
async def cache_clear_command(interaction: discord.Interaction):
    # Check if guild is approved
    if not is_approved_guild(interaction.guild.id):
        return
    
    # Check if user has admin permission
    if not has_admin_permission(interaction.user):
        await interaction.response.send_message(embed=create_permission_denied_embed(), ephemeral=True)
        return
    
    cache_manager.clear()
    
    embed = create_success_embed(
        "✅ Cache Cleared",
        "All cache entries have been cleared.",
        interaction.user
    )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

if __name__ == "__main__":
    bot_token = config_manager.get("bot_token")
    if not bot_token or bot_token == "YOUR_BOT_TOKEN_HERE":
        logger.error("Bot token not configured! Please set your bot token in config.json")
        exit(1)
    
    bot.run(bot_token)