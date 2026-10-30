import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db
from core.config import get_available_ocr_languages

logger = logging.getLogger("youtube-verifier.admin")


class AdminCog(commands.Cog, name="Administration"):
    """Server administration and bot configuration commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- Setup Hybrid Group ---

    @commands.hybrid_group(
        name="setup",
        description="Configure YouTube verification settings for this server",
        fallback="show",
    )
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def setup_cmd(self, ctx: commands.Context):
        """Displays current server settings (default action if no subcommand is specified)."""
        cfg = db.get_guild_config(ctx.guild.id)
        alt_names = cfg.get("alternative_channel_names", [])
        alt_text = ", ".join(f"`{name}`" for name in alt_names) if alt_names else "*None*"

        log_ch_id = cfg.get("log_channel_id")
        log_ch_mention = f"<#{log_ch_id}>" if log_ch_id else "*Disabled*"

        role_name = cfg.get("verified_role_name", "Subscriber")
        role_obj = discord.utils.get(ctx.guild.roles, name=role_name)
        role_display = role_obj.mention if role_obj else f"`{role_name}` *(Role not found on server)*"

        embed = discord.Embed(
            title=f"⚙️ Verification Settings - {ctx.guild.name}",
            description="Use `/setup <option>` to modify any of the settings below.",
            color=discord.Color.blue(),
        )
        embed.add_field(name="🎯 YouTube Channel", value=f"`{cfg.get('youtube_channel_name')}`", inline=True)
        embed.add_field(name="🏷️ Verified Role", value=role_display, inline=True)
        embed.add_field(name="⏳ Cooldown", value=f"`{cfg.get('cooldown_hours', 24)} hour(s)`", inline=True)
        embed.add_field(
            name="📊 Confidence Threshold",
            value=f"`{float(cfg.get('verification_threshold', 0.7)) * 100:.0f}%`",
            inline=True,
        )
        embed.add_field(name="📋 Audit Log Channel", value=log_ch_mention, inline=True)
        embed.add_field(name="🔤 Alternative Channel Names", value=alt_text, inline=False)

        embed.set_footer(text="Requires Administrator permissions to modify.")
        await ctx.reply(embed=embed)

    @setup_cmd.command(name="channel", description="Set the target YouTube channel name to verify")
    @app_commands.describe(channel_name="The exact YouTube channel name or handle")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def set_channel(self, ctx: commands.Context, *, channel_name: str):
        """Sets the YouTube channel name that users must be subscribed to."""
        db.update_guild_config(ctx.guild.id, "youtube_channel_name", channel_name.strip())
        embed = discord.Embed(
            title="✅ YouTube Channel Updated",
            description=f"The required YouTube channel is now set to: **{channel_name.strip()}**",
            color=discord.Color.green(),
        )
        await ctx.reply(embed=embed)

    @setup_cmd.command(name="role", description="Set the Discord role granted to verified subscribers")
    @app_commands.describe(role="The role to grant upon successful verification")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def set_role(self, ctx: commands.Context, role: discord.Role):
        """Sets the Discord role granted upon verification."""
        # Check hierarchy
        if ctx.guild.me.top_role <= role:
            embed = discord.Embed(
                title="⚠️ Role Hierarchy Warning",
                description=(
                    f"I have saved **{role.name}** as the verified role, but my highest role is "
                    f"lower than or equal to this role.\n"
                    "Please move the bot's role above this role in `Server Settings -> Roles` "
                    "so I can assign it to members."
                ),
                color=discord.Color.gold(),
            )
            db.update_guild_config(ctx.guild.id, "verified_role_name", role.name)
            await ctx.reply(embed=embed)
            return

        db.update_guild_config(ctx.guild.id, "verified_role_name", role.name)
        embed = discord.Embed(
            title="✅ Verified Role Updated",
            description=f"Verified members will receive the role: {role.mention}",
            color=discord.Color.green(),
        )
        await ctx.reply(embed=embed)

    @setup_cmd.command(name="cooldown", description="Set cooldown period between verification attempts (in hours)")
    @app_commands.describe(hours="Cooldown duration in hours (e.g. 24 or 0 to disable)")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def set_cooldown(self, ctx: commands.Context, hours: float):
        """Sets the cooldown period between verification attempts."""
        if hours < 0:
            await ctx.reply("❌ Cooldown cannot be negative.")
            return

        db.update_guild_config(ctx.guild.id, "cooldown_hours", hours)
        embed = discord.Embed(
            title="✅ Cooldown Updated",
            description=f"Verification cooldown set to **{hours} hour(s)**.",
            color=discord.Color.green(),
        )
        await ctx.reply(embed=embed)

    @setup_cmd.command(name="threshold", description="Set the minimum OCR confidence score (0.0 to 1.0)")
    @app_commands.describe(score="Minimum confidence score between 0.0 and 1.0 (recommended: 0.7)")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def set_threshold(self, ctx: commands.Context, score: float):
        """Sets the OCR confidence threshold."""
        if score < 0.1 or score > 1.0:
            await ctx.reply("❌ Threshold must be a value between `0.1` and `1.0`.")
            return

        db.update_guild_config(ctx.guild.id, "verification_threshold", score)
        embed = discord.Embed(
            title="✅ Confidence Threshold Updated",
            description=f"Minimum confidence threshold set to **{score * 100:.0f}%** (`{score}`).",
            color=discord.Color.green(),
        )
        await ctx.reply(embed=embed)

    @setup_cmd.command(name="add_alt", description="Add an alternative channel name (e.g., abbreviations or handles)")
    @app_commands.describe(name="Alternative channel name or handle to recognize")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def add_alt_name(self, ctx: commands.Context, *, name: str):
        """Adds an alternative recognized channel name."""
        cfg = db.get_guild_config(ctx.guild.id)
        alts = cfg.get("alternative_channel_names", [])

        clean_name = name.strip()
        if clean_name.lower() in [a.lower() for a in alts]:
            await ctx.reply(f"⚠️ `{clean_name}` is already in the alternative names list.")
            return

        alts.append(clean_name)
        db.update_guild_config(ctx.guild.id, "alternative_channel_names", alts)

        embed = discord.Embed(
            title="✅ Alternative Name Added",
            description=f"Added **{clean_name}** to recognized channel names.",
            color=discord.Color.green(),
        )
        await ctx.reply(embed=embed)

    @setup_cmd.command(name="remove_alt", description="Remove an alternative channel name")
    @app_commands.describe(name="Alternative channel name to remove")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def remove_alt_name(self, ctx: commands.Context, *, name: str):
        """Removes an alternative channel name."""
        cfg = db.get_guild_config(ctx.guild.id)
        alts = cfg.get("alternative_channel_names", [])

        target = next((a for a in alts if a.lower() == name.strip().lower()), None)
        if not target:
            await ctx.reply(f"⚠️ `{name}` was not found in the alternative names list.")
            return

        alts.remove(target)
        db.update_guild_config(ctx.guild.id, "alternative_channel_names", alts)

        embed = discord.Embed(
            title="✅ Alternative Name Removed",
            description=f"Removed **{target}** from recognized channel names.",
            color=discord.Color.green(),
        )
        await ctx.reply(embed=embed)

    @setup_cmd.command(name="log_channel", description="Set or disable the verification audit log channel")
    @app_commands.describe(channel="Text channel to receive logs, or omit to disable")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def set_log_channel(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Configures the text channel where verification logs are sent."""
        channel_id = channel.id if channel else None
        db.update_guild_config(ctx.guild.id, "log_channel_id", channel_id)

        if channel:
            embed = discord.Embed(
                title="✅ Audit Log Channel Enabled",
                description=f"Verification results will be logged to {channel.mention}.",
                color=discord.Color.green(),
            )
        else:
            embed = discord.Embed(
                title="ℹ️ Audit Logging Disabled",
                description="Verification results will no longer be logged to a channel.",
                color=discord.Color.blue(),
            )
        await ctx.reply(embed=embed)

    # --- Other Admin Commands ---

    @commands.hybrid_command(
        name="clear_cooldown",
        description="Reset the verification cooldown for a specific user",
    )
    @app_commands.describe(user="The member whose cooldown should be reset")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def clear_cooldown_cmd(self, ctx: commands.Context, user: discord.Member):
        """Resets the verification cooldown timer for a user."""
        cleared = db.clear_user_cooldown(ctx.guild.id, user.id)
        if cleared:
            embed = discord.Embed(
                title="✅ Cooldown Cleared",
                description=f"Verification cooldown for {user.mention} has been reset. They can now verify again immediately.",
                color=discord.Color.green(),
            )
        else:
            embed = discord.Embed(
                title="ℹ️ No Active Cooldown",
                description=f"{user.mention} does not have an active cooldown.",
                color=discord.Color.blue(),
            )
        await ctx.reply(embed=embed)

    @commands.hybrid_command(
        name="stats",
        description="Display bot and server verification statistics",
    )
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def stats_cmd(self, ctx: commands.Context):
        """Shows verification statistics for the server and bot diagnostics."""
        guild = ctx.guild
        cfg = db.get_guild_config(guild.id)
        role_name = cfg.get("verified_role_name", "Subscriber")
        role_obj = discord.utils.get(guild.roles, name=role_name)

        verified_count = len(role_obj.members) if role_obj else 0
        total_members = guild.member_count or len(guild.members)
        percentage = (verified_count / total_members * 100) if total_members > 0 else 0

        languages = get_available_ocr_languages()
        lang_str = ", ".join(languages) if languages else "None detected"

        embed = discord.Embed(
            title=f"📊 Statistics - {guild.name}",
            color=discord.Color.blue(),
        )
        embed.add_field(name="👥 Total Members", value=f"{total_members:,}", inline=True)
        embed.add_field(name="✅ Verified Subscribers", value=f"{verified_count:,}", inline=True)
        embed.add_field(name="📈 Verified Percentage", value=f"{percentage:.1f}%", inline=True)
        embed.add_field(name="🌐 Bot Servers", value=f"{len(self.bot.guilds):,}", inline=True)
        embed.add_field(name="⚡ Bot Latency", value=f"{round(self.bot.latency * 1000)}ms", inline=True)
        embed.add_field(name="🔤 Installed OCR Languages", value=lang_str, inline=False)

        await ctx.reply(embed=embed)

    @commands.command(name="sync", description="Sync slash commands with Discord (Admin/Owner only)")
    @commands.has_permissions(administrator=True)
    async def sync_slash_commands(self, ctx: commands.Context, scope: Optional[str] = None):
        """
        Syncs application commands with Discord.
        Usage:
            !sync         -> Syncs slash commands to the current guild immediately.
            !sync global  -> Syncs slash commands globally across all guilds.
        """
        async with ctx.typing():
            try:
                if scope and scope.lower() == "global":
                    synced = await self.bot.tree.sync()
                    await ctx.reply(f"🌍 Successfully synced **{len(synced)}** slash command(s) globally.")
                else:
                    self.bot.tree.copy_global_to(guild=ctx.guild)
                    synced = await self.bot.tree.sync(guild=ctx.guild)
                    await ctx.reply(f"🏠 Successfully synced **{len(synced)}** slash command(s) to this server.")
            except Exception as e:
                await ctx.reply(f"❌ Failed to sync slash commands: `{e}`")
                logger.error(f"Command sync error: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
