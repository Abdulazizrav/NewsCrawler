import asyncio
import logging
import sys
import os
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, html, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(BASE_DIR, ".env"))

TOKEN = os.getenv("BOT_TOKEN")
dp = Dispatcher()



@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    await message.answer(f"Hello, {html.bold(message.from_user.full_name)}!")

@dp.channel_post()
async def get_channel_id(message: types.Message):
    print("CHANNEL ID:", message.chat.id)


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
