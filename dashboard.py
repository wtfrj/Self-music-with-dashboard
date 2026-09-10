import os
import json
import asyncio
import time
from quart import Quart, render_template, request, redirect, url_for, session, websocket
from quart_cors import cors
import wavelink
import discord

app = Quart(__name__)
app = cors(app, allow_origin="*")
app.secret_key = os.urandom(32).hex()

connected_websockets: set = set()
bot_instance = None
_start_time: float = 0.0


# ─── Init ──────────────────────────────────────────────────────────────────────
def init_app(bot):
    global bot_instance, _start_time
    bot_instance = bot
    _start_time = time.time()


def get_config():
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def is_authenticated():
    return session.get('authenticated', False)


# ─── Routes ────────────────────────────────────────────────────────────────────
@app.route('/')
async def index():
    if not is_authenticated():
        return redirect(url_for('login'))
    return await render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
async def login():
    if request.method == 'POST':
        form = await request.form
        password = form.get('password', '')
        config = get_config()
        if password == config.get('dashboard_password', 'admin'):
            session['authenticated'] = True
            return redirect(url_for('index'))
        return await render_template('login.html', error="Invalid password. Try again.")
    return await render_template('login.html', error=None)


@app.route('/logout')
async def logout():
    session.pop('authenticated', None)
    return redirect(url_for('login'))


@app.route('/api/stats')
async def api_stats():
    if not is_authenticated():
        return {"error": "Unauthorized"}, 401
    if not bot_instance:
        return {"error": "Bot not ready"}, 503
    uptime_sec = int(time.time() - _start_time) if _start_time else 0
    h, rem = divmod(uptime_sec, 3600)
    m, s = divmod(rem, 60)
    return {
        "uptime": f"{h:02d}:{m:02d}:{s:02d}",
        "guilds": len(bot_instance.guilds),
        "voice_connections": len(bot_instance.voice_clients),
        "songs_played": getattr(bot_instance, 'songs_played', 0),
        "ping": round(bot_instance.latency * 1000, 1),
        "ws_clients": len(connected_websockets),
    }


# ─── WebSocket ─────────────────────────────────────────────────────────────────
@app.websocket('/ws')
async def ws():
    if not is_authenticated():
        await websocket.accept()
        await websocket.send(json.dumps({"type": "error", "message": "Unauthorized"}))
        await websocket.close(1008)
        return

    await websocket.accept()
    ws_obj = websocket._get_current_object()
    connected_websockets.add(ws_obj)

    # Send initial full state
    await send_initial_state(ws_obj)

    # Start position ticker task
    ticker_task = asyncio.create_task(_position_ticker(ws_obj))

    try:
        while True:
            data = await websocket.receive()
            await handle_ws_message(data, ws_obj)
    except asyncio.CancelledError:
        pass
    except Exception:
        pass
    finally:
        ticker_task.cancel()
        connected_websockets.discard(ws_obj)


async def _position_ticker(ws_obj):
    """Send position update every second so frontend progress bar stays in sync."""
    while True:
        await asyncio.sleep(1)
        try:
            if not bot_instance:
                continue
            for vc in bot_instance.voice_clients:
                if isinstance(vc, wavelink.Player) and vc.current:
                    paused = getattr(vc, 'paused', False)
                    if callable(paused):
                        paused = paused()
                    await ws_obj.send(json.dumps({
                        "type": "position_update",
                        "position": vc.position,
                        "length": vc.current.length,
                        "is_paused": paused,
                        "is_playing": vc.playing,
                    }))
                    break
        except Exception:
            break


# ─── State Builder ─────────────────────────────────────────────────────────────
async def send_initial_state(ws_obj):
    if not bot_instance:
        return

    is_playing  = False
    is_paused   = False
    track_info  = None
    server_info = None
    queue_info  = []
    loop_mode   = "none"
    volume      = 100

    try:
        all_servers = [
            {
                "name": g.name,
                "id": str(g.id),
                "icon": str(g.icon.url) if getattr(g, 'icon', None) and g.icon else None,
                "member_count": g.member_count,
                "channels": _get_voice_channels(g),
            }
            for g in bot_instance.guilds
        ]
    except Exception:
        all_servers = []

    for vc in bot_instance.voice_clients:
        if isinstance(vc, wavelink.Player):
            paused = getattr(vc, 'paused', False)
            if callable(paused):
                paused = paused()
            is_paused = paused

            volume = getattr(vc, 'volume', 100)

            # Loop mode
            mode = getattr(vc.queue, 'mode', None)
            if mode == wavelink.QueueMode.loop:
                loop_mode = "loop"
            elif mode == wavelink.QueueMode.loop_all:
                loop_mode = "loop_all"
            else:
                loop_mode = "none"

            if vc.current:
                is_playing = True
                track_info = {
                    "title":     vc.current.title,
                    "author":    vc.current.author,
                    "uri":       vc.current.uri,
                    "thumbnail": str(vc.current.artwork) if vc.current.artwork else None,
                    "length":    vc.current.length,
                    "position":  vc.position,
                }
                server_info = {
                    "name": vc.guild.name,
                    "id":   str(vc.guild.id),
                    "icon": str(vc.guild.icon.url) if vc.guild.icon else None,
                    "channel": vc.channel.name if vc.channel else "Unknown",
                }
                for track in vc.queue:
                    queue_info.append({
                        "title":     track.title,
                        "author":    track.author,
                        "length":    track.length,
                        "uri":       track.uri,
                        "thumbnail": str(track.artwork) if track.artwork else None,
                    })
            break

    user_data = None
    if bot_instance.user:
        av = bot_instance.user.display_avatar
        user_data = {
            "name":   bot_instance.user.name,
            "id":     str(bot_instance.user.id),
            "avatar": str(av.url) if av else None,
        }

    try:
        await ws_obj.send(json.dumps({
            "type":       "state_update",
            "is_playing": is_playing,
            "is_paused":  is_paused,
            "track":      track_info,
            "server":     server_info,
            "queue":      queue_info,
            "all_servers": all_servers,
            "user":       user_data,
            "loop_mode":  loop_mode,
            "volume":     volume,
        }))
    except Exception as e:
        connected_websockets.discard(ws_obj)


def _get_voice_channels(guild):
    channels = []
    for ch in guild.channels:
        # discord.py-self may not have StageChannel, use hasattr check
        is_vc = isinstance(ch, discord.VoiceChannel)
        is_stage = hasattr(discord, 'StageChannel') and isinstance(ch, discord.StageChannel)
        if is_vc or is_stage:
            channels.append({"id": str(ch.id), "name": ch.name, "members": len(ch.members)})
    return channels


# ─── Broadcast Helpers ─────────────────────────────────────────────────────────
async def broadcast(message: dict):
    dead = set()
    for ws_obj in connected_websockets.copy():
        try:
            await ws_obj.send(json.dumps(message))
        except Exception:
            dead.add(ws_obj)
    connected_websockets.difference_update(dead)


async def broadcast_state():
    for ws_obj in connected_websockets.copy():
        await send_initial_state(ws_obj)


# ─── WebSocket Message Handler ─────────────────────────────────────────────────
async def handle_ws_message(data_str: str, ws_obj=None):
    if not bot_instance:
        if ws_obj:
            await ws_obj.send(json.dumps({"type": "error", "message": "Bot not ready yet."}))
        return

    try:
        data   = json.loads(data_str)
        action = data.get('action')
    except json.JSONDecodeError:
        if ws_obj:
            await ws_obj.send(json.dumps({"type": "error", "message": "Invalid JSON."}))
        return

    # Helper: get active voice player
    vc: wavelink.Player | None = None
    if bot_instance.voice_clients:
        vc = bot_instance.voice_clients[0]

    # ── play ──────────────────────────────────────────────────────────────────
    if action == "play":
        query      = data.get("query", "").strip()
        guild_id   = data.get("guild_id")
        channel_id = data.get("channel_id")

        if not query:
            if ws_obj:
                await ws_obj.send(json.dumps({"type": "error", "message": "No query provided."}))
            return

        # If no vc, try to connect
        if not vc and guild_id and channel_id:
            try:
                guild   = bot_instance.get_guild(int(guild_id))
                channel = guild.get_channel(int(channel_id)) if guild else None
                if channel:
                    vc = await channel.connect(cls=wavelink.Player)
            except Exception as e:
                if ws_obj:
                    await ws_obj.send(json.dumps({"type": "error", "message": f"Could not connect to VC: {e}"}))
                return

        if not vc:
            if ws_obj:
                await ws_obj.send(json.dumps({"type": "error", "message": "Bot is not in a voice channel. Join a VC first."}))
            return

        try:
            tracks = await wavelink.Playable.search(query)
            if not tracks:
                if ws_obj:
                    await ws_obj.send(json.dumps({"type": "error", "message": f"No results found for: {query}"}))
                return
            track = tracks[0]
            await vc.queue.put_wait(track)
            if not vc.playing:
                await vc.play(vc.queue.get())
            if ws_obj:
                await ws_obj.send(json.dumps({"type": "notification", "level": "success", "message": f"▶ Playing: {track.title}"}))
            await broadcast_state()
        except Exception as e:
            if ws_obj:
                await ws_obj.send(json.dumps({"type": "error", "message": f"Search/play error: {e}"}))

    # ── skip ──────────────────────────────────────────────────────────────────
    elif action == "skip":
        if not vc or not vc.playing:
            if ws_obj:
                await ws_obj.send(json.dumps({"type": "error", "message": "Nothing is playing to skip."}))
            return
        await vc.skip(force=True)
        if ws_obj:
            await ws_obj.send(json.dumps({"type": "notification", "level": "info", "message": "⏭ Skipped!"}))
        await broadcast_state()

    # ── stop ──────────────────────────────────────────────────────────────────
    elif action == "stop":
        if not vc:
            if ws_obj:
                await ws_obj.send(json.dumps({"type": "error", "message": "Bot is not connected."}))
            return
        vc.queue.clear()
        await vc.disconnect()
        if ws_obj:
            await ws_obj.send(json.dumps({"type": "notification", "level": "info", "message": "⏹ Stopped and disconnected."}))
        await broadcast_state()

    # ── play_pause ────────────────────────────────────────────────────────────
    elif action == "play_pause":
        if not vc or not vc.current:
            if ws_obj:
                await ws_obj.send(json.dumps({"type": "error", "message": "Nothing is playing."}))
            return
        paused = getattr(vc, 'paused', False)
        if callable(paused):
            paused = paused()
        if paused:
            await vc.pause(False)
            msg = "▶ Resumed"
        else:
            await vc.pause(True)
            msg = "⏸ Paused"
        if ws_obj:
            await ws_obj.send(json.dumps({"type": "notification", "level": "info", "message": msg}))
        await broadcast_state()

    # ── volume ────────────────────────────────────────────────────────────────
    elif action == "volume":
        if not vc:
            if ws_obj:
                await ws_obj.send(json.dumps({"type": "error", "message": "Bot is not connected."}))
            return
        vol = int(data.get("value", 80))
        vol = max(0, min(100, vol))
        await vc.set_volume(vol)
        await broadcast_state()

    # ── loop ──────────────────────────────────────────────────────────────────
    elif action == "loop":
        if not vc:
            if ws_obj:
                await ws_obj.send(json.dumps({"type": "error", "message": "Bot is not connected."}))
            return
        if vc.queue.mode == wavelink.QueueMode.loop:
            vc.queue.mode = wavelink.QueueMode.normal
            state = "disabled"
        else:
            vc.queue.mode = wavelink.QueueMode.loop
            state = "enabled"
        if ws_obj:
            await ws_obj.send(json.dumps({"type": "notification", "level": "info", "message": f"🔁 Loop {state}"}))
        await broadcast_state()

    # ── remove_from_queue ─────────────────────────────────────────────────────
    elif action == "remove_queue":
        if not vc:
            return
        index = int(data.get("index", -1))
        try:
            track = vc.queue[index]
            del vc.queue[index]
            if ws_obj:
                await ws_obj.send(json.dumps({"type": "notification", "level": "info", "message": f"🗑 Removed: {track.title}"}))
            await broadcast_state()
        except (IndexError, Exception) as e:
            if ws_obj:
                await ws_obj.send(json.dumps({"type": "error", "message": f"Remove error: {e}"}))

    # ── clear_queue ───────────────────────────────────────────────────────────
    elif action == "clear_queue":
        if not vc:
            return
        vc.queue.clear()
        if ws_obj:
            await ws_obj.send(json.dumps({"type": "notification", "level": "info", "message": "🗑 Queue cleared."}))
        await broadcast_state()

    # ── join_vc ───────────────────────────────────────────────────────────────
    elif action == "join_vc":
        channel_id = data.get("channel_id", "").strip()
        guild_id   = data.get("guild_id", "").strip()

        target_channel = None
        if channel_id:
            try:
                target_channel = bot_instance.get_channel(int(channel_id))
            except (ValueError, Exception):
                pass
        elif guild_id:
            # Find any vc in that guild
            guild = bot_instance.get_guild(int(guild_id))
            if guild:
                for ch in guild.channels:
                    if isinstance(ch, discord.VoiceChannel):
                        target_channel = ch
                        break

        if not target_channel:
            if ws_obj:
                await ws_obj.send(json.dumps({"type": "error", "message": "Voice channel not found."}))
            return

        try:
            if vc:
                await vc.move_to(target_channel)
            else:
                vc = await target_channel.connect(cls=wavelink.Player)
            if ws_obj:
                await ws_obj.send(json.dumps({"type": "notification", "level": "success", "message": f"✅ Joined: {target_channel.name}"}))
            await broadcast_state()
        except Exception as e:
            if ws_obj:
                await ws_obj.send(json.dumps({"type": "error", "message": f"Could not join VC: {e}"}))

    # -- join_server
    elif action == "join_server":
        invite_url = data.get("invite_url", "").strip()
        if not invite_url:
            if ws_obj:
                await ws_obj.send(json.dumps({"type": "error", "message": "No invite URL provided."}))
            return

        # Extract invite code from full URLs like:
        # https://discord.gg/abc123
        # https://discord.com/invite/abc123
        import re
        match = re.search(r'discord(?:\.gg|(?:\.com)?/invite)/([\\w-]+)', invite_url, re.IGNORECASE)
        invite_code = match.group(1) if match else invite_url.strip('/')

        try:
            invite = await bot_instance.fetch_invite(invite_code)
            await bot_instance.accept_invite(invite)
            guild_name = invite.guild.name if invite.guild else "Unknown Server"
            if ws_obj:
                await ws_obj.send(json.dumps({"type": "notification", "level": "success", "message": f"Joined server: {guild_name}"}))
            await asyncio.sleep(1.5)
            await broadcast_state()
        except discord.NotFound:
            if ws_obj:
                await ws_obj.send(json.dumps({"type": "error", "message": "Invalid or expired invite link. Please check the URL."}))
        except discord.Forbidden:
            if ws_obj:
                await ws_obj.send(json.dumps({"type": "error", "message": "Cannot join this server. Invite may be restricted."}))
        except discord.HTTPException as e:
            if ws_obj:
                await ws_obj.send(json.dumps({"type": "error", "message": f"HTTP Error {e.status}: {e.text}"}))
        except Exception as e:
            if ws_obj:
                await ws_obj.send(json.dumps({"type": "error", "message": f"Join server error: {e}"}))

    # ── get_search_results ────────────────────────────────────────────────────
    elif action == "search":
        query = data.get("query", "").strip()
        if not query:
            return
        try:
            config  = get_config()
            limit   = config.get("search_results_limit", 5)
            tracks  = await wavelink.Playable.search(query)
            results = []
            for t in tracks[:limit]:
                results.append({
                    "title":     t.title,
                    "author":    t.author,
                    "uri":       t.uri,
                    "length":    t.length,
                    "thumbnail": str(t.artwork) if t.artwork else None,
                })
            if ws_obj:
                await ws_obj.send(json.dumps({"type": "search_results", "results": results}))
        except Exception as e:
            if ws_obj:
                await ws_obj.send(json.dumps({"type": "error", "message": f"Search error: {e}"}))

    else:
        if ws_obj:
            await ws_obj.send(json.dumps({"type": "error", "message": f"Unknown action: {action}"}))
