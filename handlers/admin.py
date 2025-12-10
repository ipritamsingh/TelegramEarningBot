import asyncio
from aiogram import Router, types, F, Bot
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
    get_user,  # <--- Added
    get_user_by_email,
    update_user_ban_status,
    admin_add_balance, 
    get_all_user_ids,
    set_daily_checkin_code,
    refund_user_balance,
    credit_referral_bonus # <--- Added for Bonus
)
from utils import shorten_link
# REFERRAL_REWARD ko config se import karna na bhulein
from config import ADMIN_IDS, BOT_TOKEN, REFERRAL_REWARD 

admin_router = Router()

def is_auth(user_id):
    return user_id in ADMIN_IDS

class AdminState(StatesGroup):
    waiting_for_user_search = State()
    waiting_for_balance_amount = State()
    waiting_for_broadcast = State()
    task_title = State()
    task_reward = State()
    task_link = State()
    task_code = State()
    waiting_for_shortener_selection = State()
    waiting_for_daily_code = State()

# ==========================================
# 🛠️ HELPER: KEYBOARDS
# ==========================================
def get_admin_dashboard_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Add New Task", callback_data="btn_add_task")
    kb.button(text="🔑 Set Check-in Code", callback_data="btn_set_code")
    kb.button(text="🗑️ Manage Tasks", callback_data="btn_manage_tasks")
    kb.button(text="👤 Search User", callback_data="btn_search_user")
    kb.button(text="📢 Broadcast", callback_data="btn_broadcast")
    kb.button(text="🔄 Refresh Stats", callback_data="btn_refresh")
    kb.adjust(2, 1, 2, 1)
    return kb.as_markup()

def get_cancel_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Cancel Operation", callback_data="btn_cancel")
    return kb.as_markup()

# ==========================================
# 1. MAIN DASHBOARD
# ==========================================
@admin_router.message(Command("start", "admin"))
async def admin_dashboard(message: types.Message, state: FSMContext):
    if not is_auth(message.from_user.id): return
    await state.clear() 

    # Unpack 4 values
    users, balance, tasks, active_today = await get_system_stats()
    
    msg = (
        "🛡️ **ADMIN CONTROL PANEL** 🛡️\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👥 **Total Users:** `{users}`\n"
        f"🟢 **Active Today:** `{active_today}`\n"
        f"💰 **Total Liability:** `₹{balance:.2f}`\n"
        f"📋 **Active Tasks:** `{tasks}`\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "👇 **Select an Action:**"
    )
    await message.answer(msg, reply_markup=get_admin_dashboard_kb())

@admin_router.callback_query(F.data == "btn_refresh")
async def refresh_stats(callback: types.CallbackQuery):
    if not is_auth(callback.from_user.id): return
    
    users, balance, tasks, active_today = await get_system_stats()
    msg = (
        "🛡️ **ADMIN CONTROL PANEL** 🛡️\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👥 **Total Users:** `{users}`\n"
        f"🟢 **Active Today:** `{active_today}`\n"
        f"💰 **Total Liability:** `₹{balance:.2f}`\n"
        f"📋 **Active Tasks:** `{tasks}`\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "👇 **Select an Action:**"
    )
    try: await callback.message.edit_text(msg, reply_markup=get_admin_dashboard_kb())
    except: await callback.answer("Stats are up to date!")

# ==========================================
# 2. SET DAILY CODE
# ==========================================
@admin_router.callback_query(F.data == "btn_set_code")
async def ask_daily_code(c: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.waiting_for_daily_code)
    await c.message.answer("🔑 **Enter New Check-in Code:**", reply_markup=get_cancel_kb())
    await c.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_daily_code))
async def save_daily_code(m: types.Message, state: FSMContext):
    code = m.text.strip()
    await set_daily_checkin_code(code)
    await m.answer(f"✅ **Code Saved:** `{code}`", reply_markup=get_admin_dashboard_kb())
    await state.clear()

# ==========================================
# 3. ADD TASK FLOW
# ==========================================
@admin_router.callback_query(F.data == "btn_add_task")
async def start_add_task(c: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.task_title)
    await c.message.answer("📝 **Step 1/4:** Enter Task Title:", reply_markup=get_cancel_kb())
    await c.answer()

@admin_router.message(StateFilter(AdminState.task_title))
async def set_title(m: types.Message, state: FSMContext):
    await state.update_data(title=m.text)
    await state.set_state(AdminState.task_reward)
    await m.answer("💰 **Step 2/4:** Enter Reward Amount:", reply_markup=get_cancel_kb())

@admin_router.message(StateFilter(AdminState.task_reward))
async def set_reward(m: types.Message, state: FSMContext):
    try:
        r = float(m.text)
        await state.update_data(reward=r)
        await state.set_state(AdminState.task_link)
        await m.answer("🔗 **Step 3/4:** Enter Link:", reply_markup=get_cancel_kb())
    except: await m.answer("❌ Invalid Number.")

@admin_router.message(StateFilter(AdminState.task_link))
async def set_link(m: types.Message, state: FSMContext):
    if "http" not in m.text: await m.answer("❌ Invalid Link."); return
    await state.update_data(link=m.text)
    await state.set_state(AdminState.task_code)
    await m.answer("🔐 **Step 4/4:** Enter Secret Code:", reply_markup=get_cancel_kb())

@admin_router.message(StateFilter(AdminState.task_code))
async def set_code_and_ask_type(m: types.Message, state: FSMContext):
    await state.update_data(code=m.text.strip())
    kb = InlineKeyboardBuilder()
    kb.button(text="🌍 All 3 (Bulk)", callback_data="create_all")
    kb.button(text="1️⃣ GPLinks Only", callback_data="create_gplinks")
    kb.button(text="2️⃣ ShrinkMe Only", callback_data="create_shrinkme")
    kb.button(text="3️⃣ ShrinkEarn Only", callback_data="create_shrinkearn")
    kb.button(text="❌ Cancel", callback_data="btn_cancel")
    kb.adjust(1)
    await m.answer("❓ **Which Shortener?**", reply_markup=kb.as_markup())
    await state.set_state(AdminState.waiting_for_shortener_selection)

@admin_router.callback_query(StateFilter(AdminState.waiting_for_shortener_selection))
async def final_create_task(c: types.CallbackQuery, state: FSMContext):
    choice = c.data
    data = await state.get_data()
    target_shorteners = []
    
    if choice == "btn_cancel":
        await state.clear(); await c.message.delete(); await admin_dashboard(c.message, state); return
    elif choice == "create_all": target_shorteners = ["gplinks", "shrinkme", "shrinkearn"]; msg_text = "⏳ Creating 3 Bulk Tasks..."
    elif choice == "create_gplinks": target_shorteners = ["gplinks"]; msg_text = "⏳ Creating GPLinks Task..."
    elif choice == "create_shrinkme": target_shorteners = ["shrinkme"]; msg_text = "⏳ Creating ShrinkMe Task..."
    elif choice == "create_shrinkearn": target_shorteners = ["shrinkearn"]; msg_text = "⏳ Creating ShrinkEarn Task..."
    
    await c.message.edit_text(msg_text)
    try:
        count = 0
        for s in target_shorteners:
            short = await shorten_link(data['link'], s)
            await add_bulk_task(f"{data['title']} ({s.upper()})", data['reward'], short, data['code'], s)
            count += 1
        await c.message.edit_text(f"✅ **Success!** Created {count} Task(s).\n📌 Title: {data['title']}")
    except Exception as e:
        await c.message.edit_text(f"❌ Error: {e}")
    
    await state.clear()
    await asyncio.sleep(2)
    await admin_dashboard(c.message, state)

# ==========================================
# 4. MANAGE TASKS
# ==========================================
@admin_router.callback_query(F.data == "btn_manage_tasks")
async def show_manage_list(c: types.CallbackQuery):
    tasks = await get_recent_tasks(10)
    if not tasks: await c.answer("Empty!", show_alert=True); return
    await c.message.answer("🗑️ **Delete Tasks:**")
    for t in tasks:
        kb = InlineKeyboardBuilder()
        kb.button(text="❌ Delete", callback_data=f"del_{t['_id']}")
        await c.message.answer(f"📌 {t['text']}\nCode: `{t['verification_code']}`", reply_markup=kb.as_markup())
    await c.answer()

@admin_router.callback_query(F.data.startswith("del_"))
async def delete_handler(c: types.CallbackQuery):
    if await delete_task_from_db(c.data.split("_")[1]): await c.message.edit_text("✅ Deleted!")
    else: await c.answer("Error.", show_alert=True)

# ==========================================
# 5. USER SEARCH & ACTIONS
# ==========================================
@admin_router.callback_query(F.data == "btn_search_user")
async def ask_search_query(c: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.waiting_for_user_search)
    await c.message.answer("👤 Enter **User ID** or **Email**:", reply_markup=get_cancel_kb())
    await c.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_user_search))
async def show_user_profile(m: types.Message, state: FSMContext):
    query = m.text.strip()
    u = None
    if query.isdigit(): u = await get_user_details(int(query))
    elif "@" in query: u = await get_user_by_email(query)
    else: await m.answer("❌ Invalid format."); return

    if not u: await m.answer("❌ User not found."); return

    kb = InlineKeyboardBuilder()
    if u.get('is_banned'): kb.button(text="✅ Unban", callback_data=f"act_unban_{u['user_id']}")
    else: kb.button(text="🚫 Ban", callback_data=f"act_ban_{u['user_id']}")
    kb.button(text="💰 Add Bal", callback_data=f"act_addbal_{u['user_id']}")
    kb.adjust(1)

    info = f"👤 **{u['first_name']}**\n🆔 `{u['user_id']}`\n📧 `{u.get('email')}`\n💰 ₹{u.get('balance', 0):.2f}\n🚫 Ban: {u.get('is_banned')}"
    await m.answer(info, reply_markup=kb.as_markup())
    await state.clear()

@admin_router.callback_query(F.data.startswith("act_"))
async def handle_user_action(c: types.CallbackQuery, state: FSMContext):
    parts = c.data.split("_")
    act, uid = parts[1], int(parts[2])

    if act == "ban":
        await update_user_ban_status(uid, True)
        await c.message.edit_text(c.message.text + "\n(BANNED)")
    elif act == "unban":
        await update_user_ban_status(uid, False)
        await c.message.edit_text(c.message.text + "\n(ACTIVE)")
    elif act == "addbal":
        await state.update_data(target_uid=uid)
        await state.set_state(AdminState.waiting_for_balance_amount)
        await c.message.answer(f"💰 Enter Amount for `{uid}`:", reply_markup=get_cancel_kb())
        await c.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_balance_amount))
async def process_add_balance(m: types.Message, state: FSMContext):
    try:
        amt = float(m.text)
        data = await state.get_data()
        await admin_add_balance(data['target_uid'], amt)
        await m.answer(f"✅ Added ₹{amt}")
        await state.clear()
        await admin_dashboard(m, state)
    except: await m.answer("Invalid Amount.")

# ==========================================
# 🔥 WITHDRAW APPROVAL LOGIC (Fixed)
# ==========================================
@admin_router.callback_query(F.data.startswith("wd_"))
async def handle_withdraw_action(c: types.CallbackQuery):
    parts = c.data.split("_")
    action = parts[1] # 'y' or 'n'
    user_id = int(parts[2])
    amount = float(parts[3])
    
    # User Bot se notification bhejna hai
    user_bot = Bot(token=BOT_TOKEN)
    
    if action == "y":
        # -----------------------------------------------
        # ✅ REFERRAL BONUS LOGIC ADDED HERE
        # -----------------------------------------------
        # Check karein user ka data
        user = await get_user(user_id)
        
        # Logic: Withdraw Request ke time count 1 ho gaya tha.
        # Isliye agar count == 1 hai, matlab ye Pehla Withdraw hai.
        if user and user.get("withdraw_count") == 1:
            referrer_id = user.get("referred_by")
            
            if referrer_id:
                # Bonus Dein
                await credit_referral_bonus(referrer_id, REFERRAL_REWARD)
                
                # Referrer ko Notify karein
                try:
                    await user_bot.send_message(
                        chat_id=referrer_id,
                        text=f"🎉 **Congratulations!**\n\nAapke friend ne apna pehla withdrawal kiya hai.\nAapko **₹{REFERRAL_REWARD}** ka Referral Bonus mila hai! 💰"
                    )
                except Exception as e:
                    print(f"Referrer Notify Error: {e}")
        # -----------------------------------------------

        # User ko Success msg bhejein
        try:
            await user_bot.send_message(
                chat_id=user_id,
                text=f"✅ **Withdrawal Approved!**\n\n💰 Amount: ₹{amount}\n🎉 Paisa aapke account me bhej diya gaya hai."
            )
        except Exception as e:
            print(f"Notify Error: {e}")
            
        await c.message.edit_text(c.message.text + "\n\n✅ **APPROVED BY ADMIN**")
        
    elif action == "n":
        # Decline: Refund Balance & Send Fail Message
        await refund_user_balance(user_id, amount)
        
        try:
            await user_bot.send_message(
                chat_id=user_id,
                text=f"❌ **Withdrawal Declined!**\n\n💰 Amount: ₹{amount}\n⚠️ Aapka paisa wapis wallet me add kar diya gaya hai.\nReason: Invalid Details."
            )
        except Exception as e:
            print(f"Notify Error: {e}")
            
        await c.message.edit_text(c.message.text + "\n\n❌ **DECLINED & REFUNDED**")
        
    await user_bot.session.close() # Close session
    await c.answer()

# ==========================================
# 6. BROADCAST
# ==========================================
@admin_router.callback_query(F.data == "btn_broadcast")
async def start_broadcast(c: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.waiting_for_broadcast)
    await c.message.answer("📢 Enter Message:", reply_markup=get_cancel_kb())
    await c.answer()

@admin_router.message(StateFilter(AdminState.waiting_for_broadcast))
async def send_broadcast(m: types.Message, state: FSMContext):
    msg_text = m.text
    status = await m.answer("⏳ Sending...")
    user_bot_sender = Bot(token=BOT_TOKEN)
    ids = await get_all_user_ids()
    count = 0
    
    for uid in ids:
        try:
            await user_bot_sender.send_message(uid, f"📢 **NOTICE**\n\n{msg_text}")
            count += 1
            await asyncio.sleep(0.05)
        except: pass
    
    await user_bot_sender.session.close()
    await status.edit_text(f"✅ Sent to {count} users.")
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