from aiogram import Router, types
from aiogram.filters import Command
from database import add_task
from config import ADMIN_IDS

admin_router = Router()

# Command format: /newtask TaskText, Reward, Link
@admin_router.message(Command("newtask"))
async def cmd_add_task(message: types.Message):
    user_id = message.from_user.id
    
    # Security Check: Kya ye Admin hai?
    if user_id not in ADMIN_IDS:
        return # Agar admin nahi hai to ignore karo

    try:
        # Message se "/newtask " hata kar baaki text lo
        args = message.text.split("/newtask ", 1)[1]
        
        # Comma se split karo data ko
        # Example: "Join Channel, 5, https://t.me/example"
        parts = args.split(",")
        
        if len(parts) != 3:
            await message.answer("❌ Format galat hai!\nUse: `/newtask Name, Reward, Link`")
            return
            
        task_text = parts[0].strip()
        reward = parts[1].strip()
        link = parts[2].strip()

        await add_task(task_text, reward, link)
        await message.answer(f"✅ Task Added Successfully!\n\n📝: {task_text}\n💰: ₹{reward}")

    except IndexError:
        await message.answer("❌ Error! Kuch likha nahi aapne.\nFormat: `/newtask Name, Reward, Link`")
    except Exception as e:
        await message.answer(f"❌ Error: {str(e)}")