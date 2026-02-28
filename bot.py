import os
import requests
import json
from datetime import datetime
from bs4 import BeautifulSoup
import time
import re

WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')
DB_FILE = "sent_hackathons.txt"

class HackathonBot:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
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
        except: pass
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

    def fetch_linkareer(self):
        """
        링커리어 400 오류 해결 버전:
        1. Variables 타입 오류를 방지하기 위해 쿼리문에 인자를 직접 주입
        2. 필터 구조를 단순화하여 서버 거부 반응 최소화
        3. 부트캠프와 해커톤 키워드를 순차적으로 조회
        """
        results = []
        today = datetime.now().strftime('%Y-%m-%d')
        seen_ids = set()

        gql_headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Origin": "https://linkareer.com",
            "Referer": "https://linkareer.com/",
        }

        for keyword in ["부트캠프", "해커톤"]:
            # 400 오류를 피하기 위해 variables 대신 쿼리 내부에 직접 값을 넣는 전략
            raw_query = f"""
            query {{
              unifiedSearch(keyword: "{keyword}", page: 1, filter: {{type: ACTIVITY}}) {{
                activities {{
                  nodes {{
                    id
                    title
                    dueDate
                    hostName
                    categories {{
                      name
                    }}
                  }
                }
              }
            }}
            """
            
            payload = {{"query": raw_query}}
            """

            try:
                time.sleep(1.0)
                res = requests.post("https://api.linkareer.com/graphql", json=payload, headers=gql_headers, timeout=15)
                
                if res.status_code != 200:
                    # 400 오류 발생 시 상세 내용 확인을 위해 로그 출력
                    print(f"  Linkareer {keyword} 응답 실패 ({res.status_code}): {res.text[:100]}")
                    continue
                
                body = res.json()
                data = body.get('data', {})
                search_res = data.get('unifiedSearch', {})
                activities = search_res.get('activities', {})
                nodes = activities.get('nodes', [])

                if not nodes:
                    nodes = self._extract_nodes(data)

                for node in nodes:
                    nid = node.get('id')
                    if not nid or nid in seen_ids:
                        continue
                    
                    title = node.get('title', '')
                    due = (node.get('dueDate') or '')[:10]
                    
                    if due and due < today:
                        continue

                    seen_ids.add(nid)
                    
                    cats = ' '.join(c.get('name','') for c in (node.get('categories') or []))
                    full_text = (title + " " + cats).lower()
                    
                    # 부트캠프 관련 키워드 검사
                    is_boot = any(k in full_text for k in ['부트캠프', 'bootcamp', 'kdt', '교육', '양성', '과정'])
                    icon = "🎓 [부트캠프]" if is_boot else "🇰🇷 [링커리어]"
                    
                    results.append({
                        "title": f"{icon} {title}",
                        "url": f"https://linkareer.com/activity/{nid}",
                        "host": node.get('hostName') or "Linkareer",
                        "date": due or "상세 확인"
                    })
            except Exception as e:
                print(f"  Linkareer {keyword} 수집 중 예외: {e}")

        return results

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
        except Exception as e: print(f"CampusPick 예외: {e}")
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
        except: pass
        return []

    # ─────────────────────────────────────────────────────
    # 유틸리티 및 실행 섹션
    # ─────────────────────────────────────────────────────

    def _extract_nodes(self, data, depth=0):
        if depth > 4: return []
        if isinstance(data, list): return data
        if isinstance(data, dict):
            for key in ('nodes', 'list', 'edges', 'items'):
                if key in data and isinstance(data[key], list): return data[key]
            for v in data.values():
                res = self._extract_nodes(v, depth+1)
                if res: return res
        return []

    def run(self):
        print("🔍 해커톤 및 부트캠프 정보 수집을 시작합니다...")
        all_items = []
        tasks = [
            ("Devpost", self.fetch_devpost), ("MLH", self.fetch_mlh),
            ("DevEvent", self.fetch_devevent), ("CampusPick", self.fetch_campuspick),
            ("Linkareer", self.fetch_linkareer)
        ]
        
        for name, fetcher in tasks:
            try:
                found = fetcher()
                print(f"📡 {name}: {len(found)}개 발견")
                all_items.extend(found)
            except Exception as e: print(f"❌ {name} 오류: {e}")

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

if __name__ == "__main__":
    if WEBHOOK_URL:
        HackathonBot().run()
    else:
        print("❌ DISCORD_WEBHOOK_URL 환경 변수가 없습니다.")
