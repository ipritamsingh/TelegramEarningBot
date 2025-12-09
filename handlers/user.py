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

user_router = Router()

# --- STATES (FSM) ---
class UserState(StatesGroup):
    waiting_for_email = State()
    waiting_for_task_code = State()

# ==========================================
# 🛠️ HELPER: MAIN MENU KEYBOARD
# ==========================================
def get_main_menu():
    """Ye function permanent buttons banayega"""
    kb = ReplyKeyboardBuilder()
    kb.button(text="🚀 Start Task")
    kb.button(text="💰 My Balance")
    kb.button(text="ℹ️ Help / Rules")
    # Layout: 2 buttons upar, 1 niche
    kb.adjust(2, 1)
    return kb.as_markup(resize_keyboard=True)

# ==========================================
# 1. START COMMAND
# ==========================================
@user_router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user = await get_user(user_id)

    # --- OLD USER ---
    if user:
        if user.get("is_banned", False):
            await message.answer("🚫 **You are BANNED!**\nContact Admin.")
            return
        
        await message.answer(
            f"Welcome back, {message.from_user.first_name}! 👋\nSelect an option below:",
            reply_markup=get_main_menu() # <--- Yahan Menu dikhaya
        )
        return

    # --- NEW USER ---
    await message.answer(
        "👋 **Welcome to Apex Earning Bot!**\n\n"
        "Account create karne ke liye apna **Email** bhejein.\n"
        "Example: `myemail@gmail.com`"
    )
    await state.set_state(UserState.waiting_for_email)

# ==========================================
# 2. EMAIL VERIFICATION
# ==========================================
@user_router.message(StateFilter(UserState.waiting_for_email))
async def process_email(message: types.Message, state: FSMContext):
    email = message.text.strip()
    
    # Regex Check
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        await message.answer("❌ Invalid Email! Try again.")
        return

    await create_user(message.from_user.id, message.from_user.first_name, message.from_user.username, email)
    await state.clear()
    
    await message.answer(
        "✅ **Account Created Successfully!**\n"
        "Ab niche diye gaye buttons se earning shuru karein! 👇",
        reply_markup=get_main_menu() # <--- Register ke baad menu dikhaya
    )

# ==========================================
# 3. GET TASK (Command OR Button)
# ==========================================
# Ab ye "/tasks" command par bhi chalega AUR "🚀 Start Task" button par bhi
@user_router.message(F.text == "🚀 Start Task")
@user_router.message(Command("tasks"))
async def cmd_get_task(message: types.Message):
    user_id = message.from_user.id
    user = await get_user(user_id)
    
    if not user:
        await message.answer("⚠️ Pehle /start karein.")
        return

    task, error_msg = await get_next_task_for_user(user_id)
    
    if not task:
        await message.answer(f"⚠️ {error_msg}")
        return

    task_id = str(task["_id"])
    s_type = task["shortener_type"].upper()
    
    # Inline Buttons (Link ke liye)
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

# ==========================================
# 4. SUBMIT CODE FLOW
# ==========================================
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
    
    if not task:
        await message.answer("❌ Task expired/deleted.")
        await state.clear(); return

    if user_input == task.get("verification_code"):
        success = await mark_task_complete(message.from_user.id, data.get("task_id"), task["reward"])
        if success:
            await message.answer(f"✅ **Correct!** ₹{task['reward']} added.")
        else:
            await message.answer("⚠️ Already completed.")
    else:
        await message.answer("❌ Wrong Code. Try again.")
    
    await state.clear()

# ==========================================
# 5. BALANCE & PROFILE (Button Added)
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
# 6. HELP (Button Added)
# ==========================================
@user_router.message(F.text == "ℹ️ Help / Rules")
@user_router.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "ℹ️ **Help & Rules**\n\n"
        "1. Daily 6 tasks allowed.\n"
        "2. Complete tasks sequentially.\n"
        "3. Do not use fake accounts.\n"
        "4. Contact Admin for payments."
    )