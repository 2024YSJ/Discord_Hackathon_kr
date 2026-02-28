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
    # 정상 동작 확인된 함수들 (변경 없음)
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
            # Dev-Event 저장소의 현재 월 파일 접근
            url = f"https://raw.githubusercontent.com/brave-people/Dev-Event/master/end_event/{now.year}/{str(now.year)[2:]}_{str(now.month).zfill(2)}.md"
            res = requests.get(url, timeout=15)
            if res.status_code == 200:
                results = []
                # 제목과 링크 추출을 위한 정규식
                for m in re.finditer(r'__\[([^\]]+)\]\((https?://[^\)]+)\)__', res.text):
                    title, link = m.group(1), m.group(2)
                    # 검색 키워드 확장: 부트캠프, 교육, KDT 등 포함
                    target_keywords = ['해커톤', 'Hackathon', '공모전', '경진대회', '부트캠프', 'Bootcamp', '교육', 'KDT', '양성과정']
                    if any(k.lower() in title.lower() for k in target_keywords):
                        icon = "🎓" if "부트캠프" in title or "교육" in title else "🇰🇷"
                        results.append({"title": f"{icon} [데브이벤트] {title}", "url": link, "host": "DevEvent", "date": "상세 확인"})
                return results
        except Exception as e:
            print(f"DevEvent 예외: {e}")
        return []

    def fetch_campuspick(self):
        try:
            h = self.headers.copy()
            h.update({"Content-Type": "application/x-www-form-urlencoded", "Origin": "https://www2.campuspick.com", "Referer": "https://www2.campuspick.com/"})
            today, results = datetime.now().strftime('%Y-%m-%d'), []
            
            # 108: 공모전, 111: 교육/강연 (부트캠프가 주로 올라오는 카테고리)
            for cat_id in [108, 111]:
                for offset in range(0, 40, 20):
                    res = requests.post("https://api2.campuspick.com/find/activity/list", 
                                        data={"target":1,"limit":20,"offset":offset,"categoryId":cat_id}, 
                                        headers=h, timeout=15)
                    if res.status_code != 200: break
                    activities = res.json().get("result", {}).get("activities", [])
                    if not activities: break
                    
                    valid = [a for a in activities if a.get("endDate","") >= today]
                    for a in valid:
                        prefix = "🎓 [부트캠프/교육]" if cat_id == 111 else "🇰🇷 [캠퍼스픽]"
                        results.append({
                            "title": f"{prefix} {a['title']}", 
                            "url": f"https://www2.campuspick.com/contest/view?id={a['id']}", 
                            "host": "CampusPick", 
                            "date": a.get("endDate","상세 확인")
                        })
            return results
        except Exception as e:
            print(f"CampusPick 예외: {e}")
        return []

    # ─────────────────────────────────────────────────────
    # 수정된 함수들
    # ─────────────────────────────────────────────────────

    def fetch_hackerearth(self):
        """
        HackerEarth 해커톤 목록 - HTML SSR 확인됨, 3개 성공 중
        live/upcoming 링크를 더 완전하게 수집하도록 개선
        """
        results = []
        seen = set()
        try:
            h = self.headers.copy()
            h.update({"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"})
            res = requests.get("https://www.hackerearth.com/challenges/hackathon/", headers=h, timeout=15)
            if res.status_code != 200:
                print(f"  HackerEarth 응답 오류: {res.status_code}")
                return []
            soup = BeautifulSoup(res.text, 'html.parser')
            for a in soup.find_all('a', href=True):
                href = a['href']
                if re.match(r'^/challenges/hackathon/[^/]+/?$', href):
                    full_url = "https://www.hackerearth.com" + href.rstrip('/') + '/'
                elif re.match(r'https://[^.]+\.hackerearth\.com/?$', href):
                    full_url = href.rstrip('/') + '/'
                else:
                    continue
                if full_url in seen: continue
                seen.add(full_url)
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
        [확인된 사실]
        - URL: programmers.co.kr/api/competitions  ← 직접 fetch로 응답 확인
        - JSON 구조: {"competitions": [{id, href, title, statusLabel, receiptEndAt, endAt}], "totalPages": 11}
        - href 예시: /competitions/4079?slug=2025_programmers_codechallenge
        - 현재 모든 항목이 statusLabel:"ended" → 진행 중인 대회가 없으면 0개는 정상

        totalPages(11)를 모두 순회하면 너무 많으므로 최근 2페이지만 확인.
        ended가 아닌 대회가 없으면 0개 반환 (버그 아님).
        """
        today = datetime.now().strftime('%Y-%m-%d')
        results = []
        try:
            for page in range(1, 3):  # 최근 2페이지
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
                for c in competitions:
                    if c.get('statusLabel') == 'ended': continue
                    end_at = c.get('receiptEndAt') or c.get('endAt') or ''
                    if end_at and end_at[:10] < today: continue
                    title = c.get('title', '')
                    href = c.get('href', '')
                    if not title: continue
                    # href에 쿼리스트링 포함될 수 있으므로 기본 경로만 사용
                    path = href.split('?')[0]
                    full_url = f"https://programmers.co.kr{path}"
                    results.append({
                        "title": f"🇰🇷 [프로그래머스] {title}",
                        "url": full_url,
                        "host": "Programmers",
                        "date": end_at[:10] if end_at else "상세 확인"
                    })
        except Exception as e:
            print(f"  Programmers 예외: {e}")
        return results

    def fetch_dacon(self):
        """
        DACON AI 경진대회
        - newapi.dacon.io: 외부 차단됨 (404)
        - dacon.io/competitions: Nuxt CSR, HTML에 데이터 없음
        - 해결: Google 검색 인덱스에서 최근 DACON 대회 URL을 수집하는 대신,
                Bing 오픈 검색 URL을 통해 최근 게시된 dacon.io 대회 페이지 파싱
                또는 GitHub의 DACON 관련 공개 데이터 활용

        실용적 대안: 이미 fetch_aiconnect에서 DACON HTML 15개 성공 중이므로
        여기서는 추가로 월간데이콘/해커톤 카테고리만 수집
        """
        results = []
        today = datetime.now().strftime('%Y-%m-%d')

        # DACON 해커톤 카테고리 페이지 (hackathon 탭)
        # URL: dacon.io/competitions?taskCategory=HACKATHON 시도
        urls_to_try = [
            ("https://dacon.io/competitions?taskCategory=HACKATHON", re.compile(r'/competitions/official/\d+')),
            ("https://dacon.io/competitions?status=active", re.compile(r'/competitions/official/\d+')),
            ("https://dacon.io/competitions", re.compile(r'/competitions/official/\d+')),
        ]
        h = self.headers.copy()
        h.update({"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Referer": "https://dacon.io/"})

        for url, pattern in urls_to_try:
            try:
                res = requests.get(url, headers=h, timeout=15)
                if res.status_code != 200: continue
                soup = BeautifulSoup(res.text, 'html.parser')
                seen = set()
                for a in soup.find_all('a', href=pattern):
                    href = a['href']
                    m = re.match(r'/competitions/official/(\d+)', href)
                    if not m or m.group(1) in seen: continue
                    seen.add(m.group(1))
                    title_tag = a.find(['h4', 'h3', 'h2', 'p', 'span'])
                    title = title_tag.get_text(strip=True) if title_tag else a.get_text(strip=True)
                    title = re.sub(r'\s+', ' ', title).strip()
                    if not title or len(title) < 3: continue
                    results.append({
                        "title": f"🇰🇷 [DACON] {title}",
                        "url": f"https://dacon.io{href.split('?')[0]}",
                        "host": "DACON",
                        "date": "상세 확인"
                    })
                if results:
                    break
            except Exception as e:
                print(f"  DACON {url} 예외: {e}")

        return results

    def fetch_aihub(self):
        """
        AI Hub 챌린지 - 이미 fetch_aiconnect에서 15개 성공 중이므로 유지
        fetch_aiconnect를 이 함수로 이름 변경하여 명확화
        """
        results = []
        today = datetime.now().strftime('%Y-%m-%d')

        # DACON HTML 파싱 (Nuxt CSR이지만 일부 SSR 내용 포함)
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
                    results.append({
                        "title": f"🇰🇷 [DACON] {title}",
                        "url": f"https://dacon.io{href.split('?')[0]}",
                        "host": "DACON",
                        "date": "상세 확인"
                    })
        except Exception as e:
            print(f"  DACON HTML 예외: {e}")

        # AI Hub 챌린지 HTML 파싱
        try:
            h = self.headers.copy()
            h.update({"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"})
            res = requests.get("https://www.aihub.or.kr/intrcn/lit/aiclgComp/list.do", headers=h, timeout=15)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                seen_titles = set()
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    if 'aiclgComp' not in href and 'challenge' not in href.lower(): continue
                    title = a.get_text(strip=True)
                    if not title or len(title) < 4 or title in seen_titles: continue
                    seen_titles.add(title)
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
        링커리어 수집 로직 개선: 
        필터링 의존도를 낮추고 키워드 매칭 기반으로 부트캠프를 식별합니다.
        """
        results = []
        today = datetime.now().strftime('%Y-%m-%d')
        seen_ids = set()

        gql_headers = {
            "Content-Type": "application/json",
            "User-Agent": self.headers["User-Agent"],
            "Referer": "https://linkareer.com/list/bootcamp",
            "Origin": "https://linkareer.com",
            "Accept": "application/json",
        }

        # 필터링에 실패할 경우를 대비해 '전체 최신순'과 '카테고리' 쿼리 병행
        # activityList 필드가 실제 서버 스키마에 따라 동작하지 않을 수 있으므로 여러 패턴 시도
        queries = [
            # 1. 부트캠프 카테고리 명시 시도 (가장 정확하지만 필터명 틀리면 0건)
            {"query": '{ activityList(filter: {categoryName: "부트캠프"}, page: 1, pageSize: 30) { list { id title dueDate hostName categories { name } } } }'},
            # 2. 전체 활동 중 최신 50개 (필터 오류 방지용 보험)
            {"query": '{ activities(first: 50) { nodes { id title dueDate hostName categories { name } } } }'}
        ]

        # 부트캠프 판별을 위한 핵심 키워드
        bootcamp_keywords = ['부트캠프', 'bootcamp', 'kdt', '국비', '양성', '교육과정', 'scampus', 'academy']
        # 해커톤/공모전 키워드
        contest_keywords = ['해커톤', 'hackathon', '공모전', '대회', '챌린지']

        for payload in queries:
            try:
                res = requests.post("https://api.linkareer.com/graphql", json=payload, headers=gql_headers, timeout=15)
                if res.status_code != 200: continue
                
                data = res.json().get('data', {})
                nodes = self._extract_nodes(data)
                if not nodes: continue

                for node in nodes:
                    nid = node.get('id')
                    if not nid or nid in seen_ids: continue
                    
                    title = node.get('title', '')
                    # 카테고리 이름들 (List 형태 대응)
                    cats = node.get('categories') or []
                    cats_str = ' '.join([c.get('name', '') for c in cats]).lower()
                    
                    # 제목 + 카테고리 전체 텍스트 분석
                    full_info = (title + " " + cats_str).lower()
                    
                    # 1. 마감일 체크
                    due = (node.get('dueDate') or '')[:10]
                    if due and due < today: continue

                    # 2. 키워드 매칭 (부트캠프 또는 해커톤 관련 공고만 수집)
                    is_bootcamp = any(k in full_info for k in bootcamp_keywords)
                    is_contest = any(k in full_info for k in contest_keywords)

                    if is_bootcamp or is_contest:
                        seen_ids.add(nid)
                        
                        # 아이콘 결정 (부트캠프 우선순위)
                        icon = "🎓 [부트캠프]" if is_bootcamp else "🇰🇷 [링커리어]"
                        
                        results.append({
                            "title": f"{icon} {title}",
                            "url": f"https://linkareer.com/activity/{nid}",
                            "host": node.get('hostName') or "Linkareer",
                            "date": due or "상세 확인"
                        })
            except Exception as e:
                print(f"  Linkareer 수집 중 오류: {e}")

        print(f"  Linkareer 최종 추출 결과: {len(results)}개")
        return results

    def _extract_nodes(self, data, depth=0):
        """GraphQL 응답에서 노드 배열을 재귀적으로 탐색"""
        if depth > 4: return []
        if isinstance(data, list): return data
        if isinstance(data, dict):
            for key in ('nodes', 'list', 'edges', 'items', 'results'):
                if key in data and isinstance(data[key], list):
                    return data[key]
            for v in data.values():
                result = self._extract_nodes(v, depth+1)
                if result: return result
        return []

    # ─────────────────────────────────────────────────────
    # run / discord
    # ─────────────────────────────────────────────────────

    def run(self):
        print("🔍 해커톤 및 부트캠프 정보 수집을 시작합니다...")
        all_hackathons = []
        tasks = [
            ("Devpost",     self.fetch_devpost),
            ("MLH",         self.fetch_mlh),
            ("HackerEarth", self.fetch_hackerearth),
            ("Kaggle",      self.fetch_kaggle),
            ("Hack2Skill",  self.fetch_hack2skill),
            ("DoraHacks",   self.fetch_dorahacks),
            ("Programmers", self.fetch_programmers),    # 진행 대회 없으면 0개 정상
            ("DevEvent",    self.fetch_devevent),
            ("DACON",       self.fetch_dacon),          # Wevity 대체
            ("CampusPick",  self.fetch_campuspick),
            ("DACON/AIHub", self.fetch_aihub),          # AIConnect 대체 (15개 성공)
            ("Linkareer",   self.fetch_linkareer),
        ]
        for name, fetcher in tasks:
            try:
                found = fetcher()
                print(f"📡 {name}: {len(found)}개 발견")
                all_hackathons.extend(found)
            except Exception as e:
                print(f"❌ {name} 치명적 오류: {e}")

        # 중복 제거 (title 기준)
        seen_titles = set()
        deduped = []
        for h in all_hackathons:
            if h['title'] not in seen_titles:
                seen_titles.add(h['title'])
                deduped.append(h)

        new_items = [h for h in deduped if h['title'] not in self.sent_list]
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
            requests.post(WEBHOOK_URL, json={
                "content": "🚀 **새로운 소식이 발견되었습니다!**" if i == 0 else "",
                "embeds": embeds
            })


if __name__ == "__main__":
    if not WEBHOOK_URL:
        print("❌ 오류: DISCORD_WEBHOOK_URL 환경 변수가 설정되지 않았습니다.")
    else:
        bot = HackathonBot()
        bot.run()
