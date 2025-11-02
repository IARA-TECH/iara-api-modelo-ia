import asyncio
import httpx
import logging

logging.basicConfig(level=logging.INFO)

async def keep_alive():
    """Periodically pings the API to keep it awake on Render."""
    while True:
        try:
            async with httpx.AsyncClient() as client:
                await client.get("https://iara-modelo-ia.onrender.com/health")
                logging.info("Ping successful")
        except Exception as e:
            logging.warning(f"Ping failed: {e}")
        await asyncio.sleep(600)
