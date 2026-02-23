import os
import requests
import json
from datetime import datetime

# 설정
WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')
DB_FILE = "sent_hackathons.txt"

class HackathonBot:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        self.sent_list = self.load_sent_list()

    def load_sent_list(self):
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return set(line.strip() for line in f if line.strip())
        return set()

    def save_sent_list(self, new_items):
        with open(DB_FILE, "a", encoding="utf-8") as f:
            for item in new_items:
                f.write(f"{item['title']}\n")

    # --- 플랫폼별 크롤러/API 호출 로직 ---

    def fetch_devpost(self):
        try:
            res = requests.get("https://devpost.com/api/hackathons", params={"status[]": "upcoming"}, headers=self.headers, timeout=10)
            return [{"title": h['title'], "url": h['url'], "host": "Devpost", "date": h.get('submission_period_dates', 'N/A')} for h in res.json()['hackathons']]
        except: return []

    def fetch_mlh(self):
        try:
            # MLH는 해당 연도의 API 엔드포인트를 주로 사용
            year = datetime.now().year
            res = requests.get(f"https://mlh.io/api/v1/hackathons?year={year}", headers=self.headers, timeout=10)
            return [{"title": h['name'], "url": h['url'], "host": "MLH", "date": f"{h['start_date']} ~ {h['end_date']}"} for h in res.json()]
        except: return []

    def fetch_devfolio(self):
        try:
            res = requests.post("https://api.devfolio.co/api/hackathons", json={"type": "open", "limit": 10}, headers=self.headers, timeout=10)
            return [{"title": h['name'], "url": f"https://{h['slug']}.devfolio.co", "host": "Devfolio", "date": h.get('start_date', 'See Website')} for h in res.json()['result']]
        except: return []

    def fetch_dorahacks(self):
        try:
            # GraphQL 기반이나 리스트 API 사용
            res = requests.get("https://dorahacks.io/api/v1/hackathon", headers=self.headers, timeout=10)
            return [{"title": h['name'], "url": f"https://dorahacks.io/hackathon/{h['id']}", "host": "DoraHacks", "date": "Check Link"} for h in res.json().get('items', [])]
        except: return []

    def fetch_unstop(self):
        try:
            url = "https://unstop.com/api/public/opportunity/search-result?opportunity=hackathons&per_page=15"
            res = requests.get(url, headers=self.headers, timeout=10)
            return [{"title": h['title'], "url": f"https://unstop.com/p/{h['public_url']}", "host": "Unstop", "date": h.get('reg_end_date', 'N/A')} for h in res.json()['data']['data']]
        except: return []

    def fetch_kaggle(self):
        try:
            # Kaggle Competitions API (비공식 리스트 접근)
            res = requests.get("https://www.kaggle.com/api/i/competitions.CompetitionService/ListCompetitions", params={"category": "all"}, headers=self.headers, timeout=10)
            items = res.json().get('competitions', [])
            return [{"title": i['title'], "url": f"https://www.kaggle.com/c/{i['ref']}", "host": "Kaggle", "date": "Ongoing"} for i in items if 'Hackathon' in i['title'] or i['reward'] == 'Knowledge']
        except: return []

    def fetch_hack2skill(self):
        try:
            res = requests.get("https://api.hack2skill.com/gethackathons", headers=self.headers, timeout=10)
            return [{"title": h['name'], "url": f"https://hack2skill.com/hackathon/{h['slug']}", "host": "Hack2Skill", "date": h.get('start_date', 'N/A')} for h in res.json().get('data', [])]
        except: return []

    def fetch_korea_info(self):
        """국내 해커톤 (DoraHacks KR 필터 또는 가상 통합 리스트)"""
        # 국내 사이트는 API가 드물어 DoraHacks의 한국 태그나 검색 결과를 대용합니다.
        results = []
        try:
            res = requests.get("https://dorahacks.io/api/v1/hackathon?topic=Korea", headers=self.headers, timeout=10)
            results = [{"title": h['name'], "url": f"https://dorahacks.io/hackathon/{h['id']}", "host": "DoraHacks KR", "date": "확인 필요"} for h in res.json().get('items', [])]
        except: pass
        return results

    def run(self):
        print("🔍 해커톤 정보 수집을 시작합니다...")
        all_hackathons = []
        
        # 각 소스 연결
        all_hackathons.extend(self.fetch_devpost())
        all_hackathons.extend(self.fetch_mlh())
        all_hackathons.extend(self.fetch_devfolio())
        all_hackathons.extend(self.fetch_dorahacks())
        all_hackathons.extend(self.fetch_unstop())
        all_hackathons.extend(self.fetch_kaggle())
        all_hackathons.extend(self.fetch_hack2skill())
        all_hackathons.extend(self.fetch_korea_info())

        # 중복 제거 (데이터베이스에 없는 제목만 추출)
        new_items = [h for h in all_hackathons if h['title'] not in self.sent_list]

        if not new_items:
            print("✅ 새로운 공고가 없습니다.")
            return

        print(f"🆕 {len(new_items)}개의 새로운 공고를 발견했습니다!")
        
        # Discord 전송
        self.send_to_discord(new_items)
        
        # 보낸 목록 저장
        self.save_sent_list(new_items)

    def send_to_discord(self, hackathons):
        # Embed 리스트 생성 (최대 10개씩 묶음 전송)
        for i in range(0, len(hackathons), 10):
            chunk = hackathons[i:i+10]
            embeds = []
            for h in chunk:
                embeds.append({
                    "title": f"🏆 {h['title']}",
                    "url": h['url'],
                    "color": 3447003,
                    "fields": [
                        {"name": "플랫폼", "value": h['host'], "inline": True},
                        {"name": "마감/일정", "value": str(h['date']), "inline": True}
                    ]
                })
            
            payload = {
                "content": "🚀 **새로운 해커톤 기회가 발견되었습니다!**" if i == 0 else "",
                "embeds": embeds
            }
            res = requests.post(WEBHOOK_URL, json=payload)
            if res.status_code != 204:
                print(f"전송 실패: {res.status_code}")

if __name__ == "__main__":
    if not WEBHOOK_URL:
        print("❌ 오류: DISCORD_WEBHOOK_URL 환경 변수가 설정되지 않았습니다.")
    else:
        bot = HackathonBot()
        bot.run()
