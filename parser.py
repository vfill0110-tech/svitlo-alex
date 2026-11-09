import re
import json
import requests
from bs4 import BeautifulSoup

CHANNEL_URL = "https://t.me/s/SvitloOleksandriyskohoRaionu"

def fetch_latest_schedule():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        response = requests.get(CHANNEL_URL, headers=headers, timeout=10)
        print(f"HTTP Status Code: {response.status_code}")
    except Exception as e:
        print(f"Error fetching URL: {e}")
        return None

    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Збираємо всі блоки повідомлень
    messages = soup.find_all('div', class_='tgme_widget_message')
    if not messages:
        messages = soup.find_all('div', class_='tgme_widget_message_text')

    for msg in reversed(messages):
        text_div = msg.find('div', class_='tgme_widget_message_text') if hasattr(msg, 'find') else msg
        if not text_div:
            continue
            
        msg_text = text_div.text
        
        # Перевіряємо, чи є в повідомленні розклад
        if "черга" not in msg_text.lower():
            continue

        # Витягуємо час публікації
        post_time_str = "--:--"
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
        
        # Проходимо по кожній черзі від 1.1 до 6.2 окремо, щоб гарантовано зловити її години
        for q_main in range(1, 7):
            for sub in [1, 2]:
                q_num = f"{q_main}.{sub}"
                
                # Шукаємо шаблон типу "Черга 1.1: [годинник]" або аналогічний
                # Шукаємо взірець десь у тексті
                pattern = rf"Черга\s+{q_num}[:\s]*([0-9,\-\s]+)"
                match = re.search(pattern, msg_text, re.IGNORECASE)
                
                if match:
                    hours_part = match.group(1)
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
                        subqueues[q_num] = intervals

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
