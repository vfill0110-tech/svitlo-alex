import re
import json
import requests
from bs4 import BeautifulSoup

# Публічна сторінка Telegram-каналу
CHANNEL_URL = "https://t.me/s/svitlo_alex"

def fetch_latest_schedule():
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(CHANNEL_URL, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Шукаємо всі пости в каналі
    messages = soup.find_all('div', class_='tgme_widget_message_text')
    if not messages:
        return None

    # Беремо найновіше повідомлення
    latest_msg = messages[-1].text

    # Шукаємо дату (наприклад: 09.11.2026)
    date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', latest_msg)
    if not date_match:
        return None
    
    raw_date = date_match.group(1)
    day, month, year = raw_date.split('.')
    formatted_date = f"{year}-{month}-{day}"

    subqueues = {}
    
    # Шукаємо рядки виду "Черга 1.1: 07-08, 10-12..."
    pattern = r'Черга\s+(\d\.\d):\s*([^\n]+)'
    matches = re.findall(pattern, latest_msg)

    for queue_num, hours_str in matches:
        intervals = []
        # Розбираємо години відключення (наприклад: 07-08 -> start: 07:00, end: 08:00)
        time_blocks = re.findall(r'(\d{2})-(\d{2})', hours_str)
        
        for start_h, end_h in time_blocks:
            end_val = "24:00" if end_h == "24" else f"{end_h}:00"
            intervals.append({
                "start": f"{start_h}:00",
                "end": end_val,
                "status": "off"
            })
        
        subqueues[queue_num] = intervals

    result = {
        "timezone": "Europe/Kyiv",
        "schedules": {
            formatted_date: {
                "subqueues": subqueues
            }
        }
    }
    return result

if __name__ == "__main__":
    data = fetch_latest_schedule()
    if data:
        with open("schedule.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("Schedule updated successfully!")
