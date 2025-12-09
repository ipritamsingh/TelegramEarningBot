import os
from dotenv import load_dotenv

load_dotenv()
# Admin Bot Token (Naya Wala)
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]

# 3 Shortener APIs
SHORTENER_CONFIG = {
    "gplinks": {
        "url": "https://gplinks.com/api",
        "key": os.getenv("GPLINKS_KEY")
    },
    "shrinkme": {
        "url": "https://shrinkme.io/api",
        "key": os.getenv("SHRINKME_KEY")
    },
    "droplink": {
        "url": "https://shrinkearn.com/api",
        "key": os.getenv("DROPLINK_KEY")
    }
}



