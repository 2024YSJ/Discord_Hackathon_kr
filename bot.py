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
            now = datetime.now()
            url = f"https://raw.githubusercontent.com/brave-people/Dev-Event/master/end_event/{now.year}/{str(now.year)[2:]}_{str(now.month).zfill(2)}.md"
            res = requests.get(url, timeout=15)
            if res.status_code == 200:
                results = []
                for m in re.finditer(r'__\[([^\]]+)\]\((https?://[^\)]+)\)__', res.text):
                    title, link = m.group(1), m.group(2)
                    target_keywords = ['해커톤', 'hackathon', '공모전', '경진대회', '부트캠프', 'bootcamp', '교육', 'kdt', '양성']
                    if any(k in title.lower() for k in target_keywords):
                        icon = "🎓" if any(b in title.lower() for b in ['부트캠프', '교육', 'kdt']) else "🇰🇷"
                        results.append({"title": f"{icon} [데브이벤트] {title}", "url": link, "host": "DevEvent", "date": "상세 확인"})
                return results
        except:
            pass
        return []

    def fetch_ssafy(self):
        """SSAFY 공지사항 게시판에서 모집 공고를 가져옵니다."""
        try:
            url = "https://www.ssafy.com/ksp/servlet/swp.board.controller.SwpBoardServlet"
            params = {"p_process": "select-board-list", "p_tabseq": "226504", "p_pageno": "1"}
            res = requests.get(url, params=params, headers=self.headers, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
            results = []
            for row in soup.select('table.tbl-list tbody tr'):
                subj_td = row.select_one('td.subj')
                if not subj_td:
                    continue
                title = subj_td.get_text(strip=True)
                if not any(k in title for k in ['모집', '공고', '기수']):
                    continue
                seq_match = re.search(r'goViewPage\((\d+)\)', str(row))
                if not seq_match:
                    continue
                seq = seq_match.group(1)
                detail_url = (
                    f"https://www.ssafy.com/ksp/servlet/swp.board.controller.SwpBoardServlet"
                    f"?p_process=select-board-view&p_tabseq=226504&p_seq={seq}"
                )
                tds = row.find_all('td')
                date = tds[-1].get_text(strip=True) if len(tds) >= 2 else '미정'
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
            if not script:
                return []
            blocks = (
                json.loads(script.string)
                .get('props', {})
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
                if not title or not any(k in title for k in ['모집', '지원', '과정', '기수', '선발']):
                    continue
                # 날짜: Notion 속성 키가 동적이므로 YYYY로 시작하는 문자열 값 탐색
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

    def fetch_kt_aivle(self):
        """KT 에이블스쿨 공지사항에서 모집 공고를 가져옵니다."""
        try:
            url = "https://aivle.kt.co.kr/home/brd/bbs/listAtclJson"
            params = {"bbsCd": "NOTICE", "pageIndex": "1"}
            res = requests.get(url, params=params, headers=self.headers, timeout=15)
            res.raise_for_status()
            results = []
            for item in res.json().get("returnList", []):
                title = item.get("atclTitle", "")
                if not any(k in title for k in ['모집', '공고', '기수', '과정', '선발']):
                    continue
                seq = item.get("atclSn", "")
                detail_url = (
                    f"https://aivle.kt.co.kr/home/brd/bbs/view?bbsCd=NOTICE&atclSn={seq}"
                    if seq else "https://aivle.kt.co.kr/home/main/goMenuPage?mcd=MC00000061"
                )
                date = item.get("regDttm", "미정")
                if date and len(date) > 10:
                    date = date[:10]
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
            ("KT 에이블스쿨", self.fetch_kt_aivle),
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
