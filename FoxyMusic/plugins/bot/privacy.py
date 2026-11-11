# ─────「 𝐅ᴏxʏ 」─────
#    Official Project Source
# ────────────────────────

from pyrogram import filters
from pyrogram.enums import ButtonStyle, ChatType
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from FoxyMusic import app
from FoxyMusic.utils.decorators.language import language
from config import BANNED_USERS, PRIVACY_LINK

@app.on_message(filters.command("privacy") & ~BANNED_USERS)
@language
async def privacy_policy(client, message: Message, _):
    if message.chat.type == ChatType.PRIVATE:
        from FoxyMusic.widgets import send_music_widget
        return await send_music_widget(message.chat.id, message.id, view="privacy")
    buttons = [
        [
            InlineKeyboardButton(
                text=_["PRIVACY_BUTTON"],
                url=PRIVACY_LINK,
                style=ButtonStyle.PRIMARY,
            ),
        ],
    ]
    await message.reply_text(
        _["privacy_1"],
        reply_markup=InlineKeyboardMarkup(buttons),
    )
