import discord
import logging
from api.earthmc import get_town_info
from county.system import add_town_to_county, remove_town_from_county, rename_county
from utils.permissions import has_admin_permission, is_approved_guild, get_nation_for_guild
from utils.embeds import create_permission_denied_embed, create_error_embed, create_success_embed, create_warning_embed
from roles.multi_guild_manager import get_multi_guild_manager

logger = logging.getLogger(__name__)

def setup_county_commands(bot):
    """Setup county management commands"""
    
    @bot.tree.command(name="county_add_town", description="Add a town to a county")
    async def county_add_town_command(interaction: discord.Interaction, county: str, town_name: str):
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
            town_result = await get_town_info(town_name)
            if not town_result["success"]:
                embed = create_error_embed("❌ Town Not Found", f"Could not find town `{town_name}`: {town_result['error']}")
                await interaction.followup.send(embed=embed)
                return
            
            town_uuid = town_result["data"]["uuid"]
            actual_town_name = town_result["data"]["name"]
            
            success, message = await add_town_to_county(guild_nation, county, town_uuid)
            
            if success:
                embed = create_success_embed("✅ Town Added to County", f"Successfully added town `{actual_town_name}` to county `{county}` in nation `{guild_nation}`.", interaction.user)
                embed.add_field(name="Town UUID", value=f"`{town_uuid}`", inline=True)
                await interaction.followup.send(embed=embed)
            else:
                if "already in county" in message:
                    embed = create_warning_embed("⚠️ Already Added", f"Town `{actual_town_name}` is {message}")
                else:
                    embed = create_error_embed("❌ County Not Found", message)
                await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in county_add_town_command: {e}")
            embed = create_error_embed("❌ Error", "An unexpected error occurred while adding the town to the county.")
            await interaction.followup.send(embed=embed)

    @bot.tree.command(name="county_remove_town", description="Remove a town from its county")
    async def county_remove_town_command(interaction: discord.Interaction, town_name: str):
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
            town_result = await get_town_info(town_name)
            if not town_result["success"]:
                embed = create_error_embed("❌ Town Not Found", f"Could not find town `{town_name}`: {town_result['error']}")
                await interaction.followup.send(embed=embed)
                return
            
            town_uuid = town_result["data"]["uuid"]
            actual_town_name = town_result["data"]["name"]
            
            success, message, removed_from_county = remove_town_from_county(guild_nation, town_uuid)
            
            if success:
                embed = create_success_embed("✅ Town Removed from County", f"Successfully removed town `{actual_town_name}` from county `{removed_from_county}` in nation `{guild_nation}`.", interaction.user)
                embed.add_field(name="Town UUID", value=f"`{town_uuid}`", inline=True)
                await interaction.followup.send(embed=embed)
            else:
                if "not currently assigned" in message:
                    embed = create_warning_embed("⚠️ Town Not in County", f"Town `{actual_town_name}` is {message}")
                else:
                    embed = create_error_embed("❌ Nation Not Found", message)
                await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error in county_remove_town_command: {e}")
            embed = create_error_embed("❌ Error", "An unexpected error occurred while removing the town from the county.")
            await interaction.followup.send(embed=embed)

    @bot.tree.command(name="county_rename", description="Rename a county")
    async def county_rename_command(interaction: discord.Interaction, old_county_name: str, new_county_name: str):
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
            success, message, towns_count = rename_county(guild_nation, old_county_name, new_county_name)
            
            if success:
                embed = create_success_embed("✅ County Renamed", f"Successfully renamed county `{old_county_name}` to `{new_county_name}` in nation `{guild_nation}`.", interaction.user)
                embed.add_field(name="Towns in County", value=f"{towns_count} towns", inline=True)
                await interaction.response.send_message(embed=embed)
            else:
                embed = create_error_embed("❌ County Rename Failed", message)
                await interaction.response.send_message(embed=embed)
                
        except Exception as e:
            logger.error(f"Error in county_rename_command: {e}")
            embed = create_error_embed("❌ Error", "An unexpected error occurred while renaming the county.")
            await interaction.response.send_message(embed=embed)

    @bot.tree.command(name="county_list", description="List all counties and their towns for this nation")
    async def county_list_command(interaction: discord.Interaction):
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
            mgm = get_multi_guild_manager()
            if not mgm:
                embed = create_error_embed("❌ System Error", "Multi-guild manager not initialized.")
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            county_system = mgm.get_county_system_for_nation(guild_nation)
            
            if not county_system.get("enabled", False):
                embed = create_warning_embed("⚠️ County System Disabled", f"The county system is not enabled for nation `{guild_nation}`.")
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            embed = discord.Embed(
                title=f"🏛️ Counties in {guild_nation}",
                color=0x2f3136,
                timestamp=discord.utils.utcnow()
            )
            
            counties = county_system.get("counties", {})
            if not counties:
                embed.description = "No counties are currently configured."
            else:
                for county_name, county_data in counties.items():
                    role_id = county_data.get("role_id")
                    role = interaction.guild.get_role(role_id) if role_id else None
                    role_text = role.mention if role else f"Role ID: {role_id} (not found)"
                    
                    towns = county_data.get("towns", [])
                    towns_text = f"{len(towns)} towns"
                    if len(towns) <= 5:
                        towns_text += f"\n`{'`, `'.join(towns)}`" if towns else ""
                    
                    embed.add_field(
                        name=f"🏛️ {county_name}",
                        value=f"**Role:** {role_text}\n**Towns:** {towns_text}",
                        inline=True
                    )
            
            no_county_role_id = county_system.get("no_county_role_id")
            if no_county_role_id:
                no_county_role = interaction.guild.get_role(no_county_role_id)
                role_text = no_county_role.mention if no_county_role else f"Role ID: {no_county_role_id} (not found)"
                embed.add_field(
                    name="🚫 No County",
                    value=f"**Role:** {role_text}\n**For towns not assigned to any county**",
                    inline=True
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error in county_list_command: {e}")
            embed = create_error_embed("❌ Error", "An unexpected error occurred while listing counties.")
            await interaction.response.send_message(embed=embed)