import aiohttp
from config import SHORTENER_CONFIG

async def shorten_link(destination_url, shortener_type):
    """
    Generic function to shorten links using different APIs
    shortener_type: 'gplinks', 'shrinkme', 'shrinkearn'
    """
    config = SHORTENER_CONFIG.get(shortener_type)
    
    # Agar config nahi mila ya Key missing hai
    if not config or not config["key"]:
        return destination_url 

    try:
        async with aiohttp.ClientSession() as session:
            # Teeno websites ka format same hai: ?api=KEY&url=URL
            params = {
                'api': config["key"],
                'url': destination_url
            }
            async with session.get(config["url"], params=params) as resp:
                data = await resp.json()
                
                # Alag-alag APIs alag response de sakti hain
                if "shortenedUrl" in data:
                    return data["shortenedUrl"]
                elif "short" in data: 
                    return data["short"]
                else:
                    return destination_url # Fail hua to original link
    except Exception as e:
        print(f"❌ Shortener Error ({shortener_type}): {e}")
        return destination_url