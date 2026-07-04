# ============================================
#  🧹 Card Info Extractor & Normalizer
#  ဘယ် format နဲ့ပဲလာလာ → 411111111111111|11|11|111
# ============================================

import re

# ============================================
#  Luhn Algorithm (Card Validator)
# ============================================
def luhn_check(card: str) -> bool:
    """Card number မှန်မမှန် Luhn algorithm နဲ့စစ်"""
    nums = [int(d) for d in card if d.isdigit()]
    if len(nums) < 13:
        return False
    
    rev_digits = nums[::-1]
    total = 0
    
    for i, d in enumerate(rev_digits):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    
    return total % 10 == 0


def is_possible_card(num_str: str) -> bool:
    """Card number ဖြစ်နိုင်ခြေ စစ်"""
    cleaned = num_str.replace(' ', '').replace('-', '')
    if not cleaned.isdigit():
        return False
    length = len(cleaned)
    if length not in [13, 15, 16, 17, 18, 19]:
        return False
    first_digit = cleaned[0]
    if first_digit not in ['3', '4', '5', '6']:
        return False
    return True


def is_valid_year(year_str: str) -> bool:
    """Year က 01-99 အတွင်းဟုတ်မဟုတ် စစ်တယ် (00 ဆို invalid)"""
    if not year_str or not year_str.isdigit():
        return False
    year_int = int(year_str)
    if len(year_str) == 2:
        return 1 <= year_int <= 99
    if len(year_str) == 4:
        return 2020 <= year_int <= 2035
    return False


# ============================================
#  နံပါတ်များကို ရှာဖွေခြင်း
# ============================================
def extract_numbers(text: str) -> list:
    """Text ထဲက ဂဏန်းအုပ်စုတွေအားလုံးကို ထုတ်ယူ"""
    nums = re.findall(r'\d+', text)
    
    spaced = re.findall(r'\d{4}\s+\d{4}\s+\d{4}\s+\d{4}', text)
    for s in spaced:
        nums.append(s.replace(' ', ''))
    
    dashed = re.findall(r'\d{4}-\d{4}-\d{4}-\d{4}', text)
    for d in dashed:
        nums.append(d.replace('-', ''))
    
    return nums


# ============================================
#  Card Info ရှာဖွေခြင်း (အဲ့ဒီ + Approved text support)
# ============================================
def find_card_info(text: str) -> list:
    """Text ထဲက card info (card, month, year, cvv) ကိုရှာ"""
    if not text:
        return []
    
    results = []
    
    # ============================================
    #  Pattern 1: Standard format (411111111111111|12|2029|580)
    # ============================================
    standard_pattern = re.compile(
        r'(\d{13,19})\s*[|,/\s:.\-]\s*(\d{2})\s*[|,/\s:.\-]\s*(\d{2,4})\s*[|,/\s:.\-]\s*(\d{3,4})'
    )
    
    for match in standard_pattern.finditer(text):
        card, month, year, cvv = match.groups()
        
        if is_possible_card(card) and is_valid_year(year):
            # Year 4 digit ဆိုရင် last 2 digit ပဲယူ
            if len(year) == 4:
                year = year[2:]
            
            if len(month) == 1:
                month = '0' + month
            
            results.append((card, month, year, cvv))
    
    # ============================================
    #  Pattern 2: Approved text format (4111111111111111|12|2029|580 | Approved 🔥)
    # ============================================
    approved_pattern = re.compile(
        r'(\d{13,19})\s*\|\s*(\d{2})\s*\|\s*(\d{2,4})\s*\|\s*(\d{3,4})\s*\|.*?Approved'
    )
    
    for match in approved_pattern.finditer(text):
        card, month, year, cvv = match.groups()
        
        if is_possible_card(card) and is_valid_year(year):
            if len(year) == 4:
                year = year[2:]
            
            if len(month) == 1:
                month = '0' + month
            
            results.append((card, month, year, cvv))
    
    # ============================================
    #  Pattern 3: Legacy format (ကျန်တဲ့ အခြားမျိုးတွေ)
    # ============================================
    all_nums = extract_numbers(text)
    
    card_candidates = []
    for num in all_nums:
        if len(num) >= 13 and len(num) <= 19 and is_possible_card(num):
            card_candidates.append(num)
    
    for card in card_candidates:
        rest_text = text
        rest_text = rest_text.replace(card, '')
        spaced_card = ' '.join([card[i:i+4] for i in range(0, len(card), 4)])
        rest_text = rest_text.replace(spaced_card, '')
        dashed_card = '-'.join([card[i:i+4] for i in range(0, len(card), 4)])
        rest_text = rest_text.replace(dashed_card, '')
        
        rest_nums = re.findall(r'\d{2,4}', rest_text)
        
        month = None
        year = None
        cvv = None
        
        two_digit = [n for n in rest_nums if len(n) == 2]
        three_digit = [n for n in rest_nums if len(n) == 3]
        four_digit = [n for n in rest_nums if len(n) == 4]
        
        # Month (01-12) ရှာ
        for n in two_digit[:]:
            if 1 <= int(n) <= 12:
                month = n
                two_digit.remove(n)
                break
        
        # Year ရှာ (00 ကိုလက်မခံ)
        for n in two_digit[:]:
            if is_valid_year(n):
                year = n
                two_digit.remove(n)
                break
        
        if year is None:
            for n in four_digit[:]:
                if is_valid_year(n):
                    year = n[2:] if len(n) == 4 else n
                    four_digit.remove(n)
                    break
        
        # CVV ရှာ
        if three_digit:
            cvv = three_digit[0]
        elif four_digit:
            for n in four_digit[:]:
                if len(n) == 4:
                    cvv = n
                    break
        
        # Valid ဆို သိမ်း
        if year and is_valid_year(year):
            if card and month and year and cvv:
                # Duplicate ဖြစ်နေမနေ ကြည့်
                is_dup = False
                for existing in results:
                    if existing[0] == card:
                        is_dup = True
                        break
                
                if not is_dup:
                    results.append((card, month, year, cvv))
    
    # ============================================
    #  Final Duplicate Removal (Card Number နဲ့)
    # ============================================
    unique_results = []
    seen_cards = set()
    
    for card, month, year, cvv in results:
        card_clean = card.replace(' ', '').replace('-', '')
        if card_clean not in seen_cards:
            seen_cards.add(card_clean)
            unique_results.append((card, month, year, cvv))
    
    return unique_results


# ============================================
#  Standard Format ပြောင်းခြင်း
# ============================================
def normalize_to_standard(card: str, month: str, year: str, cvv: str,
                          separator: str = "|", year_digits: int = 2) -> str:
    """Format အကုန် → 411111111111111|11|11|111"""
    card = card.replace(' ', '').replace('-', '')
    
    if len(month) == 1:
        month = '0' + month
    
    if len(year) == 4:
        if year_digits == 2:
            year = year[2:]
    elif len(year) == 2:
        if year_digits == 4:
            year = '20' + year if int(year) < 50 else '19' + year
    
    cvv = cvv.strip()
    
    return f"{card}{separator}{month}{separator}{year}{separator}{cvv}"


# ============================================
#  Main Clean Function (forwarder ကခေါ်တယ်)
# ============================================
def clean_text(text: str, config: dict = None) -> str:
    """
    Main function
    Input: ဘယ် format မဆို (Approved text အပါအဝင်)
    Output: 411111111111111|11|11|111 (line by line)
    ✅ Auto remove duplicates
    """
    if not text:
        return ""
    
    if config is None:
        config = {
            "validate_card": False,
            "output_separator": "|",
            "year_digits": 2
        }
    
    cards = find_card_info(text)
    
    if not cards:
        return ""
    
    results = []
    
    for card, month, year, cvv in cards:
        if config.get("validate_card", False):
            if not luhn_check(card):
                continue
        
        normalized = normalize_to_standard(
            card, month, year, cvv,
            separator=config.get("output_separator", "|"),
            year_digits=config.get("year_digits", 2)
        )
        results.append(normalized)
    
    # Duplicate ဖျက် (order မပျက်အောင်)
    seen = set()
    unique_results = []
    for r in results:
        if r not in seen:
            seen.add(r)
            unique_results.append(r)
    
    return "\n".join(unique_results)


def has_card_info(text: str) -> bool:
    """Text မှာ card info ရှိမရှိ အမြန်စစ်"""
    return len(find_card_info(text)) > 0
