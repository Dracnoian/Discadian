import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from discord.ext import tasks
import discord

from utils.verification_cache import verification_cache
from api.earthmc import get_player_info_by_uuid, get_player_info
from verification.core import verify_player
from roles.manager import handle_role_updates, revoke_nation_roles_by_uuid
from county.system import get_county_for_town_uuid, get_county_for_town
from config import config_manager

logger = logging.getLogger(__name__)

class PeriodicVerificationManager:
    def __init__(self, bot):
        self.bot = bot
        self.is_running = False
        self.current_batch = 0
        self.total_users = 0
        self.processed_users = 0
        self.failed_users = 0
        self.updated_users = 0
        self.last_run_time = None
        self.verification_task = None
        
        # Statistics
        self.stats = {
            "total_runs": 0,
            "last_run_duration": 0,
            "last_run_users": 0,
            "last_run_updates": 0,
            "last_run_failures": 0,
            "average_processing_time": 0
        }
    
    def start_periodic_verification(self):
        """Start the periodic verification task"""
        if self.verification_task and not self.verification_task.done():
            logger.warning("Periodic verification task already running")
            return
        
        interval_hours = config_manager.get("periodic_verification_interval_hours", 24)
        logger.info(f"Starting periodic verification with {interval_hours} hour interval")
        
        # Create and start the task
        self.verification_task = self.periodic_verification_loop.start()
    
    def stop_periodic_verification(self):
        """Stop the periodic verification task"""
        if self.verification_task:
            self.verification_task.cancel()
            logger.info("Periodic verification task stopped")
    
    @tasks.loop(hours=1)  # Check every hour, but only run based on config
    async def periodic_verification_loop(self):
        """Main periodic verification loop"""
        try:
            # Check if it's time to run
            interval_hours = config_manager.get("periodic_verification_interval_hours", 24)
            
            if self.last_run_time:
                time_since_last_run = datetime.utcnow() - self.last_run_time
                if time_since_last_run < timedelta(hours=interval_hours):
                    return  # Not time yet
            
            # Check if system is enabled
            if not config_manager.get("periodic_verification_enabled", False):
                logger.debug("Periodic verification is disabled")
                return
            
            if self.is_running:
                logger.warning("Periodic verification already in progress, skipping this cycle")
                return
            
            logger.info("Starting periodic verification run")
            await self.run_verification_update()
            
        except Exception as e:
            logger.error(f"Error in periodic verification loop: {e}")
    
    async def run_verification_update(self):
        """Run a complete verification update cycle"""
        start_time = time.time()
        self.is_running = True
        self.current_batch = 0
        self.processed_users = 0
        self.failed_users = 0
        self.updated_users = 0
        
        try:
            # Get all verified users
            verified_users = verification_cache.cache.get("verified_users", {})
            self.total_users = len(verified_users)
            
            if self.total_users == 0:
                logger.info("No verified users to update")
                return
            
            logger.info(f"Starting periodic verification for {self.total_users} users")
            
            # Get batch size from config
            batch_size = config_manager.get("periodic_verification_batch_size", 10)
            
            # Process users in batches
            user_items = list(verified_users.items())
            batches = [user_items[i:i + batch_size] for i in range(0, len(user_items), batch_size)]
            
            for batch_index, batch in enumerate(batches):
                self.current_batch = batch_index + 1
                logger.info(f"Processing batch {self.current_batch}/{len(batches)} ({len(batch)} users)")
                
                # Process batch with delay between users
                for player_uuid, user_data in batch:
                    try:
                        await self.update_single_user(player_uuid, user_data)
                        self.processed_users += 1
                        
                        # Small delay between users to avoid rate limiting
                        delay = config_manager.get("periodic_verification_user_delay", 2)
                        await asyncio.sleep(delay)
                        
                    except Exception as e:
                        logger.error(f"Error updating user {user_data.get('ign', 'Unknown')}: {e}")
                        self.failed_users += 1
                
                # Delay between batches
                if batch_index < len(batches) - 1:
                    batch_delay = config_manager.get("periodic_verification_batch_delay", 30)
                    logger.info(f"Waiting {batch_delay} seconds before next batch...")
                    await asyncio.sleep(batch_delay)
            
            # Update statistics
            duration = time.time() - start_time
            self.stats["total_runs"] += 1
            self.stats["last_run_duration"] = duration
            self.stats["last_run_users"] = self.processed_users
            self.stats["last_run_updates"] = self.updated_users
            self.stats["last_run_failures"] = self.failed_users
            
            # Calculate average processing time
            if self.stats["total_runs"] == 1:
                self.stats["average_processing_time"] = duration
            else:
                self.stats["average_processing_time"] = (
                    (self.stats["average_processing_time"] * (self.stats["total_runs"] - 1) + duration) 
                    / self.stats["total_runs"]
                )
            
            self.last_run_time = datetime.utcnow()
            
            logger.info(f"Periodic verification completed: {self.processed_users} processed, "
                       f"{self.updated_users} updated, {self.failed_users} failed in {duration:.1f}s")
            
            # Send summary report if configured
            await self.send_summary_report()
            
        except Exception as e:
            logger.error(f"Error in periodic verification update: {e}")
        finally:
            self.is_running = False
    
async def update_single_user(self, player_uuid: str, user_data: Dict[str, Any]) -> bool:
        """Update a single verified user with relationship status checking"""
        try:
            discord_id = user_data.get("discord_id")
            ign = user_data.get("ign")
            old_nation = user_data.get("nation")
            old_nation_uuid = user_data.get("nation_uuid")
            old_town = user_data.get("town")
            old_town_uuid = user_data.get("town_uuid")
            old_county = user_data.get("county")
            old_is_mayor = user_data.get("is_mayor", False)
            
            if not discord_id or not ign:
                logger.warning(f"Incomplete user data for UUID {player_uuid}")
                return False
            
            logger.debug(f"Updating user {ign} (Discord: {discord_id})")
            
            # Get current player information
            player_result = await get_player_info_by_uuid(player_uuid)
            
            if not player_result["success"]:
                # Try by IGN as fallback
                player_result = await get_player_info(ign)
                if not player_result["success"]:
                    logger.warning(f"Could not get current info for {ign}: {player_result['error']}")
                    return False
            
            player_data = player_result["data"]
            current_ign = player_data.get("name", ign)
            nation_data = player_data.get("nation")
            town_data = player_data.get("town")
            status_data = player_data.get("status", {})
            
            # Check if player left all nations
            if not nation_data:
                logger.info(f"User {current_ign} is no longer in any nation, revoking roles")
                await self.handle_nation_departure(discord_id, old_nation_uuid, old_nation)
                return True
            
            # Extract current information
            current_nation = nation_data.get("name")
            current_nation_uuid = nation_data.get("uuid")
            current_town = town_data.get("name") if town_data else None
            current_town_uuid = town_data.get("uuid") if town_data else None
            current_is_mayor = status_data.get("isMayor", False)
            
            # Check if still in approved nation
            approved_nations = config_manager.get_approved_nations()
            if current_nation not in approved_nations:
                logger.info(f"User {current_ign} is now in unapproved nation {current_nation}, revoking roles")
                await self.handle_nation_departure(discord_id, old_nation_uuid, old_nation)
                return True
            
            # Get current county assignment
            current_county = None
            current_county_role_id = None
            if current_nation_uuid and current_town_uuid:
                current_county, current_county_role_id, _ = get_county_for_town_uuid(current_nation_uuid, current_town_uuid)
            elif current_nation and current_town_uuid:
                current_county, current_county_role_id, _ = get_county_for_town(current_nation, current_town_uuid)
            
            # Check if anything changed
            changes = []
            if current_ign != ign:
                changes.append(f"IGN: {ign} → {current_ign}")
            if current_nation_uuid != old_nation_uuid:
                changes.append(f"Nation: {old_nation} → {current_nation}")
            if current_town_uuid != old_town_uuid:
                changes.append(f"Town: {old_town} → {current_town}")
            if current_county != old_county:
                changes.append(f"County: {old_county} → {current_county}")
            if current_is_mayor != old_is_mayor:
                changes.append(f"Mayor: {old_is_mayor} → {current_is_mayor}")
            
            if not changes:
                # Even if no basic changes, check if relationship status changed across guilds
                await self.check_and_update_relationships(discord_id, current_ign, current_nation_uuid, current_nation)
                logger.debug(f"No changes detected for user {current_ign}, but checked relationships")
                return False
            
            logger.info(f"Changes detected for {current_ign}: {', '.join(changes)}")
            
            # Update verification cache
            verification_cache.update_user_data(
                player_uuid=player_uuid,
                ign=current_ign,
                nation=current_nation,
                nation_uuid=current_nation_uuid,
                town=current_town,
                town_uuid=current_town_uuid,
                is_mayor=current_is_mayor,
                county=current_county,
                last_verified_by="periodic_system",
                last_verified_at=time.time()
            )
            
            # Update Discord roles if user is in guild + handle relationship changes
            await self.update_discord_roles_and_relationships(
                discord_id, current_ign, current_nation, current_is_mayor,
                current_county, current_county_role_id, user_data, current_nation_uuid
            )
            
            self.updated_users += 1
            return True
            
        except Exception as e:
            logger.error(f"Error updating single user {player_uuid}: {e}")
            return False

    async def check_and_update_relationships(self, discord_id: str, ign: str, nation_uuid: str, nation_name: str):
        """Check and update relationship status across all guilds even when no basic info changed"""
        try:
            # Get multi-guild manager
            mgm = get_multi_guild_manager()
            if mgm:
                await mgm.update_user_relationship_across_guilds(discord_id, ign, nation_uuid, nation_name)
        except Exception as e:
            logger.error(f"Error checking relationships for {ign}: {e}")

    async def update_discord_roles_and_relationships(self, discord_id: str, ign: str, nation: str, is_mayor: bool,
                                                   county: str, county_role_id: int, existing_verification: Dict[str, Any],
                                                   nation_uuid: str):
        """Update Discord roles with relationship checking"""
        try:
            # Update in primary guild first
            await self.update_discord_roles(discord_id, ign, nation, is_mayor, county, county_role_id, existing_verification)
            
            # Update relationships across all guilds
            mgm = get_multi_guild_manager()
            if mgm:
                await mgm.update_user_relationship_across_guilds(discord_id, ign, nation_uuid, nation)
            
        except Exception as e:
            logger.error(f"Error updating Discord roles and relationships for {ign}: {e}")
    
    async def handle_nation_departure(self, discord_id: str, old_nation_uuid: str, old_nation: str):
        """Handle when a user leaves their nation"""
        try:
            # Remove from verification cache
            verification_cache.remove_verified_user(discord_id)
            
            # Update Discord roles if user is in guild
            for guild in self.bot.guilds:
                if not config_manager.get("approved_guilds") or guild.id in config_manager.get("approved_guilds", []):
                    member = guild.get_member(int(discord_id))
                    if member:
                        if old_nation_uuid:
                            await revoke_nation_roles_by_uuid(member, old_nation_uuid, old_nation)
                        else:
                            from roles.manager import revoke_nation_roles
                            await revoke_nation_roles(member, old_nation)
                        break
            
        except Exception as e:
            logger.error(f"Error handling nation departure for Discord ID {discord_id}: {e}")
    
    async def update_discord_roles(self, discord_id: str, ign: str, nation: str, is_mayor: bool,
                                 county: str, county_role_id: int, existing_verification: Dict[str, Any]):
        """Update Discord roles for a user"""
        try:
            # Find the user in approved guilds
            for guild in self.bot.guilds:
                if not config_manager.get("approved_guilds") or guild.id in config_manager.get("approved_guilds", []):
                    member = guild.get_member(int(discord_id))
                    if member:
                        await handle_role_updates(
                            member, ign, nation, is_mayor, county, county_role_id, existing_verification
                        )
                        break
            
        except Exception as e:
            logger.error(f"Error updating Discord roles for {ign}: {e}")
    
    async def send_summary_report(self):
        """Send periodic verification summary report"""
        try:
            report_channel_id = config_manager.get("periodic_verification_report_channel")
            if not report_channel_id:
                return
            
            channel = self.bot.get_channel(report_channel_id)
            if not channel:
                logger.warning(f"Report channel {report_channel_id} not found")
                return
            
            embed = discord.Embed(
                title="🔄 Periodic Verification Summary",
                color=0x00ff00 if self.failed_users == 0 else 0xffaa00,
                timestamp=discord.utils.utcnow()
            )
            
            embed.add_field(name="👥 Total Users", value=str(self.total_users), inline=True)
            embed.add_field(name="✅ Processed", value=str(self.processed_users), inline=True)
            embed.add_field(name="🔄 Updated", value=str(self.updated_users), inline=True)
            embed.add_field(name="❌ Failed", value=str(self.failed_users), inline=True)
            embed.add_field(name="⏱️ Duration", value=f"{self.stats['last_run_duration']:.1f}s", inline=True)
            embed.add_field(name="📊 Total Runs", value=str(self.stats['total_runs']), inline=True)
            
            if self.last_run_time:
                embed.add_field(
                    name="🕒 Next Run", 
                    value=f"<t:{int((self.last_run_time + timedelta(hours=config_manager.get('periodic_verification_interval_hours', 24))).timestamp())}:R>", 
                    inline=False
                )
            
            await channel.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error sending summary report: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status of periodic verification"""
        return {
            "is_running": self.is_running,
            "current_batch": self.current_batch,
            "total_users": self.total_users,
            "processed_users": self.processed_users,
            "failed_users": self.failed_users,
            "updated_users": self.updated_users,
            "last_run_time": self.last_run_time.isoformat() if self.last_run_time else None,
            "stats": self.stats
        }

# Global instance
periodic_verification_manager = None

def setup_periodic_verification(bot):
    """Setup periodic verification system"""
    global periodic_verification_manager
    periodic_verification_manager = PeriodicVerificationManager(bot)
    
    # Start if enabled
    if config_manager.get("periodic_verification_enabled", False):
        periodic_verification_manager.start_periodic_verification()
    
    return periodic_verification_manager