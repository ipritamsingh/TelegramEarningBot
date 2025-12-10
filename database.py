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
    settings_col = None
    logging.error("❌ MONGO_URI missing in config!")
else:
    try:
        client = AsyncIOMotorClient(MONGO_URI)
        db = client['ApexDigitalDB']
        users_col = db['users']
        tasks_col = db['tasks']
        settings_col = db['settings'] # For Daily Code
        logging.info("✅ MongoDB Connected Successfully!")
    except Exception as e:
        logging.error(f"❌ MongoDB Connection Failed: {e}")
        client = None

# ==========================================
# USER FUNCTIONS
# ==========================================

async def get_user(user_id):
    """User data fetch karega"""
    if users_col is None: return None
    return await users_col.find_one({"user_id": int(user_id)})

async def get_user_by_email(email):
    """Email se user dhundne ke liye"""
    if users_col is None: return None
    return await users_col.find_one({"email": email})

# --- FIX: New Function for Email Check ---
async def is_email_registered(email):
    """Check karega ki email pehle se hai ya nahi"""
    if users_col is None: return False
    user = await users_col.find_one({"email": email})
    return user is not None
# -----------------------------------------

async def create_user(user_id, first_name, username, email, referrer_id=None):
    """Naya User create karega"""
    if users_col is None: return

    # Check agar user pehle se hai
    existing = await users_col.find_one({"user_id": int(user_id)})
    if existing: return

    new_user = {
        "user_id": int(user_id),
        "first_name": first_name,
        "username": username,
        "email": email,
        "balance": 0.0,
        "total_withdrawn": 0.0,
        "withdraw_count": 0,
        "referred_by": int(referrer_id) if referrer_id else None,
        "referral_count": 0,
        "referral_earnings": 0.0,
        "is_banned": False,
        "joining_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_active_date": None,
        "last_renew_date": None, # For Daily Unlock
        "daily_task_count": 0,
        "daily_completed_tasks": []
    }
    await users_col.insert_one(new_user)
    logging.info(f"🆕 New User Registered: {user_id}")

    # Referrer Count Update (Bonus abhi nahi milega)
    if referrer_id:
        await users_col.update_one(
            {"user_id": int(referrer_id)},
            {"$inc": {"referral_count": 1}}
        )

# ==========================================
# WITHDRAWAL LOGIC (Bonus Removed)
# ==========================================

async def process_withdrawal(user_id, amount, upi_id):
    """Withdraw request process karega (Bonus removed from here)"""
    user = await users_col.find_one({"user_id": int(user_id)})
    if not user: return "User not found"
    
    current_balance = user.get("balance", 0.0)
    withdraw_count = user.get("withdraw_count", 0)
    
    # Limits Check
    if withdraw_count == 0:
        min_limit = 2.0  # First Time
    else:
        min_limit = 20.0 # Next Time
        
    if current_balance < min_limit:
        return f"❌ Low Balance! Minimum withdraw: ₹{min_limit}"
    
    if amount > current_balance:
        return "❌ Insufficient funds."

    # Deduct User Balance
    await users_col.update_one(
        {"user_id": int(user_id)},
        {
            "$inc": {"balance": -float(amount), "total_withdrawn": float(amount), "withdraw_count": 1},
            "$set": {"last_withdraw_upi": upi_id}
        }
    )
    
    # Bonus Logic Removed from Here (Moved to Admin Approval)
    
    return "SUCCESS" 

async def credit_referral_bonus(referrer_id, reward):
    """Referrer ko bonus dene ke liye helper function"""
    # Yahan dhyan dein: Hum 'reward' variable use kar rahe hain, REFERRAL_REWARD nahi
    result = await users_col.update_one(
        {"user_id": int(referrer_id)},
        {
            "$inc": {"balance": float(reward), "referral_earnings": float(reward)}
        }
    )
    return result.modified_count > 0

async def get_user_referral_stats(user_id):
    """Invite page ke liye stats"""
    user = await users_col.find_one({"user_id": int(user_id)})
    if user:
        return user.get("referral_count", 0)
    return 0

# ==========================================
# TASK LOGIC
# ==========================================

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
    user_id = int(user_id)
    user = await users_col.find_one({"user_id": user_id})
    
    if not user: return None, "User not found. Press /start again."
    if user.get("is_banned"): return None, "🚫 You are BANNED from using this bot!"

    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # Daily Reset Logic
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

    if daily_count >= 6:
        return None, "Daily Limit (6/6) Reached! 🌙\nKal wapis aana naye tasks ke liye."

    # Sequence Logic
    if daily_count < 2: target = "gplinks"
    elif daily_count < 4: target = "shrinkme"
    else: target = "shrinkearn"

    # Fetch Random Task
    pipeline = [
        {"$match": {
            "shortener_type": target,
            "users_completed": {"$ne": user_id},
            "_id": {"$nin": completed_today}
        }},
        {"$sample": {"size": 1}}
    ]
    tasks = await tasks_col.aggregate(pipeline).to_list(1)
    
    if not tasks: 
        return None, f"No active tasks available for {target}.\nPlease wait for Admin update."
    
    return tasks[0], None

async def get_task_details(task_id):
    try: return await tasks_col.find_one({"_id": ObjectId(task_id)})
    except: return None

async def mark_task_complete(user_id, task_id, reward):
    user_id = int(user_id)
    await users_col.update_one(
        {"user_id": user_id},
        {
            "$inc": {"balance": float(reward), "daily_task_count": 1}, 
            "$push": {"daily_completed_tasks": ObjectId(task_id)}
        }
    )
    await tasks_col.update_one(
        {"_id": ObjectId(task_id)}, 
        {"$push": {"users_completed": user_id}}
    )
    return True

# ==========================================
# DAILY UNLOCK & CHECK-IN LOGIC
# ==========================================

async def set_daily_checkin_code(code):
    await settings_col.update_one(
        {"_id": "daily_code"}, 
        {"$set": {"value": code}}, 
        upsert=True
    )
    return True

async def get_daily_checkin_code():
    data = await settings_col.find_one({"_id": "daily_code"})
    return data['value'] if data else None

async def mark_user_renewed(user_id):
    today_str = datetime.now().strftime("%Y-%m-%d")
    await users_col.update_one(
        {"user_id": int(user_id)},
        {"$set": {"last_renew_date": today_str}}
    )
    return True

async def check_user_renewed_today(user_id):
    user = await users_col.find_one({"user_id": int(user_id)})
    if not user: return False
    today_str = datetime.now().strftime("%Y-%m-%d")
    return user.get("last_renew_date") == today_str

# ==========================================
# ADMIN POWER FUNCTIONS
# ==========================================

async def get_system_stats():
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    total_users = await users_col.count_documents({})
    total_tasks = await tasks_col.count_documents({})
    
    active_today = await users_col.count_documents({"last_renew_date": today_str})
    
    pipeline = [{"$group": {"_id": None, "total": {"$sum": "$balance"}}}]
    res = await users_col.aggregate(pipeline).to_list(1)
    total_balance = res[0]['total'] if res else 0.0
    
    return total_users, total_balance, total_tasks, active_today

async def get_recent_tasks(limit=10):
    return await tasks_col.find({}).sort("_id", -1).limit(limit).to_list(limit)

async def delete_task_from_db(task_id):
    try:
        res = await tasks_col.delete_one({"_id": ObjectId(task_id)})
        return res.deleted_count > 0
    except: return False

async def get_user_details(user_id):
    return await users_col.find_one({"user_id": int(user_id)})

async def update_user_ban_status(user_id, status):
    await users_col.update_one({"user_id": int(user_id)}, {"$set": {"is_banned": status}})

async def admin_add_balance(user_id, amount):
    await users_col.update_one({"user_id": int(user_id)}, {"$inc": {"balance": float(amount)}})
    return True

async def get_all_user_ids():
    users = await users_col.find({}, {"user_id": 1}).to_list(None)
    return [u['user_id'] for u in users]

async def refund_user_balance(user_id, amount):
    """Agar Admin decline kare to paisa wapis add karo"""
    await users_col.update_one(
        {"user_id": int(user_id)},
        {
            "$inc": {"balance": float(amount), "total_withdrawn": -float(amount), "withdraw_count": -1}
        }
    )
    return True