import logging
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI
from datetime import datetime
from bson.objectid import ObjectId

# --- DB CONNECTION ---
if not MONGO_URI:
    client = None
    users_col = None
    tasks_col = None
    logging.error("❌ MONGO_URI missing in config!")
else:
    try:
        client = AsyncIOMotorClient(MONGO_URI)
        db = client['ApexDigitalDB']
        users_col = db['users']
        tasks_col = db['tasks']
        logging.info("✅ MongoDB Connected Successfully!")
    except Exception as e:
        logging.error(f"❌ MongoDB Connection Failed: {e}")
        client = None

# ==========================================
# USER FUNCTIONS (User Bot ke liye)
# ==========================================

async def get_user(user_id):
    """User data fetch karega"""
    if users_col is None: return None
    return await users_col.find_one({"user_id": int(user_id)})

async def create_user(user_id, first_name, username, email):
    """Naya User create karega"""
    if users_col is None: return

    # Check agar user pehle se hai (Double Safety)
    existing = await users_col.find_one({"user_id": int(user_id)})
    if existing:
        return

    new_user = {
        "user_id": int(user_id),
        "first_name": first_name,
        "username": username,
        "email": email,
        "balance": 0.0,
        "total_withdrawn": 0.0,
        "is_banned": False,
        "joining_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_active_date": None,
        "daily_task_count": 0,
        "daily_completed_tasks": []
    }
    await users_col.insert_one(new_user)
    logging.info(f"🆕 New User Registered: {user_id}")

# ==========================================
# TASK LOGIC (Smart Allocator)
# ==========================================

async def add_bulk_task(text, reward, short_link, code, shortener_type):
    """Admin jab task add karega"""
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
    """User ke liye next task dhundega based on Sequence"""
    user_id = int(user_id)
    user = await users_col.find_one({"user_id": user_id})
    
    if not user: return None, "User not found. Press /start again."
    if user.get("is_banned"): return None, "🚫 You are BANNED from using this bot!"

    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # --- 1. DAILY RESET LOGIC ---
    if user.get("last_active_date") != today_str:
        await users_col.update_one(
            {"user_id": user_id},
            {"$set": {
                "last_active_date": today_str, 
                "daily_task_count": 0, 
                "daily_completed_tasks": []
            }}
        )
        daily_count = 0
        completed_today = []
    else:
        daily_count = user.get("daily_task_count", 0)
        completed_today = user.get("daily_completed_tasks", [])

    # --- 2. DAILY LIMIT CHECK ---
    if daily_count >= 6:
        return None, "Daily Limit (6/6) Reached! 🌙\nKal wapis aana naye tasks ke liye."

    # --- 3. SEQUENCE LOGIC (2 GP -> 2 ShrinkMe -> 2 ShrinkEarn) ---
    if daily_count < 2: 
        target = "gplinks"
    elif daily_count < 4: 
        target = "shrinkme"
    else: 
        target = "shrinkearn"

    # --- 4. FETCH RANDOM TASK ---
    pipeline = [
        {"$match": {
            "shortener_type": target,
            "users_completed": {"$ne": user_id}, # Jo kabhi nahi kiya
            "_id": {"$nin": completed_today}     # Jo aaj nahi kiya
        }},
        {"$sample": {"size": 1}} # Random 1 pick karo
    ]
    
    tasks = await tasks_col.aggregate(pipeline).to_list(1)
    
    if not tasks: 
        return None, f"No active tasks available for {target}.\nPlease wait for Admin update."
    
    return tasks[0], None

async def get_task_details(task_id):
    """Task ID se details layega (Verification ke liye)"""
    try: 
        return await tasks_col.find_one({"_id": ObjectId(task_id)})
    except: 
        return None

async def mark_task_complete(user_id, task_id, reward):
    """Task Complete hone par Balance Update"""
    user_id = int(user_id)
    
    # User Update
    await users_col.update_one(
        {"user_id": user_id},
        {
            "$inc": {"balance": float(reward), "daily_task_count": 1}, 
            "$push": {"daily_completed_tasks": ObjectId(task_id)}
        }
    )
    # Task Update
    await tasks_col.update_one(
        {"_id": ObjectId(task_id)}, 
        {"$push": {"users_completed": user_id}}
    )
    return True

# ==========================================
# ADMIN POWER FUNCTIONS (Admin Bot ke liye)
# ==========================================

async def get_system_stats():
    """Dashboard Stats"""
    users = await users_col.count_documents({})
    tasks = await tasks_col.count_documents({})
    
    # Total Balance Calculation
    pipeline = [{"$group": {"_id": None, "total": {"$sum": "$balance"}}}]
    res = await users_col.aggregate(pipeline).to_list(1)
    bal = res[0]['total'] if res else 0.0
    
    return users, bal, tasks

async def get_recent_tasks(limit=10):
    """Delete karne ke liye list"""
    return await tasks_col.find({}).sort("_id", -1).limit(limit).to_list(limit)

async def delete_task_from_db(task_id):
    """Task delete karna"""
    try:
        res = await tasks_col.delete_one({"_id": ObjectId(task_id)})
        return res.deleted_count > 0
    except: return False

async def get_user_details(user_id):
    """Admin search ke liye (Alias for get_user but ensures int)"""
    return await users_col.find_one({"user_id": int(user_id)})

async def update_user_ban_status(user_id, status):
    """Ban/Unban User"""
    await users_col.update_one(
        {"user_id": int(user_id)}, 
        {"$set": {"is_banned": status}}
    )

async def admin_add_balance(user_id, amount):
    """Admin Give/Cut Balance"""
    await users_col.update_one(
        {"user_id": int(user_id)}, 
        {"$inc": {"balance": float(amount)}}
    )
    return True

async def get_all_user_ids():
    """Broadcast ke liye"""
    users = await users_col.find({}, {"user_id": 1}).to_list(None)
    return [u['user_id'] for u in users]



# --- Naya Function Add karein ---
async def get_user_by_email(email):
    """Email se user dhundne ke liye"""
    if users_col is None: return None
    # Case-insensitive search (chhota/bada letter fark nahi padega)
    return await users_col.find_one({"email": email})



# --- NEW: RENEW TASK LOGIC ---

async def mark_user_renewed(user_id):
    """User ne 'Renew Task Today' button dabaya, aaj ki date save karo"""
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    await users_col.update_one(
        {"user_id": int(user_id)},
        {"$set": {"last_renew_date": today_str}}
    )
    return True

async def check_user_renewed_today(user_id):
    """Check karo ki user ne aaj Renew button dabaya tha ya nahi"""
    user = await users_col.find_one({"user_id": int(user_id)})
    if not user: return False
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    last_renew = user.get("last_renew_date")
    
    return last_renew == today_str