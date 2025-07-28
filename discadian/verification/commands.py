import discord
import logging
import os
import asyncio
from datetime import datetime
from discord import app_commands

from utils.permissions import has_admin_permission, is_approved_guild, get_nation_for_guild, can_verify_for_nation
from utils.responses import create_permission_denied_embed, create_error_embed, create_success_embed, create_warning_embed, response_manager
from utils.verification_cache import verification_cache
from verification.core import verify_player
from api.earthmc import get_player_info
from roles.multi_guild_manager import get_multi_guild_manager
from config import config_manager

logger = logging.getLogger(__name__)

def setup_verification_commands(bot):
    """Setup verification-related commands"""

    @bot.tree.command(name="verify", description="Verify a player's EarthMC nation membership")
    async def verify_command(interaction: discord.Interaction, member: discord.Member, ign: str, nation: str = None):
        if not is_approved_guild(interaction.guild.id):
            return
        
        guild_nation = get_nation_for_guild(interaction.guild.id)
        target_nation = nation or guild_nation
        
        if not target_nation:
            embed = create_error_embed("❌ No Nation Specified", "Please specify a nation or ensure this guild is configured for a specific nation.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if not can_verify_for_nation(interaction.user, target_nation):
            await interaction.response.send_message(embed=create_permission_denied_embed(), ephemeral=True)
            return
        
        await interaction.response.defer()
        
        try:
            existing_verification = verification_cache.get_verified_user_by_discord_id(str(member.id))
            is_reverification = existing_verification is not None
            
            result = await verify_player(str(member.id), ign, target_nation)
            
            if result.success:
                player_result = await get_player_info(ign)
                town_uuid = None
                nation_uuid = None
                
                if player_result["success"]:
                    player_data = player_result["data"]
                    town_data = player_data.get("town", {})
                    nation_data = player_data.get("nation", {})
                    town_uuid = town_data.get("uuid") if town_data else None
                    nation_uuid = nation_data.get("uuid") if nation_data else None
                
                mgm = get_multi_guild_manager()
                county_name = None
                county_role_id = None
                has_county = True
                
                # Determine relationship status
                relationship = 'citizen'  # Default for same nation
                if mgm and nation_uuid and guild_nation:
                    # Check if this is the guild's own nation
                    guild_nation_config = mgm.get_nation_config(guild_nation)
                    if guild_nation_config:
                        guild_nation_uuid = guild_nation_config.get("nation_uuid")
                        if guild_nation_uuid != nation_uuid:
                            # Different nation - check if allied
                            allied_nations = guild_nation_config.get("allied_nations", [])
                            if nation_uuid in allied_nations:
                                relationship = 'allied'
                            else:
                                relationship = 'foreigner'
                
                # Only get county info for citizens of the same nation
                if mgm and town_uuid and relationship == 'citizen':
                    county_name, county_role_id, has_county = mgm.get_county_for_town_in_nation(guild_nation, town_uuid)
                
                # Assign roles based on relationship
                if is_reverification:
                    success = await mgm.handle_role_updates_multi_guild(
                        member, ign, result.nation, result.is_mayor, county_name, county_role_id, existing_verification
                    ) if mgm else False
                else:
                    success = await mgm.assign_roles_for_nation(
                        member, ign, result.nation, result.is_mayor, county_name, county_role_id
                    ) if mgm else False
                
                if success:
                    if player_result["success"]:
                        player_data = player_result["data"]
                        player_uuid = player_data.get("uuid")
                        
                        if is_reverification:
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
                    
                    # Create success embed
                    if is_reverification:
                        embed = response_manager.create_embed(
                            "verification_update_success",
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
                    
                    # Add relationship status info
                    if relationship == 'allied':
                        embed.add_field(
                            name="🤝 Allied Nation", 
                            value=f"{result.nation} is an ally of {guild_nation}. Allied role assigned.", 
                            inline=False
                        )
                    elif relationship == 'foreigner':
                        embed.add_field(
                            name="🌍 Foreign Nation", 
                            value=f"{result.nation} is not allied with {guild_nation}. Foreigner role assigned.", 
                            inline=False
                        )
                    
                    # Add county notice for citizens only
                    if mgm and not has_county and relationship == 'citizen':
                        county_system = mgm.get_county_system_for_nation(guild_nation)
                        if county_system.get("enabled", False):
                            county_notice_embed = response_manager.create_embed(
                                "verification_county_notice",
                                town=result.town,
                                nation=result.nation
                            )
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
                if result.contradiction_data:
                    mgm = get_multi_guild_manager()
                    if mgm:
                        await mgm.send_contradiction_report(target_nation, result.contradiction_data)
                
                await interaction.followup.send(result.message)
                
        except Exception as e:
            logger.error(f"Error in verify command: {e}")
            embed = response_manager.create_embed("error_generic", message=response_manager.get_message("errors.verification_error"))
            await interaction.followup.send(embed=embed)

    @bot.tree.command(name="verify_cross_nation", description="Verify a player from any nation (assigns allied/foreigner roles)")
    async def verify_cross_nation_command(interaction: discord.Interaction, member: discord.Member, ign: str):
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
            # Get player info without nation restriction
            player_result = await get_player_info(ign)
            
            if not player_result["success"]:
                embed = create_error_embed("❌ Player Not Found", f"Could not find player `{ign}`: {player_result['error']}")
                await interaction.followup.send(embed=embed)
                return
            
            player_data = player_result["data"]
            nation_data = player_data.get("nation")
            
            if not nation_data:
                embed = create_error_embed("❌ No Nation", f"Player `{ign}` is not in any nation.")
                await interaction.followup.send(embed=embed)
                return
            
            player_nation = nation_data.get("name")
            player_nation_uuid = nation_data.get("uuid")
            town_data = player_data.get("town", {})
            status_data = player_data.get("status", {})
            
            # Check Discord linking
            from verification.links import verify_discord_links
            player_uuid = player_data.get("uuid")
            has_contradiction, contradiction_msg, is_linked = await verify_discord_links(str(member.id), ign, player_uuid)
            
            if has_contradiction:
                if contradiction_msg.startswith("Error"):
                    await interaction.followup.send(contradiction_msg)
                    return
                else:
                    mgm = get_multi_guild_manager()
                    if mgm:
                        await mgm.send_contradiction_report(guild_nation, contradiction_msg)
                    await interaction.followup.send("❌ **Link Contradiction Detected** - This has been reported to staff.")
                    return
            
            # Determine relationship
            mgm = get_multi_guild_manager()
            if not mgm:
                embed = create_error_embed("❌ System Error", "Multi-guild manager not initialized.")
                await interaction.followup.send(embed=embed)
                return
            
            # Determine relationship status
            relationship = 'foreigner'  # Default
            guild_nation_config = mgm.get_nation_config(guild_nation)
            if guild_nation_config:
                guild_nation_uuid = guild_nation_config.get("nation_uuid")
                if guild_nation_uuid == player_nation_uuid:
                    relationship = 'citizen'
                else:
                    allied_nations = guild_nation_config.get("allied_nations", [])
                    if player_nation_uuid in allied_nations:
                        relationship = 'allied'
            
            town_name = town_data.get("name", "Unknown")
            is_mayor = status_data.get("isMayor", False)
            
            # For citizens, get county info
            county_name = None
            county_role_id = None
            if relationship == 'citizen':
                town_uuid = town_data.get("uuid")
                if town_uuid:
                    county_name, county_role_id, _ = mgm.get_county_for_town_in_nation(guild_nation, town_uuid)
            
            # Assign roles
            success = await mgm.assign_roles_for_nation(
                member, ign, player_nation, is_mayor, county_name, county_role_id
            )
            
            if success:
                # Save verification data
                verification_cache.add_verified_user(
                    discord_id=str(member.id),
                    discord_username=f"{member.name}#{member.discriminator}" if member.discriminator != "0" else member.name,
                    ign=ign,
                    player_uuid=player_uuid,
                    nation=player_nation,
                    nation_uuid=player_nation_uuid,
                    town=town_name,
                    town_uuid=town_data.get("uuid"),
                    is_mayor=is_mayor,
                    county=county_name,
                    guild_id=str(interaction.guild.id),
                    verified_by=str(interaction.user.id)
                )
                
                # Create success embed
                link_status = "✅ Linked" if is_linked else "⚠️ Not linked"
                
                embed = discord.Embed(
                    title="✅ Cross-Nation Verification Successful",
                    color=0x00ff00,
                    timestamp=discord.utils.utcnow()
                )
                
                embed.add_field(name="🎮 Player", value=f"`{ign}`", inline=True)
                embed.add_field(name="🏴 Nation", value=player_nation, inline=True)
                embed.add_field(name="🏘️ Town", value=town_name, inline=True)
                embed.add_field(name="🔗 Link Status", value=link_status, inline=True)
                
                if is_mayor:
                    embed.add_field(name="👑 Status", value="Mayor", inline=True)
                
                # Add relationship-specific info
                if relationship == 'citizen':
                    embed.add_field(name="🏛️ Status", value=f"Citizen of {guild_nation}", inline=False)
                    if county_name:
                        embed.add_field(name="🏛️ County", value=county_name, inline=True)
                elif relationship == 'allied':
                    embed.add_field(name="🤝 Status", value=f"Allied Nation ({player_nation} is allied with {guild_nation})", inline=False)
                else:
                    embed.add_field(name="🌍 Status", value=f"Foreign Nation ({player_nation} is not allied with {guild_nation})", inline=False)
                
                embed.add_field(name="Verified By", value=interaction.user.mention, inline=True)
                embed.add_field(name="Verified User", value=member.mention, inline=True)
                
                await interaction.followup.send(embed=embed)
            else:
                embed = create_error_embed("❌ Role Assignment Failed", "Verification successful but role assignment failed.")
                await interaction.followup.send(embed=embed)
                
        except Exception as e:
            logger.error(f"Error in verify_cross_nation command: {e}")
            embed = response_manager.create_embed("error_generic", message="An unexpected error occurred during cross-nation verification.")
            await interaction.followup.send(embed=embed)

    @bot.tree.command(name="export_verification_data", description="Export verification data to CSV")
    async def export_verification_data_command(interaction: discord.Interaction):
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
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            filename = verification_cache.export_to_csv()
            embed = response_manager.create_embed(
                "success_generic",
                message=f"Exported verification data to CSV: {filename}",
                user_mention=interaction.user.mention
            )
            
            file = discord.File(filename, filename=filename)
            await interaction.followup.send(embed=embed, file=file)
            os.remove(filename)
            
        except Exception as e:
            logger.error(f"Error in export_verification_data_command: {e}")
            embed = response_manager.create_embed("error_generic", message="Failed to export verification data.")
            await interaction.followup.send(embed=embed)

    @bot.tree.command(name="periodic_verification_status", description="Show periodic verification status and statistics")
    async def periodic_verification_status_command(interaction: discord.Interaction):
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
        
        status = bot.periodic_verification.get_status()
        
        embed = discord.Embed(
            title="🔄 Periodic Verification Status",
            color=0x00ff00 if not status["is_running"] else 0xffaa00,
            timestamp=discord.utils.utcnow()
        )
        
        state = "🔄 Running" if status["is_running"] else "⏸️ Idle"
        embed.add_field(name="Status", value=state, inline=True)
        
        enabled = config_manager.get_global_setting("periodic_verification", {}).get("enabled", False)
        embed.add_field(name="Enabled", value="✅ Yes" if enabled else "❌ No", inline=True)
        
        interval = config_manager.get_global_setting("periodic_verification", {}).get("interval_hours", 24)
        embed.add_field(name="Interval", value=f"{interval} hours", inline=True)
        
        if status["is_running"]:
            embed.add_field(name="Current Batch", value=f"{status['current_batch']}", inline=True)
            embed.add_field(name="Processed", value=f"{status['processed_users']}/{status['total_users']}", inline=True)
            embed.add_field(name="Updated", value=str(status['updated_users']), inline=True)
        
        stats = status["stats"]
        if stats["total_runs"] > 0:
            embed.add_field(name="Total Runs", value=str(stats['total_runs']), inline=True)
            embed.add_field(name="Last Run Users", value=str(stats['last_run_users']), inline=True)
            embed.add_field(name="Last Run Updates", value=str(stats['last_run_updates']), inline=True)
            embed.add_field(name="Last Run Duration", value=f"{stats['last_run_duration']:.1f}s", inline=True)
            embed.add_field(name="Avg Duration", value=f"{stats['average_processing_time']:.1f}s", inline=True)
            embed.add_field(name="Last Run Failures", value=str(stats['last_run_failures']), inline=True)
        
        if status["last_run_time"] and enabled:
            from datetime import datetime, timedelta
            last_run = datetime.fromisoformat(status["last_run_time"])
            next_run = last_run + timedelta(hours=interval)
            embed.add_field(name="Next Run", value=f"<t:{int(next_run.timestamp())}:R>", inline=False)
        
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
            if action.value.lower() == "start":
                bot.periodic_verification.start_periodic_verification()
                config_manager.set_global_setting("periodic_verification_enabled", True)
                embed = create_success_embed("✅ Periodic Verification Started", "Periodic verification has been enabled and started.", interaction.user)
            elif action.value.lower() == "stop":
                bot.periodic_verification.stop_periodic_verification()
                embed = create_success_embed("⏹️ Periodic Verification Stopped", "Periodic verification has been stopped (but remains enabled).", interaction.user)
            elif action.value.lower() == "enable":
                config_manager.set_global_setting("periodic_verification_enabled", True)
                bot.periodic_verification.start_periodic_verification()
                embed = create_success_embed("✅ Periodic Verification Enabled", "Periodic verification has been enabled and will start automatically.", interaction.user)
            elif action.value.lower() == "disable":
                config_manager.set_global_setting("periodic_verification_enabled", False)
                bot.periodic_verification.stop_periodic_verification()
                embed = create_success_embed("❌ Periodic Verification Disabled", "Periodic verification has been disabled and stopped.", interaction.user)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in periodic verification control: {e}")
            embed = create_error_embed("❌ Error", f"Failed to {action.value} periodic verification: {str(e)}")
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name="periodic_verification_run", description="Manually trigger a periodic verification run")
    async def periodic_verification_run_command(interaction: discord.Interaction):
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
        
        if bot.periodic_verification.is_running:
            embed = create_warning_embed("⚠️ Already Running", "Periodic verification is already running. Please wait for it to complete.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            asyncio.create_task(bot.periodic_verification.run_verification_update())
            embed = create_success_embed("🔄 Manual Run Started", "Periodic verification has been manually triggered and is running in the background.", interaction.user)
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error starting manual verification run: {e}")
            embed = create_error_embed("❌ Error", f"Failed to start manual verification run: {str(e)}")
            await interaction.followup.send(embed=embed)