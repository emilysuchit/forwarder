# ============================================
#  📡 Telegram Card Forwarder - Main Script
#  Source channel → Clean → Your Channel
# ============================================

import asyncio
import os
import json
import re
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
#  ⚠️ Client ကို ဒီမှာ ကြေညာပါ (အရေးကြီး)
# ============================================
client = TelegramClient(
    session="card_forwarder_session",
    api_id=API_ID,
    api_hash=API_HASH
)

# Config for cleaner
CLEAN_CONFIG = {
    "validate_card": VALIDATE_CARD,
    "output_separator": OUTPUT_SEPARATOR,
    "year_digits": YEAR_DIGITS
}

# Source channel cache
source_entities = {}

# History file
HISTORY_FILE = "sent_history.json"
sent_history = set()  # card number (16 digit) တွေပဲ သိမ်း


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
    """4111111111111111|12|24|176 → 4111111111111111 (card number ပဲထုတ်)"""
    card_number = formatted_line.split('|')[0] if '|' in formatted_line else formatted_line
    card_number = re.sub(r'\D', '', card_number)
    if len(card_number) >= 16:
        card_number = card_number[:16]
    return card_number


def is_duplicate(formatted_line: str) -> bool:
    """Card number နဲ့ duplicate စစ်"""
    if not REMOVE_DUPLICATES:
        return False
    card_number = get_card_number(formatted_line)
    return card_number in sent_history


def mark_sent(formatted_line: str):
    """Card number ကိုပဲ history ထဲထည့်"""
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
        print("❌ Source တစ်ခုမှမရပါ! Config စစ်ပါ")
        return False
    return True


# ============================================
#  ⚠️ Handler ကို client ပြီးမှ ကြေညာပါ
# ============================================
@client.on(events.NewMessage(chats=SOURCE_CHANNELS))
async def handler(event):
    """Source channel/group က message အသစ်တိုင်း ဖမ်းပြီး forward"""
    
    message = event.message
    text = message.text or ""
    
    # Card info ပါမပါအရင်စစ်
    if not has_card_info(text):
        return
    
    # Clean လုပ်
    cleaned = clean_text(text, CLEAN_CONFIG)
    
    if not cleaned:
        return
    
    # Source name
    source_title = "Unknown"
    if message.chat:
        source_title = getattr(message.chat, 'title', str(message.chat.id))
    
    print(f"\n📩 [{source_title}] — Card info တွေ့တယ်!")
    
    # Line တစ်ကြောင်းချင်းစီ ပို့
    lines = cleaned.split('\n')
    sent_count = 0
    skip_count = 0
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Year 00 ပါနေရင် skip
        parts = line.split('|')
        if len(parts) >= 3 and parts[2] == '00':
            print(f"  ⏭️ Skip (year=00): {line}")
            skip_count += 1
            continue
        
        # Duplicate check
        if is_duplicate(line):
            skip_count += 1
            print(f"  ⏭️ Duplicate: {line}")
            continue
        
        # သင့် channel ကို ပို့
        try:
            await client.send_message(
                entity=MY_CHANNEL,
                message=line,
                link_preview=False
            )
            
            mark_sent(line)
            
            sent_count += 1
            print(f"  ✅ {line}")
            
            await asyncio.sleep(DELAY_BETWEEN_POSTS)
            
        except Exception as e:
            print(f"  ❌ Error sending: {e}")
    
    print(f"📊 Sent: {sent_count} | Skipped: {skip_count}")
    
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
                count += 1
                print(f"  ✅ {line}")
                await asyncio.sleep(DELAY_BETWEEN_POSTS)
            except Exception as e:
                print(f"  ❌ Error: {e}")
    
    print(f"📊 Backfill done: {count} items sent")
    save_history()


# ============================================
#  Main Function
# ============================================
async def main():
    print("=" * 50)
    print("  📡 Telegram Card Forwarder")
    print("  ဘယ် format → 411111111111111|11|11|111")
    print("=" * 50)
    
    # Load history
    load_history()
    
    # Login
    print("\n🔑 Logging in...")
    await client.start(phone=PHONE_NUMBER)
    me = await client.get_me()
    print(f"🟢 Logged in as: {me.first_name} (@{me.username})")
    
    # Resolve source channels
    success = await resolve_source_channels()
    if not success:
        print("❌ Exiting...")
        return
    
    # Verify target channel
    try:
        target = await client.get_entity(MY_CHANNEL)
        target_name = getattr(target, 'title', str(MY_CHANNEL))
        print(f"🎯 Target channel: {target_name}")
    except Exception as e:
        print(f"❌ Target channel error: {e}")
        return
    
    # Menu
    print("\n" + "=" * 50)
    print("  🚀 Ready! Options:")
    print("  1. Real-time forward (auto)")
    print("  2. Backfill old messages")
    print("  3. Run both")
    print("=" * 50)
    
    choice = input("\nChoose (1/2/3): ").strip()
    
    if choice in ['2', '3']:
        limit = input("Backfill limit per source (default 50): ").strip()
        limit = int(limit) if limit.isdigit() else 50
        
        for ch in SOURCE_CHANNELS:
            await backfill_source(ch, limit)
    
    if choice in ['1', '3']:
        print("\n🚀 Real-time forwarder starting...")
        print("   Press Ctrl+C to stop\n")
        print("-" * 50)
        await client.run_until_disconnected()
    else:
        print("\n✅ Done!")
        await client.disconnect()


# ============================================
#  Entry Point
# ============================================
if __name__ == "__main__":
    try:
        with client:
            client.loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\n\n👋 Stopped by user")
        save_history()
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        save_history()
