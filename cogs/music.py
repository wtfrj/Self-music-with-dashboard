import discord
from discord.ext import commands
import wavelink
import asyncio
import json
import time
from utils import log

def get_config():
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except Exception:
        return {}

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = get_config()

    async def cog_load(self):
        lavalink_uri  = self.config.get("lavalink_uri",      "http://lavalinkv4.serenetia.com:80")
        lavalink_pass = self.config.get("lavalink_password",  "https://seretia.link/discord")
        nodes = [wavelink.Node(uri=lavalink_uri, password=lavalink_pass)]
        await wavelink.Pool.connect(nodes=nodes, client=self.bot, cache_capacity=100)
        log("✅ Connected to Lavalink node.")

    # ── Wavelink Events ──────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        log(f"✅ Wavelink Node ready: {payload.node.identifier}")

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload):
        if hasattr(self.bot, 'songs_played'):
            self.bot.songs_played += 1
        await self._broadcast_state()

        # Send now-playing notification to dashboard
        import dashboard
        await dashboard.broadcast({
            "type": "notification",
            "level": "success",
            "message": f"▶ Now Playing: {payload.track.title}"
        })

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        player = payload.player
        if player and not player.queue.is_empty:
            next_track = player.queue.get()
            await player.play(next_track)
            log(f"▶ Auto-playing next: {next_track.title}")
        await self._broadcast_state()

    @commands.Cog.listener()
    async def on_wavelink_inactive_player(self, player: wavelink.Player):
        """Auto-leave when player is inactive."""
        config = get_config()
        if config.get("auto_leave_empty", True):
            timeout = config.get("auto_leave_timeout", 300)
            await asyncio.sleep(timeout)
            if not player.playing:
                await player.disconnect()
                log("⏹ Auto-disconnected (inactive).")
                await self._broadcast_state()

    async def _broadcast_state(self):
        """Helper: broadcast full state to all WS clients."""
        import dashboard
        for ws in dashboard.connected_websockets.copy():
            try:
                await dashboard.send_initial_state(ws)
            except Exception as e:
                log(f"WS broadcast error: {e}")

    # ── Helpers ──────────────────────────────────────────────────────────────
    async def _get_player(self, ctx) -> wavelink.Player | None:
        """Get or create a player for the author's VC."""
        voice = getattr(ctx.author, 'voice', None)
        channel = getattr(voice, 'channel', None) if voice else None
        if not channel:
            await ctx.send("❌ You are not in a voice channel.")
            return None
        if ctx.voice_client:
            return ctx.voice_client
        try:
            return await channel.connect(cls=wavelink.Player)
        except Exception as e:
            await ctx.send(f"❌ Could not join voice channel: `{e}`")
            return None

    # ── Commands ─────────────────────────────────────────────────────────────
    @commands.command(aliases=['j'])
    async def join(self, ctx):
        """Join the author's voice channel."""
        voice = getattr(ctx.author, 'voice', None)
        channel = getattr(voice, 'channel', None) if voice else None
        if not channel:
            return await ctx.send("❌ You are not in a voice channel.")
        try:
            if ctx.voice_client:
                await ctx.voice_client.move_to(channel)
                await ctx.send(f"↪ Moved to **{channel.name}**")
            else:
                await channel.connect(cls=wavelink.Player)
                await ctx.send(f"✅ Joined **{channel.name}**")
            await self._broadcast_state()
        except Exception as e:
            await ctx.send(f"❌ Error joining channel: `{e}`")

    @commands.command(aliases=['p'])
    async def play(self, ctx: commands.Context, *, query: str):
        """Play a song by name or URL."""
        vc = await self._get_player(ctx)
        if not vc:
            return

        async with ctx.typing():
            try:
                tracks: wavelink.Search = await wavelink.Playable.search(query)
                if not tracks:
                    return await ctx.send("❌ No results found. Try a different query.")

                track: wavelink.Playable = tracks[0]

                config = get_config()
                max_q = config.get("max_queue_size", 100)
                if vc.queue.count >= max_q:
                    return await ctx.send(f"❌ Queue is full! (max {max_q} songs)")

                await vc.queue.put_wait(track)

                if not vc.playing:
                    await vc.play(vc.queue.get())
                    await ctx.send(f"▶ **Now Playing:** {track.title}")
                else:
                    await ctx.send(f"✅ **Added to queue:** {track.title} (position {vc.queue.count})")

                log(f"▶ Play: {track.title}")
            except wavelink.LavalinkLoadException as e:
                await ctx.send(f"❌ Lavalink error: `{e}`")
            except Exception as e:
                log(f"Play error: {e}")
                await ctx.send(f"❌ Error: `{e}`")

    @commands.command(aliases=['s'])
    async def stop(self, ctx: commands.Context):
        """Stop music and disconnect."""
        if not ctx.voice_client:
            return await ctx.send("❌ Not connected to a voice channel.")
        vc: wavelink.Player = ctx.voice_client
        vc.queue.clear()
        await vc.disconnect()
        await ctx.send("⏹ Stopped and disconnected.")
        log("⏹ Stopped.")
        await self._broadcast_state()

    @commands.command(aliases=['sk'])
    async def skip(self, ctx: commands.Context):
        """Skip the current song."""
        if not ctx.voice_client:
            return await ctx.send("❌ Not connected.")
        vc: wavelink.Player = ctx.voice_client
        if not vc.playing:
            return await ctx.send("❌ Nothing is playing.")
        await vc.skip(force=True)
        await ctx.send("⏭ Skipped!")
        log("⏭ Skipped.")

    @commands.command(aliases=['pa'])
    async def pause(self, ctx: commands.Context):
        """Pause the current song."""
        if not ctx.voice_client:
            return await ctx.send("❌ Not connected.")
        vc: wavelink.Player = ctx.voice_client
        if not vc.playing:
            return await ctx.send("❌ Nothing is playing.")
        await vc.pause(True)
        await ctx.send("⏸ Paused.")
        await self._broadcast_state()

    @commands.command(aliases=['r', 'res'])
    async def resume(self, ctx: commands.Context):
        """Resume the paused song."""
        if not ctx.voice_client:
            return await ctx.send("❌ Not connected.")
        vc: wavelink.Player = ctx.voice_client
        await vc.pause(False)
        await ctx.send("▶ Resumed.")
        await self._broadcast_state()

    @commands.command(aliases=['q'])
    async def queue(self, ctx: commands.Context):
        """Show the current queue."""
        if not ctx.voice_client:
            return await ctx.send("❌ Not connected.")
        vc: wavelink.Player = ctx.voice_client
        if vc.queue.is_empty and not vc.playing:
            return await ctx.send("📭 Queue is empty.")
        msg = "**🎵 Current Queue:**\n"
        if vc.current:
            msg += f"**▶ Now Playing:** {vc.current.title}\n\n"
        for i, track in enumerate(vc.queue):
            msg += f"{i+1}. {track.title}\n"
            if i >= 9:
                msg += f"...and {vc.queue.count - 10} more."
                break
        await ctx.send(msg)

    @commands.command(aliases=['l'])
    async def loop(self, ctx: commands.Context):
        """Toggle loop mode."""
        if not ctx.voice_client:
            return await ctx.send("❌ Not connected.")
        vc: wavelink.Player = ctx.voice_client
        if vc.queue.mode == wavelink.QueueMode.loop:
            vc.queue.mode = wavelink.QueueMode.normal
            state = "disabled 🔁"
        else:
            vc.queue.mode = wavelink.QueueMode.loop
            state = "enabled 🔂"
        await ctx.send(f"Loop is now **{state}**.")
        log(f"Loop {state}")
        await self._broadcast_state()

    @commands.command(aliases=['v', 'vol'])
    async def volume(self, ctx: commands.Context, vol: int):
        """Set volume (0-100)."""
        if not ctx.voice_client:
            return await ctx.send("❌ Not connected.")
        if not 0 <= vol <= 100:
            return await ctx.send("❌ Volume must be between 0 and 100.")
        vc: wavelink.Player = ctx.voice_client
        await vc.set_volume(vol)
        await ctx.send(f"🔊 Volume set to **{vol}%**")
        log(f"Volume set to {vol}%")
        await self._broadcast_state()

    @commands.command(aliases=['c'])
    async def clear(self, ctx: commands.Context):
        """Clear the queue."""
        if not ctx.voice_client:
            return await ctx.send("❌ Not connected.")
        vc: wavelink.Player = ctx.voice_client
        vc.queue.clear()
        await ctx.send("🗑 Queue cleared.")
        log("Queue cleared.")
        await self._broadcast_state()

    @commands.command(aliases=['np', 'now'])
    async def nowplaying(self, ctx: commands.Context):
        """Show the currently playing song."""
        if not ctx.voice_client:
            return await ctx.send("❌ Not connected.")
        vc: wavelink.Player = ctx.voice_client
        if not vc.current:
            return await ctx.send("❌ Nothing is playing.")
        track = vc.current
        pos = vc.position
        length = track.length
        bar_len = 20
        filled = int((pos / length) * bar_len) if length > 0 else 0
        bar = "█" * filled + "░" * (bar_len - filled)
        def fmt(ms):
            s = ms // 1000; return f"{s//60}:{s%60:02d}"
        msg = (
            f"**▶ Now Playing**\n"
            f"🎵 **{track.title}** by *{track.author}*\n"
            f"`[{bar}]` {fmt(pos)} / {fmt(length)}\n"
            f"🔗 {track.uri}"
        )
        await ctx.send(msg)

async def setup(bot):
    await bot.add_cog(Music(bot))
