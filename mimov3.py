# Copyright (C) @TheSmartBisnu
# Channel: https://t.me/itsSmartDev
# Modified by: Meow Meow 🐱

import re
import os
import json
import time
import asyncio
import logging
import socket
import string
import random
import urllib.request
import urllib.error
from io import BytesIO
from datetime import datetime, timedelta
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
from pyrogram.enums import ParseMode
from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
    CallbackQuery
)
from config import API_ID, API_HASH, SESSION_STRING, BOT_TOKEN, ADMIN_IDS, DEFAULT_LIMIT, ADMIN_LIMIT, LOG_CHANNEL

# ─── Logging Setup ───
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# ─── BOT INFO ─────────────
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

BOT_NAME = "Meow Bot"
BOT_VERSION = "2.2"
BOT_OWNER = "Meow Meow"
OWNER_LINK = "https://t.me/kaeelann"
DEVELOPER_LINK = "https://t.me/meowmeow7070"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# ─── LIMITS ───────────────
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

NORMAL_LIMIT = 5000
PREMIUM_LIMIT = 15000

# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# ─── INITIALIZE CLIENTS ──
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

bot = Client(
    "bot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=50,
    parse_mode=ParseMode.HTML
)

user = Client(
    "user_session",
    session_string=SESSION_STRING,
    workers=50
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# ─── PERSISTENCE FILES ────
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

PREMIUM_FILE = "premium.json"
USER_DATA_FILE = "user_data.json"
STATS_FILE = "bot_stats.json"
HISTORY_FILE = "user_history.json"
BANNED_FILE = "banned_users.json"
MERGE_QUEUE_FILE = "merge_queue.json"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# ─── STORAGE ──────────────
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

scrape_queue = asyncio.Queue()
user_history = []
merge_queue = {}
banned_users = set()
user_first_seen = {}
user_scrape_count = {}

bot_stats = {
    "total_scrapes": 0,
    "total_cc_found": 0,
    "total_users": [],
    "start_time": None
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ─── LOAD/SAVE PERSISTENCE FUNCTIONS ─
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def safe_json_load(filepath, default):
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load {filepath}: {e}")
    return default

def safe_json_save(filepath, data):
    try:
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save {filepath}: {e}")

def load_all_persistent_data():
    global bot_stats, user_history, banned_users, merge_queue
    stats_data = safe_json_load(STATS_FILE, None)
    if stats_data:
        bot_stats.update(stats_data)
    else:
        bot_stats["total_users"] = []
    user_history = safe_json_load(HISTORY_FILE, [])
    banned_users = set(safe_json_load(BANNED_FILE, []))
    merge_queue_data = safe_json_load(MERGE_QUEUE_FILE, {})
    merge_queue = {int(k): v for k, v in merge_queue_data.items()}

def save_stats():
    safe_json_save(STATS_FILE, {
        "total_scrapes": bot_stats["total_scrapes"],
        "total_cc_found": bot_stats["total_cc_found"],
        "total_users": list(bot_stats["total_users"]),
        "start_time": bot_stats["start_time"]
    })

def save_history():
    safe_json_save(HISTORY_FILE, user_history[-500:])

def save_banned():
    safe_json_save(BANNED_FILE, list(banned_users))

def save_merge_queue():
    safe_json_save(MERGE_QUEUE_FILE, merge_queue)

# ─── PREMIUM SYSTEM ───────

def load_premium():
    return safe_json_load(PREMIUM_FILE, {})

def save_premium(data):
    safe_json_save(PREMIUM_FILE, data)

premium_users = load_premium()

def is_premium(user_id):
    uid = str(user_id)
    if uid not in premium_users:
        return False
    expiry = premium_users[uid].get("expiry")
    if expiry is None:
        return True
    if time.time() > expiry:
        del premium_users[uid]
        save_premium(premium_users)
        return False
    return True

def get_premium_expiry(user_id):
    uid = str(user_id)
    if uid not in premium_users:
        return None
    expiry = premium_users[uid].get("expiry")
    if expiry is None:
        return "Unlimited"
    remaining = expiry - time.time()
    if remaining <= 0:
        return "Expired"
    days = int(remaining // 86400)
    hours = int((remaining % 86400) // 3600)
    return f"{days}d {hours}h"

def get_user_limit(user_id):
    if user_id in ADMIN_IDS:
        return 999999
    if is_premium(user_id):
        return PREMIUM_LIMIT
    return NORMAL_LIMIT

# ─── USER DATA PERSISTENCE ─

def load_user_data():
    data = safe_json_load(USER_DATA_FILE, {})
    return data.get("first_seen", {}), data.get("scrape_count", {})

def save_user_data():
    safe_json_save(USER_DATA_FILE, {
        "first_seen": user_first_seen,
        "scrape_count": user_scrape_count
    })

user_first_seen, user_scrape_count = load_user_data()

def track_user(user_id):
    uid = str(user_id)
    if uid not in user_first_seen:
        user_first_seen[uid] = datetime.now().strftime("%Y-%m-%d")
        save_user_data()

def increment_scrape_count(user_id):
    uid = str(user_id)
    user_scrape_count[uid] = user_scrape_count.get(uid, 0) + 1
    save_user_data()

def is_banned(user_id):
    if user_id in ADMIN_IDS:
        return False
    return user_id in banned_users

# ─── HELPER FUNCTIONS ─────

def get_user_display(user_obj):
    name = user_obj.first_name or "Unknown"
    if user_obj.username:
        return f"{name} (@{user_obj.username})"
    return name

def remove_duplicates(messages):
    seen = set()
    unique_messages = []
    for msg in messages:
        if msg not in seen:
            seen.add(msg)
            unique_messages.append(msg)
    duplicates_removed = len(messages) - len(unique_messages)
    return unique_messages, duplicates_removed

def sanitize_filename(name):
    return re.sub(r'[^\w\s\-]', '', name).strip().replace(' ', '_')[:30]
    
# ✅ NEW: Resolve invite link channel - handles USER_ALREADY_PARTICIPANT + PEER_ID_INVALID
# ✅ FIXED: Resolve invite link - handles USER_ALREADY_PARTICIPANT + PEER_ID_INVALID
async def resolve_invite_channel(client, invite_link):
    """Invite link ကနေ channel resolve လုပ်တယ်"""
    try:
        chat = await client.join_chat(invite_link)
        return chat
    except Exception as join_err:
        err_str = str(join_err)
        if "USER_ALREADY_PARTICIPANT" in err_str or "PEER_ID_INVALID" in err_str:
            from pyrogram.raw.functions.messages import CheckChatInvite
            from pyrogram.raw.functions.channels import GetFullChannel
            from pyrogram.raw.types import InputChannel

            if "+" in invite_link:
                invite_hash = invite_link.split("+")[1]
            else:
                invite_hash = invite_link.split("joinchat/")[1]

            result = await client.invoke(CheckChatInvite(hash=invite_hash))
            raw_channel = result.chat

            # InputChannel construct လုပ်ပြီး peer cache လုပ်ပေးတယ်
            input_channel = InputChannel(
                channel_id=raw_channel.id,
                access_hash=raw_channel.access_hash
            )
            await client.invoke(GetFullChannel(channel=input_channel))

            # get_chat ခေါ်တယ်
            chat_id = int(f"-100{raw_channel.id}")
            chat = await client.get_chat(chat_id)
            return chat
        raise join_err

# ✅ FIXED: parse_channel_username - support invite links & channel IDs
def parse_channel_username(identifier):
    # Private invite link (t.me/+xxx or t.me/joinchat/xxx)
    if "t.me/+" in identifier or "t.me/joinchat/" in identifier:
        return identifier  # return full link as-is for join_chat
    if identifier.startswith("@"):
        return identifier[1:]
    if "t.me/" in identifier:
        parts = identifier.split("t.me/")
        if len(parts) > 1:
            return parts[1].strip("/")
    # Channel ID (negative number like -1003012628561)
    if identifier.lstrip("-").isdigit():
        return int(identifier)
    return identifier

# ✅ NEW: get_channel_link - generate proper link for log channel
def get_channel_link(identifier):
    """Channel link ကို မှန်ကန်စွာ ပြန်ပေးတယ်"""
    if identifier.startswith("https://t.me/+") or identifier.startswith("https://t.me/joinchat/"):
        return identifier
    if identifier.startswith("https://t.me/"):
        return identifier
    if identifier.startswith("@"):
        return f"https://t.me/{identifier[1:]}"
    if identifier.lstrip("-").isdigit():
        return None  # private ID, link မရှိ
    return f"https://t.me/{identifier}"

def parse_bin_filter(args):
    bin_filter = None
    clean_args = []
    for arg in args:
        if arg.startswith("--bin="):
            bin_filter = arg.split("=", 1)[1].strip()
        else:
            clean_args.append(arg)
    return clean_args, bin_filter

def detect_separator(line):
    if '|' in line:
        return '|'
    elif ',' in line:
        return ','
    elif ':' in line:
        return ':'
    elif '-' in line:
        return '-'
    return ' '

def convert_format(line, target_format):
    sep = detect_separator(line)
    parts = line.split(sep)
    format_map = {
        "space": " ",
        "comma": ",",
        "dash": "-",
        "colon": ":",
        "pipe": "|"
    }
    to_sep = format_map.get(target_format, "|")
    return to_sep.join(parts)

def get_uptime():
    if bot_stats.get("start_time"):
        start = datetime.fromtimestamp(bot_stats["start_time"])
        delta = datetime.now() - start
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        return f"{hours}h {minutes}m {seconds}s"
    return "N/A"

# ─── LOG ACTIVITY ───────

async def log_activity(client, user_obj, command, details="", file_bytes=None, file_name=None):
    if not LOG_CHANNEL or LOG_CHANNEL == 0:
        logger.warning("⚠️ LOG_CHANNEL not configured!")
        return

    user_display = get_user_display(user_obj)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    log_text = (
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"<b>📋 New Activity</b>\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
        f"<b>🔹 User:</b> {user_display} (<code>{user_obj.id}</code>)\n"
        f"<b>🔹 Command:</b> <code>{command}</code>\n"
    )

    if details:
        log_text += details

    log_text += (
        f"<b>🔹 Time:</b> <code>{now}</code>\n\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>"
    )

    try:
        if file_bytes and file_name:
            file_bytes.name = file_name
            await client.send_document(LOG_CHANNEL, file_bytes, caption=log_text)
        else:
            await client.send_message(LOG_CHANNEL, log_text)
        logger.info(f"✅ Log sent: {command} by {user_obj.id}")
    except Exception as e:
        logger.error(f"❌ Failed to send log: {e}")

# ─── GET REPLY FILE CONTENT ─

async def get_reply_file_content(client, message):
    if not message.reply_to_message:
        return None, "<b>❌ Please reply to a .txt file!</b>"
    reply_msg = message.reply_to_message
    if not reply_msg.document:
        return None, "<b>❌ Replied message must contain a file!</b>"
    file_name = reply_msg.document.file_name or ""
    if not file_name.endswith('.txt'):
        return None, f"<b>❌ Only .txt files supported!</b>"
    try:
        file_path = await client.download_media(reply_msg.document)
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        os.remove(file_path)
        return content, None
    except Exception as e:
        return None, f"<b>❌ Error reading file: {str(e)}</b>"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ─── LUHN ALGORITHM ────────────────
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def luhn_checksum(partial_number: str) -> str:
    """Calculate Luhn check digit for a partial card number."""
    digits = [int(d) for d in str(partial_number)]
    for i in range(len(digits) - 1, -1, -2):
        digits[i] *= 2
        if digits[i] > 9:
            digits[i] -= 9
    total = sum(digits)
    check_digit = (10 - (total % 10)) % 10
    return str(check_digit)

def generate_card(bin_prefix: str, total_length: int = 16) -> str:
    """Generate a valid credit card number using Luhn algorithm."""
    rand_count = total_length - len(bin_prefix) - 1
    if rand_count < 0:
        raise ValueError("BIN is too long for the requested card length!")
    middle = ''.join(str(random.randint(0, 9)) for _ in range(rand_count))
    partial = bin_prefix + middle
    check = luhn_checksum(partial)
    return partial + check

# ─── UI COMPONENTS ────────

def get_main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📖 Help", callback_data="help"),
            InlineKeyboardButton("🔧 Admin Commands", callback_data="admin_cmds")
        ],
        [
            InlineKeyboardButton("👨‍💻 Developer", url=DEVELOPER_LINK)
        ]
    ])

def get_back_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu")]
    ])

def get_start_text():
    return (
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"<b>🐱 Welcome to {BOT_NAME}!</b>\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
        f"<b>🔹 All-in-One CC Tool</b>\n\n"
        f"<b>📌 Features:</b>\n\n"
        f"<b>🔸 CC Scraping</b>\n"
        f"<b>🔸 CC Tools</b>\n"
        f"   (format/convert/split/merge)\n"
        f"<b>🔸 BIN Lookup</b>\n"
        f"<b>🔸 CC Generator (Luhn)</b>\n"
        f"<b>🔸 Proxy Checker</b>\n"
        f"   (HTTP/SOCKS5)\n"
        f"<b>🔸 Premium System</b>\n\n"
        f"Type /help for all commands.\n\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"<b>Bot by:</b> <a href='{OWNER_LINK}'>{BOT_OWNER} 🐱</a>"
    )

def get_help_text():
    return (
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"<b>📖 Command List</b>\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
        f"<b>🔹 General:</b>\n"
        f"<code>/start</code> - Start the bot\n"
        f"<code>/help</code> - Show this help\n"
        f"<code>/me</code> - Your profile\n"
        f"<code>/stats</code> - Bot statistics\n"
        f"<code>/history</code> - Your scrape history\n"
        f"<code>/clearhistory</code> - Clear your history\n"
        f"<code>/premium</code> - Check premium status\n\n"
        f"<b>🔹 Scraping:</b>\n"
        f"<code>/scr</code> - Scrape CC from channel\n"
        f"<code>/count</code> - Count CC (Admin)\n\n"
        f"<b>🔹 CC Tools:</b>\n"
        f"<code>/format</code> - Change CC format\n"
        f"<code>/dedupe</code> - Remove duplicates\n"
        f"<code>/sort</code> - Sort CC list\n"
        f"<code>/convert</code> - Convert CC format\n"
        f"<code>/split</code> - Split CC file\n"
        f"<code>/merge</code> - Merge CC files\n\n"
        f"<b>🔹 Filters:</b>\n"
        f"<code>/filter MM|YY</code> - Filter by date\n"
        f"<code>/filter2 BIN</code> - Filter by BIN (6-digit)\n"
        f"<code>/exbin BIN</code> - Exclude BIN\n"
        f"<code>/countbin</code> - BIN distribution\n\n"
        f"<b>🔹 Generator & Lookup:</b>\n"
        f"<code>/gen BIN</code> - Generate Luhn cards\n"
        f"<code>/validate</code> - Validate cards (Luhn)\n"
        f"<code>/bin BIN</code> - BIN information\n\n"
        f"<b>🔹 Proxy:</b>\n"
        f"<code>/proxy ip:port</code> - Check single proxy\n"
        f"<code>/proxy</code> - Reply to file to check\n\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"<b>Bot by:</b> <a href='{OWNER_LINK}'>{BOT_OWNER} 🐱</a>"
    )

def get_admin_text():
    return (
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"<b>🔧 Admin Commands</b>\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
        f"<code>/broadcast</code> - Send message to all\n"
        f"<code>/ban</code> - Ban a user\n"
        f"<code>/unban</code> - Unban a user\n"
        f"<code>/banlist</code> - List banned users\n"
        f"<code>/setlimit</code> - Set default limit\n"
        f"<code>/users</code> - Total users count\n"
        f"<code>/addpremium</code> - Add premium user\n"
        f"<code>/rmpremium</code> - Remove premium user\n"
        f"<code>/premiumlist</code> - Premium users list\n"
        f"<code>/count</code> - Count CC in channel\n"
        f"<code>/restart</code> - Restart bot\n\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"<b>Bot by:</b> <a href='{OWNER_LINK}'>{BOT_OWNER} 🐱</a>"
    )

# ─── CALLBACK HANDLER ─────

@bot.on_callback_query()
async def callback_handler(client, callback_query: CallbackQuery):
    data = callback_query.data

    if data == "help":
        await callback_query.message.edit_text(get_help_text(), reply_markup=get_back_keyboard())

    elif data == "admin_cmds":
        if callback_query.from_user.id not in ADMIN_IDS:
            await callback_query.answer("⛔ Admin only!", show_alert=True)
            return
        await callback_query.message.edit_text(get_admin_text(), reply_markup=get_back_keyboard())

    elif data == "back_to_menu":
        await callback_query.message.edit_text(get_start_text(), reply_markup=get_main_keyboard())

    await callback_query.answer()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# ─── GENERAL COMMANDS ─────
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

@bot.on_message(filters.command(["start"]))
async def start_cmd(client, message: Message):
    if is_banned(message.from_user.id):
        await message.reply_text("<b>⛔ You are banned from using this bot.</b>")
        return
    track_user(message.from_user.id)
    if message.from_user.id not in bot_stats["total_users"]:
        bot_stats["total_users"].append(message.from_user.id)
        save_stats()
    await message.reply_text(get_start_text(), reply_markup=get_main_keyboard())

@bot.on_message(filters.command(["help"]))
async def help_cmd(client, message: Message):
    if is_banned(message.from_user.id):
        await message.reply_text("<b>⛔ You are banned from using this bot.</b>")
        return
    await message.reply_text(get_help_text(), reply_markup=get_back_keyboard())

@bot.on_message(filters.command(["me"]))
async def me_cmd(client, message: Message):
    if is_banned(message.from_user.id):
        await message.reply_text("<b>⛔ You are banned from using this bot.</b>")
        return
    track_user(message.from_user.id)
    user_obj = message.from_user
    uid = str(user_obj.id)

    name = user_obj.first_name or "N/A"
    username = f"@{user_obj.username}" if user_obj.username else "Not set"
    user_id = user_obj.id

    if user_id in ADMIN_IDS:
        status = "👑 Admin"
        expiry = "Unlimited"
        limit = "Unlimited"
    elif is_premium(user_id):
        status = "⭐ Premium"
        expiry = get_premium_expiry(user_id) or "N/A"
        limit = f"{PREMIUM_LIMIT:,}"
    else:
        status = "🆓 Free"
        expiry = "-"
        limit = f"{NORMAL_LIMIT:,}"

    joined = user_first_seen.get(uid, datetime.now().strftime("%Y-%m-%d"))
    scrapes = user_scrape_count.get(uid, 0)

    me_text = (
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"<b>👤 Your Profile</b>\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
        f"<b>🔹 Name:</b> <code>{name}</code>\n"
        f"<b>🔹 Username:</b> <code>{username}</code>\n"
        f"<b>🔹 User ID:</b> <code>{user_id}</code>\n"
        f"<b>🔹 Status:</b> {status}\n"
        f"<b>🔹 Expiry:</b> <code>{expiry}</code>\n"
        f"<b>🔹 Limit:</b> <code>{limit}</code>\n"
        f"<b>🔹 Joined:</b> <code>{joined}</code>\n"
        f"<b>🔹 Scrapes:</b> <code>{scrapes}</code>\n\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"<b>Bot by:</b> <a href='{OWNER_LINK}'>{BOT_OWNER} 🐱</a>"
    )
    await message.reply_text(me_text)

@bot.on_message(filters.command(["premium"]))
async def premium_cmd(client, message: Message):
    if is_banned(message.from_user.id):
        await message.reply_text("<b>⛔ You are banned from using this bot.</b>")
        return
    user_id = message.from_user.id
    if is_premium(user_id):
        expiry = get_premium_expiry(user_id) or "N/A"
        await message.reply_text(
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"<b>⭐ Premium Status</b>\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
            f"<b>🔹 Status:</b> <code>✅ Premium</code>\n"
            f"<b>🔹 Expiry:</b> <code>{expiry}</code>\n"
            f"<b>🔹 Limit:</b> <code>{PREMIUM_LIMIT:,}</code>\n\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>"
        )
    else:
        await message.reply_text(
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"<b>⭐ Premium Status</b>\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
            f"<b>🔹 Status:</b> <code>❌ Normal</code>\n"
            f"<b>🔹 Limit:</b> <code>{NORMAL_LIMIT:,}</code>\n\n"
            f"<b>🔹 Premium Limit:</b> <code>{PREMIUM_LIMIT:,}</code>\n\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>"
        )

@bot.on_message(filters.command(["stats"]))
async def stats_cmd(client, message: Message):
    if is_banned(message.from_user.id):
        await message.reply_text("<b>⛔ You are banned from using this bot.</b>")
        return
    stats_text = (
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"<b>📊 Bot Statistics</b>\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
        f"<b>🔹 Total Scrapes:</b> <code>{bot_stats['total_scrapes']}</code>\n"
        f"<b>🔹 Total CC Found:</b> <code>{bot_stats['total_cc_found']}</code>\n"
        f"<b>🔹 Total Users:</b> <code>{len(bot_stats['total_users'])}</code>\n"
        f"<b>🔹 Banned Users:</b> <code>{len(banned_users)}</code>\n"
        f"<b>🔹 Uptime:</b> <code>{get_uptime()}</code>\n"
        f"<b>🔹 Version:</b> <code>{BOT_VERSION}</code>\n\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"<b>Bot by:</b> <a href='{OWNER_LINK}'>{BOT_OWNER} 🐱</a>"
    )
    await message.reply_text(stats_text)

@bot.on_message(filters.command(["history"]))
async def history_cmd(client, message: Message):
    if is_banned(message.from_user.id):
        await message.reply_text("<b>⛔ You are banned from using this bot.</b>")
        return
    user_id = message.from_user.id
    user_entries = [h for h in user_history if h["user_id"] == user_id]
    if not user_entries:
        await message.reply_text("<b>📭 No scrape history found.</b>")
        return
    recent = user_entries[-10:]
    history_text = (
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"<b>📜 Your Scrape History</b>\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
    )
    for i, entry in enumerate(reversed(recent), 1):
        history_text += (
            f"<b>{i}.</b> <code>{entry['channel']}</code>\n"
            f"   └ Found: <code>{entry['found']}</code> | "
            f"Time: <code>{entry['time']}</code>\n\n"
        )
    history_text += (
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"<b>Showing last {len(recent)} entries</b>"
    )
    await message.reply_text(history_text)

@bot.on_message(filters.command(["clearhistory"]))
async def clearhistory_cmd(client, message: Message):
    if is_banned(message.from_user.id):
        await message.reply_text("<b>⛔ You are banned from using this bot.</b>")
        return
    global user_history
    user_id = message.from_user.id
    before = len([h for h in user_history if h["user_id"] == user_id])
    user_history = [h for h in user_history if h["user_id"] != user_id]
    save_history()
    await message.reply_text(
        f"<b>✅ Cleared your history!</b>\n"
        f"<b>🔹 Removed:</b> <code>{before}</code> entries"
    )

# ─── SCRAPE FUNCTION ──────

async def scrape_messages(client, channel_id, limit, start_number=None, bin_filter=None):
    messages = []
    count = 0
    pattern = r'\d{16}\D*\d{2}\D*\d{2,4}\D*\d{3,4}'
    scanned = 0
    async for message in client.search_messages(channel_id):
        if count >= limit:
            break
        scanned += 1
        text = message.text if message.text else message.caption
        if text:
            matched_messages = re.findall(pattern, text)
            if matched_messages:
                for matched_message in matched_messages:
                    extracted_values = re.findall(r'\d+', matched_message)
                    if len(extracted_values) == 4:
                        card_number, mo, year, cvv = extracted_values
                        year = year[-2:]
                        if start_number and not card_number.startswith(start_number):
                            continue
                        if bin_filter and not card_number.startswith(bin_filter):
                            continue
                        formatted = f"{card_number}|{mo}|{year}|{cvv}"
                        messages.append(formatted)
                        count += 1
                        if count >= limit:
                            break
    return messages, scanned

# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# ─── /scr COMMAND ─────────
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

@bot.on_message(filters.command(["scr"]))
async def scr_cmd(client, message: Message):
    if is_banned(message.from_user.id):
        await message.reply_text("<b>⛔ You are banned from using this bot.</b>")
        return
    track_user(message.from_user.id)
    if message.from_user.id not in bot_stats["total_users"]:
        bot_stats["total_users"].append(message.from_user.id)
        save_stats()
    args = message.text.split()[1:]
    args, bin_filter = parse_bin_filter(args)

    if len(args) < 2 or len(args) > 3:
        await message.reply_text(
            "<b>⚠️ Usage:</b>\n"
            "<code>/scr @channel 100</code>\n"
            "<code>/scr https://t.me/channel 500</code>\n"
            "<code>/scr https://t.me/+invite_link 100</code>\n"
            "<code>/scr -1001234567890 200</code>\n"
            "<code>/scr @channel 100 --bin=4532</code>\n"
            "<code>/scr @channel 100 5234</code>"
        )
        return

    channel_identifier = args[0]
    raw_identifier = channel_identifier  # ✅ FIXED: original input သိမ်းထားမယ်
    channel_username = parse_channel_username(channel_identifier)

    try:
        limit = int(args[1])
    except ValueError:
        await message.reply_text("<b>⚠️ Amount must be a number!</b>")
        return

    max_lim = get_user_limit(message.from_user.id)
    if limit > max_lim:
        role = "Premium" if is_premium(message.from_user.id) else "Normal"
        await message.reply_text(
            f"<b>❌ Max limit for {role} is {max_lim}</b>\n"
            f"<b>Use /premium to check your status.</b>"
        )
        return

    start_number = args[2] if len(args) == 3 else None

    # ✅ FIXED: invite link ဆိုရင် join_chat သုံးမယ်
    # ✅ FIXED: invite link support - already joined ဆိုရင် handle မယ်
    try:
        if isinstance(channel_username, str) and ("+" in channel_username or "joinchat" in channel_username):
            chat = await resolve_invite_channel(user, channel_username)
        else:
            chat = await user.get_chat(channel_username)
        channel_name = chat.title
    except Exception as e:
        await message.reply_text(f"<b>❌ Channel not found!\n<code>{e}</code></b>")
        return

    bin_info = f"\n<b>🔹 BIN Filter:</b> <code>{bin_filter}</code>" if bin_filter else ""
    temp_msg = await message.reply_text(
        f"<b>⏳ Scraping in progress...</b>\n"
        f"<b>🔹 Channel:</b> <code>{channel_name}</code>\n"
        f"<b>🔹 Limit:</b> <code>{limit}</code>"
        f"{bin_info}\n\n"
        f"<b>⏳ Please wait...</b>"
    )

    try:
        scrapped_results, scanned = await scrape_messages(
            user, chat.id, limit, start_number, bin_filter
        )
        unique_messages, duplicates_removed = remove_duplicates(scrapped_results)

        if unique_messages:
            file_content = "\n".join(unique_messages)
            safe_name = sanitize_filename(channel_name)
            file_name = f"x{len(unique_messages)}_{safe_name}.txt"

            send_bytes = BytesIO(file_content.encode())
            send_bytes.name = file_name

            caption = (
                f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
                f"<b>✅ CC Scrapped Successfully</b>\n"
                f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
                f"<b>🔹 Source:</b> <code>{channel_name}</code>\n"
                f"<b>🔹 Found:</b> <code>{len(unique_messages)}</code>\n"
                f"<b>🔹 Duplicates:</b> <code>{duplicates_removed}</code>\n"
                f"<b>🔹 Scanned:</b> <code>{scanned}</code> messages\n"
            )
            if bin_filter:
                caption += f"<b>🔹 BIN Filter:</b> <code>{bin_filter}</code>\n"
            caption += (
                f"\n<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
                f"<b>Bot by:</b> <a href='{OWNER_LINK}'>{BOT_OWNER} 🐱</a>"
            )

            try:
                await temp_msg.delete()
            except Exception:
                pass
            await client.send_document(message.chat.id, send_bytes, caption=caption)

            bot_stats["total_scrapes"] += 1
            bot_stats["total_cc_found"] += len(unique_messages)
            save_stats()
            increment_scrape_count(message.from_user.id)
            user_history.append({
                "user_id": message.from_user.id,
                "channel": channel_name,
                "found": len(unique_messages),
                "time": datetime.now().strftime("%Y-%m-%d %H:%M")
            })
            save_history()

            # ✅ FIXED: Log channel မှာ link မှန်ကန်စွာ ပြမယ်
            log_bytes = BytesIO(file_content.encode())
            channel_link = get_channel_link(raw_identifier)
            if channel_link:
                link_display = f"<a href='{channel_link}'>{channel_name}</a>"
            else:
                link_display = f"<code>{raw_identifier}</code>"

            log_details = (
                f"<b>🔹 Channel:</b> <code>{channel_name}</code>\n"
                f"<b>🔹 Link:</b> {link_display}\n"
                f"<b>🔹 Limit:</b> <code>{limit}</code>\n"
                f"<b>🔹 Found:</b> <code>{len(unique_messages)}</code>\n"
                f"<b>🔹 Duplicates:</b> <code>{duplicates_removed}</code>\n"
            )
            if bin_filter:
                log_details += f"<b>🔹 BIN Filter:</b> <code>{bin_filter}</code>\n"
            await log_activity(
                client, message.from_user, "/scr",
                details=log_details,
                file_bytes=log_bytes,
                file_name=file_name
            )
        else:
            try:
                await temp_msg.delete()
            except Exception:
                pass
            await client.send_message(
                message.chat.id,
                f"<b>❌ No CC Found in {channel_name}</b>"
            )
    except Exception as e:
        try:
            await temp_msg.delete()
        except Exception:
            pass
        await client.send_message(message.chat.id, f"<b>❌ Error: {str(e)}</b>")

# ✅ ADMIN ONLY: /count (invite link support added)
@bot.on_message(filters.command(["count"]) & filters.user(ADMIN_IDS))
async def count_cmd(client, message: Message):
    if is_banned(message.from_user.id):
        await message.reply_text("<b>⛔ You are banned from using this bot.</b>")
        return
    track_user(message.from_user.id)
    args = message.text.split()[1:]
    if len(args) < 1:
        await message.reply_text("<b>⚠️ Usage: <code>/count @channel</code></b>")
        return
    channel_identifier = args[0]
    raw_identifier = channel_identifier  # ✅ FIXED
    channel_username = parse_channel_username(channel_identifier)
    try:
        # ✅ FIXED: invite link support
        # ✅ FIXED: invite link support - already joined handle
        if isinstance(channel_username, str) and ("+" in channel_username or "joinchat" in channel_username):
            chat = await resolve_invite_channel(user, channel_username)
        else:
            chat = await user.get_chat(channel_username)
        channel_name = chat.title
    except Exception as e:
        await message.reply_text(f"<b>❌ Channel not found!\n<code>{e}</code></b>")
        return
    try:
        count = 0
        pattern = r'\d{16}\D*\d{2}\D*\d{2,4}\D*\d{3,4}'
        async for msg in user.search_messages(chat.id):
            text = msg.text if msg.text else msg.caption
            if text:
                matched = re.findall(pattern, text)
                count += len(matched)
        try:
            await temp_msg.delete()
        except Exception:
            pass
        await client.send_message(
            message.chat.id,
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"<b>📊 CC Count Result</b>\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
            f"<b>🔹 Channel:</b> <code>{channel_name}</code>\n"
            f"<b>🔹 Total CC:</b> <code>{count}</code>\n\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>"
        )
        # ✅ FIXED: Log link
        channel_link = get_channel_link(raw_identifier)
        if channel_link:
            link_display = f"<a href='{channel_link}'>{channel_name}</a>"
        else:
            link_display = f"<code>{raw_identifier}</code>"
        await log_activity(
            client, message.from_user, "/count",
            details=f"<b>🔹 Channel:</b> <code>{channel_name}</code>\n<b>🔹 Link:</b> {link_display}\n<b>🔹 Count:</b> <code>{count}</code>\n"
        )
    except Exception as e:
        try:
            await temp_msg.delete()
        except Exception:
            pass
        await client.send_message(message.chat.id, f"<b>❌ Error: {str(e)}</b>")

# ─── CC TOOLS ────
@bot.on_message(filters.command(["format"]))
async def format_cmd(client, message: Message):
    if is_banned(message.from_user.id):
        await message.reply_text("<b>⛔ You are banned from using this bot.</b>")
        return
    args = message.text.split()[1:]
    if not args:
        await message.reply_text(
            "<b>⚠️ Usage:</b> <code>/format space</code>\n\n"
            "<b>Available formats:</b>\n"
            "• <code>space</code> → xxxx mm yy cvv\n"
            "• <code>comma</code> → xxxx,mm,yy,cvv\n"
            "• <code>dash</code> → xxxx-mm-yy-cvv\n"
            "• <code>colon</code> → xxxx:mm:yy:cvv\n"
            "• <code>pipe</code> → xxxx|mm|yy|cvv\n\n"
            "<b>Reply to a .txt file to use!</b>"
        )
        return

    target_format = args[0].lower()
    valid_formats = ['space', 'comma', 'dash', 'colon', 'pipe']
    if target_format not in valid_formats:
        await message.reply_text(f"<b>❌ Invalid format! Use: {', '.join(valid_formats)}</b>")
        return

    content, error = await get_reply_file_content(client, message)
    if error:
        await message.reply_text(f"<b>{error}</b>")
        return

    temp_msg = await message.reply_text("<b>⏳ Formatting...</b>")
    try:
        lines = [l.strip() for l in content.strip().split('\n') if l.strip()]
        formatted = [convert_format(line, target_format) for line in lines]
        file_content = "\n".join(formatted)
        result_name = f"formatted_{target_format}_{len(formatted)}.txt"

        caption = (
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"<b>✅ Format Changed</b>\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
            f"<b>🔹 Format:</b> <code>{target_format}</code>\n"
            f"<b>🔹 Lines:</b> <code>{len(formatted)}</code>\n\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"<b>Bot by:</b> <a href='{OWNER_LINK}'>{BOT_OWNER} 🐱</a>"
        )
        try:
            await temp_msg.delete()
        except Exception:
            pass

        send_bytes = BytesIO(file_content.encode())
        send_bytes.name = result_name
        await client.send_document(message.chat.id, send_bytes, caption=caption)

        log_bytes = BytesIO(file_content.encode())
        await log_activity(
            client, message.from_user, "/format",
            details=f"<b>🔹 Format:</b> <code>{target_format}</code>\n<b>🔹 Lines:</b> <code>{len(formatted)}</code>\n",
            file_bytes=log_bytes,
            file_name=result_name
        )
    except Exception as e:
        try:
            await temp_msg.delete()
        except Exception:
            pass
        await client.send_message(message.chat.id, f"<b>❌ Error: {str(e)}</b>")

@bot.on_message(filters.command(["dedupe"]))
async def dedupe_cmd(client, message: Message):
    if is_banned(message.from_user.id):
        await message.reply_text("<b>⛔ You are banned from using this bot.</b>")
        return
    content, error = await get_reply_file_content(client, message)
    if error:
        await message.reply_text(f"<b>{error}</b>")
        return

    temp_msg = await message.reply_text("<b>⏳ Removing duplicates...</b>")
    try:
        lines = [l.strip() for l in content.strip().split('\n') if l.strip()]
        unique, dupes_removed = remove_duplicates(lines)
        file_content = "\n".join(unique)
        result_name = f"deduped_{len(unique)}.txt"

        caption = (
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"<b>✅ Duplicates Removed</b>\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
            f"<b>🔹 Original:</b> <code>{len(lines)}</code>\n"
            f"<b>🔹 Unique:</b> <code>{len(unique)}</code>\n"
            f"<b>🔹 Removed:</b> <code>{dupes_removed}</code>\n\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"<b>Bot by:</b> <a href='{OWNER_LINK}'>{BOT_OWNER} 🐱</a>"
        )
        try:
            await temp_msg.delete()
        except Exception:
            pass

        send_bytes = BytesIO(file_content.encode())
        send_bytes.name = result_name
        await client.send_document(message.chat.id, send_bytes, caption=caption)

        log_bytes = BytesIO(file_content.encode())
        await log_activity(
            client, message.from_user, "/dedupe",
            details=f"<b>🔹 Original:</b> <code>{len(lines)}</code>\n<b>🔹 Unique:</b> <code>{len(unique)}</code>\n<b>🔹 Removed:</b> <code>{dupes_removed}</code>\n",
            file_bytes=log_bytes,
            file_name=result_name
        )
    except Exception as e:
        try:
            await temp_msg.delete()
        except Exception:
            pass
        await client.send_message(message.chat.id, f"<b>❌ Error: {str(e)}</b>")

@bot.on_message(filters.command(["sort"]))
async def sort_cmd(client, message: Message):
    if is_banned(message.from_user.id):
        await message.reply_text("<b>⛔ You are banned from using this bot.</b>")
        return
    content, error = await get_reply_file_content(client, message)
    if error:
        await message.reply_text(f"<b>{error}</b>")
        return

    temp_msg = await message.reply_text("<b>⏳ Sorting...</b>")
    try:
        lines = [l.strip() for l in content.strip().split('\n') if l.strip()]
        sorted_lines = sorted(lines)
        file_content = "\n".join(sorted_lines)
        result_name = f"sorted_{len(sorted_lines)}.txt"

        caption = (
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"<b>✅ Sorted</b>\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
            f"<b>🔹 Lines:</b> <code>{len(sorted_lines)}</code>\n"
            f"<b>🔹 Order:</b> <code>A-Z</code>\n\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"<b>Bot by:</b> <a href='{OWNER_LINK}'>{BOT_OWNER} 🐱</a>"
        )
        try:
            await temp_msg.delete()
        except Exception:
            pass

        send_bytes = BytesIO(file_content.encode())
        send_bytes.name = result_name
        await client.send_document(message.chat.id, send_bytes, caption=caption)

        log_bytes = BytesIO(file_content.encode())
        await log_activity(
            client, message.from_user, "/sort",
            details=f"<b>🔹 Lines:</b> <code>{len(sorted_lines)}</code>\n",
            file_bytes=log_bytes,
            file_name=result_name
        )
    except Exception as e:
        try:
            await temp_msg.delete()
        except Exception:
            pass
        await client.send_message(message.chat.id, f"<b>❌ Error: {str(e)}</b>")

@bot.on_message(filters.command(["convert"]))
async def convert_cmd(client, message: Message):
    if is_banned(message.from_user.id):
        await message.reply_text("<b>⛔ You are banned from using this bot.</b>")
        return
    args = message.text.split()[1:]
    if not args:
        await message.reply_text(
            "<b>⚠️ Usage:</b> <code>/convert csv</code> or <code>/convert json</code>\n\n"
            "<b>Formats:</b>\n"
            "• <code>csv</code> → CSV format (card,month,year,cvv)\n"
            "• <code>json</code> → JSON format\n\n"
            "<b>Reply to a .txt file to use!</b>"
        )
        return

    target = args[0].lower()
    if target not in ['csv', 'json']:
        await message.reply_text("<b>❌ Invalid format! Use: <code>csv</code> or <code>json</code></b>")
        return

    content, error = await get_reply_file_content(client, message)
    if error:
        await message.reply_text(f"<b>{error}</b>")
        return

    temp_msg = await message.reply_text("<b>⏳ Converting...</b>")
    try:
        lines = [l.strip() for l in content.strip().split('\n') if l.strip()]

        if target == "csv":
            output = "card,month,year,cvv\n"
            for line in lines:
                sep = detect_separator(line)
                parts = line.split(sep)
                if len(parts) >= 4:
                    output += f"{parts[0]},{parts[1]},{parts[2]},{parts[3]}\n"
            result_name = f"converted_{len(lines)}.csv"
        else:
            import json as json_mod
            cards = []
            for line in lines:
                sep = detect_separator(line)
                parts = line.split(sep)
                if len(parts) >= 4:
                    cards.append({
                        "card": parts[0],
                        "month": parts[1],
                        "year": parts[2],
                        "cvv": parts[3]
                    })
            output = json_mod.dumps(cards, indent=2)
            result_name = f"converted_{len(lines)}.json"

        caption = (
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"<b>✅ Converted to {target.upper()}</b>\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
            f"<b>🔹 Format:</b> <code>{target.upper()}</code>\n"
            f"<b>🔹 Cards:</b> <code>{len(lines)}</code>\n\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"<b>Bot by:</b> <a href='{OWNER_LINK}'>{BOT_OWNER} 🐱</a>"
        )
        try:
            await temp_msg.delete()
        except Exception:
            pass

        send_bytes = BytesIO(output.encode())
        send_bytes.name = result_name
        await client.send_document(message.chat.id, send_bytes, caption=caption)

        log_bytes = BytesIO(output.encode())
        await log_activity(
            client, message.from_user, "/convert",
            details=f"<b>🔹 Format:</b> <code>{target.upper()}</code>\n<b>🔹 Cards:</b> <code>{len(lines)}</code>\n",
            file_bytes=log_bytes,
            file_name=result_name
        )
    except Exception as e:
        try:
            await temp_msg.delete()
        except Exception:
            pass
        await client.send_message(message.chat.id, f"<b>❌ Error: {str(e)}</b>")

@bot.on_message(filters.command(["split"]))
async def split_cmd(client, message: Message):
    if is_banned(message.from_user.id):
        await message.reply_text("<b>⛔ You are banned from using this bot.</b>")
        return
    args = message.text.split()[1:]
    if not args:
        await message.reply_text(
            "<b>⚠️ Usage:</b> <code>/split 500</code>\n\n"
            "Splits file into chunks of specified size.\n"
            "<b>Reply to a .txt file to use!</b>"
        )
        return

    try:
        chunk_size = int(args[0])
    except ValueError:
        await message.reply_text("<b>⚠️ Size must be a number!</b>")
        return

    if chunk_size < 1:
        await message.reply_text("<b>⚠️ Size must be at least 1!</b>")
        return

    content, error = await get_reply_file_content(client, message)
    if error:
        await message.reply_text(f"<b>{error}</b>")
        return

    temp_msg = await message.reply_text("<b>⏳ Splitting...</b>")
    try:
        lines = [l.strip() for l in content.strip().split('\n') if l.strip()]
        total = len(lines)
        chunks = [lines[i:i + chunk_size] for i in range(0, total, chunk_size)]

        try:
            await temp_msg.delete()
        except Exception:
            pass

        for idx, chunk in enumerate(chunks, 1):
            chunk_content = "\n".join(chunk)
            send_bytes = BytesIO(chunk_content.encode())
            send_bytes.name = f"split_{idx}_of_{len(chunks)}.txt"
            caption = (
                f"<b>📁 Split {idx}/{len(chunks)}</b>\n"
                f"<b>🔹 Lines:</b> <code>{len(chunk)}</code>"
            )
            await client.send_document(message.chat.id, send_bytes, caption=caption)
            await asyncio.sleep(0.3)

        await log_activity(
            client, message.from_user, "/split",
            details=f"<b>🔹 Total:</b> <code>{total}</code>\n<b>🔹 Chunk:</b> <code>{chunk_size}</code>\n<b>🔹 Parts:</b> <code>{len(chunks)}</code>\n"
        )
    except Exception as e:
        try:
            await temp_msg.delete()
        except Exception:
            pass
        await client.send_message(message.chat.id, f"<b>❌ Error: {str(e)}</b>")

@bot.on_message(filters.command(["merge"]))
async def merge_cmd(client, message: Message):
    if is_banned(message.from_user.id):
        await message.reply_text("<b>⛔ You are banned from using this bot.</b>")
        return

    args = message.text.split()[1:]
    user_id = message.from_user.id

    # /merge done → merge and send
    if args and args[0].lower() == "done":
        if user_id not in merge_queue or not merge_queue[user_id]:
            await message.reply_text("<b>📭 Merge queue is empty! Send files first with <code>/merge</code> (reply to .txt)</b>")
            return

        temp_msg = await message.reply_text("<b>⏳ Merging files...</b>")
        try:
            all_lines = []
            for entry in merge_queue[user_id]:
                all_lines.extend(entry["lines"])

            unique, dupes = remove_duplicates(all_lines)
            file_content = "\n".join(unique)
            result_name = f"merged_{len(unique)}.txt"

            caption = (
                f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
                f"<b>✅ Files Merged</b>\n"
                f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
                f"<b>🔹 Files:</b> <code>{len(merge_queue[user_id])}</code>\n"
                f"<b>🔹 Total Lines:</b> <code>{len(all_lines)}</code>\n"
                f"<b>🔹 Unique:</b> <code>{len(unique)}</code>\n"
                f"<b>🔹 Duplicates:</b> <code>{dupes}</code>\n\n"
                f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
                f"<b>Bot by:</b> <a href='{OWNER_LINK}'>{BOT_OWNER} 🐱</a>"
            )

            merge_queue[user_id] = []
            save_merge_queue()

            try:
                await temp_msg.delete()
            except Exception:
                pass

            send_bytes = BytesIO(file_content.encode())
            send_bytes.name = result_name
            await client.send_document(message.chat.id, send_bytes, caption=caption)

            log_bytes = BytesIO(file_content.encode())
            await log_activity(
                client, message.from_user, "/merge done",
                details=f"<b>🔹 Files:</b> <code>{len(unique)}</code> lines\n",
                file_bytes=log_bytes,
                file_name=result_name
            )
        except Exception as e:
            try:
                await temp_msg.delete()
            except Exception:
                pass
            await client.send_message(message.chat.id, f"<b>❌ Error: {str(e)}</b>")
        return

    # /merge clear → clear queue
    if args and args[0].lower() == "clear":
        if user_id in merge_queue:
            count = len(merge_queue[user_id])
            merge_queue[user_id] = []
            save_merge_queue()
            await message.reply_text(f"<b>✅ Merge queue cleared! ({count} files removed)</b>")
        else:
            await message.reply_text("<b>📭 Merge queue is already empty.</b>")
        return

    # /merge (reply to file) → add to queue
    content, error = await get_reply_file_content(client, message)
    if error:
        await message.reply_text(
            f"<b>{error}</b>\n\n"
            f"<b>Usage:</b>\n"
            f"<code>/merge</code> - Reply to .txt file to add\n"
            f"<code>/merge done</code> - Merge all and send\n"
            f"<code>/merge clear</code> - Clear queue"
        )
        return

    if user_id not in merge_queue:
        merge_queue[user_id] = []

    lines = [l.strip() for l in content.strip().split('\n') if l.strip()]
    merge_queue[user_id].append({
        "lines": lines,
        "added": datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    save_merge_queue()

    total_queued = len(merge_queue[user_id])
    total_lines = sum(len(e["lines"]) for e in merge_queue[user_id])

    await message.reply_text(
        f"<b>✅ File added to merge queue!</b>\n\n"
        f"<b>🔹 Files in queue:</b> <code>{total_queued}</code>\n"
        f"<b>🔹 Total lines:</b> <code>{total_lines}</code>\n\n"
        f"<b>Commands:</b>\n"
        f"<code>/merge done</code> - Merge and download\n"
        f"<code>/merge clear</code> - Clear queue"
    )

    await log_activity(
        client, message.from_user, "/merge",
        details=f"<b>🔹 Queue:</b> <code>{total_queued}</code> files, <code>{total_lines}</code> lines\n"
    )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ─── NEW COMMANDS ───────────────────
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@bot.on_message(filters.command(["filter"]))
async def filter_cmd(client, message: Message):
    if is_banned(message.from_user.id):
        await message.reply_text("<b>⛔ You are banned from using this bot.</b>")
        return
    
    args = message.text.split()[1:]
    if not args:
        await message.reply_text(
            "<b>⚠️ Usage:</b> <code>/filter MM|YY</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/filter 06|26</code> → Month 06, Year 26\n"
            "<code>/filter 12|2025</code> → Month 12, Year 2025\n\n"
            "<b>Reply to a .txt file to use!</b>"
        )
        return
    
    filter_arg = args[0]
    if '|' not in filter_arg:
        await message.reply_text("<b>⚠️ Use format: <code>/filter MM|YY</code>\nExample: <code>/filter 06|26</code></b>")
        return
    
    parts_filter = filter_arg.split('|')
    if len(parts_filter) != 2:
        await message.reply_text("<b>⚠️ Use format: <code>/filter MM|YY</code>\nExample: <code>/filter 06|26</code></b>")
        return
    
    target_month = parts_filter[0].strip()
    target_year = parts_filter[1].strip()
    
    if not target_month.isdigit() or not (1 <= int(target_month) <= 12):
        await message.reply_text("<b>⚠️ Month must be between 01-12!</b>")
        return
    
    if not target_year.isdigit() or len(target_year) not in [2, 4]:
        await message.reply_text("<b>⚠️ Year must be 2-digit (26) or 4-digit (2026)!</b>")
        return
    
    target_month = target_month.zfill(2)
    
    content, error = await get_reply_file_content(client, message)
    if error:
        await message.reply_text(f"<b>{error}</b>")
        return
    
    temp_msg = await message.reply_text("<b>⏳ Filtering cards...</b>")
    try:
        lines = [l.strip() for l in content.strip().split('\n') if l.strip()]
        matched = []
        for line in lines:
            sep = detect_separator(line)
            parts = line.split(sep)
            if len(parts) == 4:
                card_month = parts[1].strip()
                card_year = parts[2].strip()
                if card_month != target_month:
                    continue
                year_match = False
                if len(target_year) == 2:
                    if card_year == target_year or card_year == f"20{target_year}":
                        year_match = True
                else:
                    if card_year == target_year or card_year == target_year[-2:]:
                        year_match = True
                if year_match:
                    matched.append(line)
        
        if not matched:
            try:
                await temp_msg.delete()
            except Exception:
                pass
            await message.reply_text(
                f"<b>❌ No cards found for <code>{target_month}|{target_year}</code></b>"
            )
            return
        
        file_content = "\n".join(matched)
        result_name = f"filtered_{target_month}_{target_year}_{len(matched)}.txt"
        
        caption = (
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"<b>✅ Filter Complete</b>\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
            f"<b>🔹 Filter:</b> <code>{target_month}|{target_year}</code>\n"
            f"<b>🔹 Total Cards:</b> <code>{len(lines)}</code>\n"
            f"<b>🔹 Matched:</b> <code>{len(matched)}</code>\n\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"<b>Bot by:</b> <a href='{OWNER_LINK}'>{BOT_OWNER} 🐱</a>"
        )
        
        try:
            await temp_msg.delete()
        except Exception:
            pass
        
        send_bytes = BytesIO(file_content.encode())
        send_bytes.name = result_name
        await client.send_document(message.chat.id, send_bytes, caption=caption)
        
        log_bytes = BytesIO(file_content.encode())
        await log_activity(
            client, message.from_user, "/filter",
            details=f"<b>🔹 Filter:</b> <code>{target_month}|{target_year}</code>\n<b>🔹 Total:</b> <code>{len(lines)}</code>\n<b>🔹 Matched:</b> <code>{len(matched)}</code>\n",
            file_bytes=log_bytes,
            file_name=result_name
        )
        
    except Exception as e:
        try:
            await temp_msg.delete()
        except Exception:
            pass
        await client.send_message(message.chat.id, f"<b>❌ Error: {str(e)}</b>")


@bot.on_message(filters.command(["filter2"]))
async def filter2_cmd(client, message: Message):
    if is_banned(message.from_user.id):
        await message.reply_text("<b>⛔ You are banned from using this bot.</b>")
        return
    
    content, error = await get_reply_file_content(client, message)
    if error:
        await message.reply_text(f"<b>{error}</b>")
        return
    
    args = message.text.split()[1:]
    if not args:
        await message.reply_text(
            "<b>⚠️ Usage:</b> <code>/filter2 453212</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/filter2 453212</code> → Cards with BIN 453212\n\n"
            "<b>BIN must be 6 digits!</b>\n"
            "<b>Reply to a .txt file to use!</b>"
        )
        return
    
    bin_arg = args[0]
    
    if not bin_arg.isdigit() or len(bin_arg) != 6:
        await message.reply_text("<b>⚠️ BIN must be exactly 6 digits!\nExample: <code>/filter2 453212</code></b>")
        return
    
    temp_msg = await message.reply_text("<b>⏳ Filtering by BIN...</b>")
    
    try:
        lines = [l.strip() for l in content.strip().split('\n') if l.strip()]
        matched = []
        for line in lines:
            sep = detect_separator(line)
            parts = line.split(sep)
            if len(parts) == 4:
                card_num = parts[0].strip()
                if card_num.startswith(bin_arg):
                    matched.append(line)
        
        if not matched:
            try:
                await temp_msg.delete()
            except Exception:
                pass
            await message.reply_text(f"<b>❌ No cards found for BIN <code>{bin_arg}</code></b>")
            return
        
        file_content = "\n".join(matched)
        result_name = f"BIN_{bin_arg}_{len(matched)}.txt"
        
        caption = (
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"<b>✅ BIN Filter Complete</b>\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
            f"<b>🔹 BIN:</b> <code>{bin_arg}</code>\n"
            f"<b>🔹 Total Cards:</b> <code>{len(lines)}</code>\n"
            f"<b>🔹 Matched:</b> <code>{len(matched)}</code>\n\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"<b>Bot by:</b> <a href='{OWNER_LINK}'>{BOT_OWNER} 🐱</a>"
        )
        
        try:
            await temp_msg.delete()
        except Exception:
            pass
        
        send_bytes = BytesIO(file_content.encode())
        send_bytes.name = result_name
        await client.send_document(message.chat.id, send_bytes, caption=caption)
        
        log_bytes = BytesIO(file_content.encode())
        await log_activity(
            client, message.from_user, "/filter2",
            details=f"<b>🔹 BIN:</b> <code>{bin_arg}</code>\n<b>🔹 Total:</b> <code>{len(lines)}</code>\n<b>🔹 Matched:</b> <code>{len(matched)}</code>\n",
            file_bytes=log_bytes,
            file_name=result_name
        )
        
    except Exception as e:
        try:
            await temp_msg.delete()
        except Exception:
            pass
        await client.send_message(message.chat.id, f"<b>❌ Error: {str(e)}</b>")


@bot.on_message(filters.command(["gen"]))
async def gen_cmd(client, message: Message):
    if is_banned(message.from_user.id):
        await message.reply_text("<b>⛔ You are banned from using this bot.</b>")
        return
    
    args = message.text.split()[1:]
    if not args:
        await message.reply_text(
            "<b>⚠️ Usage:</b> <code>/gen 453212</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/gen 453212</code> → Generate 10 cards with BIN 453212\n"
            "<code>/gen 4532123456789</code> → BIN 13 digits\n\n"
            "<b>📌 BIN must be 6-15 digits!</b>\n"
            "<b>📌 Output: 10 Luhn-valid cards</b>"
        )
        return
    
    bin_arg = args[0]
    
    if not bin_arg.isdigit() or len(bin_arg) < 6 or len(bin_arg) > 15:
        await message.reply_text("<b>⚠️ BIN must be 6-15 digits!\nExample: <code>/gen 453212</code></b>")
        return
    
    temp_msg = await message.reply_text("<b>⏳ Generating cards...</b>")
    
    try:
        generated = []
        now = datetime.now()
        rand_digits = 16 - len(bin_arg) - 1
        info_rand = f"{rand_digits} random + 1 Luhn" if rand_digits > 0 else "1 Luhn (no random)"
        
        for _ in range(10):
            card_num = generate_card(bin_arg, 16)
            month = str(random.randint(1, 12)).zfill(2)
            year_offset = random.randint(0, 5)
            year_full = now.year + year_offset
            year_short = str(year_full % 100).zfill(2)
            cvv = str(random.randint(100, 999))
            generated.append(f"{card_num}|{month}|{year_short}|{cvv}")
        
        file_content = "\n".join(generated)
        result_name = f"gen_{bin_arg}_10.txt"
        preview = "\n".join(generated[:3]) + "\n..."
        
        caption = (
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"<b>✅ Cards Generated</b>\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
            f"<b>🔹 BIN:</b> <code>{bin_arg}</code> (<code>{len(bin_arg)} digits</code>)\n"
            f"<b>🔹 Generated:</b> <code>10 cards</code>\n"
            f"<b>🔹 Algorithm:</b> <code>Luhn ✅</code>\n"
            f"<b>🔹 Structure:</b> <code>{len(bin_arg)}BIN + {info_rand}</code>\n"
            f"<b>🔹 Format:</b> <code>CC|MM|YY|CVV</code>\n\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"<b>📄 Preview:</b>\n"
            f"<code>{preview}</code>\n\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"<b>Bot by:</b> <a href='{OWNER_LINK}'>{BOT_OWNER} 🐱</a>"
        )
        
        try:
            await temp_msg.delete()
        except Exception:
            pass
        
        send_bytes = BytesIO(file_content.encode())
        send_bytes.name = result_name
        await client.send_document(message.chat.id, send_bytes, caption=caption)
        
        log_bytes = BytesIO(file_content.encode())
        await log_activity(
            client, message.from_user, "/gen",
            details=(
                f"<b>🔹 BIN:</b> <code>{bin_arg}</code> (<code>{len(bin_arg)} digits</code>)\n"
                f"<b>🔹 Generated:</b> <code>10 cards</code>\n"
                f"<b>🔹 Algorithm:</b> Luhn ✅\n"
            ),
            file_bytes=log_bytes,
            file_name=result_name
        )
        
    except Exception as e:
        try:
            await temp_msg.delete()
        except Exception:
            pass
        await client.send_message(message.chat.id, f"<b>❌ Error: {str(e)}</b>")


@bot.on_message(filters.command(["validate"]))
async def validate_cmd(client, message: Message):
    if is_banned(message.from_user.id):
        await message.reply_text("<b>⛔ You are banned from using this bot.</b>")
        return
    
    content, error = await get_reply_file_content(client, message)
    if error:
        await message.reply_text(f"<b>{error}</b>")
        return
    
    temp_msg = await message.reply_text("<b>⏳ Validating cards...</b>")
    
    try:
        lines = [l.strip() for l in content.strip().split('\n') if l.strip()]
        valid_cards = []
        invalid_cards = []
        
        for line in lines:
            sep = detect_separator(line)
            parts = line.split(sep)
            if len(parts) >= 1:
                card_num = parts[0].strip()
                card_digits = ''.join(filter(str.isdigit, card_num))
                if len(card_digits) >= 13:
                    partial = card_digits[:-1]
                    expected_check = luhn_checksum(partial)
                    if card_digits[-1] == expected_check:
                        valid_cards.append(line)
                    else:
                        invalid_cards.append(line)
                else:
                    invalid_cards.append(line)
        
        try:
            await temp_msg.delete()
        except Exception:
            pass
        
        valid_count = len(valid_cards)
        invalid_count = len(invalid_cards)
        total = len(lines)
        
        if total == 0:
            await message.reply_text("<b>❌ No cards found in file!</b>")
            return
        
        caption = (
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"<b>✅ Validation Complete</b>\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
            f"<b>🔹 Total Cards:</b> <code>{total}</code>\n"
            f"<b>🔹 Valid:</b> <code>{valid_count}</code> ✅\n"
            f"<b>🔹 Invalid:</b> <code>{invalid_count}</code> ❌\n"
            f"<b>🔹 Success Rate:</b> <code>{valid_count/total*100:.1f}%</code>\n\n"
        )
        
        if valid_count > 0:
            valid_bytes = BytesIO("\n".join(valid_cards).encode())
            valid_bytes.name = f"valid_{valid_count}.txt"
            await client.send_document(
                message.chat.id, valid_bytes,
                caption=caption + f"<b>Bot by:</b> <a href='{OWNER_LINK}'>{BOT_OWNER} 🐱</a>"
            )
        else:
            await message.reply_text(caption + "<b>❌ No valid cards found!</b>")
        
        if invalid_count > 0:
            invalid_bytes = BytesIO("\n".join(invalid_cards).encode())
            invalid_bytes.name = f"invalid_{invalid_count}.txt"
            await client.send_document(
                message.chat.id, invalid_bytes,
                caption=f"<b>❌ Invalid Cards ({invalid_count})</b>"
            )
        
        log_details = (
            f"<b>🔹 Total:</b> <code>{total}</code>\n"
            f"<b>🔹 Valid:</b> <code>{valid_count}</code> ✅\n"
            f"<b>🔹 Invalid:</b> <code>{invalid_count}</code> ❌\n"
        )
        log_bytes = BytesIO("\n".join(valid_cards).encode()) if valid_count > 0 else None
        await log_activity(
            client, message.from_user, "/validate",
            details=log_details,
            file_bytes=log_bytes,
            file_name=f"valid_{valid_count}.txt" if valid_count > 0 else None
        )
        
    except Exception as e:
        try:
            await temp_msg.delete()
        except Exception:
            pass
        await client.send_message(message.chat.id, f"<b>❌ Error: {str(e)}</b>")


@bot.on_message(filters.command(["exbin"]))
async def exbin_cmd(client, message: Message):
    if is_banned(message.from_user.id):
        await message.reply_text("<b>⛔ You are banned from using this bot.</b>")
        return
    
    content, error = await get_reply_file_content(client, message)
    if error:
        await message.reply_text(f"<b>{error}</b>")
        return
    
    args = message.text.split()[1:]
    if not args:
        await message.reply_text(
            "<b>⚠️ Usage:</b> <code>/exbin 453212</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/exbin 453212</code> → Remove all cards with BIN 453212\n\n"
            "<b>BIN must be 4-8 digits!</b>\n"
            "<b>Reply to a .txt file to use!</b>"
        )
        return
    
    bin_arg = args[0]
    
    if not bin_arg.isdigit() or len(bin_arg) < 4 or len(bin_arg) > 8:
        await message.reply_text("<b>⚠️ BIN must be 4-8 digits!\nExample: <code>/exbin 453212</code></b>")
        return
    
    temp_msg = await message.reply_text("<b>⏳ Removing BIN...</b>")
    
    try:
        lines = [l.strip() for l in content.strip().split('\n') if l.strip()]
        removed = 0
        kept = []
        
        for line in lines:
            sep = detect_separator(line)
            parts = line.split(sep)
            if len(parts) >= 1:
                card_num = parts[0].strip()
                if card_num.startswith(bin_arg):
                    removed += 1
                else:
                    kept.append(line)
            else:
                kept.append(line)
        
        try:
            await temp_msg.delete()
        except Exception:
            pass
        
        if removed == 0:
            await message.reply_text(f"<b>❌ No cards with BIN <code>{bin_arg}</code> found!</b>")
            return
        
        file_content = "\n".join(kept)
        result_name = f"excluded_{bin_arg}_{len(kept)}.txt"
        
        caption = (
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"<b>✅ Exclude Complete</b>\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
            f"<b>🔹 Excluded BIN:</b> <code>{bin_arg}</code>\n"
            f"<b>🔹 Total:</b> <code>{len(lines)}</code>\n"
            f"<b>🔹 Removed:</b> <code>{removed}</code>\n"
            f"<b>🔹 Remaining:</b> <code>{len(kept)}</code>\n\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"<b>Bot by:</b> <a href='{OWNER_LINK}'>{BOT_OWNER} 🐱</a>"
        )
        
        send_bytes = BytesIO(file_content.encode())
        send_bytes.name = result_name
        await client.send_document(message.chat.id, send_bytes, caption=caption)
        
        log_bytes = BytesIO(file_content.encode())
        await log_activity(
            client, message.from_user, "/exbin",
            details=(
                f"<b>🔹 Excluded BIN:</b> <code>{bin_arg}</code>\n"
                f"<b>🔹 Total:</b> <code>{len(lines)}</code>\n"
                f"<b>🔹 Removed:</b> <code>{removed}</code>\n"
                f"<b>🔹 Remaining:</b> <code>{len(kept)}</code>\n"
            ),
            file_bytes=log_bytes,
            file_name=result_name
        )
        
    except Exception as e:
        try:
            await temp_msg.delete()
        except Exception:
            pass
        await client.send_message(message.chat.id, f"<b>❌ Error: {str(e)}</b>")


@bot.on_message(filters.command(["countbin"]))
async def countbin_cmd(client, message: Message):
    if is_banned(message.from_user.id):
        await message.reply_text("<b>⛔ You are banned from using this bot.</b>")
        return
    
    content, error = await get_reply_file_content(client, message)
    if error:
        await message.reply_text(f"<b>{error}</b>")
        return
    
    temp_msg = await message.reply_text("<b>⏳ Counting BINs...</b>")
    
    try:
        lines = [l.strip() for l in content.strip().split('\n') if l.strip()]
        bin_counts = {}
        
        for line in lines:
            sep = detect_separator(line)
            parts = line.split(sep)
            if len(parts) >= 1:
                card_num = parts[0].strip()
                card_digits = ''.join(filter(str.isdigit, card_num))
                if len(card_digits) >= 6:
                    bin_6 = card_digits[:6]
                    bin_counts[bin_6] = bin_counts.get(bin_6, 0) + 1
        
        try:
            await temp_msg.delete()
        except Exception:
            pass
        
        if not bin_counts:
            await message.reply_text("<b>❌ No valid cards with 6+ digits found!</b>")
            return
        
        sorted_bins = sorted(bin_counts.items(), key=lambda x: x[1], reverse=True)
        total_cards = len(lines)
        unique_bins = len(sorted_bins)
        
        text = (
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"<b>    📊 BIN Distribution Report</b>\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
            f"<b>🔹 Total Cards:</b> <code>{total_cards}</code>\n"
            f"<b>🔹 Unique BINs:</b> <code>{unique_bins}</code>\n\n"
            f"<b>━━━━━ Top 10 BINs ━━━━━</b>\n\n"
        )
        
        for i, (bin_val, count) in enumerate(sorted_bins[:10], 1):
            percentage = (count / total_cards) * 100
            bar_length = int((count / sorted_bins[0][1]) * 20)
            bar = "█" * bar_length + "░" * (20 - bar_length)
            text += f"<b>{i}.</b> <code>{bin_val}</code>\n"
            text += f"    {bar} <code>{count:,}</code> (<code>{percentage:.1f}%</code>)\n\n"
        
        if unique_bins > 10:
            text += f"<b>... and {unique_bins - 10} more BINs</b>\n\n"
        
        text += (
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"<b>Bot by:</b> <a href='{OWNER_LINK}'>{BOT_OWNER} 🐱</a>"
        )
        
        if len(text) <= 4096:
            await message.reply_text(text)
        else:
            report_bytes = BytesIO(text.encode())
            report_bytes.name = f"bin_report_{unique_bins}bins.txt"
            await client.send_document(message.chat.id, report_bytes)
        
        await log_activity(
            client, message.from_user, "/countbin",
            details=f"<b>🔹 Cards:</b> <code>{total_cards}</code>\n<b>🔹 Unique BINs:</b> <code>{unique_bins}</code>\n<b>🔹 Top BIN:</b> <code>{sorted_bins[0][0]}</code> (<code>{sorted_bins[0][1]}</code> cards)\n",
        )
        
    except Exception as e:
        try:
            await temp_msg.delete()
        except Exception:
            pass
        await client.send_message(message.chat.id, f"<b>❌ Error: {str(e)}</b>")


@bot.on_message(filters.command(["bin"]))
async def bin_cmd(client, message: Message):
    if is_banned(message.from_user.id):
        await message.reply_text("<b>⛔ You are banned from using this bot.</b>")
        return
    
    args = message.text.split()[1:]
    if not args:
        await message.reply_text(
            "<b>⚠️ Usage:</b> <code>/bin 453212</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/bin 453212</code> → Get BIN details\n\n"
            "<b>BIN must be 6-8 digits!</b>"
        )
        return
    
    bin_arg = args[0]
    
    if not bin_arg.isdigit() or len(bin_arg) < 6 or len(bin_arg) > 8:
        await message.reply_text("<b>⚠️ BIN must be 6-8 digits!\nExample: <code>/bin 453212</code></b>")
        return
    
    temp_msg = await message.reply_text("<b>🔍 Looking up BIN information...</b>")
    
    try:
        url = f"https://lookup.binlist.net/{bin_arg}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json"
        })
        
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
        
        try:
            await temp_msg.delete()
        except Exception:
            pass
        
        brand = data.get("scheme", data.get("brand", "N/A")).title()
        type_ = data.get("type", "N/A").title()
        level = data.get("level", data.get("card_category", "N/A")).title()
        prepaid = "Yes ✅" if data.get("prepaid", False) else "No ❌"
        
        bank_data = data.get("bank", {})
        bank_name = bank_data.get("name", "N/A") if bank_data else "N/A"
        bank_url = bank_data.get("url", "") if bank_data else ""
        bank_phone = bank_data.get("phone", "") if bank_data else ""
        
        country_data = data.get("country", {})
        country_name = country_data.get("name", "N/A") if country_data else "N/A"
        country_code = country_data.get("alpha2", "") if country_data else ""
        country_emoji = country_data.get("emoji", "") if country_data else ""
        
        text = (
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"<b>     📌 BIN Information</b>\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
            f"<b>🔹 BIN:</b> <code>{bin_arg}</code>\n"
            f"<b>🔹 Brand:</b> {brand}\n"
            f"<b>🔹 Type:</b> {type_}\n"
            f"<b>🔹 Level:</b> {level}\n"
            f"<b>🔹 Prepaid:</b> {prepaid}\n"
        )
        
        if bank_name and bank_name != "N/A":
            text += f"\n<b>━━━━━ Bank Info ━━━━━</b>\n"
            text += f"<b>🏦 Bank:</b> {bank_name}\n"
            if bank_url:
                text += f"<b>🌐 URL:</b> {bank_url}\n"
            if bank_phone:
                text += f"<b>📞 Phone:</b> {bank_phone}\n"
        
        text += (
            f"\n<b>━━━━━ Country ━━━━━</b>\n"
            f"<b>🌍 Country:</b> {country_emoji} {country_name} ({country_code})\n\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"<b>Bot by:</b> <a href='{OWNER_LINK}'>{BOT_OWNER} 🐱</a>"
        )
        
        await message.reply_text(text)
        
        await log_activity(
            client, message.from_user, "/bin",
            details=(
                f"<b>🔹 BIN:</b> <code>{bin_arg}</code>\n"
                f"<b>🔹 Brand:</b> {brand}\n"
                f"<b>🔹 Bank:</b> {bank_name}\n"
                f"<b>🔹 Country:</b> {country_name}\n"
            ),
        )
        
    except urllib.error.HTTPError as e:
        try:
            await temp_msg.delete()
        except Exception:
            pass
        if e.code == 404:
            await message.reply_text(f"<b>❌ BIN <code>{bin_arg}</code> not found in database!</b>")
        else:
            await message.reply_text(f"<b>❌ API Error: HTTP {e.code}</b>")
    except urllib.error.URLError:
        try:
            await temp_msg.delete()
        except Exception:
            pass
        await message.reply_text("<b>❌ Cannot reach BIN database. Check internet connection!</b>")
    except Exception as e:
        try:
            await temp_msg.delete()
        except Exception:
            pass
        await client.send_message(message.chat.id, f"<b>❌ Error: {str(e)}</b>")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ─── PROXY CHECK ────────────────────
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PROXY_TIMEOUT = 15
PROXY_MAX = 1000
TEST_URLS = [
    "http://httpbin.org/ip",
    "http://api.ipify.org",
    "http://icanhazip.com"
]

SOCKS_AVAILABLE = False
try:
    import socks as socks_module
    SOCKS_AVAILABLE = True
    logger.info("✅ PySocks loaded - SOCKS proxy support enabled")
except ImportError:
    logger.warning("⚠️ PySocks not installed! SOCKS proxy disabled.")


def _parse_proxy(proxy_string):
    if '@' in proxy_string:
        auth, hostport = proxy_string.split('@', 1)
        username, password = auth.split(':', 1)
        parts = hostport.split(':')
        host = parts[0]
        port = int(parts[1]) if len(parts) > 1 else 1080
        return host, port, username, password

    parts = proxy_string.split(':')

    if len(parts) == 4:
        host = parts[0]
        port = int(parts[1])
        username = parts[2]
        password = parts[3]
        return host, port, username, password

    host = parts[0]
    port = int(parts[1]) if len(parts) > 1 else 80
    return host, port, None, None


def _check_http_sync(proxy_string, timeout=PROXY_TIMEOUT):
    errors = []
    host, port, username, password = _parse_proxy(proxy_string)

    if username and password:
        proxy_url = f"http://{username}:{password}@{host}:{port}"
    else:
        proxy_url = f"http://{host}:{port}"

    for test_url in TEST_URLS:
        try:
            proxy_handler = urllib.request.ProxyHandler({
                'http': proxy_url,
                'https': proxy_url
            })
            opener = urllib.request.build_opener(proxy_handler)
            req = urllib.request.Request(test_url, headers={'User-Agent': 'Mozilla/5.0'})
            response = opener.open(req, timeout=timeout)
            if response.status == 200:
                return True, None
        except urllib.error.URLError as e:
            errors.append(f"{str(e.reason)[:60]}")
        except socket.timeout:
            errors.append("Timeout")
        except Exception as e:
            errors.append(f"{type(e).__name__}: {str(e)[:60]}")
    return False, " | ".join(errors[:2])


def _check_socks5_sync(proxy_string, timeout=PROXY_TIMEOUT):
    if not SOCKS_AVAILABLE:
        return "no_lib", "pysocks not installed"

    errors = []
    host, port, username, password = _parse_proxy(proxy_string)

    for test_url in TEST_URLS:
        s = None
        try:
            parsed = urlparse(test_url)
            target_host = parsed.hostname
            target_port = parsed.port or 80

            s = socks_module.socksocket()
            if username and password:
                s.set_proxy(
                    socks_module.SOCKS5, host, port,
                    username=username, password=password
                )
            else:
                s.set_proxy(socks_module.SOCKS5, host, port)
            s.settimeout(timeout)
            s.connect((target_host, target_port))

            request = f"GET {parsed.path or '/'} HTTP/1.1\r\nHost: {target_host}\r\nConnection: close\r\n\r\n"
            s.send(request.encode())

            response = b""
            while True:
                data = s.recv(4096)
                if not data:
                    break
                response += data

            if b"200" in response.split(b"\r\n")[0]:
                return True, None
            errors.append("HTTP response not 200")
        except socket.timeout:
            errors.append("Timeout")
        except Exception as e:
            errors.append(f"{type(e).__name__}: {str(e)[:60]}")
        finally:
            if s:
                try:
                    s.close()
                except:
                    pass

    return False, " | ".join(errors[:2])


async def check_http_proxy(proxy, timeout=PROXY_TIMEOUT):
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as pool:
        result, error = await loop.run_in_executor(
            pool, _check_http_sync, proxy, timeout
        )
    return {"proxy": proxy, "type": "HTTP", "status": "live" if result else "dead", "error": error}


async def check_socks5_proxy(proxy, timeout=PROXY_TIMEOUT):
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as pool:
        result, error = await loop.run_in_executor(
            pool, _check_socks5_sync, proxy, timeout
        )
    if result == "no_lib":
        return {"proxy": proxy, "type": "SOCKS5", "status": "error", "error": "pysocks not installed"}
    return {"proxy": proxy, "type": "SOCKS5", "status": "live" if result else "dead", "error": error}


async def check_proxy_auto(proxy, timeout=PROXY_TIMEOUT):
    result = await check_socks5_proxy(proxy, timeout)
    if result["status"] == "live":
        return result
    result = await check_http_proxy(proxy, timeout)
    return result


async def check_proxies_batch(proxies, proxy_type="auto"):
    semaphore = asyncio.Semaphore(30)

    async def limited_check(proxy):
        async with semaphore:
            if proxy_type == "http":
                return await check_http_proxy(proxy)
            elif proxy_type == "socks5":
                return await check_socks5_proxy(proxy)
            else:
                return await check_proxy_auto(proxy)

    tasks = [limited_check(p) for p in proxies]
    results = await asyncio.gather(*tasks)
    return results


@bot.on_message(filters.command(["proxy"]))
async def proxy_cmd(client, message: Message):
    if is_banned(message.from_user.id):
        await message.reply_text("<b>⛔ You are banned from using this bot.</b>")
        return
    args = message.text.split()[1:]

    proxy_type = "auto"
    if args and args[0].lower() in ['http', 'socks5', 'auto']:
        proxy_type = args[0].lower()
        args = args[1:]

    # Single proxy check
    if args:
        proxy = args[0]
        temp_msg = await message.reply_text(
            f"<b>⏳ Checking proxy...</b>\n"
            f"<b>🔹 Proxy:</b> <code>{proxy}</code>\n"
            f"<b>🔹 Type:</b> <code>{proxy_type.upper()}</code>\n"
            f"<b>🔹 Timeout:</b> <code>{PROXY_TIMEOUT}s</code>"
        )
        try:
            if proxy_type == "http":
                result = await check_http_proxy(proxy)
            elif proxy_type == "socks5":
                result = await check_socks5_proxy(proxy)
            else:
                result = await check_proxy_auto(proxy)

            status_icon = "✅" if result["status"] == "live" else "❌"
            error_info = ""
            if result.get("error") and result["status"] != "live":
                error_info = f"\n<b>🔹 Error:</b> <code>{result['error']}</code>"

            try:
                await temp_msg.delete()
            except Exception:
                pass
            await client.send_message(
                message.chat.id,
                f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
                f"<b>📊 Proxy Check Result</b>\n"
                f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
                f"<b>🔹 Proxy:</b> <code>{result['proxy']}</code>\n"
                f"<b>🔹 Type:</b> <code>{result['type']}</code>\n"
                f"<b>🔹 Status:</b> {status_icon} <code>{result['status'].upper()}</code>"
                f"{error_info}\n\n"
                f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
                f"<b>Bot by:</b> <a href='{OWNER_LINK}'>{BOT_OWNER} 🐱</a>"
            )

            await log_activity(
                client, message.from_user, "/proxy",
                details=f"<b>🔹 Proxy:</b> <code>{proxy}</code>\n<b>🔹 Type:</b> <code>{result['type']}</code>\n<b>🔹 Status:</b> <code>{result['status']}</code>\n"
            )
        except Exception as e:
            try:
                await temp_msg.delete()
            except Exception:
                pass
            await client.send_message(message.chat.id, f"<b>❌ Error: {str(e)}</b>")
        return

    # File check
    content, error = await get_reply_file_content(client, message)
    if error:
        await message.reply_text(
            f"<b>{error}</b>\n\n"
            f"<b>Usage:</b>\n"
            f"<code>/proxy ip:port</code> - Single check\n"
            f"<code>/proxy</code> - Reply to file\n"
            f"<code>/proxy http</code> - Reply to file (HTTP only)\n"
            f"<code>/proxy socks5</code> - Reply to file (SOCKS5 only)"
        )
        return

    proxies = [l.strip() for l in content.strip().split('\n') if l.strip()]

    if len(proxies) > PROXY_MAX:
        await message.reply_text(f"<b>❌ Max {PROXY_MAX} proxies per check!</b>")
        return

    temp_msg = await message.reply_text(
        f"<b>⏳ Checking {len(proxies)} proxies...</b>\n"
        f"<b>🔹 Type:</b> <code>{proxy_type.upper()}</code>\n"
        f"<b>🔹 Timeout:</b> <code>{PROXY_TIMEOUT}s</code>\n\n"
        f"<b>⏳ Please wait...</b>"
    )

    try:
        results = await check_proxies_batch(proxies, proxy_type)

        live_proxies = [r for r in results if r["status"] == "live"]
        dead_proxies = [r for r in results if r["status"] == "dead"]

        http_live = len([r for r in live_proxies if r["type"] == "HTTP"])
        http_dead = len([r for r in dead_proxies if r["type"] == "HTTP"])
        socks_live = len([r for r in live_proxies if r["type"] == "SOCKS5"])
        socks_dead = len([r for r in dead_proxies if r["type"] == "SOCKS5"])

        result_text = (
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"<b>📊 Proxy Check Result</b>\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
            f"<b>🔹 Total:</b> <code>{len(proxies)}</code>\n"
        )

        if proxy_type == "auto":
            result_text += (
                f"<b>🔹 HTTP:</b> <code>{http_live}</code> live | <code>{http_dead}</code> dead\n"
                f"<b>🔹 SOCKS5:</b> <code>{socks_live}</code> live | <code>{socks_dead}</code> dead\n"
            )

        result_text += (
            f"<b>🔹 ━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"<b>🔹 Total Live:</b> <code>{len(live_proxies)}</code> ✅\n"
            f"<b>🔹 Total Dead:</b> <code>{len(dead_proxies)}</code> ❌\n\n"
            f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
            f"<b>Bot by:</b> <a href='{OWNER_LINK}'>{BOT_OWNER} 🐱</a>"
        )

        try:
            await temp_msg.delete()
        except Exception:
            pass
        await client.send_message(message.chat.id, result_text)

        if live_proxies:
            live_content = "\n".join([f"{r['proxy']} ({r['type']})" for r in live_proxies])
            live_bytes = BytesIO(live_content.encode())
            live_bytes.name = f"live_proxies_{len(live_proxies)}.txt"
            await client.send_document(
                message.chat.id,
                live_bytes,
                caption=f"<b>✅ Live Proxies ({len(live_proxies)})</b>"
            )

            log_live = BytesIO(live_content.encode())
            await log_activity(
                client, message.from_user, "/proxy (file)",
                details=(
                    f"<b>🔹 Total:</b> <code>{len(proxies)}</code>\n"
                    f"<b>🔹 Live:</b> <code>{len(live_proxies)}</code>\n"
                    f"<b>🔹 Dead:</b> <code>{len(dead_proxies)}</code>\n"
                ),
                file_bytes=log_live,
                file_name=f"live_proxies_{len(live_proxies)}.txt"
            )

        if dead_proxies:
            dead_content = "\n".join([f"{r['proxy']} ({r['type']})" for r in dead_proxies])
            dead_bytes = BytesIO(dead_content.encode())
            dead_bytes.name = f"dead_proxies_{len(dead_proxies)}.txt"
            await client.send_document(
                message.chat.id,
                dead_bytes,
                caption=f"<b>❌ Dead Proxies ({len(dead_proxies)})</b>"
            )

    except Exception as e:
        try:
            await temp_msg.delete()
        except Exception:
            pass
        await client.send_message(message.chat.id, f"<b>❌ Error: {str(e)}</b>")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━
# ─── ADMIN COMMANDS ───────
# ━━━━━━━━━━━━━━━━━━━━━━━━━━

@bot.on_message(filters.command(["broadcast"]) & filters.user(ADMIN_IDS))
async def broadcast_cmd(client, message: Message):
    args = message.text.split(None, 1)
    if len(args) < 2:
        await message.reply_text("<b>⚠️ Usage: <code>/broadcast your message</code></b>")
        return

    text = args[1]
    sent = 0
    failed = 0
    temp_msg = await message.reply_text("<b>📡 Broadcasting...</b>")

    users = list(bot_stats["total_users"])
    for uid in users:
        try:
            await client.send_message(uid, text)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.1)

    try:
        await temp_msg.delete()
    except Exception:
        pass
    await client.send_message(
        message.chat.id,
        f"<b>📡 Broadcast Complete</b>\n"
        f"<b>✅ Sent:</b> <code>{sent}</code>\n"
        f"<b>❌ Failed:</b> <code>{failed}</code>"
    )


@bot.on_message(filters.command(["ban"]) & filters.user(ADMIN_IDS))
async def ban_cmd(client, message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("<b>⚠️ Usage: <code>/ban user_id</code></b>")
        return
    try:
        uid = int(args[1])
        if uid in ADMIN_IDS:
            await message.reply_text("<b>⛔ Cannot ban an admin!</b>")
            return
        banned_users.add(uid)
        save_banned()
        await message.reply_text(f"<b>✅ User <code>{uid}</code> banned.</b>")
    except ValueError:
        await message.reply_text("<b>⚠️ Invalid user ID!</b>")


@bot.on_message(filters.command(["banlist"]) & filters.user(ADMIN_IDS))
async def banlist_cmd(client, message: Message):
    if not banned_users:
        await message.reply_text("<b>📭 No banned users.</b>")
        return
    ban_list = "\n".join([f"<code>{uid}</code>" for uid in sorted(banned_users)])
    await message.reply_text(
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"<b>⛔ Banned Users</b>\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
        f"{ban_list}\n\n"
        f"<b>🔹 Total:</b> <code>{len(banned_users)}</code>\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>"
    )


@bot.on_message(filters.command(["unban"]) & filters.user(ADMIN_IDS))
async def unban_cmd(client, message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("<b>⚠️ Usage: <code>/unban user_id</code></b>")
        return
    try:
        uid = int(args[1])
        banned_users.discard(uid)
        save_banned()
        await message.reply_text(f"<b>✅ User <code>{uid}</code> unbanned.</b>")
    except ValueError:
        await message.reply_text("<b>⚠️ Invalid user ID!</b>")


@bot.on_message(filters.command(["setlimit"]) & filters.user(ADMIN_IDS))
async def setlimit_cmd(client, message: Message):
    global NORMAL_LIMIT
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text(
            f"<b>⚠️ Usage:</b> <code>/setlimit 5000</code>\n"
            f"<b>Current Normal:</b> <code>{NORMAL_LIMIT}</code>\n"
            f"<b>Current Premium:</b> <code>{PREMIUM_LIMIT}</code>"
        )
        return
    try:
        new_limit = int(args[1])
        NORMAL_LIMIT = new_limit
        await message.reply_text(f"<b>✅ Normal limit set to <code>{new_limit}</code></b>")
    except ValueError:
        await message.reply_text("<b>⚠️ Must be a number!</b>")


@bot.on_message(filters.command(["users"]) & filters.user(ADMIN_IDS))
async def users_cmd(client, message: Message):
    await message.reply_text(
        f"<b>👥 Total Users: <code>{len(bot_stats['total_users'])}</code></b>"
    )


@bot.on_message(filters.command(["addpremium"]) & filters.user(ADMIN_IDS))
async def addpremium_cmd(client, message: Message):
    args = message.text.split()
    if len(args) < 3:
        await message.reply_text(
            "<b>⚠️ Usage:</b>\n"
            "<code>/addpremium user_id 30</code> (30 days)\n"
            "<code>/addpremium user_id unlimited</code> (forever)"
        )
        return

    try:
        uid = int(args[1])
    except ValueError:
        await message.reply_text("<b>⚠️ Invalid user ID!</b>")
        return

    duration = args[2].lower()

    if duration == "unlimited":
        premium_users[str(uid)] = {"expiry": None}
        save_premium(premium_users)
        await message.reply_text(
            f"<b>✅ Premium Added</b>\n\n"
            f"<b>🔹 User:</b> <code>{uid}</code>\n"
            f"<b>🔹 Duration:</b> <code>Unlimited</code>\n"
            f"<b>🔹 Limit:</b> <code>{PREMIUM_LIMIT:,}</code>"
        )
    else:
        try:
            days = int(duration)
            expiry_time = time.time() + (days * 86400)
            premium_users[str(uid)] = {"expiry": expiry_time}
            save_premium(premium_users)
            await message.reply_text(
                f"<b>✅ Premium Added</b>\n\n"
                f"<b>🔹 User:</b> <code>{uid}</code>\n"
                f"<b>🔹 Duration:</b> <code>{days} days</code>\n"
                f"<b>🔹 Limit:</b> <code>{PREMIUM_LIMIT:,}</code>"
            )
        except ValueError:
            await message.reply_text("<b>⚠️ Duration must be a number or 'unlimited'!</b>")


@bot.on_message(filters.command(["rmpremium"]) & filters.user(ADMIN_IDS))
async def rmpremium_cmd(client, message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("<b>⚠️ Usage: <code>/rmpremium user_id</code></b>")
        return

    try:
        uid = int(args[1])
    except ValueError:
        await message.reply_text("<b>⚠️ Invalid user ID!</b>")
        return

    if str(uid) in premium_users:
        del premium_users[str(uid)]
        save_premium(premium_users)
        await message.reply_text(f"<b>✅ Premium removed from <code>{uid}</code></b>")
    else:
        await message.reply_text(f"<b>⚠️ User <code>{uid}</code> is not premium!</b>")


@bot.on_message(filters.command(["premiumlist"]) & filters.user(ADMIN_IDS))
async def premiumlist_cmd(client, message: Message):
    if not premium_users:
        await message.reply_text("<b>📭 No premium users.</b>")
        return

    list_text = (
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"<b>⭐ Premium Users</b>\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>\n\n"
    )

    for uid, data in premium_users.items():
        expiry = data.get("expiry")
        if expiry is None:
            expiry_str = "Unlimited"
        else:
            remaining = expiry - time.time()
            if remaining <= 0:
                expiry_str = "Expired"
            else:
                days = int(remaining // 86400)
                hours = int((remaining % 86400) // 3600)
                expiry_str = f"{days}d {hours}h"

        list_text += f"<b>🔹</b> <code>{uid}</code> → <code>{expiry_str}</code>\n"

    list_text += (
        f"\n<b>🔹 Total:</b> <code>{len(premium_users)}</code>\n\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━━━━</b>"
    )
    await message.reply_text(list_text)


@bot.on_message(filters.command(["restart"]) & filters.user(ADMIN_IDS))
async def restart_cmd(client, message: Message):
    await message.reply_text("<b>🔄 Restarting bot...</b>")
    logger.info("🔄 Bot restart requested by admin")
    save_stats()
    save_history()
    save_banned()
    save_merge_queue()
    save_premium(premium_users)
    save_user_data()
    os._exit(0)


# ─── Run ───

if __name__ == "__main__":
    load_all_persistent_data()
    bot_stats["start_time"] = time.time()
    logger.info("🐱 Starting Meow Bot...")
    logger.info(f"✅ Loaded {len(premium_users)} premium users")
    logger.info(f"✅ Loaded {len(banned_users)} banned users")
    logger.info(f"✅ Loaded {len(user_history)} history entries")
    logger.info(f"✅ Loaded {len(merge_queue)} merge queues")
    user.start()
    bot.run()
