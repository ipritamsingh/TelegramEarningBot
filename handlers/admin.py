import asyncio
from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database import (
    add_bulk_task, 
    get_recent_tasks, 
    delete_task_from_db,
    get_system_stats, 
    get_user_details, 
    get_user_by_email,  # <--- Email Search Function
    update_user_ban_status,
    admin_add_balance, 
    get_all_user_ids
)
from utils import shorten_link
from config import ADMIN_IDS

admin_router = Router()

# --- SECURITY: GATEKEEPER ---
def is_auth(user_id):
    return user_id in ADMIN_IDS

# --- STATES (FSM) ---
class AdminState(StatesGroup):
    # User Operations
    waiting_for_user_search = State() # ID or Email input
    waiting_for_balance_amount = State()
    
    # Broadcast
    waiting_for_broadcast = State()
    
    # Add Task Process
    task_title = State()
    task_reward = State()
    task_link = State()
    task_code = State()
    waiting_for_shortener_selection = State() # Single vs Bulk Selection

# ==========================================
# 🛠️ HELPER: KEYBOARDS (UI)
# ==========================================
def get_admin_dashboard_kb():
    kb = InlineKeyboardBuilder()
    # Row 1
    kb.button(text="➕ Add New Task", callback_data="btn_add_task")
    kb.button(text="🗑️ Manage Tasks", callback_data="btn_manage_tasks")
    # Row 2
    kb.button(text="👤 Search User", callback_data="btn_search_user")
    kb.button(text="📢 Broadcast", callback_data="btn_broadcast")
    # Row 3
    kb.button(text="🔄 Refresh Stats", callback_data="btn_refresh")
    
    kb.adjust(2, 2, 1)
    return kb.as_markup()

def get_cancel_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Cancel Operation", callback_data="btn_cancel")
    return kb.as_markup()

# ==========================================
# 1. MAIN DASHBOARD (/start or /admin)
# ==========================================
@admin_router.message(Command("start", "admin"))
async def admin_dashboard(message: types.Message, state: FSMContext):
    if not is_auth(message.from_user.id): return
    await state.clear() # Reset any ongoing process

    users, balance, tasks = await get_system_stats()
    
    msg = (
        "🛡️ **ADMIN CONTROL PANEL** 🛡️\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👥 **Total Users:** `{users}`\n"
        f"💰 **Total Liability:** `₹{balance:.2f}`\n"
        f"📋 **Active Tasks:** `{tasks}`\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "👇 **Select an Action:**"
    )
    await message.answer(msg, reply_markup=get_admin_dashboard_kb())

@admin_router.callback_query(F.data == "btn_refresh")
async def refresh_stats(callback: types.CallbackQuery):
    if not is_auth(callback.from_user.id): return
    
    users, balance, tasks = await get_system_stats()
    msg = (
        "🛡️ **ADMIN CONTROL PANEL** 🛡️\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👥 **Total Users:** `{users}`\n"
        f"💰 **Total Liability:** `₹{balance:.2f}`\n"
        f"📋 **Active Tasks:** `{tasks}`\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "👇 **Select an Action:**"
    )
    try: await callback.message.edit_text(msg, reply_markup=get_admin_dashboard_kb())
    except: await callback.answer("Stats are up to date!")

# ==========================================
# 2. ADD TASK FLOW (Step-by-Step)
# ==========================================
@admin_router.callback_query(F.data == "btn_add_task")
async def start_add_task(c: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.task_title)
    await c.message.answer("📝 **Step 1/4:**\nEnter Task Title (e.g. `Viral Video`)", reply_markup=get_cancel_kb())
    await c.answer()

@admin_router.message(StateFilter(AdminState.task_title))
async def set_title(m: types.Message, state: FSMContext):
    await state.update_data(title=m.text)
    await state.set_state(AdminState.task_reward)
    await m.answer("💰 **Step 2/4:**\nEnter Reward Amount (e.g. `1.5`)", reply_markup=get_cancel_kb())

@admin_router.message(StateFilter(AdminState.task_reward))
async def set_reward(m: types.Message, state: FSMContext):
    try:
        r = float(m.text)
        await state.update_data(reward=r)
        await state.set_state(AdminState.task_link)
        await m.answer("🔗 **Step 3/4:**\nEnter Destination Link (e.g. `https://t.me/post/10`)", reply_markup=get_cancel_kb())
    except: await m.answer("❌ Invalid Number. Sirf number likhein.")

@admin_router.message(StateFilter(AdminState.task_link))
async def set_link(m: types.Message, state: FSMContext):
    if "http" not in m.text:
        await m.answer("❌ Link must start with http or https.")
        return
    await state.update_data(link=m.text)
    await state.set_state(AdminState.task_code)
    await m.answer("🔐 **Step 4/4:**\nEnter Secret Verification Code:", reply_markup=get_cancel_kb())

@admin_router.message(StateFilter(AdminState.task_code))
async def set_code_and_ask_type(m: types.Message, state: FSMContext):
    await state.update_data(code=m.text.strip())
    
    # Selection Menu
    kb = InlineKeyboardBuilder()
    kb.button(text="🌍 All 3 (Bulk)", callback_data="create_all")
    kb.button(text="1️⃣ GPLinks Only", callback_data="create_gplinks")
    kb.button(text="2️⃣ ShrinkMe Only", callback_data="create_shrinkme")
    kb.button(text="3️⃣ ShrinkEarn Only", callback_data="create_shrinkearn")
    kb.button(text="❌ Cancel", callback_data="btn_cancel")
    kb.adjust(1)

    await m.answer("❓ **Which Shortener to use?**", reply_markup=kb.as_markup())
    await state.set_state(AdminState.waiting_for_shortener_selection)

@admin_router.callback_query(StateFilter(AdminState.waiting_for_shortener_selection))
async def final_create_task(c: types.CallbackQuery, state: FSMContext):
    choice = c.data
    data = await state.get_data()
    
    target_shorteners = []
    
    if choice == "btn_cancel":
        await state.clear(); await c.message.delete(); await admin_dashboard(c.message, state); return
    elif choice == "create_all":
        target_shorteners = ["gplinks", "shrinkme", "shrinkearn"]
        msg_text = "⏳ Creating 3 Bulk Tasks..."
    elif choice == "create_gplinks":
        target_shorteners = ["gplinks"]
        msg_text = "⏳ Creating GPLinks Task..."
    elif choice == "create_shrinkme":
        target_shorteners = ["shrinkme"]
        msg_text = "⏳ Creating ShrinkMe Task..."
    elif choice == "create_shrinkearn":
        target_shorteners = ["shrinkearn"]
        msg_text = "⏳ Creating ShrinkEarn Task..."
    
    await c.message.edit_text(msg_text)
    
    try:
        count = 0
        for s in target_shorteners:
            short = await shorten_link(data['link'], s)
            await add_bulk_task(f"{data['title']} ({s.upper()})", data['reward'], short, data['code'], s)
            count += 1
            
        await c.message.edit_text(
            f"✅ **Success!**\n"
            f"Created {count} Task(s).\n"
            f"📌 Title: {data['title']}"
        )
    except Exception as e:
        await c.message.edit_text(f"❌ Error: {e}")
    
    await state.clear()
    await asyncio.sleep(2)
    await admin_dashboard(c.message, state)

# ==========================================
# 3. MANAGE & DELETE TASKS
# ==========================================
@admin_router.callback_query(F.data == "btn_manage_tasks")
async def show_manage_list(c: types.CallbackQuery):
    tasks = await get_recent_tasks(10)
    if not tasks: await c.answer("📂 Database Empty!", show_alert=True); return

    await c.message.answer("🗑️ **Recent Tasks:**\nClick Delete to remove forever.")
    for t in tasks:
        kb = InlineKeyboardBuilder()
        kb.button(text="❌ Delete Task", callback_data=f"del_{t['_id']}")
        await c.message.answer(f"📌 {t['text']}\nCode: `{t['verification_code']}`", reply_markup=kb.as_markup())
    await c.answer()

@admin_router.callback_query(F.data.startswith("del_"))
async def delete_handler(c: types.CallbackQuery):
    if await delete_task_from_db(c.data.split("_")[1]):
        await c.message.edit_text("✅ **Task Deleted!**")
    else: await c.answer("Error.", show_alert=True)

# ==========================================
# 4. USER SEARCH (ID or Email) & ACTIONS
# ==========================================
@admin_router.callback_query(F.data == "btn_search_user")
async def ask_search_query(c: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.waiting_for_user_search)
    await c.message.answer("👤 **Search User:**\nEnter **User ID** OR **Email**:", reply_markup=get_cancel_kb())
    await c.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_user_search))
async def show_user_profile(m: types.Message, state: FSMContext):
    query = m.text.strip()
    u = None

    # Logic: Agar number hai to ID, warna Email
    if query.isdigit():
        u = await get_user_details(int(query))
    elif "@" in query:
        u = await get_user_by_email(query)
    else:
        await m.answer("❌ Invalid. Number (ID) ya Email daalein.")
        return

    if not u:
        await m.answer("❌ User not found.")
        return

    # Profile & Buttons
    kb = InlineKeyboardBuilder()
    if u.get('is_banned'): kb.button(text="✅ Unban User", callback_data=f"act_unban_{u['user_id']}")
    else: kb.button(text="🚫 Ban User", callback_data=f"act_ban_{u['user_id']}")
    
    kb.button(text="💰 Add Balance", callback_data=f"act_addbal_{u['user_id']}")
    kb.adjust(1)

    info = (
        f"👤 **USER PROFILE**\n"
        f"━━━━━━━━━━━━\n"
        f"📛 Name: **{u['first_name']}**\n"
        f"🆔 ID: `{u['user_id']}`\n"
        f"📧 Email: `{u.get('email', 'N/A')}`\n"
        f"━━━━━━━━━━━━\n"
        f"💰 **Balance:** ₹{u.get('balance', 0):.2f}\n"
        f"✅ **Tasks Today:** {u.get('daily_task_count', 0)}/6\n"
        f"🚫 **Status:** {'BANNED' if u.get('is_banned') else 'Active'}\n"
        f"📅 Joined: {u.get('joining_date', '-')}"
    )
    await m.answer(info, reply_markup=kb.as_markup())
    await state.clear()

# --- ACTIONS (Ban/Unban/Add Money) ---
@admin_router.callback_query(F.data.startswith("act_"))
async def handle_user_action(c: types.CallbackQuery, state: FSMContext):
    parts = c.data.split("_")
    action, uid = parts[1], int(parts[2])

    if action == "ban":
        await update_user_ban_status(uid, True)
        await c.answer("User Banned!")
        await c.message.edit_text(c.message.text + "\n\n🚫 **STATUS: BANNED**")

    elif action == "unban":
        await update_user_ban_status(uid, False)
        await c.answer("User Unbanned!")
        await c.message.edit_text(c.message.text + "\n\n✅ **STATUS: ACTIVE**")

    elif action == "addbal":
        await state.update_data(target_uid=uid)
        await state.set_state(AdminState.waiting_for_balance_amount)
        await c.message.answer(f"💰 **Enter Amount to Add for ID `{uid}`:**", reply_markup=get_cancel_kb())
        await c.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_balance_amount))
async def process_add_balance(m: types.Message, state: FSMContext):
    try:
        amt = float(m.text)
        data = await state.get_data()
        uid = data['target_uid']
        
        await admin_add_balance(uid, amt)
        await m.answer(f"✅ **Success!** Added ₹{amt} to User `{uid}`.")
        await state.clear()
        await admin_dashboard(m, state)
    except:
        await m.answer("❌ Invalid Amount. Sirf number daalein.")

# ==========================================
# 5. BROADCAST
# ==========================================
@admin_router.callback_query(F.data == "btn_broadcast")
async def start_broadcast(c: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.waiting_for_broadcast)
    await c.message.answer("📢 **Enter Message to Broadcast:**\n(Sabhi users ko jayega)", reply_markup=get_cancel_kb())
    await c.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_broadcast))
async def send_broadcast(m: types.Message, state: FSMContext):
    msg_text = m.text
    status = await m.answer("⏳ **Sending Broadcast...**")
    
    ids = await get_all_user_ids()
    count = 0
    blocked = 0
    
    for uid in ids:
        try:
            await m.bot.send_message(uid, f"📢 **ADMIN NOTICE**\n\n{msg_text}")
            count += 1
            await asyncio.sleep(0.05) # Flood limit safe
        except:
            blocked += 1
    
    await status.edit_text(f"✅ **Broadcast Complete!**\nSent: {count}\nFailed/Blocked: {blocked}")
    await state.clear()
    await asyncio.sleep(2)
    await admin_dashboard(m, state)

# ==========================================
# CANCEL BUTTON
# ==========================================
@admin_router.callback_query(F.data == "btn_cancel")
async def cancel_operation(c: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await c.message.delete()
    await c.answer("Cancelled")
    await admin_dashboard(c.message, state)