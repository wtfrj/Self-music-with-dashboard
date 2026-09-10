import discord
from discord.ext import commands
import json
import os
import asyncio
from utils import log
import dashboard

# ─── Load Configuration ────────────────────────────────────────────────────────
try:
    with open('config.json', 'r') as f:
        config = json.load(f)
except FileNotFoundError:
    log("No config.json file found. Creating a default one. Please fill in your token.")
    config = {
        "token": "YOUR_TOKEN_HERE",
        "prefix": "$",
        "allowed": [],
        "dashboard_password": "admin",
        "dashboard_port": 5000,
        "dashboard_host": "0.0.0.0",
        "lavalink_uri": "http://lavalinkv4.subhan.com:80",
        "lavalink_password": "https://guns.lol/subhan.exe",
        "bot_status": "MADE BY wtfrj",
        "bot_status_type": "listening",
        "bot_activity_name": "MADE BY RJ",
        "max_queue_size": 100,
        "default_volume": 80,
        "auto_leave_empty": True,
        "auto_leave_timeout": 300,
        "search_results_limit": 5
    }
    with open('config.json', 'w') as f:
        json.dump(config, f, indent=4)
    exit(1)

TOKEN    = os.getenv("TOKEN")    or config.get("token")
PREFIX   = os.getenv("PREFIX")   or config.get("prefix", "$")
ALLOWED  = os.getenv("ALLOWED")  or config.get("allowed", [])
PORT     = int(os.getenv("DASHBOARD_PORT") or config.get("dashboard_port", 5000))
HOST     = os.getenv("DASHBOARD_HOST") or config.get("dashboard_host", "0.0.0.0")

# ─── Bot Class ─────────────────────────────────────────────────────────────────
# Using discord.py-self (selfbot library) — no Intents class, self_bot=True
class SelfMusicBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=PREFIX,
            self_bot=True
        )
        self.start_time = None
        self.songs_played = 0

    async def setup_hook(self):
        log("Loading cogs...")
        await self.load_extension('cogs.music')
        log("✅ Cogs loaded.")

        # Init dashboard
        dashboard.init_app(self)
        self.loop.create_task(
            dashboard.app.run_task(host=HOST, port=PORT)
        )
        log(f"✅ Dashboard running at http://127.0.0.1:{PORT}")

    async def on_ready(self):
        import time
        self.start_time = time.time()
        log(f"✅ Logged in as {self.user} (ID: {self.user.id})")

        # ── Set Bot Status to "MADE BY SUBHAN" ──────────────────────────────
        status_type_str = config.get("bot_status_type", "listening").lower()
        activity_name   = config.get("bot_activity_name", "🎵 Music | MADE BY SUBHAN")

        if status_type_str == "playing":
            activity = discord.Game(name=activity_name)
        elif status_type_str == "watching":
            activity = discord.Activity(type=discord.ActivityType.watching, name=activity_name)
        elif status_type_str == "competing":
            activity = discord.Activity(type=discord.ActivityType.competing, name=activity_name)
        else:  # default: listening
            activity = discord.Activity(type=discord.ActivityType.listening, name=activity_name)

        await self.change_presence(status=discord.Status.online, activity=activity)
        log(f"✅ Bot status set: {status_type_str.capitalize()} to '{activity_name}'")
        log("🎵 Self Music Bot is ready!")

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Missing argument: `{error.param.name}`")
            return
        if isinstance(error, commands.BadArgument):
            await ctx.send(f"❌ Bad argument: {error}")
            return
        log(f"Command error in '{ctx.command}': {error}")
        try:
            await ctx.send(f"❌ An error occurred: `{error}`")
        except Exception:
            pass

    async def on_command(self, ctx):
        log(f"CMD: '{ctx.message.content}' by {ctx.author} in {ctx.guild}/{ctx.channel}")

    async def on_message(self, message):
        await self.process_commands(message)

# ─── Run ───────────────────────────────────────────────────────────────────────
bot = SelfMusicBot()

if __name__ == "__main__":
    if not TOKEN or TOKEN == "YOUR_TOKEN_HERE":
        log("❌ Invalid token. Please set a valid token in config.json.")
    else:
        log("🚀 Starting Self Music Bot...")
        try:
            bot.run(TOKEN)
        except discord.LoginFailure:
            log("❌ Login failed. Invalid token.")
        except Exception as e:
            log(f"❌ Fatal error: {e}")
