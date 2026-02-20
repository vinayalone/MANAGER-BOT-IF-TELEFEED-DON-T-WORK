import asyncio
import logging
import os
import time
from datetime import datetime
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from dotenv import load_dotenv

# Load local .env
load_dotenv()

# --- CONFIGURATION ---
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
MANAGER_BOT_TOKEN = os.environ.get("MANAGER_BOT_TOKEN")
SESSION_STRING = os.environ.get("SESSION_STRING")

# Target Bot Details
TARGET_BOT_USERNAME = os.environ.get("TARGET_BOT_USERNAME", "@tg_feedbot")
PHONE_NUMBER_BUTTON = os.environ.get("PHONE_NUMBER_BUTTON", "919416526259 »")

# Monitoring Details
# Channel B ID (Where the autoforward bot sends messages)
MONITOR_CHANNEL_ID = int(os.environ.get("MONITOR_CHANNEL_ID", "-100123456789")) 
CHECK_INTERVAL = 35  # Seconds
RESTART_COOLDOWN = 180 # 3 minutes (Wait for bot to actually start forwarding again)

# Worker Access
worker_ids_str = os.environ.get("AUTHORIZED_WORKERS", "")
AUTHORIZED_WORKERS = [int(id.strip()) for id in worker_ids_str.split(',') if id.strip().isdigit()]

# --- STATE TRACKING ---
last_msg_time = time.time()
is_restarting = False

# ---------------------

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

if not SESSION_STRING:
    logger.critical("Error: SESSION_STRING is missing.")
    exit(1)

user_client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
bot_client = TelegramClient('manager_bot', API_ID, API_HASH).start(bot_token=MANAGER_BOT_TOKEN)

async def click_button_by_text(client, chat, text_match):
    """Finds the latest message and clicks a button matching the text."""
    await asyncio.sleep(3) 
    messages = await client.get_messages(chat, limit=1)
    if not messages:
        raise Exception("No message received from bot.")
    
    msg = messages[0]
    if msg.buttons:
        for row in msg.buttons:
            for button in row:
                if text_match.lower() in button.text.lower():
                    logger.info(f"🖱️ Clicking: {button.text}")
                    await button.click()
                    return
    raise Exception(f"Button '{text_match}' not found.")

async def perform_restart_sequence():
    """The sequence to restart the FeedBot via Settings."""
    global is_restarting, last_msg_time
    is_restarting = True
    logger.warning("🚨 Threshold exceeded! Initiating Auto-Restart...")
    
    try:
        await user_client.send_message(TARGET_BOT_USERNAME, '/start')
        await click_button_by_text(user_client, TARGET_BOT_USERNAME, "Settings")
        await click_button_by_text(user_client, TARGET_BOT_USERNAME, PHONE_NUMBER_BUTTON)
        await click_button_by_text(user_client, TARGET_BOT_USERNAME, "Bot Settings")
        await click_button_by_text(user_client, TARGET_BOT_USERNAME, "Stop")
        
        logger.info("⏳ Waiting 125s for cleanup...")
        await asyncio.sleep(125) 
        
        await click_button_by_text(user_client, TARGET_BOT_USERNAME, "Go Back")
        await click_button_by_text(user_client, TARGET_BOT_USERNAME, "Start")
        
        logger.info("✅ Auto-Restart Complete.")
        # Reset the timer so we don't restart immediately again
        last_msg_time = time.time()
        # Notify workers
        for worker in AUTHORIZED_WORKERS:
            try: await bot_client.send_message(worker, "🤖 **Auto-Restart Executed:** FeedBot was unresponsive.")
            except: pass
            
    except Exception as e:
        logger.error(f"❌ Auto-Restart Failed: {e}")
    finally:
        # Extra cooldown to let messages start flowing
        await asyncio.sleep(RESTART_COOLDOWN)
        is_restarting = False

# --- MONITORING LISTENERS ---

@user_client.on(events.NewMessage(chats=MONITOR_CHANNEL_ID))
async def watch_channel(event):
    """Listens to Channel B. Every new message resets the watchdog timer."""
    global last_msg_time
    last_msg_time = time.time()
    logger.info("📩 Message received in Channel B. Timer Reset.")

async def watchdog_loop():
    """Background task that checks the timer every 5 seconds."""
    global last_msg_time, is_restarting
    logger.info(f"🛰️ Watchdog started. Monitoring Channel: {MONITOR_CHANNEL_ID}")
    
    while True:
        await asyncio.sleep(5)
        if is_restarting:
            continue
            
        elapsed = time.time() - last_msg_time
        if elapsed > CHECK_INTERVAL:
            await perform_restart_sequence()

# --- MANUAL COMMANDS ---

@bot_client.on(events.NewMessage(pattern='/restart'))
async def manual_restart(event):
    sender = await event.get_sender()
    if sender.id not in AUTHORIZED_WORKERS:
        return await event.respond("⛔ Access Denied.")
    
    if is_restarting:
        return await event.respond("⏳ A restart is already in progress.")
        
    await event.respond("⚙️ Manual restart initiated...")
    asyncio.create_task(perform_restart_sequence())

@bot_client.on(events.NewMessage(pattern='/status'))
async def status_check(event):
    elapsed = int(time.time() - last_msg_time)
    status = "🔴 DEAD" if elapsed > CHECK_INTERVAL else "🟢 ALIVE"
    await event.respond(f"📊 **System Status**\nState: {status}\nLast Msg: {elapsed}s ago\nMonitoring: `{MONITOR_CHANNEL_ID}`")

async def main():
    logger.info("🚀 Starting clients...")
    await user_client.start()
    
    # Run the watchdog loop in the background
    asyncio.create_task(watchdog_loop())
    
    logger.info("✅ All systems operational.")
    await asyncio.gather(
        user_client.run_until_disconnected(),
        bot_client.run_until_disconnected()
    )

if __name__ == '__main__':
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        pass
