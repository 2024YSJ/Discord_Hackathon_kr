import os
import requests
import json
from datetime import datetime
from bs4 import BeautifulSoup
import time
import re
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
            # 특정 연도 필터 없이 전체를 가져와서 로컬에서 필터링하는 것이 누락을 방지함
            res = requests.get("https://mlh.io/api/v1/hackathons", headers=self.headers, timeout=15)
            if res.status_code == 200:
                now = datetime.now().strftime('%Y-%m-%d')
                return [{"title": h['name'], "url": h['url'], "host": "MLH", "date": h['start_date']} 
                        for h in res.json() if h.get('start_date', '') >= now]
        except: pass
        return []

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
                # 해커톤 목록 페이지 직접 타격
                url = "https://dorahacks.io/hackathon"
                res = requests.get(url, headers=self.headers, timeout=15)
                soup = BeautifulSoup(res.text, 'html.parser')
                script = soup.find('script', id='__NEXT_DATA__')
                if script:
                    data = json.loads(script.string)
                    # Next.js의 복잡한 데이터 트리 구조 정밀 탐색
                    queries = data.get('props', {}).get('pageProps', {}).get('apolloState', {})
                    results = []
                    for key, value in queries.items():
                        if key.startswith('Hackathon:') and value.get('name'):
                            results.append({
                                "title": value['name'],
                                "url": f"https://dorahacks.io/hackathon/{value.get('id')}",
                                "host": "DoraHacks",
                                "date": "상세 확인"
                            })
                    return results
            except: pass
            return []

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
            url = "https://www.kaggle.com/competitions?hostSegmentIdFilter=8"
            res = requests.get(url, headers=self.headers, timeout=15)
            # JSON 데이터를 뽑아내기 위한 더 정밀한 정규표현식
            match = re.search(r'window\.Kaggle\.State\s*=\s*({.*?});(?=\s*window|$)', res.text, re.DOTALL)
            if match:
                data = json.loads(match.group(1))
                items = data.get('competitionListing', {}).get('competitions', [])
                return [{"title": i['title'], "url": f"https://www.kaggle.com/c/{i['ref']}", "host": "Kaggle", "date": i.get('deadline')} for i in items]
        except: pass
        return []

    def fetch_hack2skill(self):
        try:
            url = "https://api.hack2skill.com/gethackathons"
            res = requests.get(url, headers=self.headers, timeout=15)
            if res.status_code == 200:
                return [{"title": h.get('name'), "url": f"https://hack2skill.com/hackathon/{h.get('slug')}", "host": "Hack2Skill", "date": h.get('start_date', 'N/A').split('T')[0]} for h in res.json().get('data', []) if h.get('slug')]
            return []
        except: return []

    def fetch_programmers(self):
        try:
            # 특정 카테고리가 아닌 전체 챌린지 페이지
            url = "https://programmers.co.kr/learn/challenges"
            res = requests.get(url, headers=self.headers, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
            results = []
            # 'challenge-card' 클래스 외에 제목을 포함하는 모든 링크 탐색
            for a in soup.select('a[href*="/learn/challenges/"]'):
                title_el = a.select_one('h4, .title, h5')
                if title_el:
                    title = title_el.get_text(strip=True)
                    if any(k in title for k in ['해커톤', '챌린지', '대회']):
                        results.append({
                            "title": f"🇰🇷 [프로그래머스] {title}",
                            "url": "https://programmers.co.kr" + a['href'],
                            "host": "Programmers", "date": "상세 확인"
                        })
            return results
        except: pass
        return []

    def fetch_devevent(self):
        try:
            # 웹페이지 대신 개발자가 관리하는 GitHub의 Raw JSON을 직접 타격 (차단 0%)
            url = "https://raw.githubusercontent.com/one-meter/dev-event/master/lib/events.json"
            res = requests.get(url, timeout=15)
            if res.status_code == 200:
                now = datetime.now().strftime('%Y-%m-%d')
                return [{"title": f"🇰🇷 [데브이벤트] {e['title']}", "url": e['link'], "host": "DevEvent", "date": e['startDate']} 
                        for e in res.json() if ('해커톤' in e['title'] or 'Hackathon' in e['title']) and e.get('endDate', '9999-12-31') >= now]
        except: pass
        return []

    def fetch_goorm(self):
        try:
            # 구름은 최근 '에듀'와 '레벨' 섹션이 통합되는 추세입니다.
            url = "https://level.goorm.io/l/challenge"
            res = requests.get(url, headers=self.headers, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
            results = []
            # 카드 레이아웃의 공통 부모 탐색
            for item in soup.find_all(['div', 'a'], class_=re.compile(r'card|item|challenge')):
                title_el = item.find(['h3', 'h4', 'div'], class_=re.compile(r'title|name'))
                if title_el:
                    title = title_el.get_text(strip=True)
                    link_el = item if item.name == 'a' else item.find('a')
                    if link_el and link_el.get('href'):
                        results.append({
                            "title": f"🇰🇷 [구름] {title}",
                            "url": "https://level.goorm.io" + link_el['href'],
                            "host": "goorm", "date": "상세 확인"
                        })
            return results
        except: pass
        return []

    def run(self):
        print("🔍 해커톤 정보 수집을 시작합니다...")
        all_hackathons = []
        
        # 함수 목록과 이름 매핑
        tasks = [
            ("Devpost", self.fetch_devpost),
            ("MLH", self.fetch_mlh),
            ("Devfolio", self.fetch_devfolio),
            ("Unstop", self.fetch_unstop),
            ("Kaggle", self.fetch_kaggle),
            ("Hack2Skill", self.fetch_hack2skill),
            ("DoraHacks", self.fetch_dorahacks),
            ("Programmers", self.fetch_programmers),
            ("DevEvent", self.fetch_devevent),
            ("goorm", self.fetch_goorm)
        ]
        
        for name, fetcher in tasks:
            try:
                found = fetcher()
                print(f"📡 {name}: {len(found)}개 발견") # 로그 출력
                all_hackathons.extend(found)
            except Exception as e:
                print(f"❌ {name} 실행 중 치명적 오류: {e}")

        # 중복 제거
        new_items = [h for h in all_hackathons if h['title'] not in self.sent_list]
        print(f"📊 최종 신규 공고: {len(new_items)}개")

        if not new_items:
            return

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
