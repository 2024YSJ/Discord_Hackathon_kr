import os
import requests
from datetime import datetime

WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')
DB_FILE = "sent_hackathons.txt"

class HackathonBot:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        self.sent_list = self.load_sent_list()

    def load_sent_list(self):
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "r", encoding="utf-8") as f:
                # 공백 제거 및 빈 줄 제외
                return set(line.strip() for line in f if line.strip())
        return set()

    def save_sent_list(self, new_items):
        with open(DB_FILE, "a", encoding="utf-8") as f:
            for item in new_items:
                f.write(f"{item['title']}\n")

    # --- 각 사이트별 fetch 함수 (이전 답변과 동일하게 유지) ---
    def fetch_devpost(self):
        try:
            url = "https://devpost.com/api/hackathons"
            res = requests.get(url, params={"status[]": "upcoming"}, headers=self.headers, timeout=10)
            return [{"title": h['title'], "url": h['url'], "host": "Devpost", "date": h['submission_period_dates']} for h in res.json()['hackathons']]
        except: return []

    # (필요에 따라 fetch_mlh, fetch_unstop 등을 추가하세요)

    def send_to_discord(self, hackathons):
        embeds = []
        for h in hackathons:
            embeds.append({
                "title": f"🏆 {h['title']}",
                "url": h['url'],
                "color": 5814783, # Blurple color
                "fields": [
                    {"name": "주최", "value": h['host'], "inline": True},
                    {"name": "일정", "value": str(h['date']), "inline": True}
                ],
                "footer": {"text": f"수집 일시: {datetime.now().strftime('%Y-%m-%d %H:%M')}"}
            })
        
        # 10개씩 끊어서 전송 (Discord 제한)
        for i in range(0, len(embeds), 10):
            payload = {"embeds": embeds[i:i+10]}
            requests.post(WEBHOOK_URL, json=payload)

    def run(self):
        all_found = []
        all_found.extend(self.fetch_devpost())
        # all_found.extend(self.fetch_mlh()) 등 추가 가능

        # 중복 검사: 제목이 sent_list에 없는 것만 필터링
        new_items = [h for h in all_found if h['title'] not in self.sent_list]

        if not new_items:
            print("새로운 해커톤이 없습니다.")
            return

        print(f"{len(new_items)}개의 새로운 해커톤을 발견했습니다.")
        self.send_to_discord(new_items)
        self.save_sent_list(new_items)

if __name__ == "__main__":
    bot = HackathonBot()
    bot.run()