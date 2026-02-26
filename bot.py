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
    # 기존 정상 함수 (변경 없음)
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
        [수정 원인] __NEXT_DATA__ JSON 구조 변경으로 open_hackathons 키 소실
        [해결]  HTML에서 *.devfolio.co 서브도메인 <a> 태그 직접 파싱
                실제 HTML 구조 확인:
                  <a href="https://campfire-hackathon.devfolio.co/">
                    <h3>Campfire Hackathon</h3>
                  </a>
        """
        headers = self.headers.copy()
        headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://devfolio.co/",
        })
        results = []
        seen = set()

        try:
            res = requests.get("https://devfolio.co/hackathons", headers=headers, timeout=15)
            if res.status_code != 200:
                print(f"  Devfolio 응답 오류: {res.status_code}")
                return []

            soup = BeautifulSoup(res.text, 'html.parser')

            for a in soup.find_all('a', href=True):
                href = a['href'].rstrip('/')

                # https://<slug>.devfolio.co 형태만 수집
                m = re.match(r'https://([^./]+)\.devfolio\.co$', href)
                if not m:
                    continue
                subdomain = m.group(1)
                if subdomain in ('www', 'assets'):
                    continue
                if href in seen:
                    continue
                seen.add(href)

                # 제목: <h3> 우선
                h_tag = a.find('h3') or a.find('h2') or a.find('h4')
                title = h_tag.get_text(strip=True) if h_tag else a.get_text(strip=True)
                if not title:
                    continue

                results.append({
                    "title": title,
                    "url": href,
                    "host": "Devfolio",
                    "date": "상세 확인"
                })

        except Exception as e:
            print(f"Devfolio 크롤링 예외: {e}")

        return results

    def fetch_programmers(self):
        """
        [수정 원인] programmers.co.kr → career.programmers.co.kr 도메인 이전
                   /api/competitions 엔드포인트가 구 도메인에서 404
        [해결]  1차: career.programmers.co.kr/api/competitions (JSON)
                2차: career.programmers.co.kr/competitions (HTML 파싱)
        """
        today = datetime.now().strftime('%Y-%m-%d')
        results = []

        # 1차: career API JSON
        try:
            res = requests.get(
                "https://career.programmers.co.kr/api/competitions",
                headers=self.headers, timeout=15
            )
            if res.status_code == 200:
                data = res.json()
                items = data if isinstance(data, list) else data.get('competitions', [])
                for c in items:
                    if c.get('statusLabel') == 'ended':
                        continue
                    end_at = c.get('receiptEndAt') or c.get('endAt') or ''
                    if end_at and end_at[:10] < today:
                        continue
                    title = c.get('title', '')
                    href  = c.get('href', '') or c.get('url', '')
                    if not title:
                        continue
                    full_url = (
                        f"https://career.programmers.co.kr{href}"
                        if href.startswith('/') else href
                    )
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

        # 2차: HTML 파싱
        try:
            res = requests.get(
                "https://career.programmers.co.kr/competitions",
                headers=self.headers, timeout=15
            )
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                seen = set()
                for a in soup.find_all('a', href=re.compile(r'/competitions/\d+')):
                    href = a['href']
                    path_key = re.match(r'/competitions/\d+', href)
                    if not path_key or path_key.group() in seen:
                        continue
                    seen.add(path_key.group())

                    parent = a.find_parent(['li', 'article', 'div'])
                    if parent and any(k in parent.get_text() for k in ['접수마감', '종료']):
                        continue

                    h_tag = a.find(['h3', 'h2', 'h4', 'strong', 'p'])
                    title = h_tag.get_text(strip=True) if h_tag else a.get_text(strip=True)
                    if not title:
                        continue

                    results.append({
                        "title": f"🇰🇷 [프로그래머스] {title}",
                        "url": f"https://career.programmers.co.kr{href}",
                        "host": "Programmers",
                        "date": "상세 확인"
                    })
            else:
                print(f"  Programmers HTML 응답 오류: {res.status_code}")
        except Exception as e:
            print(f"  Programmers HTML 파싱 예외: {e}")

        return results

    def fetch_wevity(self):
        """
        [수정 원인] GitHub Actions IP(데이터센터)를 Cloudflare WAF가 구조적으로 403 차단.
                   단순 헤더 강화로는 TLS fingerprint 차이로 인해 우회 불가.
        [해결]  1차: Wevity 강화 헤더로 재시도
                2차: 차단 시 공모전365(contestkorea.com)로 대체 수집
                     - IT/SW 공모전 카테고리 (wevity IT/SW와 동일 데이터 포함)
        """
        results = []

        # 1차: Wevity 강화 헤더
        try:
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0',
                'DNT': '1',
            })
            main_res = session.get('https://www.wevity.com/', timeout=15)
            time.sleep(2)

            if main_res.status_code == 200:
                session.headers.update({
                    'Referer': 'https://www.wevity.com/',
                    'Sec-Fetch-Site': 'same-origin',
                })
                for cidx, cat_label in [('20', '기획'), ('21', 'IT/SW')]:
                    url = f'https://www.wevity.com/?c=find&s=1&gub=1&cidx={cidx}'
                    res = session.get(url, timeout=15)
                    if res.status_code != 200:
                        print(f"  Wevity {cat_label} HTTP {res.status_code}")
                        continue
                    soup = BeautifulSoup(res.text, 'html.parser')
                    ul = soup.find('ul', class_='list')
                    if not ul:
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
                        a_tag = tit_div.find('a', href=True)
                        if not a_tag:
                            continue
                        title = a_tag.get_text(strip=True)
                        href = a_tag['href']
                        full_url = "https://www.wevity.com/" + href if href.startswith('?') else href
                        day_div = li.find('div', class_='day')
                        results.append({
                            "title": f"🇰🇷 [위비티-{cat_label}] {title}",
                            "url": full_url,
                            "host": "Wevity",
                            "date": day_div.get_text(strip=True) if day_div else "상세 확인"
                        })
                    time.sleep(1.5)

                if results:
                    return results

        except Exception as e:
            print(f"  Wevity 직접 접근 예외: {e}")

        # 2차: 공모전365 대체 (IT/SW, 게임/소프트웨어 카테고리)
        print("  Wevity 차단 → 공모전365 대체 수집")
        try:
            contest_headers = self.headers.copy()
            contest_headers.update({
                'Referer': 'https://www.contestkorea.com/',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'ko-KR,ko;q=0.9',
            })
            res = requests.get(
                "https://www.contestkorea.com/sub/list.php",
                params={"Txt_bcode": "030504001", "Txt_sele": "ing"},
                headers=contest_headers, timeout=15
            )
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                seen = set()
                for a in soup.find_all('a', href=re.compile(r'int_No=\d+')):
                    href = a['href']
                    m = re.search(r'int_No=(\d+)', href)
                    if not m or m.group(1) in seen:
                        continue
                    seen.add(m.group(1))
                    title = a.get_text(strip=True)
                    if not title or len(title) < 4:
                        continue
                    full_url = (
                        f"https://www.contestkorea.com{href}"
                        if href.startswith('/') else href
                    )
                    results.append({
                        "title": f"🇰🇷 [공모전365] {title}",
                        "url": full_url,
                        "host": "ContestKorea",
                        "date": "상세 확인"
                    })
        except Exception as e:
            print(f"  공모전365 대체 수집 예외: {e}")

        return results

    def fetch_aiconnect(self):
        """
        [수정 원인] aiconnect.kr은 완전한 CSR(클라이언트 사이드 렌더링).
                   서버에서 반환하는 HTML에는 데이터가 없으므로 HTML 파싱 불가.
                   window.__NUXT__ 또한 데이터가 없는 빈 상태.
        [해결]  내부 REST API 패턴 순차 시도 (브라우저 Network 탭 기준 추정)
                실패 시 AI Hub(aihub.or.kr) 챌린지 목록으로 대체
        """
        results = []
        today = datetime.now().strftime('%Y-%m-%d')

        api_headers = self.headers.copy()
        api_headers.update({
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://aiconnect.kr/competition/list",
            "Origin": "https://aiconnect.kr",
        })

        # aiconnect.kr 내부 API 후보 (URL 패턴 /main/competition/detail/{id} 에서 역추론)
        api_candidates = [
            ("GET",  "https://aiconnect.kr/api/v2/competition/list",    {"status": "open"}),
            ("GET",  "https://aiconnect.kr/api/v1/competition/list",    {"page": 1, "limit": 20}),
            ("GET",  "https://aiconnect.kr/api/competitions",            {"status": "open"}),
            ("GET",  "https://aiconnect.kr/main/api/competition/list",  {"page": 1}),
            ("POST", "https://aiconnect.kr/api/competition/list",        {}),
        ]

        for method, url, params in api_candidates:
            try:
                if method == "GET":
                    res = requests.get(url, params=params, headers=api_headers, timeout=10)
                else:
                    res = requests.post(url, json=params, headers=api_headers, timeout=10)

                if res.status_code != 200:
                    continue

                data = res.json()
                items = (
                    data if isinstance(data, list)
                    else data.get('data', data.get('competitions',
                         data.get('list', data.get('result', []))))
                )
                if not isinstance(items, list) or not items:
                    continue

                for c in items:
                    title = c.get('title') or c.get('name', '')
                    cid   = c.get('id') or c.get('competitionId') or c.get('seq', '')
                    end_d = (c.get('endDate') or c.get('end_date') or '')[:10]
                    if end_d and end_d < today:
                        continue
                    if title:
                        results.append({
                            "title": f"🇰🇷 [AI Connect] {title}",
                            "url": f"https://aiconnect.kr/main/competition/detail/{cid}/competitionInfo",
                            "host": "AIConnect",
                            "date": end_d or "상세 확인"
                        })
                if results:
                    print(f"  AIConnect API 성공: {url}")
                    return results

            except Exception:
                continue

        # 대체: AI Hub 챌린지 목록
        print("  AIConnect API 모두 실패 → AI Hub 대체 수집")
        try:
            aihub_headers = self.headers.copy()
            aihub_headers.update({
                "Accept": "application/json",
                "Referer": "https://aihub.or.kr/",
            })
            # AI Hub 공개 챌린지 API
            res = requests.get(
                "https://aihub.or.kr/api/v1/board/challenge/list",
                params={"pageIndex": 1, "pageSize": 20, "searchStatus": "ING"},
                headers=aihub_headers, timeout=15
            )
            if res.status_code == 200:
                data = res.json()
                items = data.get('data', data.get('list', []))
                for c in (items if isinstance(items, list) else []):
                    title = c.get('title') or c.get('challengeTitle', '')
                    cid   = c.get('challengeId') or c.get('id', '')
                    end_d = (c.get('endDate') or '')[:10]
                    if not title:
                        continue
                    results.append({
                        "title": f"🇰🇷 [AI Hub] {title}",
                        "url": f"https://aihub.or.kr/challenge/detail?challengeId={cid}",
                        "host": "AIHub",
                        "date": end_d or "상세 확인"
                    })
        except Exception as e:
            print(f"  AI Hub 대체 수집 예외: {e}")

        return results

    def fetch_linkareer(self):
        """
        [수정 원인] GraphQL 스키마 불일치.
                   - 기존 쿼리 { activities { nodes { id title ... } } } 는
                     실제 스키마와 달라 errors 또는 빈 nodes 반환.
                   - 해커톤 필터 없이 전체 조회 시 해당 카테고리 항목이 포함 안 됨.
        [해결]  여러 GraphQL 쿼리 패턴을 순차 시도 (errors 있으면 다음으로).
                전체 조회 후 클라이언트 필터링으로 최후 fallback.
                모두 실패 시 REST /v1/activities 시도.
        """
        results = []
        today = datetime.now().strftime('%Y-%m-%d')

        gql_headers = {
            "Content-Type": "application/json",
            "User-Agent": self.headers["User-Agent"],
            "Referer": "https://linkareer.com/",
            "Origin": "https://linkareer.com",
        }

        # 스키마 불확실성 대비 여러 쿼리 패턴 순차 시도
        queries = [
            # 패턴 A: categoryName_contains 필터
            {"query": """
                query {
                  activityList(
                    filter: { categoryName_contains: "해커톤" }
                    pagination: { page: 1, pageSize: 20 }
                  ) {
                    activities { id title dueDate categories { name } }
                  }
                }
            """},
            # 패턴 B: relay-style + type 필터
            {"query": """
                query {
                  activities(first: 20, filter: { type: HACKATHON }) {
                    nodes { id title dueDate }
                  }
                }
            """},
            # 패턴 C: keyword 파라미터
            {"query": """
                query {
                  activities(first: 20, keyword: "해커톤") {
                    nodes { id title dueDate }
                  }
                }
            """},
            # 패턴 D: 전체 조회 후 클라이언트 필터 (최후 수단)
            {"query": """
                {
                  activities(first: 50) {
                    nodes { id title dueDate categories { name } }
                  }
                }
            """},
        ]

        for payload in queries:
            try:
                res = requests.post(
                    "https://api.linkareer.com/graphql",
                    json=payload,
                    headers=gql_headers,
                    timeout=15
                )
                if res.status_code != 200:
                    continue

                body = res.json()
                if body.get('errors'):
                    continue  # 스키마 불일치 → 다음 패턴

                data = body.get('data', {})
                nodes = []
                for key in data:
                    val = data[key]
                    if isinstance(val, dict):
                        nodes = val.get('nodes', val.get('activities', []))
                    elif isinstance(val, list):
                        nodes = val
                    if nodes:
                        break

                if not nodes:
                    continue

                for node in nodes:
                    title = node.get('title', '')
                    cats  = ' '.join(c.get('name', '') for c in (node.get('categories') or []))
                    if not any(k in title + cats for k in ['해커톤', 'Hackathon', 'hackathon', '공모전']):
                        continue
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
                print(f"  Linkareer GraphQL 패턴 예외: {e}")

        # 2차: REST API
        try:
            for endpoint in [
                "https://api.linkareer.com/v1/activities",
                "https://linkareer.com/api/v1/activities",
            ]:
                res = requests.get(
                    endpoint,
                    params={"category": "해커톤", "status": "open", "limit": 20},
                    headers={"Accept": "application/json", "User-Agent": self.headers["User-Agent"]},
                    timeout=15
                )
                if res.status_code == 200:
                    data = res.json()
                    items = data if isinstance(data, list) else data.get('activities', data.get('list', []))
                    for item in (items if isinstance(items, list) else []):
                        title = item.get('title', '')
                        nid   = item.get('id', '')
                        due   = (item.get('dueDate') or item.get('due_date') or '')[:10]
                        if due and due < today:
                            continue
                        if title:
                            results.append({
                                "title": f"🇰🇷 [링커리어] {title}",
                                "url": f"https://linkareer.com/activity/{nid}",
                                "host": "Linkareer",
                                "date": due or "상세 확인"
                            })
                    if results:
                        return results
        except Exception as e:
            print(f"  Linkareer REST 예외: {e}")

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
