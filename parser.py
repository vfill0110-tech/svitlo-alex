import re
import json
import requests
from bs4 import BeautifulSoup

CHANNEL_URL = "https://t.me/s/svitlo_alex"

def fetch_latest_schedule():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        response = requests.get(CHANNEL_URL, headers=headers, timeout=10)
        print(f"HTTP Status Code: {response.status_code}")
    except Exception as e:
        print(f"Error fetching URL: {e}")
        return None

    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Шукаємо всі можливі блоки повідомлень у віджеті Telegram
    messages = soup.find_all(['div', 'section'], class_=lambda x: x and 'message' in x)
    print(f"Found message blocks: {len(messages)}")
    
    if not messages:
        # Запасний варіант: шукаємо просто всі блоки тексту на сторінці
        messages = soup.find_all('div', class_='tgme_widget_message_text')

    for msg in reversed(messages):
        msg_text = msg.text
        
        # Перевіряємо, чи є в тексті згадка черг
        if "черга" not in msg_text.lower():
            continue

        # Витягуємо час публікації, якщо є тег часу
        time_tag = msg.find('time') if hasattr(msg, 'find') else None
        post_time_str = "--:--"
        if time_tag and time_tag.has_attr('datetime'):
            dt_raw = time_tag['datetime']
            try:
                time_part = dt_raw.split('T')[1][:5]
                h, m = map(int, time_part.split(':'))
                h = (h + 2) % 24  # коригування під Київ
                post_time_str = f"{h:02d}:{m:02d}"
            except Exception:
                pass

        # Якщо час не знайшли через тег, спробуємо витягнути з самого тексту (наприклад, "станом на 18:51")
        if post_time_str == "--:--":
            time_match = re.search(r'станом на (\d{2}):(\d{2})', msg_text, re.IGNORECASE)
            if time_match:
                post_time_str = f"{time_match.group(1)}:{time_match.group(2)}"

        # Шукаємо дату у форматі DD.MM.YYYY
        date_match = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', msg_text)
        if not date_match:
            continue
        
        day, month, year = date_match.groups()
        formatted_date = f"{year}-{month}-{day}"

        subqueues = {}
        # Шукаємо всі блоки з чергами
        queue_matches = re.finditer(r'Черга\s+(\d\.\d)[:\s]*([^\n]+)', msg_text, re.IGNORECASE)
        
        for q_match in queue_matches:
            queue_num = q_match.group(1)
            hours_part = q_match.group(2)
            
            intervals = []
            time_blocks = re.findall(r'(\d{2})-(\d{2})', hours_part)
            
            for start_h, end_h in time_blocks:
                end_val = "24:00" if end_h == "24" else f"{end_h}:00"
                intervals.append({
                    "start": f"{start_h}:00",
                    "end": end_val,
                    "status": "off"
                })
            
            if intervals:
                subqueues[queue_num] = intervals

        if subqueues:
            print(f"Successfully parsed schedule for date: {formatted_date} with post time: {post_time_str}")
            return {
                "timezone": "Europe/Kyiv",
                "last_post_time": post_time_str,
                "schedules": {
                    formatted_date: {
                        "subqueues": subqueues
                    }
                }
            }
                
    print("No valid schedule post matched criteria.")
    return None

if __name__ == "__main__":
    data = fetch_latest_schedule()
    
    if not data:
        data = {
            "timezone": "Europe/Kyiv",
            "last_post_time": "--:--",
            "schedules": {}
        }
        print("Using empty template fallback.")

    with open("schedule.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("schedule.json saved successfully.")
