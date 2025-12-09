import re
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
    check_user_renewed_today
)
from config import FORCE_SUB_CHANNEL_ID, FORCE_SUB_LINK, SUPPORT_BOT_USERNAME

user_router = Router()

# --- STATES ---
class UserState(StatesGroup):
    waiting_for_email = State()
    waiting_for_task_code = State()

# ==========================================
# 🛠️ HELPERS (Logic & UI)
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

# Central Dashboard Logic
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

    # --- Old User ---
    if user:
        if user.get("is_banned", False):
            await message.answer("🚫 **You are BANNED!**\nContact Admin."); return
        await check_and_show_dashboard(message, user_id, message.from_user.first_name)
        return

    # --- New User ---
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

# ==========================================
# 3. VERIFY BUTTON HANDLER
# ==========================================
@user_router.callback_query(F.data == "check_subscription")
async def verify_click(callback: types.CallbackQuery):
    if await is_user_subscribed(callback.bot, callback.from_user.id):
        await callback.message.delete()
        await callback.message.answer(
            "✅ **Verified!** Access Granted.\nAb **🔓 Unlock Task Today** par click karein 👇", 
            reply_markup=get_main_menu()
        )
    else:
        await callback.answer("❌ Join nahi kiya! Pehle Join Channel button dabayein.", show_alert=True)

# ==========================================
# 🔥 NEW: 1-CLICK INSTANT UNLOCK (FIXED)
# ==========================================
@user_router.message(F.text == "🔓 Unlock Task Today")
async def unlock_task_request(message: types.Message):
    # Step 1: User ko Red Button dikhao
    kb = InlineKeyboardBuilder()
    kb.button(text="🔴 Click to Open Channel & Unlock", callback_data="perform_instant_unlock")
    
    await message.answer(
        "🔒 **Unlock Process:**\n\n"
        "Niche diye gaye button par **Click** karein.\n"
        "Ye automatically Channel open karega aur Task **Unlock** kar dega.",
        reply_markup=kb.as_markup()
    )

@user_router.callback_query(F.data == "perform_instant_unlock")
async def process_unlock_instant(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    # 1. Link Preparation (Ensure HTTPS)
    channel_link = str(FORCE_SUB_LINK).strip()
    if not channel_link.startswith("http"):
        channel_link = f"https://{channel_link}"

    # 2. Database Update (Backend: Unlock Task)
    await mark_user_renewed(user_id)
    
    # 3. Message Edit (Visual Confirmation) + Backup Button
    # Backup button isliye agar auto-open fail ho jaye
    kb = InlineKeyboardBuilder()
    kb.button(text="📢 Open Channel Manually", url=channel_link)

    await callback.message.edit_text(
        "✅ **Tasks UNLOCKED Successfully!**\n\n"
        "Agar channel open nahi hua to niche click karein.\n"
        "Warna **🚀 Start Task** button dabayein.",
        reply_markup=kb.as_markup()
    )
    
    # 4. THE MAGIC: Auto Open Link
    # Ye line browser/channel open karti hai
    try:
        await callback.answer("Unlocking & Opening Channel...", url=channel_link)
    except:
        await callback.answer("Unlocked! Please join channel manually.", show_alert=True)

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

    # CHECK 2: Unlock Status
    if not await check_user_renewed_today(user_id):
        await message.answer(
            "🛑 **Tasks Locked!**\n\n"
            "Tasks start karne se pehle **'🔓 Unlock Task Today'** button par click karein.",
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
    await c.message.answer("⌨️ Code:"); await c.answer()

@user_router.message(StateFilter(UserState.waiting_for_task_code))
async def verify_code(m: types.Message, state: FSMContext):
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