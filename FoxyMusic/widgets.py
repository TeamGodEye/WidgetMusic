# Telegram HTML widget support for FoxyMusic private chats.
# Widgets are served through the official Bot API; music operations reuse
# the existing FoxyMusic playback engine and its authorization rules.

import asyncio
import json
import logging
import random
import zlib

import aiohttp
from pyrogram.enums import ChatMemberStatus

import config

_LOG = logging.getLogger("FoxyMusic.widgets")
_API = "https://api.telegram.org/bot{}/{}"
_POLL_TASK = None
_STOP = asyncio.Event()

from FoxyMusic.core.mongo import mongodb
_widget_preferences = mongodb.widget_preferences
_widget_searches = mongodb.widget_searches

WIDGET_HTML = r"""
<style>
:root{color-scheme:light dark}
*{box-sizing:border-box}body{margin:0;font:14px system-ui,sans-serif;color:var(--tg-theme-text-color);background:var(--tg-theme-bg-color)}
.wrap{padding:12px;display:grid;gap:10px}.top{display:flex;align-items:center;justify-content:space-between}
.brand{font-weight:800;letter-spacing:1.5px;font-size:18px}.muted{color:var(--tg-theme-hint-color);font-size:12px}
.card{background:var(--tg-theme-secondary-bg-color);border-radius:14px;padding:12px;display:grid;gap:8px}
.title{font-weight:700;font-size:15px}.row{display:flex;gap:8px;align-items:center}.row>*{flex:1}
button{border:0;border-radius:10px;padding:10px 8px;background:var(--tg-theme-button-color);color:var(--tg-theme-button-text-color);font:600 13px system-ui;min-height:38px}
button.alt{background:var(--tg-theme-secondary-bg-color);color:var(--tg-theme-text-color);border:1px solid var(--tg-theme-section-separator-color)}
button.danger{background:var(--tg-theme-destructive-text-color);color:#fff}
.item{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:8px 0;border-bottom:1px solid var(--tg-theme-section-separator-color)}
.item:last-child{border:0}.name{min-width:0;overflow:hidden;text-overflow:ellipsis}
.small{font-size:11px;color:var(--tg-theme-hint-color)}.status{font-size:12px;color:var(--tg-theme-accent-text-color)}
#toast{min-height:16px;text-align:center;color:var(--tg-theme-hint-color);font-size:12px}
</style>
<div class="wrap">
 <div class="top"><div><div class="brand">FOXY MUSIC</div><div class="muted">PRIVATE MUSIC CONTROL CENTER</div></div><button class="alt" data-a="refresh">↻</button></div>
 <div class="card"><div class="row"><div><div class="muted">CONNECTED GROUP</div><div class="title" id="gname">Choose a group</div></div><button class="alt" data-a="groups">Switch</button></div><div class="status" id="status">Loading your music rooms…</div></div>
 <div class="card" id="player"><div class="muted">NOW PLAYING</div><div class="title" id="song">Nothing is playing</div><div class="small" id="meta">Select an active group to view playback</div><div class="row"><button data-a="pause">Ⅱ Pause</button><button data-a="resume">▶ Resume</button><button class="danger" data-a="stop">■ Stop</button></div><div class="row"><button class="alt" data-a="next">⏭ Next</button><button class="alt" data-a="shuffle">⇄ Shuffle</button></div></div>
 <div class="card"><div class="title">YOUR MUSIC GROUPS</div><div id="groups"></div><div class="row" id="groupnav"><button class="alt" data-a="gprev">‹ Previous</button><button class="alt" data-a="gnext">Next ›</button></div></div>
 <div class="card" id="searchcard"><div class="title">SEARCH RESULTS</div><div id="search"></div></div>
 <div class="card" id="infocard"><div class="muted">TRACK INFORMATION</div><div class="title" id="infotitle"></div><div class="small" id="infoduration"></div><button class="alt" data-a="openvideo">Open on YouTube</button></div>
 <div class="card"><div class="top"><div class="title">UP NEXT</div><button class="alt" data-a="queue">Refresh</button></div><div id="queue" class="small">Queue is empty</div></div>
 <div class="card"><div class="title">PLAYBACK OPTIONS</div><div class="row"><button class="alt" data-a="loop">Loop: <span id="loop">Off</span></button><button class="alt" data-a="autoplay">Autoplay: <span id="autoplay">Off</span></button></div><div class="row"><button class="alt" data-a="bass">Bass</button><button class="alt" data-a="echo">Echo</button><button class="alt" data-a="nightcore">Nightcore</button><button class="alt" data-a="slowed">Slowed</button><button class="alt" data-a="normal">Normal</button></div></div>
 <div class="row"><button class="alt" data-a="help">Help</button><button class="alt" data-a="groups">My Groups</button></div>
 <div id="toast"></div>
</div>
<script>
(function(){
 const W=window.TelegramWidget;let state={groups:[],selected:null,queue:[],page:"home"};
 const $=id=>document.getElementById(id);
 function parse(v){try{return JSON.parse(v||"{}")}catch(e){return {}}}
 function text(id,v){$(id).textContent=v||""}
 function draw(){
  const g=state.current||(state.groups||[]).find(x=>String(x.id)===String(state.selected));
  text("gname",g?g.title:"Choose a group");
  text("status",state.message|| (g?(g.active?"Music session active":"No active music session"):"Choose one of your active music groups"));
  text("song",g&&g.song?g.song:"Nothing is playing");
  text("meta",g&&g.by?("Requested by "+g.by):"FoxyMusic private controller");
  text("loop",g&&g.loop?"On":"Off");text("autoplay",g&&g.autoplay?"On":"Off");
  const gl=$("groups");gl.textContent="";
  (state.groups||[]).forEach(x=>{const b=document.createElement("button");b.className="alt";b.textContent=(String(x.id)===String(state.selected)?"✓ ":"")+x.title;b.addEventListener("click",()=>request("select:"+x.id));gl.appendChild(b);b.style.margin="3px";});
  const nav=$("groupnav");nav.style.display=(state.group_pages||1)>1?"flex":"none";
  nav.children[0].disabled=(state.group_page||0)<=0;
  nav.children[1].disabled=(state.group_page||0)>=(state.group_pages||1)-1;
  const sr=$("search");sr.textContent="";
  (state.search||[]).forEach(x=>{const d=document.createElement("div");d.className="item";const n=document.createElement("span");n.className="name";n.textContent=x.title+" · "+(x.duration||"");const b=document.createElement("button");b.textContent="Play";b.addEventListener("click",()=>request("play:"+x.id));d.appendChild(n);d.appendChild(b);sr.appendChild(d)});
  $("searchcard").style.display=(state.search&&state.search.length)?"grid":"none";
  $("infocard").style.display=state.info?"grid":"none";
  if(state.info){text("infotitle",state.info.title);text("infoduration",state.info.duration||"");}
  const q=$("queue");q.textContent="";
  if(!g||!g.queue||!g.queue.length){q.textContent="Queue is empty";return}
  g.queue.forEach((v,i)=>{const d=document.createElement("div");d.className="item";const n=document.createElement("span");n.className="name";n.textContent=(i===0?"▶ ":"")+v;d.appendChild(n);q.appendChild(d)});
 }
 function toast(s){text("toast",s||"")}
 function request(action){
  if(!W||!W.request){toast("Widget requests are not available in this Telegram client.");return}
  W.request(action).then(r=>{if(r&&r.result)toast(r.result)}).catch(e=>toast("Request failed: "+(e.code||e.name||"unknown")));
 }
 document.addEventListener("click",function(e){
  const b=e.target.closest("button[data-a]");if(!b)return;
  const a=b.dataset.a;const g=state.selected;
  if(a==="openvideo"){if(state.info&&state.info.url&&W&&W.openLink)W.openLink(state.info.url);return}
  if(a==="gprev"){request("gpage:"+Math.max(0,(state.group_page||0)-1));return}
  if(a==="gnext"){request("gpage:"+((state.group_page||0)+1));return}
  if(a==="groups"){request("groups");return}
  if(a==="help"||a==="refresh"){request(a+(g?":"+g:""));return}
  if(!g){toast("Select an active group first.");request("groups");return}
  request(a+":"+g);
 });
 W.onEvent("chatDataChanged",function(){state=parse(W.chatData);draw()});
 state=parse(W.chatData);draw();
 if(W&&W.request){W.request("refresh").then(r=>{if(r&&r.result){state=parse(r.result);draw()}}).catch(()=>{})}
})();
</script>
"""


def _compact_state(state):
    state = dict(state or {})
    state["groups"] = list(state.get("groups", []))[:4]
    state["current"] = dict(state.get("current") or {}) if state.get("current") else None
    state["search"] = list(state.get("search", []))[:4]
    state["message"] = str(state.get("message", ""))[:90]
    for group in state["groups"]:
        group["title"] = str(group.get("title", ""))[:42]
    for track in state["search"]:
        track["title"] = str(track.get("title", ""))[:48]
        track["duration"] = str(track.get("duration", ""))[:10]
    if state["current"]:
        state["current"]["title"] = str(state["current"].get("title", ""))[:42]
        state["current"]["song"] = str(state["current"].get("song", ""))[:52]
        state["current"]["by"] = str(state["current"].get("by", ""))[:20]
        state["current"]["queue"] = [str(x)[:48] for x in list(state["current"].get("queue", []))[:4]]
    raw = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    if len(raw.encode("utf-8")) <= 1024:
        return raw
    state["groups"] = state["groups"][:2]
    state["search"] = state["search"][:2]
    for group in state["groups"]:
        group["queue"] = group.get("queue", [])[:1]
    raw = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    if len(raw.encode("utf-8")) > 1024:
        current = state.get("current")
        minimal_current = None
        if current:
            minimal_current = {
                "id": current.get("id"),
                "title": str(current.get("title", ""))[:28],
                "song": str(current.get("song", ""))[:32],
                "active": bool(current.get("active")),
                "loop": bool(current.get("loop")),
                "autoplay": bool(current.get("autoplay")),
                "queue": [],
            }
        state = {
            "groups": [
                {"id": item.get("id"), "title": str(item.get("title", ""))[:28]}
                for item in state.get("groups", [])[:3]
            ],
            "current": minimal_current,
            "selected": state.get("selected"),
            "group_page": state.get("group_page", 0),
            "group_pages": state.get("group_pages", 1),
            "message": "Some details hidden. Refresh for current status.",
        }
        raw = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    return raw


async def _api(method, payload=None, session=None, timeout=20):
    if not config.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not configured")
    own = session is None
    session = session or aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=timeout)
    )
    try:
        async with session.post(
            _API.format(config.BOT_TOKEN, method),
            json=payload or {},
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as response:
            data = await response.json(content_type=None)
            if response.status != 200 or not data.get("ok"):
                raise RuntimeError(data.get("description", f"Telegram API HTTP {response.status}"))
            return data.get("result")
    finally:
        if own:
            await session.close()


async def send_music_widget(chat_id, reply_to_message_id=None, state_override=None):
    """Send the private interactive player dashboard."""
    from FoxyMusic import app

    if state_override is None:
        pref = await _widget_preferences.find_one({"user_id": int(chat_id)})
        selected = pref.get("selected_chat_id") if pref else None
        page = pref.get("group_page", 0) if pref else 0
        state = await _build_state(int(chat_id), selected, page)
    else:
        state = state_override
    payload = {
        "chat_id": int(chat_id),
        "html": WIDGET_HTML,
        "caption": "🎵 FoxyMusic — your private music control center",
        "chat_data": _compact_state(state),
        "allow_queries": True,
        "width": 0,
        "height": 0,
        "protect_content": True,
    }
    if reply_to_message_id:
        payload["reply_parameters"] = {"message_id": int(reply_to_message_id)}
    try:
        return await _api("sendWidget", payload)
    except Exception as exc:
        _LOG.warning("sendWidget unavailable; using text fallback: %s", exc)
        fallback = (
            "🎵 <b>FoxyMusic Private Player</b>\n\n"
            "The interactive widget is temporarily unavailable in this Telegram client.\n"
            "You can still use music commands in your groups, or try /player again later."
        )
        return await app.send_message(
            int(chat_id),
            fallback,
            reply_to_message_id=int(reply_to_message_id) if reply_to_message_id else None,
        )


async def send_track_info_widget(chat_id, video_id, reply_to_message_id=None):
    from FoxyMusic import YouTube

    details, _track_id = await YouTube.track(str(video_id), True)
    if not details:
        raise RuntimeError("Track information is unavailable.")
    pref = await _widget_preferences.find_one({"user_id": int(chat_id)})
    selected = pref.get("selected_chat_id") if pref else None
    page = pref.get("group_page", 0) if pref else 0
    state = await _build_state(int(chat_id), selected, page)
    state["info"] = {
        "title": str(details.get("title") or "Unknown track")[:100],
        "duration": str(details.get("duration_min") or ""),
        "url": str(details.get("link") or ""),
    }
    state["message"] = "Track information"
    return await send_music_widget(
        chat_id, reply_to_message_id, state_override=state
    )


async def _is_allowed(user_id, chat_id, served_ids=None):
    from FoxyMusic import app
    from FoxyMusic.misc import SUDOERS
    from FoxyMusic.utils.database import get_served_chats

    chat_id = int(chat_id)
    if served_ids is None:
        served = await get_served_chats()
        served_ids = {int(item["chat_id"]) for item in served}
    if chat_id not in served_ids:
        return False
    if user_id in SUDOERS:
        return True
    try:
        member = await app.get_chat_member(chat_id, int(user_id))
        if member.status == ChatMemberStatus.OWNER:
            return True
        if member.status == ChatMemberStatus.ADMINISTRATOR:
            privileges = getattr(member, "privileges", None)
            return bool(privileges and getattr(privileges, "can_manage_video_chats", False))
    except Exception:
        return False
    return False


async def _build_state(user_id, selected, page=0):
    from FoxyMusic import app
    from FoxyMusic.misc import db
    from FoxyMusic.utils.database import (
        get_served_chats, get_loop, is_autoplay_on
    )

    all_groups = []
    served_chats = await get_served_chats()
    served_ids = {int(item["chat_id"]) for item in served_chats}
    for item in served_chats[-40:]:
        chat_id = int(item["chat_id"])
        if not await _is_allowed(user_id, chat_id, served_ids):
            continue
        try:
            chat = await app.get_chat(chat_id)
            queue = db.get(chat_id, [])
            current = queue[0] if queue else {}
            all_groups.append({
                "id": int(chat_id),
                "title": str(getattr(chat, "title", "Music group"))[:64],
                "active": bool(queue),
                "song": str(current.get("title", ""))[:90],
                "by": str(current.get("by", ""))[:32],
                "queue": [str(x.get("title", "Unknown"))[:70] for x in queue[:5]],
                "loop": bool(await get_loop(chat_id)),
                "autoplay": bool(await is_autoplay_on(chat_id)),
            })
        except Exception:
            continue

    if selected is not None and not any(g["id"] == int(selected) for g in all_groups):
        selected = None
    if selected is None and all_groups:
        selected = all_groups[0]["id"]

    page_size = 4
    pages = max(1, (len(all_groups) + page_size - 1) // page_size)
    page = max(0, min(int(page or 0), pages - 1))
    visible = [
        {"id": g["id"], "title": g["title"]}
        for g in all_groups[page * page_size:(page + 1) * page_size]
    ]
    current_group = next((g for g in all_groups if g["id"] == selected), None)

    return {
        "groups": visible,
        "current": current_group,
        "selected": int(selected) if selected is not None else None,
        "group_page": page,
        "group_pages": pages,
        "message": "Choose a group" if not all_groups else "",
    }


async def _update_widget_state(query, state):
    chat = query.get("chat") or {}
    message_id = query.get("message_id")
    if chat.get("type") != "private" or not message_id:
        return
    await _api("editMessageWidgetData", {
        "chat_id": int(chat["id"]),
        "message_id": int(message_id),
        "chat_data": _compact_state(state),
    })


async def _skip_one(chat_id):
    """Advance the in-memory queue using the same playback engine as /skip."""
    import config as cfg
    from FoxyMusic import YouTube, app
    from FoxyMusic.core.call import Alone
    from FoxyMusic.misc import db
    from FoxyMusic.utils.database import (
        get_filter, get_lang, get_loop, is_autoplay_on, is_thumb_on
    )
    from FoxyMusic.utils.formatters import seconds_to_min
    from FoxyMusic.utils.stream.autoclear import auto_clean
    from FoxyMusic.utils.stream.stream import update_stream_ui
    from FoxyMusic.utils.inline.play import stream_markup
    from FoxyMusic.utils.thumbnails import get_thumb
    from strings import get_string

    check = db.get(chat_id)
    if not check:
        return "Queue is empty."
    popped = check.pop(0)
    try:
        await auto_clean(popped)
    except Exception:
        pass
    if not check:
        await Alone.stop_stream(chat_id)
        return "Playback stopped; queue finished."

    current = check[0]
    queued = current.get("file", "")
    title = str(current.get("title", "Unknown")).title()
    videoid = current.get("vidid", "")
    streamtype = current.get("streamtype", "audio")
    video = streamtype == "video"
    old_mystic = current.get("mystic")
    current["played"] = 0
    if current.get("old_dur"):
        current["dur"] = current["old_dur"]
        current["seconds"] = current.get("old_second", current.get("seconds", 0))
        current["speed_path"] = None
        current["speed"] = 1.0

    image = None
    if "live_" in queued:
        n, link = await YouTube.video(videoid, True)
        if n == 0:
            raise RuntimeError("Could not resolve the next live stream.")
        try:
            image = await YouTube.thumbnail(videoid, True)
        except Exception:
            pass
    elif "vid_" in queued:
        link, direct = await YouTube.download(videoid, old_mystic, videoid=True, video=video)
        if not link:
            raise RuntimeError("Could not download the next track.")
        try:
            image = await YouTube.thumbnail(videoid, True)
        except Exception:
            pass
    elif "index_" in queued:
        link = videoid
    else:
        link = queued
        if videoid not in ("telegram", "soundcloud"):
            try:
                image = await YouTube.thumbnail(videoid, True)
            except Exception:
                pass

    await Alone.skip_stream(chat_id, link, title, video=video, image=image)
    language = await get_lang(chat_id)
    _ = get_string(language)
    buttons = stream_markup(
        _, chat_id, await is_autoplay_on(chat_id),
        await is_thumb_on(chat_id), await get_filter(chat_id)
    )
    if "index_" in queued:
        caption = "▶️ Now playing: " + title
        thumb = cfg.STREAM_IMG_URL
    else:
        caption = "▶️ Now playing: " + title
        thumb = await get_thumb(videoid)
    run = await update_stream_ui(chat_id, chat_id, None, thumb, caption, buttons)
    current["mystic"] = run
    current["markup"] = "tg" if "live_" in queued or "index_" in queued else "stream"
    return "Skipped to: " + title


async def _perform_action(user_id, action, chat_id):
    from FoxyMusic import Alone
    from FoxyMusic.misc import db
    from FoxyMusic.utils.database import (
        autoplay_off, autoplay_on, get_loop, is_autoplay_on, set_loop
    )

    if not await _is_allowed(user_id, chat_id):
        raise PermissionError("You must be an administrator with Manage Video Chats permission in that group.")
    queue = db.get(chat_id, [])
    if action in ("pause", "resume", "next", "shuffle", "bass", "echo", "slowed", "nightcore", "normal") and not queue:
        raise RuntimeError("There is no active music queue in this group.")
    if action == "pause":
        await Alone.pause_stream(chat_id)
        return "Playback paused."
    if action == "resume":
        await Alone.resume_stream(chat_id)
        return "Playback resumed."
    if action == "stop":
        await Alone.stop_stream(chat_id)
        return "Playback stopped."
    if action == "next":
        return await _skip_one(chat_id)
    if action == "shuffle":
        if len(queue) < 3:
            raise RuntimeError("Add at least two upcoming songs to shuffle.")
        first = queue[0]
        tail = queue[1:]
        random.shuffle(tail)
        db[chat_id] = [first] + tail
        return "Upcoming queue shuffled."
    if action == "loop":
        current = await get_loop(chat_id)
        await set_loop(chat_id, 0 if current else 10)
        return "Loop " + ("disabled." if current else "enabled for 10 repeats.")
    if action == "autoplay":
        if await is_autoplay_on(chat_id):
            await autoplay_off(chat_id)
            return "Autoplay disabled."
        await autoplay_on(chat_id)
        return "Autoplay enabled."
    if action in ("bass", "echo", "slowed", "nightcore", "normal"):
        await Alone.apply_filter(chat_id, queue[0]["file"], action, queue)
        return f"{action.title()} effect applied."
    raise ValueError("Unknown widget action.")


async def send_search_widget(chat_id, query, reply_to_message_id=None):
    """Search YouTube from a private /play command and render results as widget buttons."""
    from py_yt import VideosSearch

    pref = await _widget_preferences.find_one({"user_id": int(chat_id)})
    selected = pref.get("selected_chat_id") if pref else None
    if selected is None or not await _is_allowed(int(chat_id), int(selected)):
        await send_music_widget(chat_id, reply_to_message_id)
        return False, "Choose one of your groups in the widget first, then send /play song name."
    search = VideosSearch(query, limit=5)
    results = (await search.next()).get("result", [])
    tracks = []
    for item in results[:5]:
        video_id = str(item.get("id") or "")
        if not video_id:
            continue
        tracks.append({
            "id": video_id,
            "title": str(item.get("title") or "Unknown")[:90],
            "duration": str(item.get("duration") or ""),
        })
    if not tracks:
        await send_music_widget(chat_id, reply_to_message_id)
        return False, "No songs found. Try a different search."
    await _widget_searches.update_one(
        {"user_id": int(chat_id)},
        {"$set": {"user_id": int(chat_id), "query": str(query)[:150],
                  "selected_chat_id": int(selected), "tracks": tracks}},
        upsert=True,
    )
    page = pref.get("group_page", 0)
    state = await _build_state(int(chat_id), int(selected), page)
    state["search"] = tracks
    state["message"] = "Choose a result to add it to the selected group's queue."
    await send_music_widget(chat_id, reply_to_message_id, state_override=state)
    return True, "Search results sent."


async def _play_search_result(user_id, video_id, user):
    from FoxyMusic import YouTube, app
    from FoxyMusic.utils.database import get_lang
    from FoxyMusic.utils.stream.stream import stream
    from strings import get_string

    pref = await _widget_preferences.find_one({"user_id": int(user_id)})
    search = await _widget_searches.find_one({"user_id": int(user_id)})
    if not pref or not search:
        raise RuntimeError("Search expired. Send /play song name again.")
    chat_id = int(pref.get("selected_chat_id", 0))
    if chat_id != int(search.get("selected_chat_id", 0)):
        raise RuntimeError("Your selected group changed. Search again.")
    if not await _is_allowed(user_id, chat_id):
        raise PermissionError("You no longer have permission in the selected group.")
    if not any(str(track.get("id")) == str(video_id) for track in search.get("tracks", [])):
        raise ValueError("That search result has expired. Search again.")
    details, track_id = await YouTube.track(str(video_id), True)
    if not details or not details.get("title"):
        raise RuntimeError("Could not load this song.")
    mystic = await app.send_message(int(user_id), "🎵 Adding your song to the selected group…")
    language = await get_lang(chat_id)
    _ = get_string(language)
    user_name = str(user.get("first_name") or "User")
    try:
        await stream(
            _, mystic, int(user_id), details, chat_id, user_name, chat_id,
            streamtype="youtube", forceplay=False,
        )
    except Exception as exc:
        try:
            await mystic.edit_text("❌ Could not start the song: " + type(exc).__name__)
        except Exception:
            pass
        raise
    return "Added: " + str(details.get("title", "your song"))[:100]


async def _handle_widget_query(query, session):
    from FoxyMusic import app

    user = query.get("from") or {}
    user_id = int(user.get("id", 0))
    from FoxyMusic.utils.database import is_banned_user
    chat = query.get("chat") or {}
    if chat.get("type") != "private" or int(chat.get("id", 0)) != user_id:
        await _api("answerWidgetQuery", {"widget_query_id": query["id"], "data": "Private chat only."}, session)
        return

    if await is_banned_user(user_id):
        await _api("answerWidgetQuery", {"widget_query_id": query["id"], "data": "You are blocked from using this bot."}, session)
        return
    if (query.get("type") or {}).get("type", "data") != "data":
        await _api("answerWidgetQuery", {"widget_query_id": query["id"], "data": "Unsupported widget request."}, session)
        return

    data = str(query.get("data", ""))
    parts = data.split(":")
    action = parts[0][:20]
    selected = None
    page = 0
    if len(parts) > 1:
        try:
            selected = int(parts[-1])
        except ValueError:
            selected = None

    # Acknowledge promptly; longer membership checks/playback work follows.
    await _api("answerWidgetQuery", {"widget_query_id": query["id"], "data": "Working…"}, session)

    message = ""
    if action == "help":
        message = "Select a group, then send /play song name in this private chat. The widget handles selection and playback controls."
    elif action == "groups":
        message = "Choose a group from the list below."
    elif action == "gpage" and len(parts) == 2:
        try:
            page = max(0, int(parts[1]))
            pref = await _widget_preferences.find_one({"user_id": user_id})
            selected = pref.get("selected_chat_id") if pref else None
            await _widget_preferences.update_one(
                {"user_id": user_id},
                {"$set": {"user_id": user_id, "group_page": page}},
                upsert=True,
            )
        except Exception:
            page = 0
            message = "Could not change group page."
    elif action in ("refresh", "home"):
        pref = await _widget_preferences.find_one({"user_id": user_id})
        if pref:
            selected = pref.get("selected_chat_id")
            page = pref.get("group_page", 0)
    elif action in ("pause", "resume", "stop", "next", "shuffle", "loop", "autoplay", "bass", "echo", "slowed", "nightcore", "normal"):
        if selected is None:
            message = "Select a group first."
        else:
            try:
                message = await _perform_action(user_id, action, selected)
            except Exception as exc:
                message = str(exc)[:160] or "Action failed."
    elif action == "select" and selected is not None:
        if await _is_allowed(user_id, selected):
            await _widget_preferences.update_one(
                {"user_id": user_id},
                {"$set": {"user_id": user_id, "selected_chat_id": selected}},
                upsert=True,
            )
            message = "Group selected. You can now use /play song name here."
        else:
            selected = None
            message = "You no longer have permission to control that group."
    elif action == "play" and len(parts) == 2:
        try:
            message = await _play_search_result(user_id, parts[1], user)
            pref = await _widget_preferences.find_one({"user_id": user_id})
            selected = pref.get("selected_chat_id") if pref else None
        except Exception as exc:
            message = str(exc)[:160] or "Could not start this song."
    else:
        message = "Unknown action."

    pref = await _widget_preferences.find_one({"user_id": user_id})
    if pref:
        page = pref.get("group_page", page)
        if selected is None:
            selected = pref.get("selected_chat_id")
    state = await _build_state(user_id, selected, page)
    if message:
        state["message"] = message
    try:
        await _update_widget_state(query, state)
    except Exception as exc:
        _LOG.warning("Widget state update failed: %s", exc)


async def _poll_widget_updates():
    if not config.BOT_TOKEN:
        _LOG.warning("Widget polling disabled: BOT_TOKEN is missing.")
        return
    timeout = aiohttp.ClientTimeout(total=65)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            webhook = await _api("getWebhookInfo", {}, session, timeout=15)
            if webhook and webhook.get("url"):
                _LOG.error(
                    "Widget polling disabled: a Bot API webhook is configured. "
                    "Remove the webhook before using the widget long-poll receiver."
                )
                return
        except Exception as exc:
            _LOG.error("Could not verify Bot API webhook state: %s", exc)
            return

        offset = None
        _LOG.info("Telegram widget update receiver started.")
        while not _STOP.is_set():
            payload = {"timeout": 50, "allowed_updates": ["widget_query"]}
            if offset is not None:
                payload["offset"] = offset
            try:
                updates = await _api("getUpdates", payload, session, timeout=60)
                for update in updates or []:
                    offset = int(update.get("update_id", 0)) + 1
                    query = update.get("widget_query")
                    if query:
                        try:
                            await _handle_widget_query(query, session)
                        except Exception:
                            _LOG.exception("Widget query handler failed.")
                            try:
                                await _api("answerWidgetQuery", {
                                    "widget_query_id": query["id"],
                                    "data": "The action failed. Please try again."
                                }, session, timeout=10)
                            except Exception:
                                pass
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                _LOG.warning("Widget update polling error: %s", exc)
                await asyncio.sleep(3)
        _LOG.info("Telegram widget update receiver stopped.")


def start_widget_receiver():
    global _POLL_TASK
    if _POLL_TASK and not _POLL_TASK.done():
        return _POLL_TASK
    _STOP.clear()
    _POLL_TASK = asyncio.create_task(_poll_widget_updates(), name="foxy-widget-poll")
    return _POLL_TASK


async def stop_widget_receiver():
    _STOP.set()
    global _POLL_TASK
    if _POLL_TASK and not _POLL_TASK.done():
        _POLL_TASK.cancel()
        try:
            await _POLL_TASK
        except asyncio.CancelledError:
            pass
    _POLL_TASK = None
