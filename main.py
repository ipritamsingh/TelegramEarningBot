import asyncio
import logging
import sys
import os
from aiogram import Bot, Dispatcher
from aiohttp import web
from config import BOT_TOKEN

# Note: Humne yaha se database import hata diya hai
# Kyunki ab saara kaam handlers/user.py aur handlers/admin.py kar rahe hain

from handlers.admin import admin_router
from handlers.user import user_router

# Logging setup
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

# Bot setup
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Routers jodna (Admin aur User logic)
dp.include_router(admin_router)
dp.include_router(user_router)

# --- FAKE WEB SERVER (Render Keep-Alive) ---
async def handle(request):
    return web.Response(text="Bot is Live & Running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    # Render PORT variable use karega
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Web server started on port {port}")

# --- MAIN ENGINE ---
async def main():
    logging.info("Starting Bot + Web Server...")
    
    # Bot delete webhook (Conflicts rokne ke liye)
    await bot.delete_webhook(drop_pending_updates=True)

    await asyncio.gather(
        dp.start_polling(bot),
        start_web_server()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped!")