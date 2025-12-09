import logging
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI
from datetime import datetime
from bson.objectid import ObjectId

client = AsyncIOMotorClient(MONGO_URI)
db = client['ApexDigitalDB']
users_col = db['users']
tasks_col = db['tasks']

# --- USER FUNCTIONS ---

async def get_user(user_id):
    """Check karega ki user pehle se hai ya nahi"""
    return await users_col.find_one({"user_id": user_id})

async def create_user(user_id, first_name, username, email):
    """Naya user create karega Email ke saath"""
    new_user = {
        "user_id": user_id,
        "first_name": first_name,
        "username": username,
        "email": email,  # Email ab yaha save hoga
        "balance": 0.0,
        "total_withdrawn": 0.0,
        "joining_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_active_date": None,
        "daily_task_count": 0,
        "daily_completed_tasks": []
    }
    await users_col.insert_one(new_user)
    logging.info(f"New User Created: {first_name} - {email}")

# --- TASK FUNCTIONS (Smart Logic) ---

async def add_bulk_task(text, reward, short_link, code, shortener_type):
    task_data = {
        "text": text,
        "reward": float(reward),
        "link": short_link,
        "verification_code": code,
        "shortener_type": shortener_type,
        "users_completed": []
    }
    await tasks_col.insert_one(task_data)

async def get_next_task_for_user(user_id):
    user = await users_col.find_one({"user_id": user_id})
    if not user: return None, "User not found"

    today_str = datetime.now().strftime("%Y-%m-%d")
    last_active = user.get("last_active_date")
    
    # Date Reset Logic
    if last_active != today_str:
        await users_col.update_one(
            {"user_id": user_id},
            {"$set": {"last_active_date": today_str, "daily_task_count": 0, "daily_completed_tasks": []}}
        )
        daily_count = 0
        completed_today = []
    else:
        daily_count = user.get("daily_task_count", 0)
        completed_today = user.get("daily_completed_tasks", [])

    if daily_count >= 6:
        return None, "Daily Limit Reached (6/6). Come back tomorrow!"

    # Sequence: 2 GP -> 2 ShrinkMe -> 2 ShrinkEarn
    if daily_count < 2: target_type = "gplinks"
    elif daily_count < 4: target_type = "shrinkme"
    else: target_type = "shrinkearn"

    pipeline = [
        {"$match": {
            "shortener_type": target_type,
            "users_completed": {"$ne": user_id},
            "_id": {"$nin": completed_today}
        }},
        {"$sample": {"size": 1}}
    ]
    tasks = await tasks_col.aggregate(pipeline).to_list(length=1)

    if not tasks: return None, f"No tasks available for {target_type}."
    return tasks[0], None

async def get_task_details(task_id):
    try: return await tasks_col.find_one({"_id": ObjectId(task_id)})
    except: return None

async def mark_task_complete(user_id, task_id, reward):
    await users_col.update_one(
        {"user_id": user_id},
        {"$inc": {"balance": reward, "daily_task_count": 1}, "$push": {"daily_completed_tasks": ObjectId(task_id)}}
    )
    await tasks_col.update_one(
        {"_id": ObjectId(task_id)},
        {"$push": {"users_completed": user_id}}
    )
    return True
    # --- ADMIN MANAGEMENT FUNCTIONS ---

async def get_recent_tasks(limit=10):
    """Admin ko dikhane ke liye last 10 tasks layega"""
    # Sort by _id descending (Jo naya hai wo pehle aayega)
    cursor = tasks_col.find({}).sort("_id", -1).limit(limit)
    return await cursor.to_list(length=limit)

async def delete_task_from_db(task_id):
    """Task ID se task delete karega"""
    from bson.objectid import ObjectId
    try:
        result = await tasks_col.delete_one({"_id": ObjectId(task_id)})
        return result.deleted_count > 0 # True agar delete hua, False agar nahi mila
    except Exception as e:
        print(f"Delete Error: {e}")
        return False