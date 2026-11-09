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
    messages = soup.find_all('div', class_='tgme_widget_message_text')
    
    print(f"Found messages count: {len(messages)}")
    if not messages:
        return None

    for msg in reversed(messages):
        msg_text = msg.text
        
        # Шукаємо пости, що стосуються графіків погодинних відключень
        if "графіка погодинних відключень" not in msg_text.lower() and "черга" not in msg_text.lower():
            continue

        # Шукаємо дату у форматі DD.MM.YYYY
        date_match = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', msg_text)
        if not date_match:
            continue
        
        day, month, year = date_match.groups()
        formatted_date = f"{year}-{month}-{day}"

        subqueues = {}
        lines = msg_text.split('\n')
        for line in lines:
            line = line.strip()
            queue_match = re.search(r'Черга\s+(\d\.\d):\s*(.+)', line)
            if queue_match:
                queue_num = queue_match.group(1)
                hours_part = queue_match.group(2)
                
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
            print(f"Successfully parsed schedule for date: {formatted_date}")
            return {
                "timezone": "Europe/Kyiv",
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
            "schedules": {}
        }
        print("Using empty template fallback.")

    with open("schedule.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("schedule.json saved successfully.")
