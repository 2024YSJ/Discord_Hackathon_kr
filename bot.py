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
        """MLH 2026 시즌 페이지 크롤링 (실제 HTML 구조 기반)"""
        try:
            url = "https://mlh.io/seasons/2026/events"
            res = requests.get(url, headers=self.headers, timeout=15)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                results = []
                # MLH는 이벤트를 <a> 태그 안에 <h3>으로 표시 (CSS 클래스 없음)
                seen = set()
                for a in soup.find_all('a', href=True):
                    h3 = a.find('h3')
                    if not h3:
                        continue
                    title = h3.get_text(strip=True)
                    if not title or title in seen:
                        continue
                    seen.add(title)
                    link = a['href'].split('?')[0]  # UTM 파라미터 제거
                    if not link.startswith('http'):
                        link = "https://mlh.io" + link
                    # 날짜는 <a> 태그 내 텍스트 노드 (예: "FEB 27 - MAR 01")
                    date_str = "2026 Season"
                    for child in a.children:
                        text = str(child).strip()
                        if re.match(r'^[A-Z]{3}\s+\d+', text):
                            date_str = text
                            break
                    results.append({
                        "title": title,
                        "url": link,
                        "host": "MLH",
                        "date": date_str
                    })
                print(f"📡 MLH: {len(results)}개 추출 성공")
                return results
            else:
                print(f"MLH 응답 오류: {res.status_code}")
        except Exception as e:
            print(f"MLH 크롤링 예외 발생: {e}")
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
            headers = self.headers.copy()
            headers.update({
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            })
            url = "https://dorahacks.io/hackathon"
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                script = soup.find('script', id='__NEXT_DATA__')
                if script:
                    data = json.loads(script.string)
                    # Next.js Apollo State 탐색
                    queries = data.get('props', {}).get('pageProps', {}).get('apolloState', {})
                    results = []
                    for key, value in queries.items():
                        if key.startswith('Hackathon:') and isinstance(value, dict) and value.get('name'):
                            results.append({
                                "title": value['name'],
                                "url": f"https://dorahacks.io/hackathon/{value.get('id', '')}",
                                "host": "DoraHacks",
                                "date": "상세 확인"
                            })
                    return results
        except Exception as e:
            print(f"DoraHacks 크롤링 예외: {e}")
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
        # Kaggle은 클라이언트 사이드 렌더링으로 window.Kaggle.State가 더 이상 존재하지 않음
        # __NEXT_DATA__ 또는 JSON-LD 방식 시도
        try:
            url = "https://www.kaggle.com/competitions?hostSegmentIdFilter=8"
            res = requests.get(url, headers=self.headers, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
            # Next.js 데이터 시도
            script = soup.find('script', id='__NEXT_DATA__')
            if script:
                data = json.loads(script.string)
                items = data.get('props', {}).get('pageProps', {}).get('competitions', [])
                return [{"title": i['title'], "url": f"https://www.kaggle.com/c/{i.get('ref', i.get('id', ''))}", "host": "Kaggle", "date": i.get('deadline', 'N/A')} for i in items if i.get('title')]
            # JSON-LD 구조화 데이터 시도
            for s in soup.find_all('script', type='application/ld+json'):
                try:
                    ld = json.loads(s.string)
                    if isinstance(ld, list):
                        return [{"title": e.get('name', ''), "url": e.get('url', ''), "host": "Kaggle", "date": e.get('endDate', 'N/A')} for e in ld if e.get('name')]
                except: continue
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
        """brave-people/Dev-Event 마크다운 파일 파싱 (한국 개발 이벤트)"""
        try:
            now = datetime.now()
            year_short = str(now.year)[2:]   # 예: "26"
            month = str(now.month).zfill(2)  # 예: "02"
            url = f"https://raw.githubusercontent.com/brave-people/Dev-Event/master/end_event/{now.year}/{year_short}_{month}.md"
            res = requests.get(url, timeout=15)
            if res.status_code == 200:
                results = []
                # 마크다운 형식: - __[제목](URL)__
                for m in re.finditer(r'__\[([^\]]+)\]\((https?://[^\)]+)\)__', res.text):
                    title, link = m.group(1), m.group(2)
                    if any(k in title for k in ['해커톤', 'Hackathon', 'hackathon', '공모전', '경진대회']):
                        results.append({
                            "title": f"🇰🇷 [데브이벤트] {title}",
                            "url": link,
                            "host": "DevEvent",
                            "date": "상세 확인"
                        })
                return results
        except Exception as e:
            print(f"DevEvent 크롤링 예외 발생: {e}")
        return []

    def fetch_goorm(self):
        try:
            headers = self.headers.copy()
            headers.update({
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            })
            url = "https://level.goorm.io/l/challenge"
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code != 200:
                return []
            soup = BeautifulSoup(res.text, 'html.parser')
            results = []
            seen = set()
            for item in soup.find_all(['div', 'a'], class_=re.compile(r'card|item|challenge|contest')):
                title_el = item.find(['h3', 'h4', 'h2', 'div', 'span'], class_=re.compile(r'title|name|subject'))
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if not title or title in seen:
                    continue
                seen.add(title)
                link_el = item if item.name == 'a' else item.find('a')
                if link_el and link_el.get('href'):
                    href = link_el['href']
                    full_url = href if href.startswith('http') else "https://level.goorm.io" + href
                    results.append({
                        "title": f"🇰🇷 [구름] {title}",
                        "url": full_url,
                        "host": "goorm",
                        "date": "상세 확인"
                    })
            return results
        except Exception as e:
            print(f"Goorm 크롤링 예외: {e}")
        return []

    def fetch_wevity(self):
        """위비티 해커톤 공모전 목록 파싱 (서버사이드 렌더링)"""
        try:
            url = "https://www.wevity.com/?c=find&s=1&sp=contents&sw=%ED%95%B4%EC%BB%A4%ED%86%A4"
            res = requests.get(url, headers=self.headers, timeout=15)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                results = []
                ul = soup.find('ul', class_='list')
                if not ul:
                    return []
                for li in ul.find_all('li'):
                    if 'top' in li.get('class', []):
                        continue
                    # 마감된 항목 스킵 (dday span에 'end' 클래스)
                    if li.find('span', class_='end'):
                        continue
                    tit_div = li.find('div', class_='tit')
                    if not tit_div:
                        continue
                    a = tit_div.find('a', href=True)
                    if not a:
                        continue
                    title = a.get_text(strip=True)
                    if not title:
                        continue
                    href = a['href']
                    full_url = "https://www.wevity.com/" + href if href.startswith('?') else href
                    day_div = li.find('div', class_='day')
                    date_str = day_div.get_text(separator=' ', strip=True) if day_div else "상세 확인"
                    results.append({
                        "title": f"🇰🇷 [위비티] {title}",
                        "url": full_url,
                        "host": "Wevity",
                        "date": date_str
                    })
                return results
        except Exception as e:
            print(f"Wevity 크롤링 예외: {e}")
        return []

    def fetch_campuspick(self):
        """캠퍼스픽 해커톤 공모전 목록"""
        try:
            headers = self.headers.copy()
            headers.update({
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
                "Referer": "https://www.campuspick.com/",
            })
            # campuspick.com은 www2로 리다이렉트됨
            url = "https://www2.campuspick.com/contest?category=108&keyword=%ED%95%B4%EC%BB%A4%ED%86%A4"
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                results = []
                # 공모전 링크 패턴으로 항목 탐색
                for a in soup.find_all('a', href=re.compile(r'/contest/\d+')):
                    title_el = a.find(['h3', 'h4', 'h2', 'p', 'span'],
                                       class_=re.compile(r'title|name|tit|subject'))
                    title = title_el.get_text(strip=True) if title_el else a.get_text(strip=True)
                    if not title:
                        continue
                    href = a['href']
                    full_url = "https://www2.campuspick.com" + href if href.startswith('/') else href
                    results.append({
                        "title": f"🇰🇷 [캠퍼스픽] {title}",
                        "url": full_url,
                        "host": "CampusPick",
                        "date": "상세 확인"
                    })
                return results
        except Exception as e:
            print(f"CampusPick 크롤링 예외: {e}")
        return []

    def fetch_aiconnect(self):
        """AI Connect 대회 목록 (Nuxt.js, window.__NUXT__ 데이터 탐색)"""
        try:
            headers = self.headers.copy()
            headers.update({
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9",
                "Referer": "https://aiconnect.kr/",
            })
            res = requests.get("https://aiconnect.kr/competition/list", headers=headers, timeout=15)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                results = []
                for script in soup.find_all('script'):
                    text = script.get_text()
                    if '__NUXT__' not in text:
                        continue
                    m = re.search(r'window\.__NUXT__\s*=\s*(\{.+\})\s*;?\s*$', text, re.DOTALL)
                    if not m:
                        continue
                    try:
                        nuxt = json.loads(m.group(1))
                        # 가능한 경로들 순서대로 탐색
                        candidates = [
                            nuxt.get('state', {}).get('competitions', []),
                            nuxt.get('state', {}).get('items', []),
                            nuxt.get('data', [{}])[0].get('competitions', []) if nuxt.get('data') else [],
                        ]
                        for comps in candidates:
                            if not isinstance(comps, list) or not comps:
                                continue
                            for c in comps:
                                if not isinstance(c, dict):
                                    continue
                                title = c.get('title') or c.get('name', '')
                                cid = c.get('id') or c.get('competitionId', '')
                                if title:
                                    results.append({
                                        "title": f"🇰🇷 [AI Connect] {title}",
                                        "url": f"https://aiconnect.kr/competition/detail/{cid}",
                                        "host": "AIConnect",
                                        "date": c.get('endDate', '상세 확인')
                                    })
                            break
                    except json.JSONDecodeError:
                        pass
                return results
        except Exception as e:
            print(f"AIConnect 크롤링 예외: {e}")
        return []

    def fetch_linkareer(self):
        """링커리어 GraphQL API - 해커톤 활동 검색"""
        try:
            query = "{ activities { nodes { id title organizationName categories { name } createdAt } } }"
            res = requests.post(
                "https://api.linkareer.com/graphql",
                json={"query": query},
                headers={"Content-Type": "application/json",
                         "User-Agent": self.headers["User-Agent"]},
                timeout=15
            )
            if res.status_code == 200:
                nodes = res.json().get('data', {}).get('activities', {}).get('nodes', [])
                results = []
                for node in nodes:
                    title = node.get('title', '')
                    cats = ' '.join(c.get('name', '') for c in (node.get('categories') or []))
                    if any(k in title + cats for k in ['해커톤', 'Hackathon', 'hackathon']):
                        nid = node.get('id', '')
                        results.append({
                            "title": f"🇰🇷 [링커리어] {title}",
                            "url": f"https://linkareer.com/activity/{nid}",
                            "host": "Linkareer",
                            "date": "상세 확인"
                        })
                return results
        except Exception as e:
            print(f"Linkareer 크롤링 예외: {e}")
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
            ("goorm", self.fetch_goorm),
            ("Wevity", self.fetch_wevity),
            ("CampusPick", self.fetch_campuspick),
            ("AIConnect", self.fetch_aiconnect),
            ("Linkareer", self.fetch_linkareer),
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
