import discord

def create_permission_denied_embed() -> discord.Embed:
    """Create a permission denied embed"""
    return discord.Embed(
        title="❌ Permission Denied",
        description="You don't have permission to use this command.",
        color=0xff0000
    )

def create_error_embed(title: str, description: str) -> discord.Embed:
    """Create a generic error embed"""
    return discord.Embed(
        title=title,
        description=description,
        color=0xff0000
    )

def create_success_embed(title: str, description: str, user: discord.Member = None) -> discord.Embed:
    """Create a success embed with optional user attribution"""
    embed = discord.Embed(
        title=title,
        description=description,
        color=0x00ff00,
        timestamp=discord.utils.utcnow()
    )
    if user:
        embed.add_field(name="Modified By", value=user.mention, inline=True)
    return embed

def create_warning_embed(title: str, description: str) -> discord.Embed:
    """Create a warning embed"""
    return discord.Embed(
        title=title,
        description=description,
        color=0xffaa00
    )