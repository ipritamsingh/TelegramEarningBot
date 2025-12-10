import re
import asyncio # Required for delay
from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from database import (
    get_user, 
    create_user, 
    get_next_task_for_user, 
    get_task_details, 
    mark_task_complete,
    mark_user_renewed,
    check_user_renewed_today,
    get_daily_checkin_code # Ensure this exists in database.py
)
from config import FORCE_SUB_CHANNEL_ID, FORCE_SUB_LINK, SUPPORT_BOT_USERNAME

user_router = Router()

# --- STATES ---
class UserState(StatesGroup):
    waiting_for_email = State()
    waiting_for_task_code = State()
    waiting_for_daily_checkin_code = State() # For daily unlock code

# ==========================================
# 🛠️ HELPERS
# ==========================================

def get_main_menu():
    kb = ReplyKeyboardBuilder()
    kb.button(text="🔓 Unlock Task Today") 
    kb.button(text="🚀 Start Task")
    kb.button(text="💰 My Balance")
    kb.button(text="ℹ️ Help / Rules")
    kb.adjust(1, 2, 1)
    return kb.as_markup(resize_keyboard=True)

def get_join_channel_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="📢 Join Official Channel", url=FORCE_SUB_LINK)
    kb.button(text="✅ Check & Verify", callback_data="check_subscription")
    kb.adjust(1)
    return kb.as_markup()

async def is_user_subscribed(bot, user_id):
    try:
        channel_id = int(FORCE_SUB_CHANNEL_ID)
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        if member.status in ['creator', 'administrator', 'member']:
            return True
        return False
    except Exception as e:
        print(f"[ERROR] Force Sub Check Failed: {e}")
        return False 

async def check_and_show_dashboard(message, user_id, first_name):
    if await is_user_subscribed(message.bot, user_id):
        await message.answer(
            f"🎉 **Verification Successful!**\n\nWelcome {first_name}! 👇\n"
            "Aaj ke tasks shuru karne ke liye **'🔓 Unlock Task Today'** par click karein:",
            reply_markup=get_main_menu()
        )
    else:
        await message.answer(
            f"⚠️ **Action Required!**\n\nHello {first_name}, bot use karne ke liye hamara Channel join karna zaroori hai.",
            reply_markup=get_join_channel_kb()
        )

# ==========================================
# 1. START COMMAND
# ==========================================
@user_router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user = await get_user(user_id)

    if user:
        if user.get("is_banned", False):
            await message.answer("🚫 **You are BANNED!**\nContact Admin."); return
        await check_and_show_dashboard(message, user_id, message.from_user.first_name)
        return

    await message.answer("👋 **Welcome!**\nAccount banane ke liye apna **Email** bhejein.")
    await state.set_state(UserState.waiting_for_email)

# ==========================================
# 2. EMAIL FLOW
# ==========================================
@user_router.message(StateFilter(UserState.waiting_for_email))
async def process_email(message: types.Message, state: FSMContext):
    email = message.text.strip()
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        await message.answer("❌ Invalid Email."); return

    await create_user(message.from_user.id, message.from_user.first_name, message.from_user.username, email)
    await state.clear()
    await check_and_show_dashboard(message, message.from_user.id, message.from_user.first_name)

@user_router.callback_query(F.data == "check_subscription")
async def verify_click(callback: types.CallbackQuery):
    if await is_user_subscribed(callback.bot, callback.from_user.id):
        await callback.message.delete()
        await callback.message.answer(
            "✅ **Verified!** Access Granted.\nAb **🔓 Unlock Task Today** par click karein 👇", 
            reply_markup=get_main_menu()
        )
    else:
        await callback.answer("❌ Join nahi kiya!", show_alert=True)

# ==========================================
# 🔥 NEW: 3-STEP SECURE UNLOCK LOGIC
# ==========================================
@user_router.message(F.text == "🔓 Unlock Task Today")
async def unlock_task_request(message: types.Message):
    # 1. Link Preparation
    channel_link = str(FORCE_SUB_LINK).strip()
    if not channel_link.startswith("http"):
        channel_link = f"https://{channel_link}"
    
    # 2. Initial Button (Only Red Button)
    kb_initial = InlineKeyboardBuilder()
    kb_initial.button(text="🔴 Open & Unlock", url=channel_link)
    
    # Send Message
    msg = await message.answer(
        "🔒 **Unlock Process Started...**\n\n"
        "1️⃣ Upar **Red Button** par click karein aur Channel me **Check-in Code** dekhein.\n"
        "2️⃣ **3 Second wait karein**, Submit button appear hoga...",
        reply_markup=kb_initial.as_markup()
    )

    # 3. Wait for 3 Seconds (User goes to channel)
    await asyncio.sleep(3)

    # 4. Update Message (Show Submit Button)
    kb_final = InlineKeyboardBuilder()
    kb_final.button(text="🔴 Open & Unlock", url=channel_link)
    kb_final.button(text="✅ Submit & Unlock", callback_data="ask_daily_code") # Triggers input
    kb_final.adjust(1)

    try:
        await msg.edit_reply_markup(reply_markup=kb_final.as_markup())
    except:
        pass # Ignore if user deleted message

# --- ASK CODE HANDLER ---
@user_router.callback_query(F.data == "ask_daily_code")
async def ask_checkin_code(c: types.CallbackQuery, state: FSMContext):
    await state.set_state(UserState.waiting_for_daily_checkin_code)
    await c.message.answer("⌨️ **Enter Today's Check-in Code:**\n(Jo aapne channel par dekha)")
    await c.answer()

# --- VERIFY CODE HANDLER ---
@user_router.message(StateFilter(UserState.waiting_for_daily_checkin_code))
async def verify_daily_code(m: types.Message, state: FSMContext):
    user_input = m.text.strip()
    
    # Database se Admin ka set kiya hua code lao
    real_code = await get_daily_checkin_code()
    
    if not real_code:
        await m.answer("⚠️ Admin ne aaj ka Code set nahi kiya hai. Please wait.")
        await state.clear()
        return

    # Check Logic (Case Insensitive)
    if user_input.lower() == real_code.lower():
        # SUCCESS: Update Database (Unlock Task)
        await mark_user_renewed(m.from_user.id)
        
        await m.answer(
            "✅ **Code Correct! Tasks Unlocked.**\n\n"
            "Ab aap **🚀 Start Task** button use kar sakte hain.\n"
            "Happy Earning! 💰",
            reply_markup=get_main_menu()
        )
        await state.clear()
    else:
        await m.answer("❌ **Wrong Code!**\nChannel check karein aur sahi code dalein.")
        # Note: Hum state clear nahi kar rahe taaki user dobara try kar sake

# ==========================================
# 4. TASK LOGIC (Secure)
# ==========================================
@user_router.message(F.text == "🚀 Start Task")
@user_router.message(Command("tasks"))
async def cmd_get_task(message: types.Message):
    user_id = message.from_user.id

    # CHECK 1: Force Subscribe
    if not await is_user_subscribed(message.bot, user_id):
        await message.answer("⚠️ **Alert:** Channel Left! Join wapis karein:", reply_markup=get_join_channel_kb())
        return

    # CHECK 2: Unlock Status (Database Check)
    if not await check_user_renewed_today(user_id):
        await message.answer(
            "🛑 **Tasks Locked!**\n\n"
            "1. **'🔓 Unlock Task Today'** par click karein.\n"
            "2. Channel se Code lein aur Submit karein.",
            reply_markup=get_main_menu()
        )
        return

    # CHECK 3: Fetch Task
    task, err = await get_next_task_for_user(user_id)
    if not task: await message.answer(f"⚠️ {err}"); return

    kb = InlineKeyboardBuilder()
    kb.button(text=f"🔗 Complete {task['shortener_type'].upper()}", url=task["link"])
    kb.button(text="✍️ Submit Code", callback_data=f"askcode_{str(task['_id'])}")
    kb.adjust(1)
    
    await message.answer(
        f"🎯 **Your Next Task**\n\n"
        f"📌 Title: {task['text']}\n"
        f"⚡ Type: {task['shortener_type'].upper()}\n"
        f"💰 Reward: ₹{task['reward']}\n\n"
        "Link open karein aur code copy karke layein.",
        reply_markup=kb.as_markup()
    )

# --- Code Submission ---
@user_router.callback_query(F.data.startswith("askcode_"))
async def ask_code(c: types.CallbackQuery, state: FSMContext):
    await state.update_data(tid=c.data.split("_")[1]); await state.set_state(UserState.waiting_for_task_code)
    await c.message.answer("⌨️ Task Code:"); await c.answer()

@user_router.message(StateFilter(UserState.waiting_for_task_code))
async def verify_task_code(m: types.Message, state: FSMContext):
    d = await state.get_data(); t = await get_task_details(d.get("tid"))
    if not t: await m.answer("Expired."); await state.clear(); return
    
    if m.text.strip() == t["verification_code"]:
        if await mark_task_complete(m.from_user.id, str(t["_id"]), t["reward"]): await m.answer("✅ Added.")
        else: await m.answer("⚠️ Done.")
    else: await m.answer("❌ Wrong.")
    await state.clear()

# ==========================================
# 5. BALANCE & HELP
# ==========================================
@user_router.message(F.text == "💰 My Balance")
async def cmd_balance(message: types.Message):
    user = await get_user(message.from_user.id)
    if not user: return

    msg = (
        f"👤 **{user['first_name']}**\n"
        f"📧 {user.get('email')}\n"
        f"-----------------\n"
        f"💰 **Balance: ₹{user.get('balance', 0.0):.2f}**\n"
        f"✅ Tasks Today: {user.get('daily_task_count', 0)}/6"
    )
    await message.answer(msg)

@user_router.message(F.text == "ℹ️ Help / Rules")
async def cmd_help(message: types.Message):
    kb = InlineKeyboardBuilder()
    if SUPPORT_BOT_USERNAME:
        kb.button(text="👨‍💻 Contact Support", url=f"https://t.me/{SUPPORT_BOT_USERNAME}")
    
    await message.answer(
        "📜 **OFFICIAL RULES & GUIDELINES**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "1️⃣ **Daily Limits:** Aap daily sirf 6 Tasks complete kar sakte hain.\n\n"
        "2️⃣ **Task Sequence:** Tasks ko sequence me karein (GPLinks -> ShrinkMe -> ShrinkEarn).\n\n"
        "3️⃣ **Prohibited Activities:**\n"
        "   ❌ Multiple Accounts allowed nahi hain.\n"
        "   ❌ VPN/Proxy ka use sakht mana hai.\n"
        "   ❌ Fake/Self-Referral se Ban ho sakte hain.\n\n"
        "4️⃣ **Payments:** Withdrawal requests 24-48 hours me process ki jati hain.",
        reply_markup=kb.as_markup()
    )