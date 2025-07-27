import discord
import logging
from api.earthmc import get_town_info
from county.system import add_town_to_county, remove_town_from_county, rename_county
from utils.permissions import has_admin_permission, is_approved_guild
from utils.embeds import create_permission_denied_embed, create_error_embed, create_success_embed, create_warning_embed

logger = logging.getLogger(__name__)

def setup_county_commands(bot):
    """Setup county management commands"""
    
    @bot.tree.command(name="county_add_town", description="Add a town to a county")
    async def county_add_town_command(interaction: discord.Interaction, nation: str, county: str, town_name: str):
        # Check if guild is approved
        if not is_approved_guild(interaction.guild.id):
            return
        
        # Check if user has admin permission
        if not has_admin_permission(interaction.user):
            await interaction.response.send_message(embed=create_permission_denied_embed(), ephemeral=True)
            return
        
        await interaction.response.defer()
        
        try:
            # Get town UUID from name
            town_result = await get_town_info(town_name)
            if not town_result["success"]:
                embed = create_error_embed(
                    "❌ Town Not Found",
                    f"Could not find town `{town_name}`: {town_result['error']}"
                )
                await interaction.followup.send(embed=embed)
                return
            
            town_uuid = town_result["data"]["uuid"]
            actual_town_name = town_result["data"]["name"]
            
            # Add town to county
            success, message = await add_town_to_county(nation, county, town_uuid)
            
            if success:
                embed = create_success_embed(
                    "✅ Town Added to County",
                    f"Successfully added town `{actual_town_name}` to county `{county}` in nation `{nation}`.",
                    interaction.user
                )
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
            embed = create_error_embed(
                "❌ Error",
                "An unexpected error occurred while adding the town to the county."
            )
            await interaction.followup.send(embed=embed)

    @bot.tree.command(name="county_remove_town", description="Remove a town from its county")
    async def county_remove_town_command(interaction: discord.Interaction, nation: str, town_name: str):
        # Check if guild is approved
        if not is_approved_guild(interaction.guild.id):
            return
        
        # Check if user has admin permission
        if not has_admin_permission(interaction.user):
            await interaction.response.send_message(embed=create_permission_denied_embed(), ephemeral=True)
            return
        
        await interaction.response.defer()
        
        try:
            # Get town UUID from name
            town_result = await get_town_info(town_name)
            if not town_result["success"]:
                embed = create_error_embed(
                    "❌ Town Not Found",
                    f"Could not find town `{town_name}`: {town_result['error']}"
                )
                await interaction.followup.send(embed=embed)
                return
            
            town_uuid = town_result["data"]["uuid"]
            actual_town_name = town_result["data"]["name"]
            
            # Remove town from county
            success, message, removed_from_county = remove_town_from_county(nation, town_uuid)
            
            if success:
                embed = create_success_embed(
                    "✅ Town Removed from County",
                    f"Successfully removed town `{actual_town_name}` from county `{removed_from_county}` in nation `{nation}`.",
                    interaction.user
                )
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
            embed = create_error_embed(
                "❌ Error",
                "An unexpected error occurred while removing the town from the county."
            )
            await interaction.followup.send(embed=embed)

    @bot.tree.command(name="county_rename", description="Rename a county")
    async def county_rename_command(interaction: discord.Interaction, nation: str, old_county_name: str, new_county_name: str):
        # Check if guild is approved
        if not is_approved_guild(interaction.guild.id):
            return
        
        # Check if user has admin permission
        if not has_admin_permission(interaction.user):
            await interaction.response.send_message(embed=create_permission_denied_embed(), ephemeral=True)
            return
        
        try:
            # Rename county
            success, message, towns_count = rename_county(nation, old_county_name, new_county_name)
            
            if success:
                embed = create_success_embed(
                    "✅ County Renamed",
                    f"Successfully renamed county `{old_county_name}` to `{new_county_name}` in nation `{nation}`.",
                    interaction.user
                )
                embed.add_field(name="Towns in County", value=f"{towns_count} towns", inline=True)
                await interaction.response.send_message(embed=embed)
            else:
                embed = create_error_embed("❌ County Rename Failed", message)
                await interaction.response.send_message(embed=embed)
                
        except Exception as e:
            logger.error(f"Error in county_rename_command: {e}")
            embed = create_error_embed(
                "❌ Error",
                "An unexpected error occurred while renaming the county."
            )
            await interaction.response.send_message(embed=embed)