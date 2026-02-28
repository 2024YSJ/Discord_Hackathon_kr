import os
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
