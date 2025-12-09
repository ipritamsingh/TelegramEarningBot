import re
from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database import get_user, create_user, get_next_task_for_user, get_task_details, mark_task_complete

user_router = Router()

# --- STATES ---
class UserState(StatesGroup):
    waiting_for_email = State() # Email lene ke liye state
    waiting_for_task_code = State() # Task code lene ke liye state

# --- 1. START COMMAND & EMAIL CHECK ---
@user_router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user = await get_user(user_id)

    # Agar user pehle se database me hai
    if user:
        await message.answer(f"Welcome back, {message.from_user.first_name}! 👋\n\nUse /tasks to earn money.")
        return

    # Agar naya user hai -> Email maango
    await message.answer(
        "👋 **Welcome to Apex Earning Bot!**\n\n"
        "Account create karne ke liye, kripya apna **Email Address** bhejein.\n"
        "Example: `myemail@gmail.com`"
    )
    # Bot ab 'Sunne' ke mode me hai (Email ka wait karega)
    await state.set_state(UserState.waiting_for_email)

# --- 2. EMAIL VERIFICATION & ACCOUNT CREATION ---
@user_router.message(StateFilter(UserState.waiting_for_email))
async def process_email(message: types.Message, state: FSMContext):
    email = message.text.strip()
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    username = message.from_user.username

    # Email format check (Regex)
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    if not re.match(email_regex, email):
        await message.answer("❌ **Invalid Email!**\nKripya sahi email bhejein (e.g., test@gmail.com).")
        return

    # Database me save karo
    await create_user(user_id, first_name, username, email)
    
    # State clear karo (Bot normal mode me aa gaya)
    await state.clear()
    
    await message.answer(
        "✅ **Account Created Successfully!**\n\n"
        f"👤 Name: {first_name}\n"
        f"📧 Email: {email}\n"
        f"💰 Balance: ₹0.0\n\n"
        "Ab aap /tasks command use karke earning shuru kar sakte hain!"
    )

# --- 3. GET TASK COMMAND ---
@user_router.message(Command("tasks"))
async def cmd_get_task(message: types.Message):
    user_id = message.from_user.id
    
    # Check karo user exist karta hai ya nahi (just in case)
    user = await get_user(user_id)
    if not user:
        await message.answer("⚠️ Pehle /start dabakar account banayein.")
        return

    task, error_msg = await get_next_task_for_user(user_id)
    
    if not task:
        await message.answer(f"⚠️ {error_msg}")
        return

    task_id = str(task["_id"])
    s_type = task["shortener_type"].upper()
    
    kb = InlineKeyboardBuilder()
    kb.button(text=f"🔗 Complete {s_type} Task", url=task["link"])
    kb.button(text="✍️ Submit Code", callback_data=f"askcode_{task_id}")
    kb.adjust(1)
    
    await message.answer(
        f"🎯 **Your Next Task**\n\n"
        f"📌 Title: {task['text']}\n"
        f"⚡ Type: {s_type}\n"
        f"💰 Reward: ₹{task['reward']}\n\n"
        f"Link open karein aur code copy karke yahan submit karein.",
        reply_markup=kb.as_markup()
    )

# --- 4. ASK FOR CODE (Button Click) ---
@user_router.callback_query(F.data.startswith("askcode_"))
async def ask_for_code(callback: types.CallbackQuery, state: FSMContext):
    task_id = callback.data.split("_")[1]
    await state.update_data(task_id=task_id)
    
    # State change karo -> Waiting for Code
    await state.set_state(UserState.waiting_for_task_code)
    
    await callback.message.answer("⌨️ **Enter Verification Code:**")
    await callback.answer()

# --- 5. VERIFY CODE ---
@user_router.message(StateFilter(UserState.waiting_for_task_code))
async def verify_code(message: types.Message, state: FSMContext):
    user_input = message.text.strip()
    data = await state.get_data()
    task_id = data.get("task_id")
    user_id = message.from_user.id

    task = await get_task_details(task_id)
    if not task:
        await message.answer("❌ Error: Task not found.")
        await state.clear()
        return

    if user_input == task.get("verification_code"):
        success = await mark_task_complete(user_id, task_id, task["reward"])
        if success:
            await message.answer(f"✅ **Correct Code!**\n₹{task['reward']} added to wallet.")
        else:
            await message.answer("⚠️ Task already completed.")
    else:
        await message.answer("❌ **Wrong Code!** Try again.")
    
    await state.clear()