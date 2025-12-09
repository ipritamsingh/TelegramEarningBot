import asyncio
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database import (
    add_bulk_task, 
    get_recent_tasks, 
    delete_task_from_db,
    get_system_stats,      # New
    get_user_details,      # New
    update_user_ban_status,# New
    admin_add_balance,     # New
    get_all_user_ids       # New
)
from utils import shorten_link
from config import ADMIN_IDS

admin_router = Router()

# --- SECURITY CHECK (Gatekeeper) ---
# Ye check karega ki command dene wala asli Admin hai ya nahi
def is_authorized(user_id):
    return user_id in ADMIN_IDS

# ==========================================
# 1. ADMIN DASHBOARD (/start ya /admin)
# ==========================================
@admin_router.message(Command("start", "admin"))
async def cmd_admin_dashboard(message: types.Message):
    # Agar Admin nahi hai to ignore karo
    if not is_authorized(message.from_user.id): return

    # Database se stats nikalo
    users, balance, tasks = await get_system_stats()
    
    msg = (
        "🔐 **SECURE ADMIN CONTROL PANEL** 🔐\n"
        "Welcome Admin! Yahan se poora system control karein.\n\n"
        f"👥 **Total Users:** {users}\n"
        f"💰 **Total Liability:** ₹{balance:.2f}\n"
        f"📋 **Active Tasks:** {tasks}\n\n"
        "**👇 Available Commands:**\n"
        "`/addbulk Title, Reward, Link, Code` (Add Tasks)\n"
        "`/managetasks` (Delete Tasks)\n"
        "`/user ID` (Check User Info)\n"
        "`/ban ID` (Ban User)\n"
        "`/unban ID` (Unban User)\n"
        "`/give ID Amount` (Add Balance)\n"
        "`/broadcast Message` (Send to All)"
    )
    await message.answer(msg)

# ==========================================
# 2. BULK TASK ADDING (Aapka Purana Code Modified)
# ==========================================
@admin_router.message(Command("addbulk"))
async def cmd_bulk_add(message: types.Message):
    if not is_authorized(message.from_user.id): return

    try:
        # Expected Format: /addbulk Title, Reward, Link, Code
        if "/addbulk " not in message.text:
            await message.answer("❌ **Error:** Format galat hai.\nUse: `/addbulk Title, 1.5, https://link.com, CODE123`")
            return

        args = message.text.split("/addbulk ", 1)[1]
        parts = args.split(",")
        
        if len(parts) != 4:
            await message.answer("❌ **Error:** 4 cheezein chahiye.\n`Title, Reward, Link, Code`")
            return

        name = parts[0].strip()
        reward = parts[1].strip()
        long_link = parts[2].strip()
        code = parts[3].strip()

        status_msg = await message.answer("⏳ **Processing...**\n3 Shorteners ke links generate ho rahe hain.")
        
        # 3 Shorteners Logic
        shorteners = ["gplinks", "shrinkme", "shrinkearn"]
        
        for s_type in shorteners:
            # 1. Link Shorten
            short_url = await shorten_link(long_link, s_type)
            
            # 2. Save to DB
            task_text = f"{name} ({s_type.upper()})"
            await add_bulk_task(task_text, reward, short_url, code, s_type)

        await status_msg.edit_text(
            f"✅ **Success!**\n"
            f"Original: {name}\n"
            f"Created 3 Tasks: GP -> ShrinkMe -> ShrinkEarn"
        )

    except Exception as e:
        await message.answer(f"❌ **Error:** {str(e)}")

# ==========================================
# 3. MANAGE & DELETE TASKS
# ==========================================
@admin_router.message(Command("managetasks"))
async def cmd_manage_tasks(message: types.Message):
    if not is_authorized(message.from_user.id): return

    # Last 10 tasks lao
    tasks = await get_recent_tasks(limit=10)

    if not tasks:
        await message.answer("📂 Database me koi Task nahi hai.")
        return

    await message.answer("🗑️ **Delete Tasks:**\nNiche diye gaye buttons se task delete karein.")

    for task in tasks:
        task_id = str(task["_id"])
        
        kb = InlineKeyboardBuilder()
        kb.button(text="❌ Delete This Task", callback_data=f"del_{task_id}")
        
        info_text = (
            f"📌 **{task['text']}**\n"
            f"💰 ₹{task['reward']} | 🔐 Code: `{task['verification_code']}`"
        )
        await message.answer(info_text, reply_markup=kb.as_markup())

@admin_router.callback_query(F.data.startswith("del_"))
async def handle_delete_task(callback: types.CallbackQuery):
    if not is_authorized(callback.from_user.id): return

    task_id = callback.data.split("_")[1]
    
    # DB se delete karo
    if await delete_task_from_db(task_id):
        await callback.answer("✅ Task Deleted!")
        await callback.message.delete() # Message hata do
    else:
        await callback.answer("❌ Error: Task nahi mila.", show_alert=True)

# ==========================================
# 4. USER MANAGEMENT (Check, Ban, Give Money)
# ==========================================

# -- CHECK USER INFO --
@admin_router.message(Command("user"))
async def cmd_user_info(message: types.Message):
    if not is_authorized(message.from_user.id): return
    try:
        # User ID nikalo command se
        target_id = int(message.text.split()[1])
        user = await get_user_details(target_id)
        
        if user:
            msg = (
                f"👤 **User Details:**\n"
                f"Name: {user['first_name']}\n"
                f"ID: `{user['user_id']}`\n"
                f"📧 Email: {user.get('email', 'N/A')}\n"
                f"💰 Balance: ₹{user.get('balance', 0):.2f}\n"
                f"🚫 Banned: {user.get('is_banned', False)}\n"
                f"📅 Joined: {user.get('joining_date', 'Unknown')}"
            )
            await message.answer(msg)
        else:
            await message.answer("❌ User nahi mila database me.")
    except:
        await message.answer("❌ Format: `/user 12345678`")

# -- BAN USER --
@admin_router.message(Command("ban"))
async def cmd_ban(message: types.Message):
    if not is_authorized(message.from_user.id): return
    try:
        uid = int(message.text.split()[1])
        await update_user_ban_status(uid, True)
        await message.answer(f"🚫 User {uid} has been **BANNED**.")
    except:
        await message.answer("❌ Format: `/ban 12345678`")

# -- UNBAN USER --
@admin_router.message(Command("unban"))
async def cmd_unban(message: types.Message):
    if not is_authorized(message.from_user.id): return
    try:
        uid = int(message.text.split()[1])
        await update_user_ban_status(uid, False)
        await message.answer(f"✅ User {uid} has been **UNBANNED**.")
    except:
        await message.answer("❌ Format: `/unban 12345678`")

# -- GIVE BALANCE (Add Money) --
@admin_router.message(Command("give"))
async def cmd_give(message: types.Message):
    if not is_authorized(message.from_user.id): return
    try:
        args = message.text.split()
        uid = int(args[1])
        amount = float(args[2])
        
        if await admin_add_balance(uid, amount):
            await message.answer(f"💰 ₹{amount} added to User {uid} successfully.")
        else:
            await message.answer("❌ User not found.")
    except:
        await message.answer("❌ Format: `/give ID Amount` (e.g., `/give 12345 50`)")

# -- BROADCAST (Send Message to All) --
@admin_router.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message):
    if not is_authorized(message.from_user.id): return
    
    # Message text nikalo
    msg_text = message.text.split("/broadcast ", 1)[1] if len(message.text.split()) > 1 else None
    
    if not msg_text:
        await message.answer("❌ Message likhein. Ex: `/broadcast Hello All`")
        return

    status = await message.answer("📢 **Sending Broadcast...**")
    
    # Database se IDs lao
    all_ids = await get_all_user_ids()
    count = 0
    
    # Note: Admin Bot sirf unhe bhej payega jinhone Admin Bot start kiya hai.
    # Lekin database update sabka ho raha hai.
    for uid in all_ids:
        try:
            await message.bot.send_message(uid, f"📢 **Admin Notice:**\n\n{msg_text}")
            count += 1
            await asyncio.sleep(0.05) # Flood wait avoid karne ke liye
        except:
            pass # Agar block kiya hai to ignore karo
            
    await status.edit_text(f"✅ **Broadcast Sent!**\nSuccess: {count} users")