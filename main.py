import asyncio
import logging
import os
import sys
import traceback
from typing import Optional

import aiohttp
import discord
from discord.ext import commands, tasks

from core.config import (
    DISCORD_TOKEN,
    COMMAND_PREFIX,
    SYNC_SLASH_COMMANDS_GLOBALLY,
    find_and_configure_tesseract,
    logger,
)
from core.database import db

# Initial extensions to load
INITIAL_EXTENSIONS = [
    "cogs.verification",
    "cogs.admin",
    "cogs.general",
]


class YouTubeVerificationBot(commands.Bot):
    """
    Production-ready Discord bot for verifying YouTube subscriptions via screenshot OCR.
    Supports both Slash Commands and Prefix Commands.
    """

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        super().__init__(
            command_prefix=commands.when_mentioned_or(COMMAND_PREFIX),
            intents=intents,
            help_command=None,  # Using custom hybrid /help command
        )

        self.http_session: Optional[aiohttp.ClientSession] = None
        self._has_synced: bool = False

    async def setup_hook(self) -> None:
        """Asynchronous setup routine called before the bot connects to Discord."""
        # 1. Initialize persistent HTTP session
        self.http_session = aiohttp.ClientSession()

        # 2. Check and configure Tesseract OCR
        tess_ok, tess_info = find_and_configure_tesseract()
        if not tess_ok:
            logger.warning("Bot is starting without active Tesseract OCR. Verification commands will warn users.")

        # 3. Load Cogs
        for ext in INITIAL_EXTENSIONS:
            try:
                await self.load_extension(ext)
                logger.info(f"Loaded extension: {ext}")
            except Exception as e:
                logger.error(f"Failed to load extension {ext}: {e}")
                traceback.print_exc()

        # 4. Start background periodic tasks
        self.periodic_save_task.start()

    async def close(self) -> None:
        """Gracefully closes HTTP sessions and flushes databases on shutdown."""
        logger.info("Bot shutting down. Saving all data to disk...")
        db.save_all()
        if self.http_session and not self.http_session.closed:
            await self.http_session.close()
        await super().close()

    @tasks.loop(hours=1.0)
    async def periodic_save_task(self):
        """Flushes configuration and cooldown databases to disk hourly."""
        db.save_all()
        logger.debug("Periodic backup of configs and cooldowns completed.")

    @periodic_save_task.before_loop
    async def before_periodic_save(self):
        await self.wait_until_ready()


bot = YouTubeVerificationBot()


# --- Event Handlers ---

@bot.event
async def on_ready():
    """Triggered when the bot successfully establishes a connection with Discord."""
    logger.info(f"Logged in as: {bot.user.name} (ID: {bot.user.id})")
    logger.info(f"Connected to {len(bot.guilds)} guild(s).")

    # Sync slash commands once connected if configured
    if SYNC_SLASH_COMMANDS_GLOBALLY and not bot._has_synced:
        try:
            logger.info("Syncing application slash commands globally with Discord...")
            synced = await bot.tree.sync()
            bot._has_synced = True
            logger.info(f"Successfully synced {len(synced)} application slash command(s).")
        except Exception as e:
            logger.error(f"Failed to sync slash commands on ready: {e}")

    # Set presence activity
    activity = discord.Activity(
        type=discord.ActivityType.watching,
        name=f"/verify | {COMMAND_PREFIX}help",
    )
    await bot.change_presence(activity=activity, status=discord.Status.online)
    logger.info("Bot presence set successfully.")


@bot.event
async def on_guild_join(guild: discord.Guild):
    """Triggered when the bot joins a new Discord guild."""
    logger.info(f"Joined new guild: {guild.name} (ID: {guild.id}) with {guild.member_count} members.")

    # Initialize default configuration
    db.get_guild_config(guild.id)

    # Find the best channel to send the welcome message
    target_channel = guild.system_channel
    if not target_channel or not target_channel.permissions_for(guild.me).send_messages:
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                target_channel = channel
                break

    if target_channel:
        embed = discord.Embed(
            title="👋 Thanks for adding YouTube Subscription Verifier!",
            description=(
                "I help automate granting roles to members who subscribe to your YouTube channel "
                "by analyzing their screenshots using OCR.\n\n"
                "**Quick Setup (Admins):**\n"
                "1. `/setup channel <Channel Name>` - Set your target YouTube channel.\n"
                "2. `/setup role <@Role>` - Select the role granted to verified subscribers.\n"
                "3. Make sure my bot role is positioned **above** the verified role in Server Settings.\n\n"
                "**Member Verification:**\n"
                "Members can simply run `/verify` and attach a screenshot of their subscription."
            ),
            color=discord.Color.green(),
        )
        embed.set_footer(text=f"Type /help or {COMMAND_PREFIX}help for full command list.")
        try:
            await target_channel.send(embed=embed)
        except discord.Forbidden:
            pass


@bot.event
async def on_command_error(ctx: commands.Context, error: Exception):
    """Global error handler for prefix and hybrid commands."""
    # Ignore command not found
    if isinstance(error, commands.CommandNotFound):
        return

    # User lacks permissions
    if isinstance(error, commands.MissingPermissions):
        missing = ", ".join(error.missing_permissions)
        embed = discord.Embed(
            title="❌ Permission Denied",
            description=f"You need the **{missing}** permission to use this command.",
            color=discord.Color.red(),
        )
        await ctx.reply(embed=embed)
        return

    # Bot lacks permissions
    if isinstance(error, commands.BotMissingPermissions):
        missing = ", ".join(error.missing_permissions)
        embed = discord.Embed(
            title="❌ Bot Missing Permissions",
            description=f"I require the **{missing}** permission to perform this action.",
            color=discord.Color.red(),
        )
        await ctx.reply(embed=embed)
        return

    # Bad argument
    if isinstance(error, commands.BadArgument):
        embed = discord.Embed(
            title="❌ Invalid Argument",
            description=str(error),
            color=discord.Color.red(),
        )
        await ctx.reply(embed=embed)
        return

    # Channel only check
    if isinstance(error, commands.NoPrivateMessage):
        embed = discord.Embed(
            title="❌ Server Only",
            description="This command can only be used within a server.",
            color=discord.Color.red(),
        )
        await ctx.reply(embed=embed)
        return

    # Other errors
    logger.error(f"Unhandled command error in '{ctx.command}': {error}")
    traceback.print_exception(type(error), error, error.__traceback__)

    embed = discord.Embed(
        title="⚠️ An Unexpected Error Occurred",
        description="An error occurred while executing this command. Please try again later.",
        color=discord.Color.red(),
    )
    try:
        await ctx.reply(embed=embed)
    except Exception:
        pass


# --- Application Entrypoint ---

def main():
    if not DISCORD_TOKEN or DISCORD_TOKEN == "your_bot_token_here":
        logger.critical(
            "CRITICAL: DISCORD_TOKEN is missing in your .env file.\n"
            "Please create or edit your .env file and set DISCORD_TOKEN to your bot token.\n"
            "See .env.example for guidance."
        )
        sys.exit(1)

    try:
        bot.run(DISCORD_TOKEN)
    except discord.LoginFailure:
        logger.critical("CRITICAL: Invalid Discord token provided. Please verify your token in .env.")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"Bot failed to start: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
