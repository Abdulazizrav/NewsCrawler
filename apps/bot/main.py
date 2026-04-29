import asyncio
import logging
import sys
import os
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, html, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ChatMemberUpdated
from aiogram.filters.chat_member_updated import ChatMemberUpdatedFilter, ADMINISTRATOR, MEMBER, IS_NOT_MEMBER

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(BASE_DIR, ".env"))

TOKEN = os.getenv("BOT_TOKEN")
dp = Dispatcher()



@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    await message.answer(f"Hello, {html.bold(message.from_user.full_name)}!")

@dp.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=IS_NOT_MEMBER >> ADMINISTRATOR))
async def bot_added_as_admin(event: ChatMemberUpdated):
    chat = event.chat
    user = event.from_user
    
    text = f"✅ Bot successfully added as Administrator!\n\n" \
           f"📢 <b>Channel Name:</b> {chat.title}\n" \
           f"🆔 <b>Channel ID:</b> <code>{chat.id}</code>\n\n" \
           f"<i>Please copy the Channel ID and use it in your dashboard to add this channel.</i>"
           
    try:
        # Send a private message to the user who added the bot
        await event.bot.send_message(chat_id=user.id, text=text)
    except Exception:
        # Fallback to sending a message to the channel itself
        try:
            await event.bot.send_message(chat_id=chat.id, text=text)
        except Exception as e:
            logging.error(f"Failed to send channel ID info: {e}")

@dp.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=IS_NOT_MEMBER >> MEMBER))
async def bot_added_as_member(event: ChatMemberUpdated):
    chat = event.chat
    user = event.from_user
    
    text = f"✅ Bot successfully added to channel!\n\n" \
           f"📢 <b>Channel Name:</b> {chat.title}\n" \
           f"🆔 <b>Channel ID:</b> <code>{chat.id}</code>\n\n" \
           f"⚠️ <i>Warning: I was added as a regular member. I need to be an <b>Administrator</b> to send messages to this channel!</i>"
           
    try:
        await event.bot.send_message(chat_id=user.id, text=text)
    except Exception:
        try:
            await event.bot.send_message(chat_id=chat.id, text=text)
        except Exception as e:
            logging.error(f"Failed to send channel ID info: {e}")


@dp.message(Command("send"))
async def send_to_channels(message: Message):
    channel_ids = [
        -1003137913233,
        -1003297166224,
        -1003271941579,
        -1003212919486,
        -1003297440345,
        -1003285475111,
    ]

    for channel_id in channel_ids:
        await message.bot.send_message(
            chat_id=channel_id,
            text="Zahro Ulashova"
        )


@dp.message()
async def get_forwarded_channel_id(message: Message):
    if message.forward_from_chat:
        chat = message.forward_from_chat
        chat_info = f"""Channel ID: {chat.id}
Channel Titile: {chat.title} 
        """
        await message.answer(chat_info)


async def main() -> None:
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
