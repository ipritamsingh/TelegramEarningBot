from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database import add_bulk_task, get_recent_tasks, delete_task_from_db
from utils import shorten_link
from config import ADMIN_IDS

admin_router = Router()

# --- 1. BULK TASK ADD (Purana wala logic) ---
@admin_router.message(Command("addbulk"))
async def cmd_bulk_add(message: types.Message):
    # Security Check
    if message.from_user.id not in ADMIN_IDS:
        return

    try:
        # Expected Format: /addbulk Title, Reward, Link, Code
        if "/addbulk " not in message.text:
            await message.answer("❌ **Error:** Format galat hai.\nUse: `/addbulk Title, 1.5, https://link.com, CODE123`")
            return

        args = message.text.split("/addbulk ", 1)[1]
        parts = args.split(",")
        
        if len(parts) != 4:
            await message.answer("❌ **Error:** 4 cheezein chahiye (comma se alag).\nExample: `Title, Reward, Link, Code`")
            return

        name = parts[0].strip()
        reward = parts[1].strip()
        long_link = parts[2].strip()
        code = parts[3].strip()

        status_msg = await message.answer("⏳ **Processing...**\n3 Shorteners ke links bana raha hoon.")
        
        # 3 Shorteners ke liye loop
        shorteners = ["gplinks", "shrinkme", "shrinkearn"]
        
        count = 0
        for s_type in shorteners:
            # Link Shorten
            short_url = await shorten_link(long_link, s_type)
            
            # DB me save (Name me shortener ka naam add kar denge taaki admin ko pata rahe)
            task_text = f"{name} ({s_type.upper()})"
            await add_bulk_task(task_text, reward, short_url, code, s_type)
            count += 1

        await status_msg.edit_text(
            f"✅ **Success!**\n"
            f"Total {count} Tasks Created.\n"
            f"Sequence: GP -> ShrinkMe -> ShrinkEarn"
        )

    except Exception as e:
        await message.answer(f"❌ **Error:** {str(e)}")


# --- 2. MANAGE TASKS (List & Delete) ---
@admin_router.message(Command("managetasks"))
async def cmd_manage_tasks(message: types.Message):
    if message.from_user.id not in ADMIN_IDS: return

    # Last 10 tasks lao
    tasks = await get_recent_tasks(limit=10)

    if not tasks:
        await message.answer("📂 Database me koi Task nahi hai.")
        return

    await message.answer("🛠️ **Recent 10 Tasks:**\nDelete karne ke liye button dabayein.")

    for task in tasks:
        task_id = str(task["_id"])
        text = task["text"]
        reward = task["reward"]
        code = task["verification_code"]

        # Delete Button Banao
        kb = InlineKeyboardBuilder()
        kb.button(text="🗑️ Delete Task", callback_data=f"del_{task_id}")
        
        info_text = (
            f"📌 **{text}**\n"
            f"💰 ₹{reward} | 🔐 Code: `{code}`\n"
            f"🆔 `{task_id}`"
        )
        
        await message.answer(info_text, reply_markup=kb.as_markup())


# --- 3. DELETE BUTTON HANDLER ---
@admin_router.callback_query(F.data.startswith("del_"))
async def handle_delete_task(callback: types.CallbackQuery):
    # Security Check (Sirf Admin delete kar sake)
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Aap Admin nahi hain!", show_alert=True)
        return

    task_id = callback.data.split("_")[1]
    
    # DB se delete karo
    success = await delete_task_from_db(task_id)
    
    if success:
        await callback.answer("✅ Task Deleted!")
        # Message update karke batao ki delete ho gaya
        await callback.message.edit_text(f"🗑️ **Task Deleted Successfully!**\n(ID: {task_id})")
    else:
        await callback.answer("❌ Error: Task nahi mila ya pehle hi delete ho gaya.", show_alert=True)