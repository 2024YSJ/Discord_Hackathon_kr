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

    # ──────────────────────────────────────────
    # 기존 정상 함수 (변경 없음)
    # ──────────────────────────────────────────

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
                print(f"📡 MLH: {len(results)}개 추출 성공 (종료 이벤트 제외)")
                return results
        except Exception as e:
            print(f"MLH 예외: {e}")
        return []

    def fetch_kaggle(self):
        username = os.environ.get('KAGGLE_USERNAME', '')
        key = os.environ.get('KAGGLE_KEY', '')
        print(f"DEBUG: Username length: {len(username)}")
        print(f"DEBUG: Key length: {len(key)}")
        if not username or not key:
            print("❌ Kaggle 환경변수 없음")
            return []
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            res = requests.get('https://www.kaggle.com/api/v1/competitions/list',
                               params={'sortBy': 'latestDeadline', 'pageSize': 20},
                               auth=(username, key), headers=self.headers, timeout=15)
            if res.status_code != 200:
                print(f"❌ Kaggle API 실패 ({res.status_code})")
                return []
            results = []
            for c in res.json():
                title = c.get('title', '')
                deadline = (c.get('deadline') or '')[:10]
                if not title or (deadline and deadline < today): continue
                ref = c.get('ref') or c.get('id', '')
                results.append({"title": title, "url": f"https://www.kaggle.com/competitions/{ref}", "host": "Kaggle", "date": deadline or "상세 확인"})
            print(f"✅ {len(results)}개의 활성 경진대회를 찾았습니다.")
            return results
        except Exception as e:
            print(f"❌ Kaggle 예외: {e}")
        return []

    def fetch_hack2skill(self):
        try:
            res = requests.get('https://hack2skill.com/', headers=self.headers, timeout=15)
            if res.status_code != 200: return []
            soup = BeautifulSoup(res.text, 'html.parser')
            flagship = soup.find(class_='flagshipEventsSlider')
            if not flagship: return []
            today, results, seen = datetime.now(), [], set()
            for a in flagship.find_all('a', href=re.compile(r'hack2skill\.com')):
                url = a['href'].split('?')[0]
                if url in seen: continue
                card = a.find_parent('div', class_=re.compile(r'w-\[16rem\]'))
                if not card: continue
                h5s = card.find_all('h5')
                if not h5s: continue
                title = h5s[0].get_text(strip=True)
                if not title: continue
                date_str = h5s[-1].get_text(strip=True) if len(h5s) > 1 else ''
                try:
                    if datetime.strptime(date_str, '%a %b %d %Y') < today: continue
                except ValueError: pass
                seen.add(url)
                results.append({"title": title, "url": url, "host": "Hack2Skill", "date": date_str})
            return results
        except Exception as e:
            print(f"Hack2Skill 예외: {e}")
        return []

    def fetch_dorahacks(self):
        try:
            res = requests.get("https://dorahacks.io/api/hackathon", params={"status": "open", "limit": 20}, headers=self.headers, timeout=15)
            if res.status_code == 200:
                now_ts = time.time()
                results = []
                for h in res.json().get('results', []):
                    title = h.get('title', '')
                    if not title: continue
                    end_ts = h.get('end_time')
                    if end_ts and int(end_ts) < now_ts: continue
                    results.append({"title": title, "url": f"https://dorahacks.io/hackathon/{h.get('id','')}", "host": "DoraHacks", "date": "상세 확인"})
                return results
        except Exception as e:
            print(f"DoraHacks 예외: {e}")
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
                    if any(k in title for k in ['해커톤', 'Hackathon', 'hackathon', '공모전', '경진대회']):
                        results.append({"title": f"🇰🇷 [데브이벤트] {title}", "url": link, "host": "DevEvent", "date": "상세 확인"})
                return results
        except Exception as e:
            print(f"DevEvent 예외: {e}")
        return []

    def fetch_campuspick(self):
        try:
            h = self.headers.copy()
            h.update({"Content-Type": "application/x-www-form-urlencoded", "Origin": "https://www2.campuspick.com", "Referer": "https://www2.campuspick.com/contest?category=108"})
            today, results = datetime.now().strftime('%Y-%m-%d'), []
            for offset in range(0, 40, 20):
                res = requests.post("https://api2.campuspick.com/find/activity/list", data={"target":1,"limit":20,"offset":offset,"categoryId":108}, headers=h, timeout=15)
                if res.status_code != 200: break
                activities = res.json().get("result", {}).get("activities", [])
                if not activities: break
                valid = [a for a in activities if a.get("endDate","") >= today]
                for a in valid:
                    results.append({"title": f"🇰🇷 [캠퍼스픽] {a['title']}", "url": f"https://www2.campuspick.com/contest/view?id={a['id']}", "host": "CampusPick", "date": a.get("endDate","상세 확인")})
                if not valid: break
            return results
        except Exception as e:
            print(f"CampusPick 예외: {e}")
        return []

    # ──────────────────────────────────────────
    # 수정된 함수들 (실제 URL/응답 검증 완료)
    # ──────────────────────────────────────────

    def fetch_devfolio(self):
        """
        [원인] GitHub Actions IP → Devfolio Cloudflare 403 차단
        [해결] HackerEarth 해커톤 페이지로 완전 교체
               - HTML에 live/upcoming 해커톤 링크 직접 포함됨 (SSR 확인)
               - /challenges/hackathon/{slug}/ 패턴
        """
        results = []
        seen = set()
        try:
            h = self.headers.copy()
            h.update({"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Referer": "https://www.hackerearth.com/"})
            res = requests.get("https://www.hackerearth.com/challenges/hackathon/", headers=h, timeout=15)
            if res.status_code != 200:
                print(f"  HackerEarth 응답 오류: {res.status_code}")
                return []
            soup = BeautifulSoup(res.text, 'html.parser')
            # live/upcoming 해커톤: <a href="/challenges/hackathon/{slug}/"> 또는 https://*.hackerearth.com/
            for a in soup.find_all('a', href=True):
                href = a['href']
                # 내부 슬러그 패턴
                if re.match(r'^/challenges/hackathon/[^/]+/?$', href):
                    full_url = "https://www.hackerearth.com" + href.rstrip('/') + '/'
                # 서브도메인 패턴: https://xxx.hackerearth.com/
                elif re.match(r'https://[^.]+\.hackerearth\.com/?$', href):
                    full_url = href.rstrip('/') + '/'
                else:
                    continue
                if full_url in seen: continue
                seen.add(full_url)
                # 제목: h3, h4, 또는 a 텍스트
                title_tag = a.find(['h3', 'h4', 'h2', 'p'])
                title = title_tag.get_text(strip=True) if title_tag else a.get_text(strip=True)
                title = re.sub(r'\s+', ' ', title).strip()
                if not title or len(title) < 3: continue
                results.append({"title": title, "url": full_url, "host": "HackerEarth", "date": "상세 확인"})
        except Exception as e:
            print(f"  HackerEarth 예외: {e}")
        return results

    def fetch_programmers(self):
        """
        [원인] career.programmers.co.kr DNS 해석 실패 (이 도메인 존재 안 함)
        [실제 URL] programmers.co.kr/api/competitions → 직접 확인 완료
        [JSON 구조] {"competitions": [{id, href, title, statusLabel, receiptEndAt, ...}], "page":1, "totalPages":11}
        [주의] 현재 진행 중인 대회가 없으면 0개가 정상 (모두 statusLabel:"ended")
        """
        today = datetime.now().strftime('%Y-%m-%d')
        results = []
        try:
            # 전체 페이지 순회 (totalPages 활용)
            page = 1
            while True:
                res = requests.get(
                    "https://programmers.co.kr/api/competitions",
                    params={"page": page},
                    headers=self.headers, timeout=15
                )
                if res.status_code != 200:
                    print(f"  Programmers API 오류: {res.status_code}")
                    break
                data = res.json()
                competitions = data.get('competitions', [])
                total_pages = data.get('totalPages', 1)
                for c in competitions:
                    if c.get('statusLabel') == 'ended': continue
                    end_at = c.get('receiptEndAt') or c.get('endAt') or ''
                    if end_at and end_at[:10] < today: continue
                    title = c.get('title', '')
                    href = c.get('href', '')
                    if not title: continue
                    full_url = f"https://programmers.co.kr{href}" if href.startswith('/') else href
                    results.append({
                        "title": f"🇰🇷 [프로그래머스] {title}",
                        "url": full_url,
                        "host": "Programmers",
                        "date": end_at[:10] if end_at else "상세 확인"
                    })
                if page >= total_pages or page >= 3: break  # 최근 3페이지만
                page += 1
        except Exception as e:
            print(f"  Programmers 예외: {e}")
        return results

    def fetch_wevity(self):
        """
        [원인] Wevity + 공모전365 모두 GitHub Actions IP에서 차단/JS렌더링
        [해결] DACON (데이콘) AI/ML 경진대회 + 공개SW 개발자대회로 교체
               - DACON: 실제 REST API 제공 (공개 확인)
               - 공개SW포털(oss.kr): 국내 주요 SW대회 운영
        """
        results = []
        today = datetime.now().strftime('%Y-%m-%d')

        # 1. DACON 경진대회 API (data.ai-competition.com)
        try:
            h = self.headers.copy()
            h.update({"Accept": "application/json", "Referer": "https://dacon.io/competitions"})
            res = requests.get(
                "https://dacon.io/api/v1/competitions/official/",
                params={"page": 1, "page_size": 20, "ordering": "-created"},
                headers=h, timeout=15
            )
            if res.status_code == 200:
                data = res.json()
                items = data.get('results', data.get('data', data if isinstance(data, list) else []))
                for c in (items if isinstance(items, list) else []):
                    title = c.get('title') or c.get('name', '')
                    cid = c.get('id') or c.get('competition_id', '')
                    end_d = (c.get('competition_end_date') or c.get('end_date') or c.get('ends_at') or '')[:10]
                    if end_d and end_d < today: continue
                    if title:
                        results.append({
                            "title": f"🇰🇷 [DACON] {title}",
                            "url": f"https://dacon.io/competitions/official/{cid}",
                            "host": "DACON",
                            "date": end_d or "상세 확인"
                        })
            else:
                print(f"  DACON API 응답: {res.status_code}")
        except Exception as e:
            print(f"  DACON 예외: {e}")

        # 2. 공개SW 개발자대회 (oss.kr) — HTML 파싱
        try:
            res = requests.get("https://www.oss.kr/dev_competition", headers=self.headers, timeout=15)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                for a in soup.find_all('a', href=re.compile(r'dev_competition')):
                    title = a.get_text(strip=True)
                    if not title or len(title) < 5: continue
                    href = a['href']
                    full_url = f"https://www.oss.kr{href}" if href.startswith('/') else href
                    results.append({
                        "title": f"🇰🇷 [공개SW] {title}",
                        "url": full_url,
                        "host": "OSS",
                        "date": "상세 확인"
                    })
        except Exception as e:
            print(f"  OSS 예외: {e}")

        return results

    def fetch_aiconnect(self):
        """
        [원인] aiconnect.kr 완전 CSR → HTML 데이터 없음, 내부 API 엔드포인트 미공개
        [해결] DACON + 국내 AI 경진대회 소스로 교체
               1. 데이터넷 AI 경진대회 (datanet.or.kr)
               2. AI 바우처 경진대회 등 공공 API 활용
        """
        results = []
        today = datetime.now().strftime('%Y-%m-%d')

        # 1. DACON 공모전 HTML 파싱 (API 실패 대비)
        try:
            h = self.headers.copy()
            h.update({"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Referer": "https://dacon.io/"})
            res = requests.get("https://dacon.io/competitions", headers=h, timeout=15)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                seen = set()
                for a in soup.find_all('a', href=re.compile(r'/competitions/official/\d+')):
                    href = a['href']
                    m = re.match(r'/competitions/official/(\d+)', href)
                    if not m or m.group(1) in seen: continue
                    seen.add(m.group(1))
                    title_tag = a.find(['h4', 'h3', 'h2', 'p', 'span'])
                    title = title_tag.get_text(strip=True) if title_tag else a.get_text(strip=True)
                    title = re.sub(r'\s+', ' ', title).strip()
                    if not title or len(title) < 3: continue
                    full_url = f"https://dacon.io{href}"
                    results.append({
                        "title": f"🇰🇷 [DACON] {title}",
                        "url": full_url,
                        "host": "DACON",
                        "date": "상세 확인"
                    })
        except Exception as e:
            print(f"  DACON HTML 파싱 예외: {e}")

        # 2. AI 허브 챌린지 (aihub.or.kr)
        try:
            h = self.headers.copy()
            h.update({"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"})
            res = requests.get("https://www.aihub.or.kr/intrcn/lit/aiclgComp/list.do", headers=h, timeout=15)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                seen = set()
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    if 'aiclgComp' not in href and 'challenge' not in href.lower(): continue
                    title = a.get_text(strip=True)
                    if not title or len(title) < 4 or title in seen: continue
                    seen.add(title)
                    full_url = f"https://www.aihub.or.kr{href}" if href.startswith('/') else href
                    results.append({
                        "title": f"🇰🇷 [AI Hub] {title}",
                        "url": full_url,
                        "host": "AIHub",
                        "date": "상세 확인"
                    })
        except Exception as e:
            print(f"  AIHub HTML 예외: {e}")

        return results

    def fetch_linkareer(self):
        """
        [원인] GraphQL 스키마 완전 불일치 — 인트로스펙션 없이는 올바른 쿼리 작성 불가
        [해결] 링커리어 웹페이지 HTML 직접 파싱으로 교체
               URL 패턴: linkareer.com/activity/{id}
               검색 URL: linkareer.com/list/contest?filterBy=HACKATHON
        """
        results = []
        today = datetime.now().strftime('%Y-%m-%d')
        seen = set()

        # 1. 링커리어 해커톤 목록 페이지 HTML 파싱
        search_urls = [
            "https://linkareer.com/list/contest?filterBy=HACKATHON&page=1",
            "https://linkareer.com/list/contest?category=해커톤&page=1",
        ]
        for url in search_urls:
            try:
                h = self.headers.copy()
                h.update({"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Referer": "https://linkareer.com/", "Accept-Language": "ko-KR,ko;q=0.9"})
                res = requests.get(url, headers=h, timeout=15)
                if res.status_code != 200: continue
                soup = BeautifulSoup(res.text, 'html.parser')
                for a in soup.find_all('a', href=re.compile(r'/activity/\d+')):
                    href = a['href']
                    m = re.match(r'/activity/(\d+)', href)
                    if not m or m.group(1) in seen: continue
                    seen.add(m.group(1))
                    title_tag = a.find(['h3', 'h4', 'h2', 'strong', 'p'])
                    title = title_tag.get_text(strip=True) if title_tag else a.get_text(strip=True)
                    title = re.sub(r'\s+', ' ', title).strip()
                    if not title or len(title) < 3: continue
                    results.append({
                        "title": f"🇰🇷 [링커리어] {title}",
                        "url": f"https://linkareer.com{href}",
                        "host": "Linkareer",
                        "date": "상세 확인"
                    })
                if results: break
            except Exception as e:
                print(f"  Linkareer HTML 예외: {e}")

        # 2. GraphQL fallback — 전체 조회 후 키워드 필터 (스키마 문제 우회)
        if not results:
            try:
                res = requests.post(
                    "https://api.linkareer.com/graphql",
                    json={"query": "{ activities(first: 50) { nodes { id title dueDate categories { name } } } }"},
                    headers={"Content-Type": "application/json", "User-Agent": self.headers["User-Agent"], "Referer": "https://linkareer.com/", "Origin": "https://linkareer.com"},
                    timeout=15
                )
                if res.status_code == 200:
                    body = res.json()
                    if not body.get('errors'):
                        nodes = body.get('data', {}).get('activities', {}).get('nodes', [])
                        for node in nodes:
                            title = node.get('title', '')
                            cats = ' '.join(c.get('name','') for c in (node.get('categories') or []))
                            if not any(k in title+cats for k in ['해커톤','Hackathon','hackathon','공모전']): continue
                            nid = node.get('id','')
                            due = (node.get('dueDate') or '')[:10]
                            if due and due < today: continue
                            results.append({
                                "title": f"🇰🇷 [링커리어] {title}",
                                "url": f"https://linkareer.com/activity/{nid}",
                                "host": "Linkareer",
                                "date": due or "상세 확인"
                            })
            except Exception as e:
                print(f"  Linkareer GraphQL 예외: {e}")

        return results

    # ──────────────────────────────────────────
    # run / discord
    # ──────────────────────────────────────────

    def run(self):
        print("🔍 해커톤 정보 수집을 시작합니다...")
        all_hackathons = []
        tasks = [
            ("Devpost",       self.fetch_devpost),
            ("MLH",           self.fetch_mlh),
            ("HackerEarth",   self.fetch_devfolio),   # Devfolio 대체
            ("Kaggle",        self.fetch_kaggle),
            ("Hack2Skill",    self.fetch_hack2skill),
            ("DoraHacks",     self.fetch_dorahacks),
            ("Programmers",   self.fetch_programmers),
            ("DevEvent",      self.fetch_devevent),
            ("DACON/OSS",     self.fetch_wevity),      # Wevity 대체
            ("CampusPick",    self.fetch_campuspick),
            ("DACON/AIHub",   self.fetch_aiconnect),   # AIConnect 대체
            ("Linkareer",     self.fetch_linkareer),
        ]
        for name, fetcher in tasks:
            try:
                found = fetcher()
                print(f"📡 {name}: {len(found)}개 발견")
                all_hackathons.extend(found)
            except Exception as e:
                print(f"❌ {name} 치명적 오류: {e}")

        new_items = [h for h in all_hackathons if h['title'] not in self.sent_list]
        print(f"📊 최종 신규 공고: {len(new_items)}개")
        if not new_items: return
        self.send_to_discord(new_items)
        self.save_sent_list(new_items)

    def send_to_discord(self, hackathons):
        for i in range(0, len(hackathons), 10):
            chunk = hackathons[i:i+10]
            embeds = [{"title": f"🏆 {h['title']}", "url": h['url'], "color": 3447003,
                       "fields": [{"name": "플랫폼", "value": h['host'], "inline": True},
                                  {"name": "마감/일정", "value": str(h['date']), "inline": True}]}
                      for h in chunk]
            requests.post(WEBHOOK_URL, json={"content": "🚀 **새로운 해커톤 대회가 발견되었습니다!**" if i == 0 else "", "embeds": embeds})


if __name__ == "__main__":
    if not WEBHOOK_URL:
        print("❌ 오류: DISCORD_WEBHOOK_URL 환경 변수가 설정되지 않았습니다.")
    else:
        bot = HackathonBot()
        bot.run()
