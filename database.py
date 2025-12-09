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