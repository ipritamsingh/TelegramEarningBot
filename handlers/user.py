import re
import asyncio # Required for delay
from aiogram import Router, types, F, Bot
from aiogram.filters import Command, StateFilter, CommandStart, CommandObject
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
    get_daily_checkin_code,
    credit_referral_bonus,
    get_user_referral_stats,
    process_withdrawal
)
from config import FORCE_SUB_CHANNEL_ID, FORCE_SUB_LINK, SUPPORT_BOT_USERNAME, REFERRAL_REWARD, MIN_WITHDRAW_FIRST, MIN_WITHDRAW_NEXT, PAYMENT_LOG_CHANNEL, ADMIN_BOT_TOKEN

user_router = Router()

# --- STATES ---
class UserState(StatesGroup):
    waiting_for_email = State()
    waiting_for_task_code = State()
    waiting_for_daily_checkin_code = State() # Daily unlock code
    waiting_for_upi_id = State() # Withdraw

# ==========================================
# 🛠️ HELPERS (Updated Menu)
# ==========================================

def get_main_menu():
    kb = ReplyKeyboardBuilder()
    # Row 1
    kb.button(text="🔓 Unlock Task Today") 
    # Row 2
    kb.button(text="🚀 Start Task")
    # Row 3 (New Buttons)
    kb.button(text="💰 Wallet / Withdraw")
    kb.button(text="🤝 Invite & Earn")
    # Row 4
    kb.button(text="ℹ️ Help / Rules")
    
    # Layout set karo (1, 1, 2, 1)
    kb.adjust(1, 1, 2, 1)
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
# 1. START COMMAND (Referral Tracking)
# ==========================================
@user_router.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject, state: FSMContext):
    user_id = message.from_user.id
    user = await get_user(user_id)

    if user:
        if user.get("is_banned", False):
            await message.answer("🚫 **You are BANNED!**\nContact Admin."); return
        
        # Agar user purana hai to Menu refresh kar do
        await message.answer(f"Welcome back, {message.from_user.first_name}!", reply_markup=get_main_menu())
        return

    # Store Referral ID if present
    referrer_id = command.args
    if referrer_id and str(referrer_id) != str(user_id):
        await state.update_data(referrer_id=referrer_id)

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

    # Get Referral Data
    data = await state.get_data()
    referrer_id = data.get("referrer_id")

    await create_user(message.from_user.id, message.from_user.first_name, message.from_user.username, email, referrer_id)
    
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
# 🔥 3-STEP SECURE UNLOCK LOGIC
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

    # 3. Wait for 3 Seconds
    await asyncio.sleep(3)

    # 4. Update Message (Show Submit Button)
    kb_final = InlineKeyboardBuilder()
    kb_final.button(text="🔴 Open & Unlock", url=channel_link)
    kb_final.button(text="✅ Submit & Unlock", callback_data="ask_daily_code")
    kb_final.adjust(1)

    try:
        await msg.edit_reply_markup(reply_markup=kb_final.as_markup())
    except:
        pass 

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
    real_code = await get_daily_checkin_code()
    
    if not real_code:
        await m.answer("⚠️ Admin ne aaj ka Code set nahi kiya hai. Please wait.")
        await state.clear()
        return

    if user_input.lower() == real_code.lower():
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

# ==========================================
# 4. TASK LOGIC
# ==========================================
@user_router.message(F.text == "🚀 Start Task")
@user_router.message(Command("tasks"))
async def cmd_get_task(message: types.Message):
    user_id = message.from_user.id

    if not await is_user_subscribed(message.bot, user_id):
        await message.answer("⚠️ **Alert:** Channel Left! Join wapis karein:", reply_markup=get_join_channel_kb())
        return

    # Unlock Check
    if not await check_user_renewed_today(user_id):
        await message.answer(
            "🛑 **Tasks Locked!**\n\n"
            "1. **'🔓 Unlock Task Today'** par click karein.\n"
            "2. Channel se Code lein aur Submit karein.",
            reply_markup=get_main_menu()
        )
        return

    task, err = await get_next_task_for_user(user_id)
    if not task: await message.answer(f"⚠️ {err}"); return

    kb = InlineKeyboardBuilder()
    kb.button(text=f"🔗 Complete Task", url=task["link"])
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

@user_router.callback_query(F.data.startswith("askcode_"))
async def ask_code(c: types.CallbackQuery, state: FSMContext):
    await state.update_data(tid=c.data.split("_")[1]); await state.set_state(UserState.waiting_for_task_code)
    await c.message.answer("⌨️ Code:"); await c.answer()

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
# 5. WALLET & WITHDRAW (Updated UI & Request)
# ==========================================
@user_router.message(F.text == "💰 Wallet / Withdraw")
async def wallet_menu(message: types.Message):
    user = await get_user(message.from_user.id)
    if not user: return

    bal = user.get('balance', 0.0)
    w_count = user.get('withdraw_count', 0)
    limit = MIN_WITHDRAW_FIRST if w_count == 0 else MIN_WITHDRAW_NEXT
    
    # User Details Display
    name = user.get('first_name', 'User')
    email = user.get('email', 'Not Set')
    join_date = user.get('joining_date', 'N/A')

    kb = InlineKeyboardBuilder()
    kb.button(text="💸 Withdraw Now", callback_data="req_withdraw")
    
    msg = (
        "💰 **YOUR WALLET DASHBOARD**\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Name:** {name}\n"
        f"📧 **Email:** {email}\n"
        f"📅 **Joined:** {join_date}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💵 **Current Balance:** ₹{bal:.2f}\n"
        f"🏧 **Total Withdrawn:** ₹{user.get('total_withdrawn', 0):.2f}\n\n"
        "⚠️ **Rules:**\n"
        f"🔹 Next Withdraw Limit: ₹{limit}\n"
        "👇 Withdraw karne ke liye button dabayein:"
    )
    await message.answer(msg, reply_markup=kb.as_markup())

@user_router.callback_query(F.data == "req_withdraw")
async def ask_upi(c: types.CallbackQuery, state: FSMContext):
    await state.set_state(UserState.waiting_for_upi_id)
    await c.message.answer(
        "📝 **Enter Payment Details**\n\n"
        "Apna **UPI ID** ya **Mobile Number** dhyan se likhein.\n"
        "Example:\n"
        "🔹 `8888888888@paytm`\n"
        "🔹 `name@ybl`\n\n"
        "⚠️ **WARNING:** Galat details dalne par paisa loss ho jayega. Dobara refund nahi milega.",
        reply_markup=InlineKeyboardBuilder().button(text="❌ Cancel", callback_data="cancel_withdraw").as_markup()
    )
    await c.answer()

@user_router.callback_query(F.data == "cancel_withdraw")
async def cancel_w(c: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await c.message.delete()
    await c.answer("Cancelled")

@user_router.message(StateFilter(UserState.waiting_for_upi_id))
async def process_withdraw_req(m: types.Message, state: FSMContext):
    upi_id = m.text.strip()
    user_id = m.from_user.id
    user = await get_user(user_id)
    
    limit = MIN_WITHDRAW_FIRST if user.get('withdraw_count', 0) == 0 else MIN_WITHDRAW_NEXT
    balance = user.get('balance', 0)
    
    if balance < limit:
        await m.answer(f"❌ **Low Balance!**\nMin Withdraw: ₹{limit}")
        await state.clear()
        return

    # 1. Deduct Balance Immediately (Pending State)
    result = await process_withdrawal(user_id, balance, upi_id)
    
    if result == "SUCCESS" or (isinstance(result, tuple) and result[0] == "SUCCESS_WITH_BONUS"):
        
        # User ko Pending Message
        await m.answer(
            "⏳ **Withdrawal Request Submitted!**\n\n"
            f"💰 Amount: ₹{balance}\n"
            f"🏦 UPI: `{upi_id}`\n\n"
            "Admin approval ke baad paisa mil jayega (24-48 Hrs).",
            reply_markup=get_main_menu()
        )
        
        # Admin Group Notification
        if PAYMENT_LOG_CHANNEL and ADMIN_BOT_TOKEN:
            try:
                # Admin Bot use karke message bhejo
                admin_bot = Bot(token=ADMIN_BOT_TOKEN)
                
                # Approve/Decline Buttons
                kb = InlineKeyboardBuilder()
                kb.button(text="✅ Approve", callback_data=f"wd_y_{user_id}_{balance}")
                kb.button(text="❌ Decline", callback_data=f"wd_n_{user_id}_{balance}")
                kb.adjust(2)
                
                msg_text = (
                    "🔔 **NEW WITHDRAWAL REQUEST**\n"
                    "━━━━━━━━━━━━━━━━\n"
                    f"👤 Name: {user['first_name']}\n"
                    f"📧 Email: {user.get('email')}\n"
                    f"🆔 ID: `{user_id}`\n"
                    f"💰 Amount: **₹{balance}**\n"
                    f"🏦 UPI: `{upi_id}`\n"
                    f"📅 Joined: {user.get('joining_date')}"
                )
                
                await admin_bot.send_message(chat_id=PAYMENT_LOG_CHANNEL, text=msg_text, reply_markup=kb.as_markup())
                await admin_bot.session.close()
                
            except Exception as e:
                print(f"Admin Notify Error: {e}")
        
    else:
        await m.answer(f"❌ Error: {result}")
    
    await state.clear()

# ==========================================
# 6. INVITE & OTHERS
# ==========================================
@user_router.message(F.text == "🤝 Invite & Earn")
async def invite_menu(message: types.Message):
    user_id = message.from_user.id
    user = await get_user(user_id)
    bot_info = await message.bot.get_me()
    
    # Generate Link
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
    
    # Stats
    total_refs = user.get('referral_count', 0)
    total_earned = user.get('referral_earnings', 0.0)
    
    msg = (
        "🤝 **REFER & EARN PROGRAM**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 **Reward:** ₹{REFERRAL_REWARD} per Active Refer\n"
        "*(Note: Bonus tab milega jab aapka dost first withdraw karega)*\n\n"
        f"🔗 **Your Link:**\n`{ref_link}`\n\n"
        "📊 **Your Performance:**\n"
        f"👥 Total Joined: `{total_refs}`\n"
        f"💸 Bonus Earned: `₹{total_earned:.2f}`\n\n"
        "⚠️ **Terms:** Fake referrals leads to Ban."
    )
    
    kb = InlineKeyboardBuilder()
    kb.button(text="📤 Share Link", url=f"https://t.me/share/url?url={ref_link}&text=Join and Earn Money Daily!")
    await message.answer(msg, reply_markup=kb.as_markup())

@user_router.message(F.text == "ℹ️ Help / Rules")
async def cmd_help(message: types.Message):
    kb = InlineKeyboardBuilder()
    if SUPPORT_BOT_USERNAME:
        kb.button(text="👨‍💻 Contact Support", url=f"https://t.me/{SUPPORT_BOT_USERNAME}")
    
    await message.answer(
        "📜 **OFFICIAL RULES & GUIDELINES**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "1️⃣ **Daily Limits:** Aap daily sirf 6 Tasks complete kar sakte hain.\n\n"
        "2️⃣ **Task Sequence:** Tasks ko sequence me karein.\n\n"
        "3️⃣ **Prohibited Activities:**\n"
        "   ❌ Multiple Accounts allowed nahi hain.\n"
        "   ❌ VPN/Proxy ka use sakht mana hai.\n"
        "   ❌ Fake/Self-Referral se Ban ho sakte hain.\n\n"
        "4️⃣ **Payments:** Withdrawal requests 24-48 hours me process ki jati hain.",
        reply_markup=kb.as_markup()
    )