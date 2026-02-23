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
            # 연도를 특정하지 않고 전체 목록을 가져온 뒤 현재 시점 데이터만 추출
            url = "https://mlh.io/api/v1/hackathons" 
            res = requests.get(url, headers=self.headers, timeout=15)
            if res.status_code == 200:
                data = res.json()
                now_str = datetime.now().strftime('%Y-%m-%d')
                # 시작일이 현재보다 미래인 것만 필터링
                upcoming = [h for h in data if h.get('start_date', '') >= now_str]
                return [{"title": h['name'], "url": h['url'], "host": "MLH", "date": h['start_date']} for h in upcoming]
            return []
        except Exception as e:
            print(f"MLH Error: {e}")
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
            # Kaggle은 위조된 헤더가 매우 중요합니다.
            kaggle_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                "Accept": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": "https://www.kaggle.com/competitions"
            }
            # 엔드포인트 파라미터 최신화
            url = "https://www.kaggle.com/api/i/competitions.CompetitionService/ListCompetitions"
            params = {"category": "all", "listCompetitionsRequest.sort": "LATEST"}
            
            res = requests.get(url, params=params, headers=kaggle_headers, timeout=15)
            if res.status_code == 200:
                items = res.json().get('competitions', [])
                results = []
                for i in items:
                    title = i.get('title', '')
                    # 상금/보상 체계가 'Knowledge'이거나 제목에 키워드가 있는 것 추출
                    if any(k in title.lower() for k in ['hackathon', 'challenge']) or i.get('rewardTypeName') == 'Knowledge':
                        results.append({
                            "title": title, 
                            "url": f"https://www.kaggle.com/c/{i.get('ref')}", 
                            "host": "Kaggle", 
                            "date": i.get('deadline', 'Ongoing').split('T')[0]
                        })
                return results
            return []
        except Exception as e:
            print(f"Kaggle Error: {e}")
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
        """프로그래머스 챌린지/해커톤 수집"""
        results = []
        try:
            # 프로그래머스 스킬 체크 및 챌린지 페이지
            url = "https://programmers.co.kr/learn/challenges"
            res = requests.get(url, headers=self.headers, timeout=15)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                # 해커톤이나 챌린지 카드 탐색
                items = soup.select('.challenge-card')
                for item in items:
                    title = item.select_one('.title').text.strip()
                    if '해커톤' in title or '챌린지' in title:
                        link = "https://programmers.co.kr" + item.select_one('a')['href']
                        results.append({
                            "title": f"🇰🇷 [프로그래머스] {title}",
                            "url": link,
                            "host": "Programmers",
                            "date": "진행중/마감확인"
                        })
        except Exception as e:
            print(f"Programmers Error: {e}")
        return results

    def fetch_devevent(self):
        """국내 IT 행사 큐레이션 '데브이벤트' 수집"""
        results = []
        try:
            # 해커톤 카테고리/태그 기반 (비공식 API 또는 페이지)
            url = "https://dev-event.vercel.app/api/events" # 데브이벤트는 오픈소스로 관리되는 경우가 많음
            res = requests.get(url, headers=self.headers, timeout=15)
            if res.status_code == 200:
                events = res.json()
                for e in events:
                    title = e.get('title', '')
                    if '해커톤' in title or 'Hackathon' in title:
                        results.append({
                            "title": f"🇰🇷 [데브이벤트] {title}",
                            "url": e.get('link', ''),
                            "host": "DevEvent",
                            "date": e.get('period', '확인필요')
                        })
        except:
            # API 실패 시 페이지 크롤링으로 백업
            try:
                url = "https://dev-event.vercel.app/"
                res = requests.get(url, headers=self.headers, timeout=15)
                soup = BeautifulSoup(res.text, 'html.parser')
                # 텍스트 내 '해커톤' 포함 링크 탐색
                for a in soup.find_all('a'):
                    if '해커톤' in a.text:
                        results.append({
                            "title": f"🇰🇷 [데브이벤트] {a.text.strip()}",
                            "url": a['href'],
                            "host": "DevEvent",
                            "date": "확인필요"
                        })
            except: pass
        return results

    def fetch_goorm(self):
        """구름(goorm) 해커톤 섹션 수집"""
        results = []
        try:
            url = "https://level.goorm.io/l/challenge"
            res = requests.get(url, headers=self.headers, timeout=15)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                # 구름톤 등 챌린지 카드 추출
                for card in soup.select('.challenge-card-item'):
                    title = card.select_one('.card-title').text.strip()
                    link = "https://level.goorm.io" + card.select_one('a')['href']
                    results.append({
                        "title": f"🇰🇷 [구름] {title}",
                        "url": link,
                        "host": "goorm",
                        "date": "일정확인"
                    })
        except Exception as e:
            print(f"goorm Error: {e}")
        return results

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
