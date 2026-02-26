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

    # ──────────────────────────────────────────
    # 기존 정상 함수들 (변경 없음)
    # ──────────────────────────────────────────

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
                    a_text = a.get_text(separator=' ', strip=True).replace(title, '')
                    date_parts = re.findall(r'([A-Z]{3})\s+(\d{1,2})', a_text)
                    if date_parts:
                        date_str = ' - '.join(f"{m} {d}" for m, d in date_parts) if len(date_parts) > 1 else f"{date_parts[0][0]} {date_parts[0][1]}"
                        mon, day = date_parts[-1]
                        end_m = MONTHS.get(mon, 0)
                        if end_m:
                            event_end = datetime(today.year, end_m, int(day))
                            if event_end < today:
                                continue
                    else:
                        date_str = "2026 Season"
                    results.append({"title": title, "url": link, "host": "MLH", "date": date_str})
                print(f"📡 MLH: {len(results)}개 추출 성공 (종료 이벤트 제외)")
                return results
        except Exception as e:
            print(f"MLH 크롤링 예외 발생: {e}")
        return []

    def fetch_kaggle(self):
        username = os.environ.get('KAGGLE_USERNAME', '')
        key = os.environ.get('KAGGLE_KEY', '')
        print(f"DEBUG: Username length: {len(username)}")
        print(f"DEBUG: Key length: {len(key)}")
        if not username or not key:
            print("❌ 오류: Kaggle 환경변수가 설정되지 않았습니다.")
            return []
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            res = requests.get(
                'https://www.kaggle.com/api/v1/competitions/list',
                params={'sortBy': 'latestDeadline', 'pageSize': 20},
                auth=(username, key),
                headers=self.headers, timeout=15
            )
            if res.status_code != 200:
                print(f"❌ API 요청 실패 (Status: {res.status_code}): {res.text}")
                return []
            data = res.json()
            results = []
            for c in data:
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
            print(f"✅ {len(results)}개의 활성 경진대회를 찾았습니다.")
            return results
        except Exception as e:
            print(f"❌ Kaggle 크롤링 중 예외 발생: {e}")
            return []

    def fetch_hack2skill(self):
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
                results.append({"title": title, "url": url, "host": "Hack2Skill", "date": date_str})
            return results
        except Exception as e:
            print(f"Hack2Skill 크롤링 예외: {e}")
        return []

    def fetch_dorahacks(self):
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

    def fetch_devevent(self):
        try:
            now = datetime.now()
            year_short = str(now.year)[2:]
            month = str(now.month).zfill(2)
            url = f"https://raw.githubusercontent.com/brave-people/Dev-Event/master/end_event/{now.year}/{year_short}_{month}.md"
            res = requests.get(url, timeout=15)
            if res.status_code == 200:
                results = []
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

    def fetch_campuspick(self):
        try:
            api_headers = self.headers.copy()
            api_headers.update({
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://www2.campuspick.com",
                "Referer": "https://www2.campuspick.com/contest?category=108",
            })
            today = datetime.now().strftime('%Y-%m-%d')
            results = []
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
                if not valid:
                    break
            return results
        except Exception as e:
            print(f"CampusPick 크롤링 예외: {e}")
        return []

    # ──────────────────────────────────────────
    # 수정된 함수들
    # ──────────────────────────────────────────

    def fetch_devfolio(self):
        """
        [수정] __NEXT_DATA__ JSON 파싱 → HTML 링크 직접 파싱 방식으로 변경.
        Devfolio는 SSR이지만 __NEXT_DATA__ 구조가 자주 바뀌므로,
        페이지에 렌더링된 <a href="https://xxx.devfolio.co/"> 링크를 직접 추출.
        open / upcoming 두 페이지를 모두 순회.
        """
        results = []
        seen = set()
        pages = [
            "https://devfolio.co/hackathons/open",
            "https://devfolio.co/hackathons/upcoming",
        ]
        headers = self.headers.copy()
        headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })

        for page_url in pages:
            try:
                res = requests.get(page_url, headers=headers, timeout=15)
                if res.status_code != 200:
                    print(f"  Devfolio {page_url} 응답 오류: {res.status_code}")
                    continue

                soup = BeautifulSoup(res.text, 'html.parser')

                # devfolio 해커톤 서브도메인 링크: https://<slug>.devfolio.co/
                for a in soup.find_all('a', href=re.compile(r'https://[^/]+\.devfolio\.co/?$')):
                    href = a['href'].rstrip('/')
                    if href in seen:
                        continue

                    # 내부 링크(devfolio.co/hackathons 등) 제외
                    if href in ('https://devfolio.co', 'https://devfolio.co/hackathons'):
                        continue

                    # 제목: <h3> 또는 <h2> 우선 탐색, 없으면 a 텍스트
                    h_tag = a.find(['h3', 'h2', 'h4'])
                    title = h_tag.get_text(strip=True) if h_tag else a.get_text(strip=True)
                    if not title:
                        continue

                    seen.add(href)
                    results.append({
                        "title": title,
                        "url": href,
                        "host": "Devfolio",
                        "date": "상세 확인"
                    })

                time.sleep(1)
            except Exception as e:
                print(f"  Devfolio {page_url} 예외: {e}")

        print(f"📡 Devfolio: {len(results)}개 추출 성공")
        return results

    def fetch_programmers(self):
        """
        [수정] 엔드포인트를 career.programmers.co.kr/competitions 로 변경.
        기존 /api/competitions 는 404 반환.
        HTML 파싱 방식으로 fallback 추가.
        """
        results = []
        today = datetime.now().strftime('%Y-%m-%d')

        # 1차 시도: career API
        try:
            res = requests.get(
                "https://career.programmers.co.kr/api/competitions",
                headers=self.headers, timeout=15
            )
            if res.status_code == 200:
                data = res.json()
                # 응답 구조: {competitions: [...]} 또는 [...] 직접
                items = data if isinstance(data, list) else data.get('competitions', [])
                for c in items:
                    if c.get('statusLabel') == 'ended':
                        continue
                    end_at = c.get('receiptEndAt') or c.get('endAt') or ''
                    if end_at and end_at[:10] < today:
                        continue
                    title = c.get('title', '')
                    href = c.get('href', '') or c.get('url', '')
                    base = 'https://career.programmers.co.kr'
                    full_url = f"{base}{href}" if href.startswith('/') else href
                    results.append({
                        "title": f"🇰🇷 [프로그래머스] {title}",
                        "url": full_url,
                        "host": "Programmers",
                        "date": end_at[:10] if end_at else "상세 확인"
                    })
                if results:
                    return results
        except Exception as e:
            print(f"  Programmers career API 예외: {e}")

        # 2차 시도: HTML 파싱 (career.programmers.co.kr/competitions)
        try:
            res = requests.get(
                "https://career.programmers.co.kr/competitions",
                headers=self.headers, timeout=15
            )
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                # 대회 카드 링크 수집
                for a in soup.find_all('a', href=re.compile(r'/competitions/\d+')):
                    href = a['href']
                    # 이미 마감된 배지 확인
                    card = a.find_parent(['li', 'div', 'article'])
                    if card:
                        status_txt = card.get_text()
                        if '마감' in status_txt and '접수마감' not in status_txt:
                            continue
                    h_tag = a.find(['h3', 'h2', 'h4', 'strong'])
                    title = h_tag.get_text(strip=True) if h_tag else a.get_text(strip=True)
                    if not title:
                        continue
                    full_url = f"https://career.programmers.co.kr{href}" if href.startswith('/') else href
                    results.append({
                        "title": f"🇰🇷 [프로그래머스] {title}",
                        "url": full_url,
                        "host": "Programmers",
                        "date": "상세 확인"
                    })
        except Exception as e:
            print(f"  Programmers HTML 파싱 예외: {e}")

        return results

    def fetch_wevity(self):
        """
        [수정] 403 우회를 위해 더 완전한 브라우저 헤더 세트 사용.
        Accept-Encoding 명시, sec-fetch 헤더 추가, 쿠키 세션 활용 강화.
        카테고리 ID 변경 가능성 대비 '해커톤' 키워드 검색도 추가.
        """
        category_ids = ['20', '21']
        results = []

        try:
            session = requests.Session()
            # 완전한 브라우저 헤더 세트
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0',
            })

            # 메인 페이지 먼저 방문해서 쿠키 수집
            main_res = session.get('https://www.wevity.com/', timeout=15)
            if main_res.status_code != 200:
                print(f"  Wevity 메인 접근 실패: {main_res.status_code}")
                return []

            time.sleep(1.5)

            for cidx in category_ids:
                # Referer를 메인 페이지로 설정
                session.headers.update({
                    'Referer': 'https://www.wevity.com/',
                    'Sec-Fetch-Site': 'same-origin',
                })
                url = f'https://www.wevity.com/?c=find&s=1&gub=1&cidx={cidx}'
                res = session.get(url, timeout=15)

                if res.status_code != 200:
                    print(f"  Wevity 카테고리 {cidx} 접근 실패: {res.status_code}")
                    continue

                soup = BeautifulSoup(res.text, 'html.parser')
                ul = soup.find('ul', class_='list')
                if not ul:
                    # 대안: class 없이 li 목록 탐색
                    ul = soup.find('div', class_=re.compile(r'list|contest'))
                if not ul:
                    print(f"  Wevity 카테고리 {cidx}: 목록 요소를 찾지 못함")
                    continue

                for li in ul.find_all('li'):
                    if 'top' in li.get('class', []):
                        continue
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
                    href = a['href']
                    full_url = "https://www.wevity.com/" + href if href.startswith('?') else href

                    cat_label = "기획" if cidx == '20' else "IT/SW"
                    day_div = li.find('div', class_='day')
                    date_str = day_div.get_text(strip=True) if day_div else "상세 확인"

                    results.append({
                        "title": f"🇰🇷 [위비티-{cat_label}] {title}",
                        "url": full_url,
                        "host": "Wevity",
                        "date": date_str
                    })

                time.sleep(2)

        except Exception as e:
            print(f"Wevity 크롤링 예외: {e}")

        return results

    def fetch_aiconnect(self):
        """
        [수정] Nuxt.js window.__NUXT__ 대신 REST API 엔드포인트 직접 호출.
        aiconnect.kr은 /api/v1/competitions 형태의 내부 API를 사용.
        실패 시 HTML에서 대회 링크를 직접 파싱하는 fallback 추가.
        """
        results = []
        today = datetime.now().strftime('%Y-%m-%d')

        # 1차 시도: 내부 REST API
        api_endpoints = [
            "https://aiconnect.kr/api/v1/competitions",
            "https://aiconnect.kr/api/competitions",
        ]
        api_headers = self.headers.copy()
        api_headers.update({
            "Accept": "application/json",
            "Referer": "https://aiconnect.kr/competition/list",
            "Origin": "https://aiconnect.kr",
            "X-Requested-With": "XMLHttpRequest",
        })

        for endpoint in api_endpoints:
            try:
                res = requests.get(endpoint, headers=api_headers, timeout=15)
                if res.status_code == 200:
                    data = res.json()
                    # 다양한 응답 구조 처리
                    items = (
                        data if isinstance(data, list)
                        else data.get('data', data.get('competitions', data.get('list', [])))
                    )
                    if isinstance(items, list) and items:
                        for c in items:
                            title = c.get('title') or c.get('name', '')
                            cid = c.get('id') or c.get('competitionId', '')
                            end_date = (c.get('endDate') or c.get('end_date') or '')[:10]
                            if end_date and end_date < today:
                                continue
                            if title:
                                results.append({
                                    "title": f"🇰🇷 [AI Connect] {title}",
                                    "url": f"https://aiconnect.kr/competition/detail/{cid}/competitionInfo",
                                    "host": "AIConnect",
                                    "date": end_date or "상세 확인"
                                })
                        if results:
                            return results
            except Exception as e:
                print(f"  AIConnect API {endpoint} 예외: {e}")

        # 2차 시도: HTML 파싱 (대회 카드 링크 수집)
        try:
            html_headers = self.headers.copy()
            html_headers.update({
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9",
            })
            res = requests.get(
                "https://aiconnect.kr/competition/list",
                headers=html_headers, timeout=15
            )
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                # 대회 상세 페이지 링크 패턴: /competition/detail/{id}/...
                seen = set()
                for a in soup.find_all('a', href=re.compile(r'/competition/detail/\d+')):
                    href = a['href']
                    # 중복 제거: 앞부분 경로만 키로 사용
                    key = re.match(r'/competition/detail/\d+', href)
                    if not key or key.group() in seen:
                        continue
                    seen.add(key.group())

                    h_tag = a.find(['h3', 'h2', 'h4', 'p', 'span'])
                    title = h_tag.get_text(strip=True) if h_tag else a.get_text(strip=True)
                    if not title:
                        continue

                    full_url = f"https://aiconnect.kr{href}" if href.startswith('/') else href
                    results.append({
                        "title": f"🇰🇷 [AI Connect] {title}",
                        "url": full_url,
                        "host": "AIConnect",
                        "date": "상세 확인"
                    })
        except Exception as e:
            print(f"  AIConnect HTML 파싱 예외: {e}")

        return results

    def fetch_linkareer(self):
        """
        [수정] GraphQL 쿼리를 실제 동작하는 형식으로 변경.
        기존 쿼리는 스키마 불일치로 빈 결과 반환.
        카테고리 필터와 페이지네이션을 포함한 올바른 쿼리로 교체.
        실패 시 REST API fallback 추가.
        """
        results = []

        # 1차 시도: GraphQL (수정된 쿼리)
        try:
            query = """
            query GetActivities($filter: ActivityFilterInput, $page: Int, $size: Int) {
              activities(filter: $filter, page: $page, size: $size) {
                list {
                  id
                  title
                  categories { name }
                  organization { name }
                  dueDate
                }
              }
            }
            """
            variables = {
                "filter": {"categoryNames": ["해커톤", "공모전"]},
                "page": 1,
                "size": 20
            }
            res = requests.post(
                "https://api.linkareer.com/graphql",
                json={"query": query, "variables": variables},
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": self.headers["User-Agent"],
                    "Referer": "https://linkareer.com/",
                    "Origin": "https://linkareer.com",
                },
                timeout=15
            )
            if res.status_code == 200:
                data = res.json()
                # 다양한 응답 구조 처리
                nodes = (
                    data.get('data', {}).get('activities', {}).get('list')
                    or data.get('data', {}).get('activities', {}).get('nodes', [])
                )
                if nodes:
                    today = datetime.now().strftime('%Y-%m-%d')
                    for node in nodes:
                        title = node.get('title', '')
                        cats = ' '.join(c.get('name', '') for c in (node.get('categories') or []))
                        if any(k in title + cats for k in ['해커톤', 'Hackathon', 'hackathon', '공모전']):
                            nid = node.get('id', '')
                            due = (node.get('dueDate') or '')[:10]
                            if due and due < today:
                                continue
                            results.append({
                                "title": f"🇰🇷 [링커리어] {title}",
                                "url": f"https://linkareer.com/activity/{nid}",
                                "host": "Linkareer",
                                "date": due or "상세 확인"
                            })
                    if results:
                        return results
        except Exception as e:
            print(f"  Linkareer GraphQL 예외: {e}")

        # 2차 시도: 기본 GraphQL 쿼리 (이전 방식 호환)
        try:
            query_basic = """
            {
              activities(first: 30, filter: { categoryName_in: ["해커톤"] }) {
                nodes {
                  id
                  title
                  categories { name }
                  dueDate
                }
              }
            }
            """
            res = requests.post(
                "https://api.linkareer.com/graphql",
                json={"query": query_basic},
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": self.headers["User-Agent"],
                    "Referer": "https://linkareer.com/",
                },
                timeout=15
            )
            if res.status_code == 200:
                today = datetime.now().strftime('%Y-%m-%d')
                nodes = res.json().get('data', {}).get('activities', {}).get('nodes', [])
                for node in nodes:
                    title = node.get('title', '')
                    nid = node.get('id', '')
                    due = (node.get('dueDate') or '')[:10]
                    if due and due < today:
                        continue
                    results.append({
                        "title": f"🇰🇷 [링커리어] {title}",
                        "url": f"https://linkareer.com/activity/{nid}",
                        "host": "Linkareer",
                        "date": due or "상세 확인"
                    })
        except Exception as e:
            print(f"  Linkareer GraphQL 기본 쿼리 예외: {e}")

        # 3차 시도: REST API fallback
        if not results:
            try:
                res = requests.get(
                    "https://api.linkareer.com/v1/activities",
                    params={"category": "해커톤", "status": "open", "limit": 20},
                    headers={
                        "Accept": "application/json",
                        "User-Agent": self.headers["User-Agent"],
                        "Referer": "https://linkareer.com/",
                    },
                    timeout=15
                )
                if res.status_code == 200:
                    today = datetime.now().strftime('%Y-%m-%d')
                    data = res.json()
                    items = data if isinstance(data, list) else data.get('activities', data.get('list', []))
                    for item in items:
                        title = item.get('title', '')
                        nid = item.get('id', '')
                        due = (item.get('dueDate') or item.get('due_date') or '')[:10]
                        if due and due < today:
                            continue
                        results.append({
                            "title": f"🇰🇷 [링커리어] {title}",
                            "url": f"https://linkareer.com/activity/{nid}",
                            "host": "Linkareer",
                            "date": due or "상세 확인"
                        })
            except Exception as e:
                print(f"  Linkareer REST fallback 예외: {e}")

        return results

    # ──────────────────────────────────────────
    # run / discord
    # ──────────────────────────────────────────

    def run(self):
        print("🔍 해커톤 정보 수집을 시작합니다...")
        all_hackathons = []

        tasks = [
            ("Devpost",     self.fetch_devpost),
            ("MLH",         self.fetch_mlh),
            ("Devfolio",    self.fetch_devfolio),
            ("Kaggle",      self.fetch_kaggle),
            ("Hack2Skill",  self.fetch_hack2skill),
            ("DoraHacks",   self.fetch_dorahacks),
            ("Programmers", self.fetch_programmers),
            ("DevEvent",    self.fetch_devevent),
            ("Wevity",      self.fetch_wevity),
            ("CampusPick",  self.fetch_campuspick),
            ("AIConnect",   self.fetch_aiconnect),
            ("Linkareer",   self.fetch_linkareer),
        ]

        for name, fetcher in tasks:
            try:
                found = fetcher()
                print(f"📡 {name}: {len(found)}개 발견")
                all_hackathons.extend(found)
            except Exception as e:
                print(f"❌ {name} 실행 중 치명적 오류: {e}")

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
