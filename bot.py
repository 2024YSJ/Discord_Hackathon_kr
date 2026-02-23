import os
import requests
import json
from datetime import datetime
from bs4 import BeautifulSoup
import time

# 설정
WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')
DB_FILE = "sent_hackathons.txt"

class HackathonBot:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        # Kaggle 전용 헤더 (base_headers 대용)
        self.base_headers = self.headers.copy()
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

    # --- 플랫폼별 크롤러/API 호출 메서드 (클래스 내부로 들여쓰기 완료) ---

    def fetch_devpost(self):
        try:
            custom_headers = self.headers.copy()
            custom_headers.update({
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Referer": "https://devpost.com/hackathons",
                "X-Requested-With": "XMLHttpRequest"
            })
            params = {"status[]": "upcoming", "sort_by": "Recently Added"}
            url = "https://devpost.com/api/hackathons"
            res = requests.get(url, params=params, headers=custom_headers, timeout=15)
            if res.status_code == 200:
                data = res.json()
                hackathons = data.get('hackathons', [])
                return [{"title": h['title'], "url": h['url'], "host": "Devpost", "date": h.get('submission_period_dates', 'N/A')} for h in hackathons]
            return []
        except: return []

    def fetch_mlh(self):
        try:
            year = datetime.now().year
            url = f"https://mlh.io/api/v1/hackathons?year={year}"
            res = requests.get(url, headers=self.headers, timeout=15)
            if res.status_code == 200:
                data = res.json()
                now_str = datetime.now().strftime('%Y-%m-%d')
                return [{"title": h['name'], "url": h['url'], "host": "MLH", "date": h['start_date']} for h in data if h.get('start_date', '') >= now_str][:10]
            return []
        except: return []

    def fetch_devfolio(self):
        try:
            dev_headers = self.headers.copy()
            dev_headers.update({"Origin": "https://devfolio.co", "Referer": "https://devfolio.co/hackathons", "X-Requested-With": "XMLHttpRequest"})
            url = "https://api.devfolio.co/api/hackathons"
            res = requests.post(url, json={"type": "open", "limit": 15, "range": "upcoming"}, headers=dev_headers, timeout=15)
            if res.status_code == 200:
                return [{"title": h.get('name'), "url": f"https://{h.get('slug')}.devfolio.co", "host": "Devfolio", "date": h.get('start_date', 'N/A')} for h in res.json().get('result', []) if h.get('slug')]
            return []
        except: return []

    def fetch_dorahacks(self):
        try:
            url = "https://dorahacks.io/api/v1/hackathon"
            res = requests.get(url, params={"size": 10}, headers=self.headers, timeout=15)
            if res.status_code == 200:
                data = res.json()
                items = data.get('data', {}).get('items', []) if 'data' in data else data.get('items', [])
                return [{"title": h.get('name'), "url": f"https://dorahacks.io/hackathon/{h.get('id')}", "host": "DoraHacks", "date": "Check Website"} for h in items if h.get('id')]
            return []
        except: return []

    def fetch_unstop(self):
        try:
            url = "https://unstop.com/api/public/opportunity/search-result?opportunity=hackathons&per_page=15"
            res = requests.get(url, headers=self.headers, timeout=15)
            if res.status_code == 200:
                items = res.json().get('data', {}).get('data', [])
                return [{"title": h.get('title'), "url": f"https://unstop.com/p/{h.get('public_url')}", "host": "Unstop", "date": h.get('reg_end_date', 'N/A').split('T')[0]} for h in items if h.get('public_url')]
            return []
        except: return []

    def fetch_kaggle(self):
        try:
            kaggle_headers = self.base_headers.copy()
            kaggle_headers.update({"Referer": "https://www.kaggle.com/competitions", "X-Requested-With": "XMLHttpRequest"})
            url = "https://www.kaggle.com/api/i/competitions.CompetitionService/ListCompetitions"
            res = requests.get(url, params={"category": "all", "listCompetitionsRequest.sort": "LATEST"}, headers=kaggle_headers, timeout=15)
            if res.status_code == 200:
                items = res.json().get('competitions', [])
                results = []
                for i in items:
                    title = i.get('title', '')
                    if any(k in title.lower() for k in ['hackathon', 'challenge']) or i.get('rewardType') == 'KNOWLEDGE':
                        results.append({"title": title, "url": f"https://www.kaggle.com/c/{i.get('ref')}", "host": "Kaggle", "date": i.get('deadline', 'Ongoing').split('T')[0]})
                return results[:10]
            return []
        except: return []

    def fetch_hack2skill(self):
        try:
            url = "https://api.hack2skill.com/gethackathons"
            res = requests.get(url, headers=self.headers, timeout=15)
            if res.status_code == 200:
                return [{"title": h.get('name'), "url": f"https://hack2skill.com/hackathon/{h.get('slug')}", "host": "Hack2Skill", "date": h.get('start_date', 'N/A').split('T')[0]} for h in res.json().get('data', []) if h.get('slug')]
            return []
        except: return []

    def fetch_wevity(self):
        results = []
        try:
            url = "https://www.wevity.com/?c=find&s=1&gub=1&cat=30"
            res = requests.get(url, headers=self.headers, timeout=15)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                for item in soup.select('.list li'):
                    title_tag = item.select_one('.tit a')
                    if title_tag and any(k in title_tag.text for k in ['해커톤', 'Hackathon']):
                        results.append({"title": f"🇰🇷 [위비티] {title_tag.text.strip()}", "url": "https://www.wevity.com/" + title_tag['href'], "host": "Wevity", "date": item.select_one('.dday').text.strip() if item.select_one('.dday') else "기한확인"})
        except: pass
        return results

    def fetch_linkareer(self):
        results = []
        try:
            url = "https://linkareer.com/list/contest?filterType=category&filterValue=11"
            res = requests.get(url, headers=self.headers, timeout=15)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                for item in soup.find_all('h5'):
                    if '해커톤' in item.text:
                        results.append({"title": f"🇰🇷 [링커리어] {item.text.strip()}", "url": url, "host": "Linkareer", "date": "상세 확인"})
        except: pass
        return results

    def fetch_campuspick(self):
        results = []
        try:
            url = "https://www.campuspick.com/contest"
            res = requests.get(url, headers=self.headers, timeout=15)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                for a in soup.select('a.item'):
                    title = a.select_one('h2').text.strip() if a.select_one('h2') else ""
                    if '해커톤' in title:
                        results.append({"title": f"🇰🇷 [캠퍼스픽] {title}", "url": "https://www.campuspick.com" + a['href'], "host": "Campuspick", "date": a.select_one('.dday').text.strip() if a.select_one('.dday') else "진행중"})
        except: pass
        return results

    def run(self):
        print("🔍 해커톤 정보 수집을 시작합니다...")
        all_hackathons = []
        
        # 수집 함수 실행
        all_hackathons.extend(self.fetch_devpost())
        all_hackathons.extend(self.fetch_mlh())
        all_hackathons.extend(self.fetch_devfolio())
        all_hackathons.extend(self.fetch_unstop())
        all_hackathons.extend(self.fetch_kaggle())
        all_hackathons.extend(self.fetch_hack2skill())
        all_hackathons.extend(self.fetch_dorahacks())
        all_hackathons.extend(self.fetch_wevity())
        all_hackathons.extend(self.fetch_linkareer())
        all_hackathons.extend(self.fetch_campuspick())

        # 중복 제거 (데이터베이스에 없는 제목만 추출)
        new_items = [h for h in all_hackathons if h['title'] not in self.sent_list]

        if not new_items:
            print("✅ 새로운 공고가 없습니다.")
            return

        print(f"🆕 {len(new_items)}개의 새로운 공고를 발견했습니다!")
        self.send_to_discord(new_items)
        self.save_sent_list(new_items)

    def send_to_discord(self, hackathons):
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
                "content": "🚀 **새로운 해커톤 대회가 발견되었습니다!**" if i == 0 else "",
                "embeds": embeds
            }
            requests.post(WEBHOOK_URL, json=payload)

if __name__ == "__main__":
    if not WEBHOOK_URL:
        print("❌ 오류: DISCORD_WEBHOOK_URL 환경 변수가 설정되지 않았습니다.")
    else:
        bot = HackathonBot()
        bot.run()
