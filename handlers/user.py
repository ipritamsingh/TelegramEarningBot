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
    mark_task_complete
)
from config import FORCE_SUB_CHANNEL_ID, FORCE_SUB_LINK, SUPPORT_BOT_USERNAME

user_router = Router()

# --- STATES ---
class UserState(StatesGroup):
    waiting_for_email = State()
    waiting_for_task_code = State()

# ==========================================
# 🛠️ HELPERS
# ==========================================

# 1. MAIN MENU (Earning Options)
def get_main_menu():
    kb = ReplyKeyboardBuilder()
    kb.button(text="🚀 Start Task")
    kb.button(text="💰 My Balance")
    kb.button(text="ℹ️ Help / Rules")
    kb.adjust(2, 1)
    return kb.as_markup(resize_keyboard=True)

# 2. JOIN CHANNEL BUTTONS
def get_join_channel_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="📢 Join Official Channel", url=FORCE_SUB_LINK)
    kb.button(text="✅ Check & Verify", callback_data="check_subscription")
    kb.adjust(1)
    return kb.as_markup()

# 3. CHECK SUBSCRIPTION LOGIC
async def is_user_subscribed(bot, user_id):
    try:
        # User ka status check karo channel me
        member = await bot.get_chat_member(chat_id=FORCE_SUB_CHANNEL_ID, user_id=user_id)
        if member.status in ['creator', 'administrator', 'member']:
            return True
        return False
    except Exception as e:
        # Agar Bot admin nahi hai channel me ya ID galat hai
        return False 

# 4. CENTRAL DASHBOARD CONTROLLER (New & Old User Dono ke liye)
async def check_and_show_dashboard(message, user_id, first_name):
    """
    Ye function check karega ki user ne join kiya hai ya nahi.
    Agar Joined hai -> Menu dikhayega.
    Agar Nahi hai -> Join Button dikhayega.
    """
    if await is_user_subscribed(message.bot, user_id):
        # ✅ User Verified
        await message.answer(
            f"🎉 **Verification Successful!**\n\nWelcome {first_name}! 👇\nEarning shuru karne ke liye option select karein:",
            reply_markup=get_main_menu()
        )
    else:
        # ❌ User Not Verified
        await message.answer(
            f"⚠️ **Action Required!**\n\nHello {first_name}, bot use karne ke liye hamara **Official Channel** join karna zaroori hai.\n\n👇 **Join karein aur Verify par click karein:**",
            reply_markup=get_join_channel_kb()
        )

# ==========================================
# 1. START COMMAND
# ==========================================
@user_router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user = await get_user(user_id)

    # --- A. OLD USER ---
    if user:
        if user.get("is_banned", False):
            await message.answer("🚫 **You are BANNED!**\nContact Admin.")
            return
        
        # Purana user hai, par channel check zaroori hai
        await check_and_show_dashboard(message, user_id, message.from_user.first_name)
        return

    # --- B. NEW USER (Email Flow) ---
    await message.answer(
        "👋 **Welcome to Apex Earning Bot!**\n\n"
        "Account create karne ke liye apna **Email** bhejein.\n"
        "Example: `myemail@gmail.com`"
    )
    await state.set_state(UserState.waiting_for_email)

# ==========================================
# 2. EMAIL VERIFICATION -> THEN CHANNEL CHECK
# ==========================================
@user_router.message(StateFilter(UserState.waiting_for_email))
async def process_email(message: types.Message, state: FSMContext):
    email = message.text.strip()
    
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        await message.answer("❌ Invalid Email! Try again.")
        return

    # User Create
    await create_user(message.from_user.id, message.from_user.first_name, message.from_user.username, email)
    await state.clear()
    
    # Account ban gaya, ab Force Join check karo
    await check_and_show_dashboard(message, message.from_user.id, message.from_user.first_name)

# ==========================================
# 3. CHECK JOIN BUTTON HANDLER
# ==========================================
@user_router.callback_query(F.data == "check_subscription")
async def verify_click(callback: types.CallbackQuery):
    if await is_user_subscribed(callback.bot, callback.from_user.id):
        await callback.message.delete()
        await callback.message.answer(
            "✅ **Verified!** Access Granted.", 
            reply_markup=get_main_menu()
        )
    else:
        await callback.answer("❌ Aapne abhi tak Channel Join nahi kiya!", show_alert=True)

# ==========================================
# 4. TASK LOGIC (Double Check)
# ==========================================
@user_router.message(F.text == "🚀 Start Task")
@user_router.message(Command("tasks"))
async def cmd_get_task(message: types.Message):
    # Agar user ne channel leave kar diya ho to pakad lo
    if not await is_user_subscribed(message.bot, message.from_user.id):
        await message.answer("⚠️ **Alert:** Aapne Channel leave kar diya!\nJoin wapis karein:", reply_markup=get_join_channel_kb())
        return

    user_id = message.from_user.id
    user = await get_user(user_id)
    if not user: await message.answer("⚠️ /start karein."); return

    task, error_msg = await get_next_task_for_user(user_id)
    if not task: await message.answer(f"⚠️ {error_msg}"); return

    task_id = str(task["_id"])
    s_type = task["shortener_type"].upper()
    
    kb = InlineKeyboardBuilder()
    kb.button(text=f"🔗 Complete {s_type}", url=task["link"])
    kb.button(text="✍️ Submit Code", callback_data=f"askcode_{task_id}")
    kb.adjust(1)
    
    await message.answer(
        f"🎯 **Your Next Task**\n\n"
        f"📌 Title: {task['text']}\n"
        f"⚡ Type: {s_type}\n"
        f"💰 Reward: ₹{task['reward']}\n\n"
        "Link open karein aur code copy karke layein.",
        reply_markup=kb.as_markup()
    )

# --- Task Code Logic ---
@user_router.callback_query(F.data.startswith("askcode_"))
async def ask_for_code(callback: types.CallbackQuery, state: FSMContext):
    task_id = callback.data.split("_")[1]
    await state.update_data(task_id=task_id)
    await state.set_state(UserState.waiting_for_task_code)
    await callback.message.answer("⌨️ **Enter Verification Code:**")
    await callback.answer()

@user_router.message(StateFilter(UserState.waiting_for_task_code))
async def verify_code(message: types.Message, state: FSMContext):
    user_input = message.text.strip()
    data = await state.get_data()
    task = await get_task_details(data.get("task_id"))
    
    if not task: await message.answer("❌ Task expired."); await state.clear(); return

    if user_input == task.get("verification_code"):
        success = await mark_task_complete(message.from_user.id, data.get("task_id"), task["reward"])
        if success: await message.answer(f"✅ **Correct!** ₹{task['reward']} added.")
        else: await message.answer("⚠️ Already completed.")
    else: await message.answer("❌ Wrong Code.")
    await state.clear()

# ==========================================
# 5. BALANCE
# ==========================================
@user_router.message(F.text == "💰 My Balance")
@user_router.message(Command("balance"))
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

# ==========================================
# 6. HELP & SUPPORT BOT
# ==========================================
@user_router.message(F.text == "ℹ️ Help / Rules")
@user_router.message(Command("help"))
async def cmd_help(message: types.Message):
    # Support button
    kb = InlineKeyboardBuilder()
    if SUPPORT_BOT_USERNAME:
        kb.button(text="👨‍💻 Contact Support", url=f"https://t.me/{SUPPORT_BOT_USERNAME}")
    
    await message.answer(
        "ℹ️ **Help & Rules**\n\n"
        "1. Daily 6 tasks allowed.\n"
        "2. Complete tasks sequentially (GP -> ShrinkMe).\n"
        "3. Do not use fake accounts or VPN.\n"
        "4. Payment process ke liye admin se contact karein.",
        reply_markup=kb.as_markup()
    )