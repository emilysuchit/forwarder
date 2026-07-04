# ============================================
#  📡 Telegram Card Forwarder - Main Script
#  + SQLite Database + Auto Export
# ============================================

import asyncio
import os
import json
import re
import sqlite3
from datetime import datetime
from telethon import TelegramClient, events
from telethon.tl.types import Channel

from config import (
    API_ID, API_HASH, PHONE_NUMBER,
    SOURCE_CHANNELS, MY_CHANNEL,
    DELAY_BETWEEN_POSTS,
    VALIDATE_CARD, REMOVE_DUPLICATES,
    SAVE_SENT_HISTORY,
    OUTPUT_SEPARATOR, YEAR_DIGITS
)
from cleaner import clean_text, has_card_info


# ============================================
#  Client Setup
# ============================================
client = TelegramClient(
    session="card_forwarder_session",
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

# ============================================
#  Database အဆင့်တွေ
# ============================================
DB_FILE = "cards.db"
HISTORY_FILE = "sent_history.json"
EXPORT_FILE = "cards_export.txt"
EXPORT_LIMIT = 5000  # 5000 ခုပြည့်တိုင်း export

def init_database():
    """Database ဖန်တီးတယ်"""
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
            status TEXT DEFAULT 'active'
        )
    ''')
    
    conn.commit()
    conn.close()
    print(f"✅ Database initialized: {DB_FILE}")


def insert_card(card_number: str, month: str, year: str, cvv: str, source: str):
    """Card ကို database ထဲထည့်"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        formatted = f"{card_number}|{month}|{year}|{cvv}"
        
        cursor.execute('''
            INSERT INTO cards (card_number, month, year, cvv, source_group)
            VALUES (?, ?, ?, ?, ?)
        ''', (card_number, month, year, cvv, source))
        
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        # Duplicate card
        return False
    except Exception as e:
        print(f"❌ DB insert error: {e}")
        return False


def get_card_count() -> int:
    """Database ထဲမှာ card ဘယ်နှစ်ခုရှိလဲ"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM cards")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except:
        return 0


def export_cards_to_txt(limit: int = 5000, offset: int = 0):
    """Database ကနေ txt export လုပ်တယ်"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT card_number, month, year, cvv FROM cards
            WHERE status = 'active'
            ORDER BY id DESC
            LIMIT ? OFFSET ?
        ''', (limit, offset))
        
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            print("❌ No cards to export")
            return None
        
        # Export file name နဲ့ timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_filename = f"cards_export_{timestamp}_{len(rows)}.txt"
        
        with open(export_filename, 'w') as f:
            for card, month, year, cvv in rows:
                line = f"{card}|{month}|{year}|{cvv}"
                f.write(line + '\n')
        
        print(f"\n📥 Export ပြီးပြီ!")
        print(f"   📁 File: {export_filename}")
        print(f"   📊 Total cards: {len(rows)}")
        
        return export_filename
    
    except Exception as e:
        print(f"❌ Export error: {e}")
        return None


def auto_export_if_milestone(count: int):
    """5000/10000/15000 ခုပြည့်တိုင်း auto export"""
    if count % EXPORT_LIMIT == 0 and count > 0:
        print(f"\n🎉 Milestone! {count} cards accumulated!")
        export_cards_to_txt(limit=EXPORT_LIMIT)


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
    """Card number ပဲထုတ်"""
    card_number = formatted_line.split('|')[0] if '|' in formatted_line else formatted_line
    card_number = re.sub(r'\D', '', card_number)
    if len(card_number) >= 16:
        card_number = card_number[:16]
    return card_number


def is_duplicate(formatted_line: str) -> bool:
    """Duplicate စစ်"""
    if not REMOVE_DUPLICATES:
        return False
    card_number = get_card_number(formatted_line)
    return card_number in sent_history


def mark_sent(formatted_line: str):
    """Sent list ထဲထည့်"""
    if REMOVE_DUPLICATES:
        card_number = get_card_number(formatted_line)
        if card_number:
            sent_history.add(card_number)


# ============================================
#  Source Channels Resolve
# ============================================
async def resolve_source_channels():
    global source_entities
    
    print("\n🔍 Source channels/groups ရှာနေတယ်...")
    
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
    """Source group မှာ message အသစ်တိုင်း"""
    
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
    
    print(f"\n📩 [{source_title}] — Card info တွေ့တယ်!")
    
    lines = cleaned.split('\n')
    sent_count = 0
    skip_count = 0
    db_count_before = get_card_count()
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Year 00 check
        parts = line.split('|')
        if len(parts) >= 3 and parts[2] == '00':
            print(f"  ⏭️ Skip (year=00): {line}")
            skip_count += 1
            continue
        
        # Duplicate check
        if is_duplicate(line):
            skip_count += 1
            continue
        
        # Telegram channel ကို ပို့
        try:
            await client.send_message(
                entity=MY_CHANNEL,
                message=line,
                link_preview=False
            )
            
            mark_sent(line)
            
            # Database ထဲထည့်
            if len(parts) >= 4:
                card, month, year, cvv = parts[0], parts[1], parts[2], parts[3]
                insert_card(card, month, year, cvv, source_title)
            
            sent_count += 1
            print(f"  ✅ {line}")
            
            await asyncio.sleep(DELAY_BETWEEN_POSTS)
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
    
    # Summary
    db_count_after = get_card_count()
    new_cards = db_count_after - db_count_before
    
    print(f"📊 Sent: {sent_count} | DB added: {new_cards} | Total DB: {db_count_after}")
    
    # Auto export milestone check
    auto_export_if_milestone(db_count_after)
    
    if sent_count > 0:
        save_history()


# ============================================
#  Backfill
# ============================================
async def backfill_source(channel_source, limit=50):
    entity = await client.get_entity(channel_source)
    channel_name = getattr(entity, 'title', str(channel_source))
    
    print(f"\n🔄 Backfilling {channel_name} (last {limit} messages)...")
    
    count = 0
    async for message in client.iter_messages(entity, limit=limit):
        text = message.text or ""
        
        if not has_card_info(text):
            continue
        
        cleaned = clean_text(text, CLEAN_CONFIG)
        if not cleaned:
            continue
        
        for line in cleaned.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            if is_duplicate(line):
                continue
            
            try:
                await client.send_message(
                    entity=MY_CHANNEL,
                    message=line,
                    link_preview=False
                )
                mark_sent(line)
                
                parts = line.split('|')
                if len(parts) >= 4:
                    card, month, year, cvv = parts[0], parts[1], parts[2], parts[3]
                    insert_card(card, month, year, cvv, channel_name)
                
                count += 1
                print(f"  ✅ {line}")
                await asyncio.sleep(DELAY_BETWEEN_POSTS)
            except Exception as e:
                print(f"  ❌ Error: {e}")
    
    print(f"📊 Backfill done: {count} items sent")
    print(f"📈 Total in DB: {get_card_count()}")
    save_history()


# ============================================
#  Main Function
# ============================================
async def main():
    print("=" * 50)
    print("  📡 Telegram Card Forwarder")
    print("  + Database + Auto Export")
    print("=" * 50)
    
    # Initialize database
    init_database()
    
    # Load history
    load_history()
    
    current_count = get_card_count()
    print(f"\n📊 Cards in DB: {current_count}")
    
    # Login
    print("\n🔑 Logging in...")
    await client.start(phone=PHONE_NUMBER)
    me = await client.get_me()
    print(f"🟢 Logged in as: {me.first_name} (@{me.username})")
    
    # Resolve source
    success = await resolve_source_channels()
    if not success:
        return
    
    # Verify target
    try:
        target = await client.get_entity(MY_CHANNEL)
        target_name = getattr(target, 'title', str(MY_CHANNEL))
        print(f"🎯 Target channel: {target_name}")
    except Exception as e:
        print(f"❌ Target error: {e}")
        return
    
    # Menu
    print("\n" + "=" * 50)
    print("  🚀 Options:")
    print("  1. Real-time forward")
    print("  2. Backfill old messages")
    print("  3. Run both")
    print("  4. Export cards to TXT")
    print("  5. Check DB stats")
    print("=" * 50)
    
    choice = input("\nChoose (1-5): ").strip()
    
    if choice == '4':
        # Export
        limit = input("Export limit (default 5000): ").strip()
        limit = int(limit) if limit.
