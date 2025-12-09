import logging
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI

# Logging setup
logging.basicConfig(level=logging.INFO)

# 1. Database se connection banana
if not MONGO_URI:
    logging.error("MONGO_URI nahi mila! .env file check karo.")
    client = None
else:
    try:
        client = AsyncIOMotorClient(MONGO_URI)
        db = client['ApexDigitalDB']  # Database ka naam
        users_col = db['users']       # Table ka naam jaha user save honge
        logging.info("MongoDB Connected Successfully! ✅")
    except Exception as e:
        logging.error(f"MongoDB Connection Failed: {e}")
        client = None

# 2. User ko Database me add karne ka function
async def add_user(user_id, first_name, username):
    if users_col is None:
        return
    
    # Check karo ki user pehle se hai ya nahi
    user = await users_col.find_one({"user_id": user_id})
    
    if not user:
        # Naya user banayo
        new_user = {
            "user_id": user_id,
            "first_name": first_name,
            "username": username,
            "balance": 0.0,
            "total_withdrawn": 0.0,
            "email": None,
            "joining_date": None  # Baad me datetime add karenge
        }
        await users_col.insert_one(new_user)
        logging.info(f"New User Added: {first_name} ({user_id})")
        return True # New user tha
    else:
        return False # Old user tha
        # --- TASKS SECTION (Naya Code) ---
tasks_col = db['tasks'] # Tasks ki nayi table

async def add_task(task_text, reward, link, task_type="auto"):
    """
    Admin ke liye: Naya task database me dalne ke liye
    """
    task_data = {
        "text": task_text,
        "reward": float(reward),
        "link": link,
        "type": task_type,
        "users_completed": [] # Kin logo ne task kar liya
    }
    await tasks_col.insert_one(task_data)
    logging.info(f"New Task Created: {task_text}")

async def get_active_tasks(user_id):
    """
    User ke liye: Wo tasks dikhana jo usne abhi tak nahi kiye
    """
    # Aise tasks dhundo jiske 'users_completed' list me ye user NA ho
    tasks = await tasks_col.find({
        "users_completed": {"$ne": user_id}
    }).to_list(length=10)
    return tasks

async def complete_task(user_id, task_id, reward):
    """
    Jab user task kar le, to balance badhana aur task ko 'done' mark karna
    """
    # 1. User ka balance badhao
    await users_col.update_one(
        {"user_id": user_id},
        {"$inc": {"balance": reward}}
    )
    
    # 2. Task me user ka ID add karo (taaki dobara na kar sake)
    from bson.objectid import ObjectId # ID match karne ke liye zaroori hai
    await tasks_col.update_one(
        {"_id": ObjectId(task_id)},
        {"$push": {"users_completed": user_id}}
    )
    return True