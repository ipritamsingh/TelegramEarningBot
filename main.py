import asyncio
import logging
import sys
import os
from aiogram import Bot, Dispatcher
from aiohttp import web
from config import BOT_TOKEN, ADMIN_BOT_TOKEN # Dono tokens import kiye

# Routers
from handlers.user import user_router
from handlers.admin import admin_router

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

# --- 1. SETUP USER BOT (Users ke liye) ---
if not BOT_TOKEN:
    logging.error("❌ BOT_TOKEN missing! User bot nahi chalega.")
    sys.exit(1)

user_bot = Bot(token=BOT_TOKEN)
dp_user = Dispatcher()
# User Bot me sirf User wale commands (Tasks, Balance) honge
dp_user.include_router(user_router)

# --- 2. SETUP ADMIN BOT (Control ke liye) ---
admin_bot = None
dp_admin = None

if ADMIN_BOT_TOKEN:
    logging.info("✅ Admin Bot Token Found! Setting up Admin Bot...")
    admin_bot = Bot(token=ADMIN_BOT_TOKEN)
    dp_admin = Dispatcher()
    # Admin Bot me sirf Admin wale commands (Add Task, Ban) honge
    dp_admin.include_router(admin_router)
else:
    logging.warning("⚠️ ADMIN_BOT_TOKEN nahi mila. Sirf User Bot chalega.")

# --- 3. FAKE WEB SERVER (Render Keep-Alive) ---
async def handle(request):
    return web.Response(text="Apex System is Live (Dual Bot Running)!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"🌍 Web server started on port {port}")

# --- 4. MAIN ENGINE ---
async def main():
    logging.info("🚀 Starting Apex Dual Bot System...")
    
    # Conflict Errors rokne ke liye purane updates delete karo
    await user_bot.delete_webhook(drop_pending_updates=True)
    
    # Tasks list (Jo cheezein chalani hain)
    tasks = [
        dp_user.start_polling(user_bot), # User Bot start
        start_web_server()               # Web Server start
    ]
    
    # Agar Admin Bot set hai, to use bhi chalao
    if admin_bot:
        await admin_bot.delete_webhook(drop_pending_updates=True)
        tasks.append(dp_admin.start_polling(admin_bot))
        logging.info("🛡️ Admin Bot is Active & Listening!")
    
    # Sabko ek saath run karo
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Bots Stopped Manually!")