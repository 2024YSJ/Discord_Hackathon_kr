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
        """MLH 2026 시즌 페이지 크롤링 - 미래 이벤트만 반환"""
        MONTHS = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,
                  'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
        try:
            url = "https://mlh.io/seasons/2026/events"
            res = requests.get(url, headers=self.headers, timeout=15)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                results = []
                today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                seen = set()
                for a in soup.find_all('a', href=True):
                    h3 = a.find('h3')
                    if not h3:
                        continue
                    title = h3.get_text(strip=True)
                    if not title or title in seen:
                        continue
                    seen.add(title)
                    link = a['href'].split('?')[0]
                    if not link.startswith('http'):
                        link = "https://mlh.io" + link
                    # <a> 전체 텍스트에서 날짜 패턴 추출 (예: "FEB 27", "MAR 01")
                    a_text = a.get_text(separator=' ', strip=True).replace(title, '')
                    date_parts = re.findall(r'([A-Z]{3})\s+(\d{1,2})', a_text)
                    if date_parts:
                        date_str = ' - '.join(f"{m} {d}" for m, d in date_parts) if len(date_parts) > 1 else f"{date_parts[0][0]} {date_parts[0][1]}"
                        # 종료일(마지막 날짜)이 오늘 이전이면 스킵
                        mon, day = date_parts[-1]
                        end_m = MONTHS.get(mon, 0)
                        if end_m:
                            event_end = datetime(today.year, end_m, int(day))
                            if event_end < today:
                                continue
                    else:
                        date_str = "2026 Season"
                    results.append({
                        "title": title,
                        "url": link,
                        "host": "MLH",
                        "date": date_str
                    })
                print(f"📡 MLH: {len(results)}개 추출 성공 (종료 이벤트 제외)")
                return results
            else:
                print(f"MLH 응답 오류: {res.status_code}")
        except Exception as e:
            print(f"MLH 크롤링 예외 발생: {e}")
        return []

    def fetch_devfolio(self):
        """devfolio.co/hackathons의 __NEXT_DATA__ 에서 open/upcoming/featured 해커톤 추출"""
        try:
            dev_headers = self.headers.copy()
            dev_headers.update({
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            })
            res = requests.get("https://devfolio.co/hackathons", headers=dev_headers, timeout=15)
            if res.status_code != 200:
                return []
            soup = BeautifulSoup(res.text, 'html.parser')
            script = soup.find('script', id='__NEXT_DATA__')
            if not script:
                return []
            page_data = json.loads(script.string)
            queries = page_data['props']['pageProps']['dehydratedState']['queries']
            if not queries:
                return []
            qdata = queries[0]['state']['data']
            today = datetime.now().strftime('%Y-%m-%d')
            seen = set()
            results = []
            for section in ('open_hackathons', 'upcoming_hackathons', 'featured_hackathons'):
                for h in qdata.get(section, []):
                    slug = h.get('slug', '')
                    name = h.get('name', '')
                    if not slug or not name or slug in seen:
                        continue
                    seen.add(slug)
                    ends_at = (h.get('ends_at') or '')[:10]
                    if ends_at and ends_at < today:
                        continue
                    results.append({
                        "title": name,
                        "url": f"https://{slug}.devfolio.co",
                        "host": "Devfolio",
                        "date": ends_at or "상세 확인"
                    })
            return results
        except Exception as e:
            print(f"Devfolio 크롤링 예외: {e}")
            return []

    def fetch_dorahacks(self):
        """DoraHacks REST API - 진행 중인 해커톤 목록"""
        try:
            import time as _time
            res = requests.get(
                "https://dorahacks.io/api/hackathon",
                params={"status": "open", "limit": 20},
                headers=self.headers, timeout=15
            )
            if res.status_code == 200:
                now_ts = _time.time()
                results = []
                for h in res.json().get('results', []):
                    title = h.get('title', '')
                    if not title:
                        continue
                    # end_time이 현재 이전이면 스킵
                    end_ts = h.get('end_time')
                    if end_ts and int(end_ts) < now_ts:
                        continue
                    results.append({
                        "title": title,
                        "url": f"https://dorahacks.io/hackathon/{h.get('id', '')}",
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
        """Kaggle 공식 API (KAGGLE_USERNAME + KAGGLE_KEY 환경변수 필요)"""
        username = os.environ.get('KAGGLE_USERNAME')
        key = os.environ.get('KAGGLE_KEY')
        if not username or not key:
            return []
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            res = requests.get(
                'https://www.kaggle.com/api/v1/competitions/list',
                params={'sortBy': 'latestDeadline', 'pageSize': 20},
                auth=(username, key),
                headers=self.headers, timeout=15
            )
            if res.status_code == 200:
                results = []
                for c in res.json():
                    title = c.get('title', '')
                    deadline = (c.get('deadline') or '')[:10]
                    if not title or (deadline and deadline < today):
                        continue
                    ref = c.get('ref') or c.get('id', '')
                    results.append({
                        "title": title,
                        "url": f"https://www.kaggle.com/competitions/{ref}",
                        "host": "Kaggle",
                        "date": deadline or "상세 확인"
                    })
                return results
        except Exception as e:
            print(f"Kaggle 크롤링 예외: {e}")
        return []

    def fetch_hack2skill(self):
        """Hack2Skill 홈페이지 flagship 이벤트 파싱 (서버사이드 렌더링)"""
        try:
            res = requests.get('https://hack2skill.com/', headers=self.headers, timeout=15)
            if res.status_code != 200:
                return []
            soup = BeautifulSoup(res.text, 'html.parser')
            flagship = soup.find(class_='flagshipEventsSlider')
            if not flagship:
                return []
            today = datetime.now()
            results = []
            seen = set()
            for a in flagship.find_all('a', href=re.compile(r'hack2skill\.com')):
                url = a['href'].split('?')[0]
                if url in seen:
                    continue
                card = a.find_parent('div', class_=re.compile(r'w-\[16rem\]'))
                if not card:
                    continue
                h5s = card.find_all('h5')
                if not h5s:
                    continue
                title = h5s[0].get_text(strip=True)
                if not title:
                    continue
                date_str = h5s[-1].get_text(strip=True) if len(h5s) > 1 else ''
                try:
                    event_date = datetime.strptime(date_str, '%a %b %d %Y')
                    if event_date < today:
                        continue
                except ValueError:
                    pass
                seen.add(url)
                results.append({
                    "title": title,
                    "url": url,
                    "host": "Hack2Skill",
                    "date": date_str
                })
            return results
        except Exception as e:
            print(f"Hack2Skill 크롤링 예외: {e}")
        return []

    def fetch_programmers(self):
        """프로그래머스 대회 공식 API"""
        try:
            res = requests.get("https://programmers.co.kr/api/competitions",
                               headers=self.headers, timeout=15)
            if res.status_code == 200:
                today = datetime.now().strftime('%Y-%m-%d')
                results = []
                for c in res.json().get('competitions', []):
                    if c.get('statusLabel') == 'ended':
                        continue
                    # 접수 마감이 이미 지난 경우 스킵
                    end_at = c.get('receiptEndAt') or c.get('endAt') or ''
                    if end_at and end_at[:10] < today:
                        continue
                    title = c.get('title', '')
                    href  = c.get('href', '')
                    results.append({
                        "title": f"🇰🇷 [프로그래머스] {title}",
                        "url": f"https://programmers.co.kr{href}",
                        "host": "Programmers",
                        "date": end_at[:10] if end_at else "상세 확인"
                    })
                return results
        except Exception as e:
            print(f"Programmers 크롤링 예외: {e}")
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
        # level.goorm.io는 Vue SPA로 서버사이드 렌더링이 없어 크롤링 불가
        return []

    def fetch_wevity(self):
        """위비티 해커톤 공모전 목록 파싱 (세션 쿠키로 403 우회)"""
        try:
            session = requests.Session()
            session.headers.update(self.headers)
            session.headers.update({
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
            })
            # 메인 페이지 먼저 방문해 PHPSESSID 쿠키 획득
            session.get('https://www.wevity.com/', timeout=10)
            res = session.get(
                'https://www.wevity.com/',
                params={'c': 'find', 's': '1', 'sp': 'contents', 'sw': '해커톤'},
                timeout=15
            )
            print(f"  Wevity HTTP {res.status_code}, {len(res.text)} bytes")
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                ul = soup.find('ul', class_='list')
                if not ul:
                    print("  Wevity: ul.list 요소를 찾지 못함")
                    return []
                results = []
                li_all = ul.find_all('li')
                print(f"  Wevity: {len(li_all)}개 li 발견")
                for li in li_all:
                    if 'top' in li.get('class', []):
                        continue
                    # dday span 텍스트로 마감 여부 확인 ('마감임박'은 포함)
                    dday_span = li.find('span', class_='dday')
                    if dday_span and dday_span.get_text(strip=True) == '마감':
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
        """캠퍼스픽 내부 API (api2.campuspick.com/find/activity/list POST)"""
        try:
            api_headers = self.headers.copy()
            api_headers.update({
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://www2.campuspick.com",
                "Referer": "https://www2.campuspick.com/contest?category=108",
            })
            today = datetime.now().strftime('%Y-%m-%d')
            results = []
            # categoryId=108 (해커톤), 페이지 순회
            for offset in range(0, 40, 20):
                res = requests.post(
                    "https://api2.campuspick.com/find/activity/list",
                    data={"target": 1, "limit": 20, "offset": offset, "categoryId": 108},
                    headers=api_headers, timeout=15
                )
                if res.status_code != 200:
                    break
                activities = res.json().get("result", {}).get("activities", [])
                if not activities:
                    break
                valid = [a for a in activities if a.get("endDate", "") >= today]
                for a in valid:
                    results.append({
                        "title": f"🇰🇷 [캠퍼스픽] {a['title']}",
                        "url": f"https://www2.campuspick.com/contest/view?id={a['id']}",
                        "host": "CampusPick",
                        "date": a.get("endDate", "상세 확인")
                    })
                # 첫 페이지에 유효 결과 없으면 중단
                if not valid:
                    break
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
