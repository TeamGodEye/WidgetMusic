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
.wrap{padding:12px;display:grid;gap:10px}.page{display:none}.page.active{display:grid}.copy{white-space:pre-wrap;line-height:1.5}.helpgrid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px}.helpgrid button{min-width:0}.nav{position:sticky;top:0;z-index:2}.top{display:flex;align-items:center;justify-content:space-between}
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
 <div class="top"><div><div class="brand">FOXY MUSIC</div><div class="muted">PRIVATE WIDGET</div></div><button class="alt" data-a="refresh">↻</button></div>
 <div class="row nav"><button class="alt" data-a="view:start">Home</button><button class="alt" data-a="view:help">Help</button><button class="alt" data-a="view:settings">Settings</button><button class="alt" data-a="view:player">Player</button></div>
 <section id="page-start" class="page card"><div class="title">Welcome to FoxyMusic</div><div id="welcome" class="copy"></div><div class="row"><button data-a="view:help">Help & Commands</button><button class="alt" data-a="view:settings">Settings</button></div><div class="row"><button class="alt" data-a="addgroup">Add to Group</button><button class="alt" data-a="network">Network</button><button class="alt" data-a="developer">Developer</button></div></section>
 <section id="page-help" class="page card"><div class="title" id="helptitle">Help & Commands</div><div id="helpgrid" class="helpgrid"></div><div id="helpbody" class="copy"></div><div class="row" id="helpnav"><button class="alt" data-a="helpprev">‹ Previous</button><button class="alt" data-a="helpnext">Next ›</button></div><div class="row"><button class="alt" data-a="view:start">‹ Back to Home</button><button class="alt" data-a="view:start">Close</button></div></section>
 <section id="page-settings" class="page card"><div class="title">Private Settings</div><div class="copy">Private bot settings and tools.</div><div class="row"><button data-a="view:language">Language</button><button class="alt" data-a="view:privacy">Privacy</button><button class="alt" data-a="view:ping">Bot Status</button><button class="alt" data-a="view:createpost">Post Creator</button><button class="alt" data-a="view:sudo">SUDO</button></div><div class="row"><button class="alt" data-a="view:start">‹ Back to Home</button></div></section>
 <section id="page-language" class="page card"><div class="title">Choose Language</div><div id="langgrid" class="helpgrid"></div><div class="row"><button class="alt" data-a="view:settings">‹ Back</button></div></section>
 <section id="page-privacy" class="page card"><div class="title">Privacy</div><div id="privacytext" class="copy"></div><div class="row"><button class="alt" data-a="view:settings">‹ Back</button><button data-a="privacyurl">Open Policy</button></div></section>
 <section id="page-createpost" class="page card"><div class="title">Post Creator</div><div class="copy">Choose a post type. Send requested text, IDs, URLs and photos in this chat; choose options here.</div><div class="row"><button data-a="posttype:hidden">Hidden Preview</button><button class="alt" data-a="posttype:normal">Normal Post</button></div><div id="poststatus" class="status"></div><div id="postactions" class="row"></div><div class="row"><button class="danger" data-a="postcancel">Cancel Setup</button><button class="alt" data-a="view:start">‹ Home</button></div></section>
 <section id="page-sudo" class="page card"><div class="title">SUDO Control Center</div><div class="copy" id="sudotext">Checking access…</div><div class="helpgrid" id="sudogrid"></div><div class="row"><button class="alt" data-a="view:start">‹ Home</button></div></section>
 <section id="page-sent" class="page card"><div class="title">Sent Account</div><div class="copy" id="senttext"></div><div class="row"><button class="danger" data-a="sentlogout">Logout Account</button><button class="alt" data-a="view:sudo">‹ SUDO</button></div></section>
 <section id="page-ping" class="page card"><div class="title">Bot Status</div><div id="pingtext" class="copy"></div><div class="row"><button data-a="ping">Refresh Status</button><button class="alt" data-a="view:settings">‹ Back</button></div></section>
 <section id="page-player" class="page">
 <div class="top"><div><div class="brand">FOXY MUSIC</div><div class="muted">PRIVATE MUSIC CONTROL CENTER</div></div><button class="alt" data-a="refresh">↻</button></div>
 <div class="card"><div class="row"><div><div class="muted">CONNECTED GROUP</div><div class="title" id="gname">Choose a group</div></div><button class="alt" data-a="groups">Switch</button></div><div class="status" id="status">Loading your music rooms…</div></div>
 <div class="card" id="player"><div class="muted">NOW PLAYING</div><div class="title" id="song">Nothing is playing</div><div class="small" id="meta">Select an active group to view playback</div><div class="row"><button data-a="pause">Ⅱ Pause</button><button data-a="resume">▶ Resume</button><button class="danger" data-a="stop">■ Stop</button></div><div class="row"><button class="alt" data-a="next">⏭ Next</button><button class="alt" data-a="shuffle">⇄ Shuffle</button></div></div>
 <div class="card"><div class="title">YOUR MUSIC GROUPS</div><div id="groups"></div><div class="row" id="groupnav"><button class="alt" data-a="gprev">‹ Previous</button><button class="alt" data-a="gnext">Next ›</button></div></div>
 <div class="card" id="searchcard"><div class="title">SEARCH RESULTS</div><div id="search"></div></div>
 <div class="card" id="infocard"><div class="muted">TRACK INFORMATION</div><div class="title" id="infotitle"></div><div class="small" id="infoduration"></div><button class="alt" data-a="openvideo">Open on YouTube</button></div>
 <div class="card"><div class="top"><div class="title">UP NEXT</div><button class="alt" data-a="queue">Refresh</button></div><div id="queue" class="small">Queue is empty</div></div>
 <div class="card"><div class="title">PLAYBACK OPTIONS</div><div class="row"><button class="alt" data-a="loop">Loop: <span id="loop">Off</span></button><button class="alt" data-a="autoplay">Autoplay: <span id="autoplay">Off</span></button></div><div class="row"><button class="alt" data-a="bass">Bass</button><button class="alt" data-a="echo">Echo</button><button class="alt" data-a="nightcore">Nightcore</button><button class="alt" data-a="slowed">Slowed</button><button class="alt" data-a="normal">Normal</button></div></div>
 <div class="row"><button class="alt" data-a="help">Help</button><button class="alt" data-a="groups">My Groups</button></div>
 </section>
 <div id="toast"></div>
</div>
<script>
(function(){
 const W=window.TelegramWidget;let state={groups:[],selected:null,queue:[],view:"start"};
 const $=id=>document.getElementById(id);
 function parse(v){try{return JSON.parse(v||"{}")}catch(e){return {}}}
 function text(id,v){$(id).textContent=v||""}
 function draw(){
  const view=state.view||"start";
  document.querySelectorAll(".page").forEach(p=>p.classList.toggle("active",p.id==="page-"+view));
  $("welcome").innerHTML=state.welcome||"Welcome to FoxyMusic. Add the bot to your group to start music in voice chat.";
  $("helpbody").innerHTML=state.help_text||"";text("helptitle",state.help_title||"Help & Commands");
  const hn=$("helpnav"); if(hn) hn.style.display=state.help_chunks>1?"flex":"none";
  const hg=$("helpgrid"); if(hg && !hg.dataset.ready){hg.dataset.ready="1";for(let i=1;i<=12;i++){const b=document.createElement("button");b.className="alt";b.textContent=(state.help_labels||[])[i-1]||("Section "+i);b.dataset.help="hb"+i;b.addEventListener("click",()=>request("help:hb"+i));hg.appendChild(b)}}
  const lg=$("langgrid"); if(lg && !lg.dataset.ready){lg.dataset.ready="1";(state.languages||[]).forEach(x=>{const b=document.createElement("button");b.className="alt";b.textContent=x.name;b.addEventListener("click",()=>request("language:"+x.code));lg.appendChild(b)})}
  $("privacytext").innerHTML=state.privacy_text||"";text("pingtext",state.ping_text||"");text("poststatus",state.post_status||"");text("sudotext",state.sudo_text||"");text("senttext",state.sent_text||"");
  const pa=$("postactions");if(pa){pa.textContent="";const add=(label,action)=>{const b=document.createElement("button");b.className="alt";b.textContent=label;b.addEventListener("click",()=>request(action));pa.appendChild(b)};const step=state.post_step||"";if(step==="position"){add("Video Above Text","postposition:above");add("Video Below Text","postposition:below")}else if(step==="format"){add("Format 1","postformat:1");add("Format 2","postformat:2")}else if(step==="color"){add("Blue","postcolor:blue");add("Green","postcolor:green");add("Red","postcolor:red");add("Default","postcolor:default")}}
  const sg=$("sudogrid");if(sg&&!sg.dataset.ready){sg.dataset.ready="1";(state.sudo_commands||[]).forEach(x=>{const b=document.createElement("button");b.className="alt";b.textContent=x;b.addEventListener("click",()=>request("sudocmd:"+x));sg.appendChild(b)})}
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
  if(a.startsWith("view:")){request(a);return}
  if(a==="helpprev"){request("help:"+(state.help_section||"hb1")+":"+Math.max(0,(state.help_chunk||0)-1));return}
  if(a==="helpnext"){request("help:"+(state.help_section||"hb1")+":"+((state.help_chunk||0)+1));return}
  if(a==="addgroup"){if(W&&W.openTelegramLink)W.openTelegramLink(state.addgroup_url);return}
  if(a==="network"){if(W&&W.openTelegramLink)W.openTelegramLink("https://t.me/FoxryHQ");return}
  if(a==="developer"){if(W&&W.openTelegramLink)W.openTelegramLink("tg://user?id="+state.owner_id);return}
  if(a==="privacyurl"){if(W&&W.openLink&&state.privacy_url)W.openLink(state.privacy_url);return}
  if(a==="ping"){request("ping");return}
  if(a==="sentlogout"){request("sentlogout");return}
  if(a.startsWith("posttype:")||a.startsWith("postformat:")||a.startsWith("postposition:")||a.startsWith("postcolor:")){request(a);return}
  if(a==="postcancel"){request("postcancel");return}
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

WIDGET_HTML_START = r"""
<style>
*{box-sizing:border-box}body{margin:0;background:#0b0810;color:#f8f1fa;font:14px system-ui}.wrap{padding:14px;display:grid;gap:12px;background:radial-gradient(ellipse at 90% 0%,#54224f,transparent 48%),#0b0810}.top,.row{display:flex;align-items:center;gap:8px}.top{justify-content:space-between}.row>*{flex:1}.brand{font-size:16px;font-weight:900;letter-spacing:2px;color:#f5a6e7}.muted{font-size:10px;color:#b9a7bf;letter-spacing:1px}.hero{padding:18px;border:1px solid #ffffff25;border-radius:22px;background:linear-gradient(140deg,#482044,#17101f);display:grid;gap:13px}.eyebrow{font-size:10px;letter-spacing:2px;color:#f1a9df;font-weight:800}.hero h1{font-size:32px;margin:5px 0}.welcome{font-size:13px;line-height:1.5;color:#e7d9ec}.disc{width:82px;height:82px;border-radius:50%;margin-left:auto;background:repeating-radial-gradient(circle,#16121b 0 4px,#34243c 5px 7px);border:5px solid #d36bb9;display:grid;place-items:center}.disc:after{content:'F';width:26px;height:26px;border-radius:50%;display:grid;place-items:center;background:#c65fc2;font-weight:900}.feature{background:#ffffff0b;border:1px solid #ffffff1b;border-radius:13px;padding:11px;display:grid;gap:4px}.feature b{font-size:12px}.feature span{font-size:11px;color:#b9a7bf}button{border:0;border-radius:11px;padding:11px 8px;background:linear-gradient(110deg,#d94db0,#8c55e8);color:white;font:700 12px system-ui;min-height:40px}button.alt{background:#ffffff0c;border:1px solid #ffffff20;color:#f7efff}#toast{text-align:center;color:#b9a7bf;font-size:11px;min-height:14px}
</style>
<div class="wrap"><div class="top"><div><div class="brand">FOXY MUSIC</div><div class="muted">PREMIUM TELEGRAM MUSIC</div></div><button class="alt" data-a="startview:help">Explore ↗</button></div>
<section class="hero"><div><div class="eyebrow">YOUR MUSIC · YOUR VIBE</div><h1>Foxy<span style="color:#ef8bd0">Music</span></h1><div class="muted" id="hello">WELCOME</div><div class="welcome" id="welcome"></div></div><div class="disc"></div><div class="row"><button data-a="startview:player">Open Music Player ↗</button><button class="alt" data-a="addgroup">Add to Group</button></div><div class="muted">A PREMIUM MUSIC EXPERIENCE FOR YOUR COMMUNITY</div></section>
<div class="muted">EXPLORE FOXYMUSIC</div><div class="row"><div class="feature"><b>♫ Music Player</b><span>Playback and queue controls</span></div><div class="feature"><b>✦ Smart Controls</b><span>Settings and music effects</span></div></div>
<div class="row"><button data-a="startview:help">Help & Commands</button><button class="alt" data-a="startview:settings">Settings</button></div><div class="row"><button class="alt" data-a="network">Community</button><button class="alt" data-a="developer">Developer</button><button class="alt" data-a="startview:privacy">Privacy</button></div><div class="muted" style="text-align:center">MADE FOR YOUR TELEGRAM COMMUNITY</div><div id="toast"></div></div>
<script>(function(){const W=window.TelegramWidget;let s={};try{s=JSON.parse(W.chatData||"{}")}catch(e){}const $=id=>document.getElementById(id);$("welcome").innerHTML=s.welcome||"Your premium music companion for Telegram groups and channels.";$("hello").textContent=s.user_name?"WELCOME, "+s.user_name.toUpperCase():"WELCOME TO YOUR MUSIC SPACE";function req(a){W.request(a).catch(()=>{$("toast").textContent="Request failed. Try again."})}document.addEventListener("click",e=>{const b=e.target.closest("button[data-a]");if(!b)return;const a=b.dataset.a;if(a.startsWith("startview:")){req(a);return}if(a==="addgroup"){if(W.openTelegramLink)W.openTelegramLink(s.addgroup_url);return}if(a==="network"){if(W.openTelegramLink)W.openTelegramLink("https://t.me/FoxryHQ");return}if(a==="developer"){if(W.openTelegramLink)W.openTelegramLink("tg://user?id="+s.owner_id)}})})();</script>
"""


def _compact_state(state):
    state = dict(state or {})
    view = state.get("view", "player")
    if view != "player":
        common = {"view": view, "message": str(state.get("message", ""))[:90]}
        if view == "start":
            common.update({"welcome": str(state.get("welcome", ""))[:600], "user_name": str(state.get("user_name", ""))[:48], "addgroup_url": state.get("addgroup_url", ""), "owner_id": state.get("owner_id", 0)})
        elif view == "help":
            common.update({"help_labels": list(state.get("help_labels", []))[:12], "help_section": state.get("help_section"), "help_title": str(state.get("help_title", "Help & Commands"))[:60], "help_text": str(state.get("help_text", ""))[:700], "help_chunk": int(state.get("help_chunk", 0)), "help_chunks": int(state.get("help_chunks", 1))})
        elif view == "language":
            common["languages"] = list(state.get("languages", []))[:30]
        elif view == "privacy":
            common.update({"privacy_text": str(state.get("privacy_text", ""))[:500], "privacy_url": str(state.get("privacy_url", ""))[:250]})
        elif view == "ping":
            common["ping_text"] = str(state.get("ping_text", ""))[:500]
        elif view == "createpost":
            common["post_status"] = str(state.get("post_status", ""))[:300]
            common["post_step"] = str(state.get("post_step", ""))[:20]
        elif view == "sudo":
            common.update({"sudo_text": str(state.get("sudo_text", ""))[:300], "sudo_commands": list(state.get("sudo_commands", []))[:32]})
        elif view == "sent":
            common["sent_text"] = str(state.get("sent_text", ""))[:300]
        state = common
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


async def _build_page_state(user_id, view="start", section=None, chunk=0):
    """Build localized private landing/help/settings state from original strings."""
    from FoxyMusic.utils.database import get_lang
    from strings import get_string, helpers, languages_present
    language = await get_lang(int(user_id))
    _ = get_string(language)
    import config as cfg
    from FoxyMusic import app
    try:
        tg_user = await app.get_users(int(user_id))
        user_name = " ".join(x for x in (tg_user.first_name, tg_user.last_name) if x).strip() or "there"
    except Exception:
        user_name = "there"
    import html as _html
    bot_name = getattr(app, "name", None) or getattr(app, "username", None) or "FoxyMusic"
    state = {"view": view, "user_name": user_name, "welcome": str(_["start_2"]).format(_html.escape(user_name), _html.escape(str(bot_name)))}
    state["help_labels"] = [str(_.get(f"H_B_{i}", f"Section {i}")) for i in range(1, 13)]
    state["languages"] = [{"code": code, "name": name} for code, name in languages_present.items()]
    state["privacy_text"] = str(_.get("privacy_1", "Privacy information is available from the policy link."))
    state["privacy_url"] = str(getattr(cfg, "PRIVACY_LINK", ""))
    state["owner_id"] = int(getattr(cfg, "OWNER_ID", 0))
    from FoxyMusic import app
    state["addgroup_url"] = f"https://t.me/{app.username}?startgroup=true"
    state["help_text"] = ""
    state["help_section"] = None
    state["help_title"] = "Help & Commands"
    if section and str(section).startswith("hb"):
        try:
            index = int(str(section)[2:])
            if 1 <= index <= 12 and not (index == 7 and int(user_id) not in __import__("FoxyMusic.misc", fromlist=["SUDOERS"]).SUDOERS):
                full_text = str(getattr(helpers, f"HELP_{index}"))
                chunks = []
                current = ""
                for line in full_text.splitlines(keepends=True):
                    if len((current + line).encode("utf-8")) > 650 and current:
                        chunks.append(current)
                        current = ""
                    current += line
                if current or not chunks:
                    chunks.append(current)
                chunk = max(0, min(int(chunk or 0), len(chunks)-1))
                state["help_section"] = f"hb{index}"
                state["help_chunk"] = chunk
                state["help_chunks"] = len(chunks)
                state["help_text"] = chunks[chunk]
                state["help_title"] = state["help_labels"][index-1]
            elif index == 7:
                state["help_text"] = "This section is only available to SUDO users."
        except Exception:
            state["help_text"] = "This help section is unavailable."
    if view == "createpost":
        from FoxyMusic.plugins.misc.createpost import SESSIONS
        session = SESSIONS.get(int(user_id), {})
        state["post_step"] = str(session.get("step", "post_type"))
        step_text = {
            "post_type": "Select Hidden Preview or Normal Post to begin.",
            "chat_id": "Send the target group/channel Chat ID in this private chat.",
            "position": "Choose whether the video preview appears above or below the text.",
            "hidden_text": "Send the complete text/caption for the hidden-preview post.",
            "hidden_video": "Send a direct MP4 video URL.",
            "format": "Choose the normal post format.",
            "user_id": "Send the Telegram User ID to mention in the post.",
            "color": "Choose the button colour.",
            "photo": "Send a photo or a direct image URL.",
        }
        state["post_status"] = step_text.get(state["post_step"], "Post Creator is processing your request.")
    if view == "sudo":
        from FoxyMusic.misc import SUDOERS
        if int(user_id) in SUDOERS:
            state["sudo_text"] = "SUDO access verified. Select a command to view its private-chat usage.\n\nSUDO users: " + str(len(SUDOERS))
            state["sudo_commands"] = ["sent", "createpost", "broadcast", "clean", "ac", "activevoice", "activevideo", "speedtest", "getlog", "update", "restart", "maintenance", "autoend", "autoleave", "logger", "blchat", "whitelistchat", "block", "unblock", "blocked", "gban", "ungban", "gbannedusers", "addsudo", "delsudo", "tts", "ttsdur", "ttstxt", "eval", "sh"]
            try:
                from config import OWNER_ID
                from FoxyMusic import app
                rows = []
                for uid in [int(OWNER_ID)] + sorted(int(x) for x in SUDOERS if int(x) != int(OWNER_ID)):
                    try:
                        u = await app.get_users(uid)
                        rows.append((u.first_name or "User") + " · " + str(uid))
                    except Exception:
                        rows.append("User · " + str(uid))
                state["sudo_text"] += "\n\n" + "\n".join(rows[:8])
            except Exception:
                pass
        else:
            state["sudo_text"] = "This panel is available to SUDO users only."
    if view == "sent":
        from FoxyMusic.misc import SUDOERS
        from FoxyMusic.plugins.misc.Sent import AUTHENTICATED_CLIENTS
        from FoxyMusic.core.mongo import mongodb
        if int(user_id) not in SUDOERS:
            state["sent_text"] = "SUDO access is required."
        else:
            record = await mongodb.sent_accounts.find_one({"owner_id": int(user_id)})
            connected = int(user_id) in AUTHENTICATED_CLIENTS
            state["sent_text"] = ("Connected account: " + str(record.get("first_name", "Connected")) if record else ("Authenticated client is connected" if connected else "No connected account found."))
    if view == "ping":
        from datetime import datetime
        from FoxyMusic.core.call import Alone
        from FoxyMusic.utils import bot_sys_stats
        try:
            up, cpu, ram, disk = await bot_sys_stats()
            ptg = await Alone.ping()
            state["ping_text"] = f"CPU: {cpu}\nRAM: {ram}\nDisk: {disk}\nVoice engine ping: {ptg} ms\nStatus: Online"
        except Exception:
            state["ping_text"] = "FoxyMusic is online. Detailed metrics are temporarily unavailable."
    return state


async def send_music_widget(chat_id, reply_to_message_id=None, state_override=None, view="player", section=None):
    """Send the private interactive player dashboard."""
    from FoxyMusic import app

    if state_override is None:
        pref = await _widget_preferences.find_one({"user_id": int(chat_id)})
        selected = pref.get("selected_chat_id") if pref else None
        page = pref.get("group_page", 0) if pref else 0
        page_state = await _build_page_state(int(chat_id), view, section)
        state = await _build_state(int(chat_id), selected, page) if view == "player" else {}
        state.update(page_state)
        state["view"] = view
    else:
        state = state_override
    widget_html = WIDGET_HTML_START if state.get("view") == "start" else WIDGET_HTML
    compressed_size = len(zlib.compress(widget_html.encode("utf-8"), 9))
    if len(widget_html.encode("utf-8")) > 32768 or compressed_size > 4096:
        raise RuntimeError(f"Widget HTML exceeds Telegram limits ({compressed_size} compressed bytes).")
    payload = {
        "chat_id": int(chat_id),
        "html": widget_html,
        "caption": "🎵 FoxyMusic — private control center",
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
    state["view"] = "player"
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


async def update_createpost_widget(user_id, status=None):
    """Refresh the existing Post Creator widget after a private-chat input."""
    from FoxyMusic.plugins.misc.createpost import SESSIONS
    session = SESSIONS.get(int(user_id), {})
    message_id = session.get("widget_message_id")
    if not message_id:
        return False
    state = await _build_page_state(int(user_id), "createpost")
    if status:
        state["post_status"] = str(status)[:300]
    try:
        await _api("editMessageWidgetData", {
            "chat_id": int(user_id),
            "message_id": int(message_id),
            "chat_data": _compact_state(state),
        })
        return True
    except Exception as exc:
        if "message is not modified" in str(exc).lower():
            return True
        _LOG.warning("Could not refresh Post Creator widget: %s", exc)
        return False


async def _update_widget_state(query, state):
    chat = query.get("chat") or {}
    message_id = query.get("message_id")
    if chat.get("type") != "private" or not message_id:
        return
    try:
        await _api("editMessageWidgetData", {
            "chat_id": int(chat["id"]),
            "message_id": int(message_id),
            "chat_data": _compact_state(state),
        })
    except RuntimeError as exc:
        if "message is not modified" not in str(exc).lower():
            raise


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
    if action == "help" and len(parts) == 1:
        message = "Choose a help category."
    elif action == "startview" and len(parts) == 2:
        target = parts[1]
        if target in {"help", "settings", "language", "privacy", "ping", "player", "createpost", "sudo", "sent"}:
            page_state = await _build_page_state(user_id, target)
            pref = await _widget_preferences.find_one({"user_id": user_id})
            selected = pref.get("selected_chat_id") if pref else None
            page = pref.get("group_page", 0) if pref else 0
            state = await _build_state(user_id, selected, page) if target == "player" else {}
            state.update(page_state)
            state["view"] = target
            await send_music_widget(user_id, state_override=state, view=target)
            return
        message = "Unknown section."
    elif action == "view" and len(parts) == 2:
        target = parts[1]
        if target in {"start", "help", "settings", "language", "privacy", "ping", "player", "createpost", "sudo", "sent"}:
            page_state = await _build_page_state(user_id, target)
            pref = await _widget_preferences.find_one({"user_id": user_id})
            selected = pref.get("selected_chat_id") if pref else None
            page = pref.get("group_page", 0) if pref else 0
            state = await _build_state(user_id, selected, page) if target == "player" else {}
            state.update(page_state)
            state["view"] = target
            if target == "start":
                await send_music_widget(user_id, state_override=state, view="start")
            else:
                await _update_widget_state(query, state)
            return
        message = "Unknown section."
    elif action == "help" and len(parts) in (2, 3):
        try:
            chunk = int(parts[2]) if len(parts) == 3 else 0
        except ValueError:
            chunk = 0
        page_state = await _build_page_state(user_id, "help", parts[1], chunk)
        pref = await _widget_preferences.find_one({"user_id": user_id})
        selected = pref.get("selected_chat_id") if pref else None
        page = pref.get("group_page", 0) if pref else 0
        state = {}
        state.update(page_state)
        state["view"] = "help"
        await _update_widget_state(query, state)
        return
    elif action == "language" and len(parts) == 2:
        from FoxyMusic.utils.database import set_lang
        from strings import languages_present
        code = parts[1]
        if code not in languages_present:
            message = "Unsupported language."
        else:
            await set_lang(user_id, code)
            message = "Language updated."
            page_state = await _build_page_state(user_id, "settings")
            page_state["message"] = message
            pref = await _widget_preferences.find_one({"user_id": user_id})
            selected = pref.get("selected_chat_id") if pref else None
            state = {}
            state.update(page_state)
            state["view"] = "settings"
            await _update_widget_state(query, state)
            return
    elif action == "ping":
        page_state = await _build_page_state(user_id, "ping")
        pref = await _widget_preferences.find_one({"user_id": user_id})
        selected = pref.get("selected_chat_id") if pref else None
        state = {}
        state.update(page_state)
        state["view"] = "ping"
        await _update_widget_state(query, state)
        return
    elif action == "posttype" and len(parts) == 2:
        from FoxyMusic.plugins.misc.createpost import SESSIONS, LOCK
        selected_type = parts[1]
        if selected_type not in ("hidden", "normal"):
            message = "Invalid post type."
        else:
            async with LOCK:
                SESSIONS[user_id] = {"step": "chat_id", "post_type": selected_type, "widget_message_id": int(query.get("message_id", 0) or 0)}
            state = await _build_page_state(user_id, "createpost")
            state["post_status"] = "Selected " + ("Hidden Preview" if selected_type == "hidden" else "Normal Post") + ". Send the target Chat ID in this private chat to continue."
            await _update_widget_state(query, state)
            await app.send_message(user_id, "🛠 <b>Post Creator</b>\n\nSend the target group/channel Chat ID here. Example: <code>-1001234567890</code>")
            return
    elif action in ("postformat", "postposition", "postcolor") and len(parts) == 2:
        from FoxyMusic.plugins.misc.createpost import SESSIONS, LOCK
        session_state = SESSIONS.get(user_id)
        if not session_state:
            message = "Post Creator session expired. Open it again."
        else:
            value = parts[1]
            expected = {"postformat": ("format", ("1", "2")), "postposition": ("position", ("above", "below")), "postcolor": ("color", ("blue", "green", "red", "default"))}[action]
            step_name, allowed = expected
            if session_state.get("step") != step_name or value not in allowed:
                message = "That choice is not valid for the current step."
            else:
                session_state[step_name] = value
                next_step = {"postformat": "user_id", "postposition": "hidden_text", "postcolor": "photo"}[action]
                session_state["step"] = next_step
                prompts = {
                    "user_id": "Send the Telegram User ID whose name and mention should appear in the post.",
                    "hidden_text": "Send the complete text/caption you want in the post.",
                    "photo": "Send the image as a Telegram photo, or send a direct image URL.",
                }
                await app.send_message(user_id, prompts[next_step])
                state = await _build_page_state(user_id, "createpost")
                state["post_status"] = prompts[next_step]
                await _update_widget_state(query, state)
                return
    elif action == "postcancel":
        from FoxyMusic.plugins.misc.createpost import SESSIONS
        SESSIONS.pop(user_id, None)
        state = await _build_page_state(user_id, "createpost")
        state["post_status"] = "Post Creator cancelled. Choose a post type to start again."
        state["post_step"] = "post_type"
        await _update_widget_state(query, state)
        return
    elif action == "sentlogout":
        from FoxyMusic.misc import SUDOERS
        from FoxyMusic.plugins.misc.Sent import unregister_authenticated_client
        from FoxyMusic.core.mongo import mongodb
        if user_id not in SUDOERS:
            message = "SUDO access is required."
        else:
            user_client = unregister_authenticated_client(user_id)
            if user_client is not None:
                try:
                    result = user_client.disconnect()
                    if hasattr(result, "__await__"):
                        await result
                except Exception:
                    pass
            await mongodb.sent_accounts.delete_one({"owner_id": user_id})
            state = await _build_page_state(user_id, "sent")
            state["sent_text"] = "Connected account logged out. Saved feature data cleared."
            await _update_widget_state(query, state)
            return
    elif action == "sudocmd" and len(parts) >= 2:
        from FoxyMusic.misc import SUDOERS
        if user_id not in SUDOERS:
            message = "SUDO access is required."
        else:
            command_name = parts[1]
            state = await _build_page_state(user_id, "sudo")
            state["message"] = f"Run /{command_name} in this private chat to execute it."
            await _update_widget_state(query, state)
            return
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
    elif action in ("refresh", "home", "queue"):
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
