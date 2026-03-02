import os
import json
import requests
import re
from datetime import datetime
from bs4 import BeautifulSoup

WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')
DB_FILE = "sent_hackathons.txt"

LINKAREER_GRAPHQL_URL = "https://api.linkareer.com/graphql"

LINKAREER_QUERY = """
query FetchActivities($filterBy: ActivityFilter, $page: Int!, $pageSize: Int!) {
  activities(
    filterBy: $filterBy
    pagination: { page: $page, pageSize: $pageSize }
    orderBy: { field: CREATED_AT, direction: DESC }
  ) {
    totalCount
    nodes {
      id
      title
      organizationName
      recruitCloseAt
    }
  }
}
"""

class HackathonBot:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        self.linkareer_headers = {
            **self.headers,
            "Content-Type": "application/json",
            "Origin": "https://linkareer.com",
            "Referer": "https://linkareer.com/",
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

    # ─────────────────────────────────────────────────────
    # 수집 함수 섹션
    # ─────────────────────────────────────────────────────

    def fetch_devpost(self):
        try:
            h = self.headers.copy()
            h.update({"Accept": "application/json", "Referer": "https://devpost.com/hackathons", "X-Requested-With": "XMLHttpRequest"})
            res = requests.get("https://devpost.com/api/hackathons", params={"status[]": "upcoming", "sort_by": "Recently Added"}, headers=h, timeout=15)
            if res.status_code == 200:
                return [{"title": h['title'], "url": h['url'], "host": "Devpost", "date": h.get('submission_period_dates', 'N/A')}
                        for h in res.json().get('hackathons', [])]
        except:
            pass
        return []

    def fetch_mlh(self):
        MONTHS = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
        try:
            res = requests.get("https://mlh.io/seasons/2026/events", headers=self.headers, timeout=15)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                results, today, seen = [], datetime.now().replace(hour=0,minute=0,second=0,microsecond=0), set()
                for a in soup.find_all('a', href=True):
                    h3 = a.find('h3')
                    if not h3: continue
                    title = h3.get_text(strip=True)
                    if not title or title in seen: continue
                    seen.add(title)
                    link = a['href'].split('?')[0]
                    if not link.startswith('http'): link = "https://mlh.io" + link
                    a_text = a.get_text(separator=' ', strip=True).replace(title, '')
                    date_parts = re.findall(r'([A-Z]{3})\s+(\d{1,2})', a_text)
                    if date_parts:
                        date_str = ' - '.join(f"{m} {d}" for m,d in date_parts) if len(date_parts)>1 else f"{date_parts[0][0]} {date_parts[0][1]}"
                        mon, day = date_parts[-1]
                        end_m = MONTHS.get(mon, 0)
                        if end_m and datetime(today.year, end_m, int(day)) < today: continue
                    else:
                        date_str = "2026 Season"
                    results.append({"title": title, "url": link, "host": "MLH", "date": date_str})
                return results
        except Exception as e:
            print(f"MLH 예외: {e}")
        return []

    def _fetch_linkareer(self, filter_by, label):
        """링커리어 GraphQL API로 활동 목록을 가져옵니다."""
        results = []
        page = 1
        page_size = 20
        try:
            while True:
                payload = {
                    "query": LINKAREER_QUERY,
                    "variables": {
                        "filterBy": filter_by,
                        "page": page,
                        "pageSize": page_size,
                    },
                }
                res = requests.post(
                    LINKAREER_GRAPHQL_URL,
                    json=payload,
                    headers=self.linkareer_headers,
                    timeout=15,
                )
                res.raise_for_status()
                data = res.json()
                nodes = data["data"]["activities"]["nodes"]
                total = data["data"]["activities"]["totalCount"]

                for a in nodes:
                    close_date = "미정"
                    if a.get("recruitCloseAt"):
                        close_ts = int(a["recruitCloseAt"]) / 1000
                        close_date = datetime.fromtimestamp(close_ts).strftime("%Y-%m-%d")
                    results.append({
                        "title": a["title"],
                        "url": f"https://linkareer.com/activity/{a['id']}",
                        "host": f"링커리어 | {a.get('organizationName', '-')}",
                        "date": f"마감: {close_date}",
                    })

                if page * page_size >= total:
                    break
                page += 1

        except Exception as e:
            print(f"링커리어 {label} 수집 실패: {e}")

        return results

    def fetch_linkareer_hackathon(self):
        """링커리어에서 해커톤 공고를 가져옵니다."""
        return self._fetch_linkareer(
            filter_by={"q": "해커톤", "status": "OPEN"},
            label="해커톤",
        )

    def fetch_linkareer_bootcamp(self):
        """링커리어에서 부트캠프 공고를 가져옵니다 (교육 타입, activityTypeID=6)."""
        return self._fetch_linkareer(
            filter_by={"activityTypeID": 6, "status": "OPEN"},
            label="부트캠프",
        )

    def fetch_campuspick(self):
        try:
            h = self.headers.copy()
            h.update({"Content-Type": "application/x-www-form-urlencoded", "Origin": "https://www2.campuspick.com", "Referer": "https://www2.campuspick.com/"})
            today, results = datetime.now().strftime('%Y-%m-%d'), []
            for cat_id in [108, 111]: # 108: 공모전, 111: 교육/강연
                res = requests.post("https://api2.campuspick.com/find/activity/list", data={"target":1,"limit":20,"offset":0,"categoryId":cat_id}, headers=h, timeout=15)
                if res.status_code == 200:
                    activities = res.json().get("result", {}).get("activities", [])
                    for a in activities:
                        if a.get("endDate","") >= today:
                            prefix = "🎓 [부트캠프/교육]" if cat_id == 111 else "🇰🇷 [캠퍼스픽]"
                            results.append({"title": f"{prefix} {a['title']}", "url": f"https://www2.campuspick.com/contest/view?id={a['id']}", "host": "CampusPick", "date": a.get("endDate","상세 확인")})
            return results
        except Exception as e:
            print(f"CampusPick 예외: {e}")
        return []

    def fetch_devevent(self):
        try:
            # README.md에 현재 진행 중/예정 행사 목록이 있음 (end_event/는 종료된 행사)
            res = requests.get(
                "https://raw.githubusercontent.com/brave-people/Dev-Event/master/README.md",
                headers=self.headers, timeout=15
            )
            if res.status_code == 200:
                results, seen = [], set()
                keywords = ['해커톤', 'hackathon', '공모전', '경진대회', '부트캠프', 'bootcamp', '교육', 'kdt', '양성']
                for m in re.finditer(r'__\[([^\]]+)\]\((https?://[^\)]+)\)__', res.text):
                    title, link = m.group(1), m.group(2)
                    if link in seen:
                        continue
                    if any(k in title.lower() for k in keywords):
                        seen.add(link)
                        icon = "🎓" if any(b in title.lower() for b in ['부트캠프', '교육', 'kdt']) else "🇰🇷"
                        results.append({"title": f"{icon} [데브이벤트] {title}", "url": link, "host": "DevEvent", "date": "상세 확인"})
                return results
        except Exception as e:
            print(f"DevEvent 수집 실패: {e}")
        return []

    def fetch_ssafy(self):
        """SSAFY 공지사항 게시판에서 모집 공고를 가져옵니다."""
        try:
            url = "https://www.ssafy.com/ksp/servlet/swp.board.controller.SwpBoardServlet"
            params = {"p_process": "select-board-list", "p_tabseq": "226504", "p_pageno": "1"}
            h = self.headers.copy()
            h.update({
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "ko-KR,ko;q=0.9",
            })
            res = requests.get(url, params=params, headers=h, timeout=15)
            if res.status_code != 200:
                print(f"SSAFY 응답 오류: {res.status_code}")
                return []
            soup = BeautifulSoup(res.text, 'html.parser')
            # 실제 구조: <li class="_top"> 안에 <span class="td td1"><a>, <span class="td td2">
            results = []
            for li in soup.select('li._top'):
                td1 = li.select_one('span.td1')
                if not td1:
                    continue
                a = td1.find('a')
                if not a:
                    continue
                # <i class="ico_noti"> 태그([공지] 텍스트) 제거 후 제목 추출
                for ico in a.find_all('i'):
                    ico.decompose()
                title = a.get_text(strip=True)
                if not any(k in title for k in ['모집', '공고', '기수']):
                    continue
                seq_match = re.search(r'goViewPage\((\d+)\)', a.get('href', ''))
                if not seq_match:
                    continue
                seq = seq_match.group(1)
                detail_url = (
                    f"https://www.ssafy.com/ksp/servlet/swp.board.controller.SwpBoardServlet"
                    f"?p_process=select-board-view&p_tabseq=226504&p_seq={seq}"
                )
                date_span = li.select_one('span.td2')
                date = date_span.get_text(strip=True) if date_span else '미정'
                results.append({
                    "title": f"[SSAFY] {title}",
                    "url": detail_url,
                    "host": "SSAFY (삼성 청년 SW 아카데미)",
                    "date": date,
                })
            return results
        except Exception as e:
            print(f"SSAFY 수집 실패: {e}")
        return []

    def fetch_woowacourse(self):
        """우아한테크코스 공지사항에서 모집 공고를 가져옵니다."""
        try:
            res = requests.get("https://woowacourse.io/notice", headers=self.headers, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
            script = soup.find('script', id='__NEXT_DATA__')
            keywords = ['모집', '지원', '과정', '기수', '선발']
            if script:
                data = json.loads(script.string)
                blocks = (
                    data.get('props', {})
                    .get('pageProps', {})
                    .get('recordMap', {})
                    .get('block', {})
                )
                results = []
                for block_id, block_data in blocks.items():
                    value = block_data.get('value', {})
                    if value.get('type') != 'page':
                        continue
                    props = value.get('properties', {})
                    title_arr = props.get('title', [])
                    if not title_arr:
                        continue
                    title = title_arr[0][0] if title_arr else ''
                    if not title or not any(k in title for k in keywords):
                        continue
                    date = '미정'
                    for key, val in props.items():
                        if key == 'title' or not val:
                            continue
                        try:
                            candidate = val[0][0]
                            if isinstance(candidate, str) and re.match(r'\d{4}', candidate):
                                date = candidate[:10]
                                break
                        except (IndexError, TypeError):
                            pass
                    results.append({
                        "title": f"[우테코] {title}",
                        "url": f"https://woowacourse.io/notice/{block_id}",
                        "host": "우아한테크코스",
                        "date": date,
                    })
                if results:
                    return results

            # fallback: 페이지 내 링크 직접 추출
            results = []
            seen = set()
            for a in soup.find_all('a', href=True):
                title = a.get_text(strip=True)
                href = a['href']
                if not title or not any(k in title for k in keywords):
                    continue
                if href in seen:
                    continue
                seen.add(href)
                if not href.startswith('http'):
                    href = 'https://woowacourse.io' + href
                results.append({
                    "title": f"[우테코] {title}",
                    "url": href,
                    "host": "우아한테크코스",
                    "date": "상세 확인",
                })
            return results
        except Exception as e:
            print(f"우아한테크코스 수집 실패: {e}")
        return []

    def fetch_boostcamp(self):
        """네이버 부스트캠프 모집 공고를 가져옵니다."""
        results = []
        pages = [
            ("https://boostcamp.connect.or.kr/guide_ai.html", "AI Tech"),
            ("https://boostcamp.connect.or.kr/main_wm.html", "Web·Mobile"),
        ]
        for url, course in pages:
            try:
                res = requests.get(url, headers=self.headers, timeout=15)
                if res.status_code != 200:
                    continue
                soup = BeautifulSoup(res.text, 'html.parser')
                text = soup.get_text(separator=' ', strip=True)
                # 모집 중 여부 확인
                recruiting_keywords = ['모집 중', '지원 기간', '모집 기간', '접수 기간', '모집합니다', '지원하기', '원서접수']
                if not any(k in text for k in recruiting_keywords):
                    continue
                # 기수 추출
                cohort_match = re.search(r'(\d+)기', text)
                cohort = f" {cohort_match.group(1)}기" if cohort_match else ""
                # 날짜 추출
                date_match = re.search(r'(\d{4}[년.\-]\s*\d{1,2}[월.\-]\s*\d{1,2}[일]?)', text)
                date = date_match.group(1).strip() if date_match else '상세 확인'
                results.append({
                    "title": f"[부스트캠프] {course}{cohort} 모집",
                    "url": url,
                    "host": "네이버 부스트캠프",
                    "date": date,
                })
            except Exception as e:
                print(f"부스트캠프 {course} 수집 실패: {e}")
        return results

    def fetch_kt_techup(self):
        """KT Cloud TECH UP K-디지털 트레이닝 부트캠프 모집 정보를 가져옵니다."""
        try:
            res = requests.get("https://ktcloud-techup.com/", headers=self.headers, timeout=15)
            res.encoding = 'utf-8'
            if res.status_code != 200:
                return []
            soup = BeautifulSoup(res.text, 'html.parser')
            now = datetime.now()
            # JSON-LD FAQPage에서 교육 일정 추출
            start_date = end_date = None
            for script in soup.find_all('script', type='application/ld+json'):
                try:
                    data = json.loads(script.string)
                    if data.get('@type') != 'FAQPage':
                        continue
                    for qa in data.get('mainEntity', []):
                        answer = qa.get('acceptedAnswer', {}).get('text', '')
                        dates = re.findall(r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일', answer)
                        if len(dates) >= 2:
                            start_date = datetime(int(dates[0][0]), int(dates[0][1]), int(dates[0][2]))
                            end_date = datetime(int(dates[1][0]), int(dates[1][1]), int(dates[1][2]))
                            break
                except Exception:
                    pass
                if start_date:
                    break
            # 교육 종료일이 지난 경우 건너뜀
            if end_date and end_date < now:
                return []
            date_str = (f"{start_date.strftime('%Y.%m.%d')} ~ {end_date.strftime('%Y.%m.%d')}"
                        if start_date and end_date else "상세 확인")
            return [{
                "title": "[KT Cloud TECH UP] 부트캠프 9개 트랙 모집 (K-디지털 트레이닝)",
                "url": "https://ktcloud-techup.com/",
                "host": "kt cloud TECH UP",
                "date": date_str,
            }]
        except Exception as e:
            print(f"KT Cloud TechUp 수집 실패: {e}")
        return []

    def fetch_boottent(self):
        """부트텐트에서 Data/AI 카테고리 부트캠프 공고를 가져옵니다.
        서버는 전체 캠프를 반환하므로 categories 필드로 클라이언트 필터링합니다.
        """
        try:
            res = requests.get(
                "https://boottent.com/camps",
                headers=self.headers,
                timeout=15,
            )
            if res.status_code != 200:
                print(f"부트텐트: HTTP {res.status_code}")
                return []

            # Next.js RSC 스트림에서 campList 추출: self.__next_f.push([1, "...json..."]) 패턴
            pushes = re.findall(r'self\.__next_f\.push\((\[.*?\])\)', res.text, re.DOTALL)
            all_camps = []
            for p in pushes:
                if '\\"campList\\"' not in p:
                    continue
                try:
                    inner = json.loads(p)[1]  # 이중 이스케이프 해제
                    arr_str = self._extract_json_array(inner, 'campList')
                    if arr_str:
                        all_camps = json.loads(arr_str)
                except Exception:
                    pass
                break

            if not all_camps:
                print("부트텐트: campList 데이터 없음")
                return []

            today = datetime.now().strftime('%Y-%m-%d')
            target_cats = {'data', 'ai'}
            results = []
            for camp in all_camps:
                if not set(camp.get('categories', [])) & target_cats:
                    continue
                camp_id = camp.get('campId', '')
                batch_id = camp.get('batchId', '')
                title = camp.get('title', '').strip()
                end_date = camp.get('endDate', '')
                start_date = camp.get('startDate', '')
                if not title or not camp_id:
                    continue
                if end_date and end_date < today:
                    continue
                url = (f"https://boottent.com/camps/{camp_id}_{batch_id}"
                       if batch_id else f"https://boottent.com/camps/{camp_id}")
                date_str = (f"{start_date} ~ {end_date}" if start_date and end_date
                            else end_date or start_date or "상세 확인")
                results.append({
                    "title": f"[부트텐트] {title}",
                    "url": url,
                    "host": "부트텐트 (boottent.com)",
                    "date": f"마감: {date_str}",
                })
            return results
        except Exception as e:
            print(f"부트텐트 수집 실패: {e}")
        return []

    def _extract_json_array(self, s, key):
        """문자열 s에서 key에 해당하는 JSON 배열을 괄호 매칭으로 추출합니다."""
        pattern = f'"{key}":'
        idx = s.find(pattern)
        if idx == -1:
            return None
        start = s.index('[', idx + len(pattern))
        depth, in_string, escape = 1, False, False
        backslash = chr(92)
        for i in range(start + 1, len(s)):
            c = s[i]
            if escape:
                escape = False
                continue
            if c == backslash and in_string:
                escape = True
                continue
            if c == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == '[':
                depth += 1
            elif c == ']':
                depth -= 1
                if depth == 0:
                    return s[start:i + 1]
        return None

    def fetch_kt_aivle(self):
        """KT 에이블스쿨 주요소식 페이지에서 모집 공고를 가져옵니다."""
        try:
            # 공지 JSON API가 막혀 있어 주요소식(MC00000058) HTML 페이지를 파싱
            # GitHub Actions(AWS IP)에서 403이 발생할 수 있음 - 브라우저 헤더로 우회 시도
            h = self.headers.copy()
            h.update({
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": "https://aivle.kt.co.kr/",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            })
            res = requests.get(
                "https://aivle.kt.co.kr/home/main/goMenuPage?mcd=MC00000058",
                headers=h, timeout=15
            )
            if res.status_code == 403:
                print("KT 에이블스쿨: 서버에서 접근 차단됨 (IP 제한 추정), 건너뜁니다.")
                return []
            res.raise_for_status()
            soup = BeautifulSoup(res.text, 'html.parser')
            results = []
            keywords = ['모집', '공고', '기수', '과정', '선발']
            for subj_div in soup.select('div.td.subject'):
                a = subj_div.find('a')
                if not a:
                    continue
                title = a.get_text(strip=True)
                if not any(k in title for k in keywords):
                    continue
                seq_match = re.search(r"readPtlBbsAtcl\('(\d+)'\)", a.get('href', ''))
                seq = seq_match.group(1) if seq_match else ''
                # 날짜: 같은 행(부모)의 형제 div에서 추출
                row = subj_div.parent
                date_div = row.select_one('div.td.date') if row else None
                date = date_div.get_text(strip=True) if date_div else '상세 확인'
                detail_url = (
                    f"https://aivle.kt.co.kr/home/brd/bbs/view?bbsCd=NEWS&atclSn={seq}"
                    if seq else "https://aivle.kt.co.kr/home/main/goMenuPage?mcd=MC00000058"
                )
                results.append({
                    "title": f"[KT 에이블스쿨] {title}",
                    "url": detail_url,
                    "host": "KT 에이블스쿨 (AIVLE School)",
                    "date": date,
                })
            return results
        except Exception as e:
            print(f"KT 에이블스쿨 수집 실패: {e}")
        return []

    # ─────────────────────────────────────────────────────
    # 유틸리티 및 실행 섹션
    # ─────────────────────────────────────────────────────

    def send_to_discord(self, items):
        for i in range(0, len(items), 10):
            chunk = items[i:i+10]
            embeds = [{"title": f"✨ {h['title']}", "url": h['url'], "color": 5814783,
                    "fields": [{"name": "플랫폼", "value": h['host'], "inline": True},
                                {"name": "마감/일정", "value": str(h['date']), "inline": True}]}
                    for h in chunk]
            requests.post(WEBHOOK_URL, json={
                "content": "🚀 **새로운 소식이 도착했습니다!**" if i == 0 else "",
                "embeds": embeds
            })

    def run(self):
        print("🔍 해커톤 및 부트캠프 정보 수집을 시작합니다...")
        all_items = []
        tasks = [
            ("Devpost", self.fetch_devpost),
            ("MLH", self.fetch_mlh),
            ("DevEvent", self.fetch_devevent),
            ("CampusPick", self.fetch_campuspick),
            ("링커리어 해커톤", self.fetch_linkareer_hackathon),
            ("링커리어 부트캠프", self.fetch_linkareer_bootcamp),
            ("SSAFY", self.fetch_ssafy),
            ("우아한테크코스", self.fetch_woowacourse),
            ("부스트캠프", self.fetch_boostcamp),
            ("KT Cloud TechUp", self.fetch_kt_techup),
            ("KT 에이블스쿨", self.fetch_kt_aivle),
            ("부트텐트", self.fetch_boottent),
        ]

        for name, fetcher in tasks:
            try:
                found = fetcher()
                print(f"📡 {name}: {len(found)}개 발견")
                all_items.extend(found)
            except Exception as e:
                print(f"❌ {name} 오류: {e}")

        # 중복 제거 (제목 기준) 및 신규 항목 필터링
        seen_titles, deduped = set(), []
        for item in all_items:
            if item['title'] not in seen_titles:
                seen_titles.add(item['title'])
                deduped.append(item)

        new_items = [i for i in deduped if i['title'] not in self.sent_list]
        print(f"📊 최종 신규 공고: {len(new_items)}개")

        if new_items:
            self.send_to_discord(new_items)
            self.save_sent_list(new_items)

if __name__ == "__main__":
    if WEBHOOK_URL:
        HackathonBot().run()
    else:
        print("❌ DISCORD_WEBHOOK_URL 환경 변수가 없습니다.")
