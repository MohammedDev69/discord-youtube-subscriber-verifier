import time
import discord
from discord.ext import commands

from core.database import db


class GeneralCog(commands.Cog, name="General"):
    """General utility and information commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(
        name="help",
        description="Display information on how to use the bot and available commands",
    )
    async def help_cmd(self, ctx: commands.Context):
        """Displays the categorized help manual."""
        prefix = ctx.clean_prefix
        is_admin = False
        if ctx.guild and isinstance(ctx.author, discord.Member):
            is_admin = ctx.author.guild_permissions.administrator

        embed = discord.Embed(
            title="📖 YouTube Subscription Verifier - Help Manual",
            description=(
                "This bot verifies whether members are subscribed to your YouTube channel "
                "by analyzing uploaded screenshots using computer vision and optical character recognition (OCR).\n\n"
                "All commands work with both **Slash Commands (`/`)** and **Prefix Commands (`!` or your custom prefix)**."
            ),
            color=discord.Color.blurple(),
        )

        # General Member Commands
        embed.add_field(
            name="👥 Member Commands",
            value=(
                f"• `/{'verify'}` or `{prefix}verify`\n"
                "  Attach a screenshot proving you are subscribed to receive the verified role.\n"
                f"• `/{'ping'}` or `{prefix}ping`\n"
                "  Check the bot's latency and connection speed.\n"
                f"• `/{'about'}` or `{prefix}about`\n"
                "  View bot specifications and open-source information."
            ),
            inline=False,
        )

        # Admin Commands
        admin_text = (
            f"• `/{'setup'}` or `{prefix}setup`\n"
            "  View or edit settings (channel, role, cooldown, threshold, alternative names).\n"
            f"• `/{'setup channel'} <name>` - Set required YouTube channel.\n"
            f"• `/{'setup role'} <@role>` - Set the verified subscriber role.\n"
            f"• `/{'setup cooldown'} <hours>` - Set attempt cooldown (default: 24h).\n"
            f"• `/{'setup threshold'} <0.1-1.0>` - Set minimum OCR confidence.\n"
            f"• `/{'setup add_alt'} <name>` - Add channel handle or alias.\n"
            f"• `/{'stats'}` or `{prefix}stats`\n"
            "  View server member verification statistics.\n"
            f"• `/{'clear_cooldown'} <@user>`\n"
            "  Reset the verification cooldown for a user.\n"
            f"• `{prefix}sync [global]`\n"
            "  Sync slash commands with Discord."
        )

        embed.add_field(
            name="🛡️ Administrator Commands",
            value=admin_text,
            inline=False,
        )

        # Tips for Verification
        embed.add_field(
            name="📸 Tips for Fast Verification",
            value=(
                "1. **Clear Screenshot:** Make sure text is sharp and readable.\n"
                "2. **Visible Status:** The button must clearly state **'Subscribed'** (or your language's equivalent: 'مشترك', 'Abonné', 'Suscrito').\n"
                "3. **Channel Identity:** The channel name or handle must be visible in the image."
            ),
            inline=False,
        )

        embed.set_footer(text="Tip: You can use slash commands anywhere by typing /")
        await ctx.reply(embed=embed)

    @commands.hybrid_command(
        name="ping",
        description="Check the bot's websocket latency and API response time",
    )
    async def ping_cmd(self, ctx: commands.Context):
        """Measures API latency and websocket heartbeat."""
        start_time = time.perf_counter()
        msg = await ctx.reply("🏓 Pinging...")
        end_time = time.perf_counter()

        api_latency = round((end_time - start_time) * 1000)
        ws_latency = round(self.bot.latency * 1000)

        embed = discord.Embed(
            title="🏓 Pong!",
            color=discord.Color.green(),
        )
        embed.add_field(name="Heartbeat (Websocket)", value=f"`{ws_latency} ms`", inline=True)
        embed.add_field(name="Roundtrip (API)", value=f"`{api_latency} ms`", inline=True)

        await msg.edit(content=None, embed=embed)

    @commands.hybrid_command(
        name="about",
        description="Information about this bot and its technology stack",
    )
    async def about_cmd(self, ctx: commands.Context):
        """Displays project description, version, and architecture information."""
        embed = discord.Embed(
            title="🤖 YouTube Subscription Verifier Bot",
            description=(
                "An open-source, production-grade Discord bot designed to automate role assignment "
                "by verifying YouTube channel subscriptions using computer vision (OpenCV) and "
                "Optical Character Recognition (Tesseract OCR)."
            ),
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="✨ Core Features",
            value=(
                "• Hybrid command system (Slash `/` & Prefix `!`)\n"
                "• Multi-stage image preprocessing (Adaptive threshold, contrast enhancement)\n"
                "• Multilingual OCR detection (Arabic, English, French, Spanish, German, etc.)\n"
                "• Anti-spoofing heuristic filters\n"
                "• Per-server configuration with zero database setup required"
            ),
            inline=False,
        )
        embed.add_field(name="📚 Framework", value="discord.py v2.x", inline=True)
        embed.add_field(name="👁️ OCR Engine", value="Tesseract & OpenCV", inline=True)
        embed.add_field(name="📄 License", value="MIT License", inline=True)
        embed.set_footer(text="Ready for publishing and open distribution.")

        await ctx.reply(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(GeneralCog(bot))

