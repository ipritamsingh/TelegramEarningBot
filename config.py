import os
from dotenv import load_dotenv

# Local development ke liye .env file load karega
load_dotenv()

# Variables ko yaha define karte hain
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
# Admin IDs ko comma se split karke list banayenge
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]

if not BOT_TOKEN:
    print("Error: BOT_TOKEN not found in .env file!")