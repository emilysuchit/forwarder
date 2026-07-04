# ============================================
#  ⚙️ Telegram Card Forwarder Config
# ============================================

# === Telegram API (my.telegram.org မှာယူ) ===
API_ID = 36597864
API_HASH = "4bcff41d7149cf6e6e9ee06416d62632"       # ← ⚠️ my.telegram.org က hash အစစ်ထည့်ပါ
PHONE_NUMBER = "+959664282332"

# === Source Groups (စောင့်ကြည့်မယ့် group များ) ===
SOURCE_CHANNELS = [
    -1001218056496,
    -1001451060271,
    -1003776351370,
    -1003899786458,
]

# === Your Channel (ပြန်ပို့မယ့် channel) ===
MY_CHANNEL = -1003954900164

# === Settings ===
DELAY_BETWEEN_POSTS = 3              # post တစ်ခုစီကြား စက္ကန့် (group တွေက အများကြီးလာနိုင်လို့ 3 ထား)
VALIDATE_CARD = False                # Luhn algorithm check
REMOVE_DUPLICATES = True
SAVE_SENT_HISTORY = True

# === Output Format ===
OUTPUT_SEPARATOR = "|"
YEAR_DIGITS = 2
