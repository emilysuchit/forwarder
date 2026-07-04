# ============================================
#  📡 Telegram Card Forwarder
#  + Auto Export to Channel
# ============================================

import asyncio
import os
import json
import re
import sqlite3
from datetime import datetime
from telethon import TelegramClient, events
from telethon.tl.types import Channel

# ============================================
#  Environment Variables ကနေယူ
# ============================================
API_ID = int(os.getenv("API_ID", "36597864"))
API_HASH = os.getenv("API_HASH", "your_hash")
PHONE_NUMBER = os.getenv("PHONE_NUMBER", "+959664282332")
SOURCE_CHANNELS_STR = os.getenv("SOURCE_CHANNELS", "-1001218056496,-1001451060271,-1003776351370")
MY_CHANNEL = int(os.getenv("MY_CHANNEL", "-1003954900164"))

# Parse source channels
SOURCE_CHANNELS = []
for ch in SOURCE_CHANNELS_STR.split(','):
    try:
        SOURCE_CHANNELS.append(int(ch.strip()))
    except:
        SOURCE_CHANNELS.append(ch.strip())

DELAY_BETWEEN_POSTS = int(os.getenv("DELAY_BETWEEN_POSTS", "3"))
VALIDATE_CARD = os.getenv("VALIDATE_CARD", "False") == "True"
REMOVE_DUPLICATES = os.getenv("REMOVE_DUPLICATES", "True") == "True"
SAVE_SENT_HISTORY = os.getenv("SAVE_SENT_HISTORY", "True") == "True"
OUTPUT_SEPARATOR = os.getenv("OUTPUT_SEPARATOR", "|")
YEAR_DIGITS = int(os.getenv("YEAR_DIGITS", "2"))
EXPORT_LIMIT = int(os.getenv("EXPORT_LIMIT", "5000"))

from cleaner import clean_text, has_card_info

# ============================================
#  Client Setup
# ============================================
client = TelegramClient(
    session="/tmp/card_forwarder_session",
    api_id=API_ID,
    api_hash=API_HASH
)

CLEAN_CONFIG = {
    "validate_card": VALIDATE_CARD,
    "output_separator": OUTPUT_SEPARATOR,
    "year_digits": YEAR_DIGITS
}

source_entities = {}
sent_history = set()

DB_FILE = "/tmp/cards.db"
HISTORY_FILE = "/tmp/sent_history.json"
EXPORT_DIR = "/tmp"

# ============================================
#  Database Functions
# ============================================
def init_database():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_number TEXT NOT NULL UNIQUE,
            month TEXT,
            year TEXT,
            cvv TEXT,
            source_group TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'active',
            exported INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()
    print(f"✅ Database initialized: {DB_FILE}")


def insert_card(card_number: str, month: str, year: str, cvv: str, source: str):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO cards (card_number, month, year, cvv, source_group)
            VALUES (?, ?, ?, ?, ?)
        ''', (card_number, month, year, cvv, source))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False
    except Exception as e:
        print(f"❌ DB insert error: {e}")
        return False


def get_card_count() -> int:
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM cards")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except:
        return 0


def get_unexported_count() -> int:
    """Export မလုပ်သေးတဲ့ cards ဘယ်နှစ်ခုရှိလဲ"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM cards WHERE exported = 0")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except:
        return 0


def export_cards_to_txt() -> str:
    """Export လုပ်ပြီးသား cards ကို txt ထုတ်တယ်"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Export မလုပ်သေးတဲ့ cards
        cursor.execute('''
            SELECT id, card_number, month, year, cvv FROM cards
            WHERE exported = 0
            ORDER BY id DESC
            LIMIT ?
        ''', (EXPORT_LIMIT,))
        
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return None
        
        # Export file ဖန်တီး
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_filename = f"{EXPORT_DIR}/cards_export_{timestamp}_{len(rows)}.txt"
        
        card_ids = []
        with open(export_filename, 'w', encoding='utf-8') as f:
            for card_id, card, month, year, cvv in rows:
                line = f"{card}|{month}|{year}|{cvv}"
                f.write(line + '\n')
                card_ids.append(card_id)
        
        # Database မှာ exported flag ပြင်
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        for cid in card_ids:
            cursor.execute("UPDATE cards SET exported = 1 WHERE id = ?", (cid,))
        conn.commit()
        conn.close()
        
        print(f"\n✅ Export Complete!")
        print(f"   📁 File: {export_filename}")
        print(f"   📊 Cards: {len(rows)}")
        
        return export_filename
    
    except Exception as e:
        print(f"❌ Export error: {e}")
        return None


async def send_export_file_to_channel(filename: str):
    """Export file ကို channel ထဲ ပို့တယ်"""
    try:
        if not os.path.exists(filename):
            print(f"❌ File မရှိ: {filename}")
            return False
        
        # File size ကြည့်
        file_size = os.path.getsize(filename)
        file_size_mb = file_size / (1024 * 1024)
        
        # File count ရွေ
        with open(filename, 'r') as f:
            line_count = len(f.readlines())
        
        # Message ဖန်တီး
        message = f"""
🎉 **Milestone Alert!** 
📊 5000 Cards Exported

📁 File: {os.path.basename(filename)}
📏 Size: {file_size_mb:.2f} MB
📝 Cards: {line_count}
⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Format: card|month|year|cvv
"""
        
        # Channel ထဲ file ပို့
        await client.send_file(
            entity=MY_CHANNEL,
            file=filename,
            caption=message
        )
        
        print(f"✅ File sent to channel: {os.path.basename(filename)}")
        return True
        
    except Exception as e:
        print(f"❌ Send file error: {e}")
        return False


def milestone_reached(current_count: int, previous_count: int) -> bool:
    """5000 ပြည့်တယ်ဘူး check"""
    if current_count >= EXPORT_LIMIT and previous_count < EXPORT_LIMIT:
        return True
    
    # 10000, 15000, 20000 etc
    if current_count % EXPORT_LIMIT == 0 and current_count > 0:
        return True
    
    return False


# ============================================
#  History Management
# ============================================
def load_history():
    global sent_history
    if not SAVE_SENT_HISTORY:
        return
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                data = json.load(f)
                sent_history = set(data)
            print(f"📋 History loaded: {len(sent_history)} items")
        except:
            sent_history = set()


def save_history():
    if not SAVE_SENT_HISTORY:
        return
    try:
        with open(HISTORY_FILE, 'w') as f:
            json.dump(list(sent_history), f)
    except Exception as e:
        print(f"⚠️ History save error: {e}")


def get_card_number(formatted_line: str) -> str:
    card_number = formatted_line.split('|')[0] if '|' in formatted_line else formatted_line
    card_number = re.sub(r'\D', '', card_number)
    if len(card_number) >= 16:
        card_number = card_number[:16]
    return card_number


def is_duplicate(formatted_line: str) -> bool:
    if not REMOVE_DUPLICATES:
        return False
    card_number = get_card_number(formatted_line)
    return card_number in sent_history


def mark_sent(formatted_line: str):
    if REMOVE_DUPLICATES:
        card_number = get_card_number(formatted_line)
        if card_number:
            sent_history.add(card_number)


# ============================================
#  Resolve Source Channels
# ============================================
async def resolve_source_channels():
    global source_entities
    
    print("\n🔍 Source channels ရှာနေတယ်...")
    
    for ch in SOURCE_CHANNELS:
        try:
            entity = await client.get_entity(ch)
            name = getattr(entity, 'title', str(ch))
            source_entities[entity.id] = entity
            print(f"  ✅ {name} (id: {entity.id})")
        except Exception as e:
            print(f"  ❌ {ch} — Error: {e}")
    
    print(f"\n📡 Source: {len(source_entities)} ခု ရပြီ")
    
    if not source_entities:
        print("❌ Source တစ်ခုမှမရပါ!")
        return False
    return True


# ============================================
#  Message Handler
# ============================================
@client.on(events.NewMessage(chats=SOURCE_CHANNELS))
async def handler(event):
    message = event.message
    text = message.text or ""
    
    if not has_card_info(text):
        return
    
    cleaned = clean_text(text, CLEAN_CONFIG)
    
    if not cleaned:
        return
    
    source_title = "Unknown"
    if message.chat:
        source_title = getattr(message.chat, 'title', str(message.chat.id))
    
    print(f"\n📩 [{source_title}]")
    
    lines = cleaned.split('\n')
    sent_count = 0
    skip_count = 0
    db_count_before = get_card_count()
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        parts = line.split('|')
        if len(parts) >= 3 and parts[2] == '00':
            skip_count += 1
            continue
        
        if is_duplicate(line):
            skip_count += 1
            continue
        
        try:
            await client.send_message(
                entity=MY_CHANNEL,
                message=line,
                link_preview=False
            )
            
            mark_sent(line)
            
            if len(parts) >= 4:
                card, month, year, cvv = parts[0], parts[1], parts[2], parts[3]
                insert_card(card, month, year, cvv, source_title)
            
            sent_count += 1
            print(f"  ✅ {line}")
            
            await asyncio.sleep(DELAY_BETWEEN_POSTS)
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
    
    db_count_after = get_card_count()
    new_cards = db_count_after - db_count_before
    
    print(f"📊 Sent: {sent_count} | DB: +{new_cards} | Total: {db_count_after}")
    
    # Milestone check - 5000 ပြည့်ရင် export & send
    if db_count_after >= EXPORT_LIMIT and get_unexported_count() > 0:
        print(f"\n🎉 Milestone Reached! {db_count_after} cards!")
        export_file = export_cards_to_txt()
        if export_file:
            await send_export_file_to_channel(export_file)
    
    if sent_count > 0:
        save_history()


# ============================================
#  Main Function
# ============================================
async def main():
    print("=" * 50)
    print("  📡 Telegram Card Forwarder")
    print("  Auto Export + Channel Upload")
    print("=" * 50)
    
    init_database()
    load_history()
    
    current_count = get_card_count()
    unexported = get_unexported_count()
