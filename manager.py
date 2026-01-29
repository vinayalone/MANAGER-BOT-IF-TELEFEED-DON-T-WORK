import asyncio
import logging
import os
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from dotenv import load_dotenv

# Load local .env (if you are testing on PC)
load_dotenv()

# --- CONFIGURATION FROM RAILWAY VARIABLES ---

API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
MANAGER_BOT_TOKEN = os.environ.get("MANAGER_BOT_TOKEN")

# The long text code you generated in Step 1
SESSION_STRING = os.environ.get("SESSION_STRING")

# Get workers and clean them up
worker_ids_str = os.environ.get("AUTHORIZED_WORKERS", "")
AUTHORIZED_WORKERS = [int(id.strip()) for id in worker_ids_str.split(',') if id.strip().isdigit()]

TARGET_BOT_USERNAME = os.environ.get("TARGET_BOT_USERNAME", "@tg_feedbot")
PHONE_NUMBER_BUTTON = os.environ.get("PHONE_NUMBER_BUTTON", "919416526259 »")

# ---------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Safety Check
if not SESSION_STRING:
    logger.critical("Error: SESSION_STRING is missing. You cannot log in without it.")
    exit(1)

# Initialize Clients
# Client 1: Uses the String Session to log in as YOU
user_client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

# Client 2: The Bot
bot_client = TelegramClient('manager_bot', API_ID, API_HASH).start(bot_token=MANAGER_BOT_TOKEN)

async def click_button_by_text(client, chat, text_match):
    """Finds the latest message and clicks a button matching the text."""
    await asyncio.sleep(2) 
    
    messages = await client.get_messages(chat, limit=1)
    if not messages:
        raise Exception("No message received from bot.")
    
    msg = messages[0]
    
    if msg.buttons:
        for row in msg.buttons:
            for button in row:
                if text_match.lower() in button.text.lower():
                    logger.info(f"Clicking button: {button.text}")
                    await button.click()
                    return
    
    raise Exception(f"Button containing '{text_match}' not found.")

@bot_client.on(events.NewMessage(pattern='/restart'))
async def handler(event):
    sender = await event.get_sender()
    
    if sender.id not in AUTHORIZED_WORKERS:
        await event.respond(f"⛔ Access Denied.")
        return

    logger.info(f"Restart initiated by worker: {sender.id}")
    await event.respond("⚙️ Starting restart sequence...")

    try:
        await user_client.send_message(TARGET_BOT_USERNAME, '/start')
        await click_button_by_text(user_client, TARGET_BOT_USERNAME, "Settings")
        await click_button_by_text(user_client, TARGET_BOT_USERNAME, PHONE_NUMBER_BUTTON)
        await click_button_by_text(user_client, TARGET_BOT_USERNAME, "Bot Settings")
        await click_button_by_text(user_client, TARGET_BOT_USERNAME, "Stop")
        
        await asyncio.sleep(125) # Wait 2 minutes
        
        await click_button_by_text(user_client, TARGET_BOT_USERNAME, "Go Back")
        await click_button_by_text(user_client, TARGET_BOT_USERNAME, "Start")
        
        await event.respond("✅ Success! TeleFeed has been restarted.")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await event.respond(f"❌ Failed: {str(e)}")

async def main():
    logger.info("Starting clients...")
    await user_client.start()
    await asyncio.gather(
        user_client.run_until_disconnected(),
        bot_client.run_until_disconnected()
    )

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
