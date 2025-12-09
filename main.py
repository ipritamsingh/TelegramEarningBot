import asyncio
import logging
import sys
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiohttp import web # Ye hum fake server ke liye use karenge
from config import BOT_TOKEN
from database import add_user

# Logging setup
logging.basicConfig(level=logging.INFO, stream=sys.stdout)




# ... purane imports ...
from handlers.admin import admin_router # Import kiya

# Bot setup
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Router Connect karna
dp.include_router(admin_router)

# --- USER HANDLERS (Isse baad me alag file me dalenge) ---


# --- HANDLERS ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user = message.from_user
    is_new = await add_user(user.id, user.first_name, user.username)
    if is_new:
        await message.answer(f"Welcome {user.first_name}! 🚀\nAapka account create kar diya gaya hai.")
    else:
        await message.answer(f"Welcome back {user.first_name}! 👋\nAap pehle se register hain.")

# --- FAKE WEB SERVER (Render ko khush rakhne ke liye) ---
async def handle(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    # Render PORT environment variable deta hai, use wo use karna padega
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Web server started on port {port}")

# --- MAIN ENGINE ---
async def main():
    logging.info("Starting Bot + Web Server...")
    
    # Hum dono kaam ek saath karenge: Bot Polling + Web Server
    await asyncio.gather(
        dp.start_polling(bot),
        start_web_server()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped!")