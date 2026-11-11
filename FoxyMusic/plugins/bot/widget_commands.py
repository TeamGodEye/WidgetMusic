# Private-chat HTML widget entry points. Group/channel handlers are intentionally untouched.
from pyrogram import filters
from pyrogram.types import Message

from FoxyMusic import app
from FoxyMusic.widgets import send_music_widget
from config import BANNED_USERS


@app.on_message(filters.private & filters.command(["settings", "setting"]) & ~BANNED_USERS)
async def private_settings_widget(client, message: Message):
    await send_music_widget(message.chat.id, message.id, view="settings")


@app.on_message(filters.private & filters.command(["player", "music", "dashboard"]) & ~BANNED_USERS)
async def private_player_widget(client, message: Message):
    await send_music_widget(message.chat.id, message.id, view="player")


@app.on_message(filters.private & filters.command(["queue", "cqueue", "playing", "cplaying"]) & ~BANNED_USERS)
async def private_queue_widget(client, message: Message):
    await send_music_widget(message.chat.id, message.id, view="player")


@app.on_message(filters.private & filters.command(["play"]) & ~BANNED_USERS)
async def private_play_search(client, message: Message):
    if len(message.command) < 2:
        await send_music_widget(message.chat.id, message.id, view="player")
        await message.reply_text("Choose a group in the widget, then send /play song name here to search.")
        return
    from FoxyMusic.widgets import send_search_widget
    query = message.text.split(None, 1)[1].strip()
    if len(query) > 180:
        return await message.reply_text("Please keep the song search under 180 characters.")
    ok, info = await send_search_widget(message.chat.id, query, message.id)
    if not ok:
        await message.reply_text(info)
