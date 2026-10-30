import logging
from typing import Optional
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from core.database import db
from core.ocr import download_image, verify_screenshot_async, VerificationResult

logger = logging.getLogger("youtube-verifier.verification")

SUPPORTED_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")


class VerificationCog(commands.Cog, name="Verification"):
    """Handles member YouTube subscription verification workflows."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(
        name="verify",
        description="Verify your YouTube subscription by uploading a screenshot",
    )
    @app_commands.describe(
        image="Attach a screenshot showing your subscription to the YouTube channel",
        image_url="Or provide a direct URL to your subscription screenshot",
    )
    @commands.guild_only()
    async def verify(
        self,
        ctx: commands.Context,
        image: Optional[discord.Attachment] = None,
        image_url: Optional[str] = None,
    ):
        """
        Verifies your YouTube subscription by analyzing an uploaded screenshot.
        Can be used both as a slash command `/verify` and a prefix command `!verify`.
        """
        # Defer immediately to allow OCR pipeline ample processing time
        await ctx.defer()

        guild = ctx.guild
        member = ctx.author
        cfg = db.get_guild_config(guild.id)

        channel_name = cfg.get("youtube_channel_name", "YouTube Channel")
        role_name = cfg.get("verified_role_name", "Subscriber")
        cooldown_hours = float(cfg.get("cooldown_hours", 24))
        threshold = float(cfg.get("verification_threshold", 0.7))
        alt_names = cfg.get("alternative_channel_names", [])

        # 1. Cooldown Check
        is_cooldown, remaining, expiry = db.check_user_cooldown(guild.id, member.id, cooldown_hours)
        if is_cooldown and remaining and expiry:
            expiry_timestamp = int(expiry.timestamp())
            embed = discord.Embed(
                title="⏳ Verification On Cooldown",
                description=(
                    f"You recently attempted verification.\n"
                    f"You can try again <t:{expiry_timestamp}:R> (at <t:{expiry_timestamp}:f>)."
                ),
                color=discord.Color.orange(),
            )
            embed.set_footer(text=f"Cooldown period: {cooldown_hours} hour(s)")
            await ctx.reply(embed=embed)
            return

        # 2. Extract Screenshot Attachment or URL
        target_url: Optional[str] = None

        if image is not None:
            target_url = image.url
        elif ctx.message and ctx.message.attachments:
            target_url = ctx.message.attachments[0].url
        elif image_url is not None and image_url.startswith(("http://", "https://")):
            target_url = image_url

        if not target_url:
            embed = discord.Embed(
                title="📸 Screenshot Required",
                description=(
                    f"Please attach a clear screenshot showing that you are subscribed to **{channel_name}**.\n\n"
                    "**How to verify:**\n"
                    "• **Slash Command:** Type `/verify` and attach your image in the prompt.\n"
                    "• **Prefix Command:** Type `!verify` and attach the image to your message."
                ),
                color=discord.Color.blurple(),
            )
            await ctx.reply(embed=embed)
            return

        # Validate file extension
        url_clean = target_url.split("?")[0].lower()
        if not any(url_clean.endswith(ext) for ext in SUPPORTED_IMAGE_EXTENSIONS):
            embed = discord.Embed(
                title="❌ Unsupported File Format",
                description="Please provide an image in PNG, JPG, JPEG, WEBP, or BMP format.",
                color=discord.Color.red(),
            )
            await ctx.reply(embed=embed)
            return

        # 3. Download Image
        image_bytes = await download_image(target_url, session=getattr(self.bot, "http_session", None))
        if not image_bytes:
            embed = discord.Embed(
                title="❌ Image Download Failed",
                description="Could not download the provided image. Please try uploading the image directly.",
                color=discord.Color.red(),
            )
            await ctx.reply(embed=embed)
            return

        # 4. Perform OCR Analysis
        result: VerificationResult = await verify_screenshot_async(
            image_bytes=image_bytes,
            channel_name=channel_name,
            alternative_names=alt_names,
            threshold=threshold,
        )

        # Record attempt for cooldown
        db.record_attempt(guild.id, member.id)

        # 5. Handle Verification Result
        if result.is_verified:
            # Find the role
            target_role = discord.utils.get(guild.roles, name=role_name)

            if target_role is None:
                embed = discord.Embed(
                    title="⚠️ Role Not Found",
                    description=(
                        f"You successfully proved your subscription to **{channel_name}**, "
                        f"but the role **@{role_name}** does not exist in this server.\n"
                        "Please notify a server administrator to configure the role using `/setup role`."
                    ),
                    color=discord.Color.gold(),
                )
                await ctx.reply(embed=embed)
                return

            # Check if member already has role
            if target_role in member.roles:
                embed = discord.Embed(
                    title="✅ Already Verified",
                    description=f"You already have the **{target_role.name}** role!",
                    color=discord.Color.green(),
                )
                await ctx.reply(embed=embed)
                return

            # Assign role
            try:
                await member.add_roles(target_role, reason="YouTube subscription verified via screenshot OCR")
                embed = discord.Embed(
                    title="🎉 Subscription Verified Successfully!",
                    description=(
                        f"Congratulations {member.mention}! Your subscription to **{channel_name}** "
                        f"has been verified, and you've been granted the **{target_role.mention}** role."
                    ),
                    color=discord.Color.green(),
                )
                embed.add_field(name="Target Channel", value=channel_name, inline=True)
                embed.add_field(name="Role Granted", value=target_role.name, inline=True)
                embed.add_field(name="Confidence Score", value=f"{result.confidence * 100:.1f}%", inline=True)
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.set_footer(text="Thank you for supporting the channel!")

                await ctx.reply(embed=embed)
                logger.info(f"Verified member {member} (ID: {member.id}) in guild '{guild.name}' (ID: {guild.id}).")

                # Send log to admin logging channel if configured
                await self._send_audit_log(guild, cfg, member, True, result)

            except discord.Forbidden:
                embed = discord.Embed(
                    title="❌ Missing Role Permissions",
                    description=(
                        "I don't have permission to assign this role.\n\n"
                        "**For Server Admins:**\n"
                        "1. Ensure the bot has the **Manage Roles** permission.\n"
                        "2. Move the bot's role **higher** than the verified role in `Server Settings -> Roles`."
                    ),
                    color=discord.Color.red(),
                )
                await ctx.reply(embed=embed)
                logger.warning(f"Forbidden: Cannot assign role '{role_name}' to {member} in guild '{guild.name}'.")
        else:
            # Verification failed
            embed = discord.Embed(
                title="❌ Verification Failed",
                description=result.failure_reason or "Subscription could not be verified.",
                color=discord.Color.red(),
            )
            embed.add_field(
                name="💡 Tips for Successful Verification",
                value=(
                    f"1. Make sure you are subscribed to **{channel_name}**.\n"
                    "2. The screenshot must clearly display the channel name and the button showing **Subscribed** (or **مشترك**).\n"
                    "3. Avoid blurry, cropped, or low-resolution images."
                ),
                inline=False,
            )
            if result.confidence > 0:
                embed.set_footer(text=f"Detected Confidence: {result.confidence * 100:.1f}% | Threshold: {threshold * 100:.0f}%")

            await ctx.reply(embed=embed)
            logger.info(
                f"Verification failed for {member} (ID: {member.id}) in '{guild.name}'. Reason: {result.failure_reason}"
            )
            await self._send_audit_log(guild, cfg, member, False, result)

    async def _send_audit_log(
        self,
        guild: discord.Guild,
        cfg: dict,
        member: discord.Member,
        success: bool,
        result: VerificationResult,
    ) -> None:
        """Sends an audit log entry to the server's configured log channel, if any."""
        log_channel_id = cfg.get("log_channel_id")
        if not log_channel_id:
            return

        channel = guild.get_channel(int(log_channel_id))
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        try:
            status_text = "PASSED" if success else "FAILED"
            embed = discord.Embed(
                title=f"Verification Log: {status_text}",
                color=discord.Color.green() if success else discord.Color.red(),
                timestamp=datetime.utcnow(),
            )
            embed.add_field(name="User", value=f"{member.mention} ({member.name})", inline=True)
            embed.add_field(name="Confidence", value=f"{result.confidence * 100:.1f}%", inline=True)
            embed.add_field(name="Language", value=result.detected_language, inline=True)
            if not success and result.failure_reason:
                embed.add_field(name="Failure Reason", value=result.failure_reason, inline=False)

            await channel.send(embed=embed)
        except Exception as e:
            logger.warning(f"Failed to send verification log to channel {log_channel_id}: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(VerificationCog(bot))

