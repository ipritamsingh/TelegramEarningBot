import aiohttp
from config import SHORTENER_CONFIG

async def shorten_link(destination_url, shortener_type):
    """
    shortener_type example: 'gplinks', 'shrinkme', 'shrinkearn'
    """
    config = SHORTENER_CONFIG.get(shortener_type)
    
    if not config or not config["key"]:
        return destination_url # Agar key nahi hai to original link bhej do

    try:
        async with aiohttp.ClientSession() as session:
            params = {
                'api': config["key"],
                'url': destination_url
            }
            async with session.get(config["url"], params=params) as resp:
                data = await resp.json()
                
                if "shortenedUrl" in data:
                    return data["shortenedUrl"]
                elif "short" in data:
                    return data["short"]
                else:
                    return destination_url
    except Exception as e:
        print(f"Error in {shortener_type}: {e}")
        return destination_url