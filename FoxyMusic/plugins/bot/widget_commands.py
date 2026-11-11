# Private-chat HTML widget entry points.
from pyrogram import filters
from pyrogram.types import Message

from FoxyMusic import app
from FoxyMusic.widgets import send_music_widget
from config import BANNED_USERS


@app.on_message(
    filters.private
    & filters.command(["player", "music", "dashboard", "settings", "queue"])
    & ~BANNED_USERS
)
async def private_music_dashboard(client, message: Message):
    try:
        await send_music_widget(
            chat_id=message.chat.id,
            reply_to_message_id=message.id,
        )
    except Exception as exc:
        await message.reply_text(
            "The interactive music widget could not be opened right now. "
            "Please try again in a moment.\n\n"
            f"<code>{type(exc).__name__}</code>"
        )


@app.on_message(
    filters.private
    & filters.command(["play"])
    & ~BANNED_USERS
)
async def private_play_search(client, message: Message):
    if len(message.command) < 2:
        await send_music_widget(
            chat_id=message.chat.id,
            reply_to_message_id=message.id,
        )
        await message.reply_text(
            "Choose a group in the music widget, then send <code>/play song name</code> here to search."
        )
        return
    from FoxyMusic.widgets import send_search_widget
    query = message.text.split(None, 1)[1].strip()
    if len(query) > 180:
        return await message.reply_text("Please keep the song search under 180 characters.")
    try:
        ok, info = await send_search_widget(
            chat_id=message.chat.id,
            query=query,
            reply_to_message_id=message.id,
        )
        if not ok:
            await message.reply_text(info)
    except Exception as exc:
        await message.reply_text(
            "❌ Song search failed. Please try again.\n"
            f"<code>{type(exc).__name__}</code>"
        )
