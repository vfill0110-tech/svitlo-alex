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
    messages = soup.find_all('div', class_='tgme_widget_message')
    
    print(f"Found messages count: {len(messages)}")
    if not messages:
        return None

    for msg in reversed(messages):
        text_div = msg.find('div', class_='tgme_widget_message_text')
        if not text_div:
            continue
        
        msg_text = text_div.text
        
        # Перевіряємо, чи є в повідомленні графік відключень
        if "черга" not in msg_text.lower():
            continue

        # Витягуємо час публікації поста
        time_tag = msg.find('time', class_='tgme_widget_message_date')
        post_time_str = "--:--"
        if time_tag and time_tag.has_attr('datetime'):
            dt_raw = time_tag['datetime']
            try:
                time_part = dt_raw.split('T')[1][:5]
                h, m = map(int, time_part.split(':'))
                # Коригування під київський час (UTC+2 / UTC+3, тут додаємо 2 год або витягуємо чистий час)
                h = (h + 2) % 24
                post_time_str = f"{h:02d}:{m:02d}"
            except Exception:
                post_time_str = "назад"

        # Шукаємо дату у форматі DD.MM.YYYY
        date_match = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', msg_text)
        if not date_match:
            continue
        
        day, month, year = date_match.groups()
        formatted_date = f"{year}-{month}-{day}"

        subqueues = {}
        # Шукаємо всі згадки черг у тексті (наприклад, "Черга 1.1: 07-08, 10-12...")
        # Використовуємо знаходження за шаблоном "Черга X.X"
        queue_matches = re.finditer(r'Черга\s+(\d\.\d)[:\s]*([^\n]+)', msg_text, re.IGNORECASE)
        
        for q_match in queue_matches:
            queue_num = q_match.group(1)
            hours_part = q_match.group(2)
            
            intervals = []
            # Знаходимо всі часові пари типу 07-08, 18-20 тощо
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
