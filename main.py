import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from config import BOT_TOKEN
from database import add_user # Humara banaya hua database function import kiya

# Logging setup
logging.basicConfig(level=logging.INFO)

# Bot init
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- HANDLERS ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user = message.from_user
    
    # 1. Database me user ko save karo
    is_new = await add_user(user.id, user.first_name, user.username)
    
    # 2. User ko reply karo
    if is_new:
        await message.answer(f"Welcome {user.first_name}! 🚀\nAapka account create kar diya gaya hai.")
    else:
        await message.answer(f"Welcome back {user.first_name}! 👋\nAap pehle se register hain.")

# --- MAIN ---
async def main():
    print("Bot is starting with Database...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped!")