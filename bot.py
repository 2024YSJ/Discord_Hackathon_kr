import os
import requests
import json
from datetime import datetime
from bs4 import BeautifulSoup
import requests
# 설정
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

    # --- 플랫폼별 크롤러/API 호출 로직 ---

def fetch_devpost(self):
        try:
            # 1. 헤더 보강 (가장 중요)
            custom_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
                "Referer": "https://devpost.com/hackathons",
                "X-Requested-With": "XMLHttpRequest"
            }
            
            # 2. 파라미터 구체화
            params = {
                "status[]": "upcoming",
                "sort_by": "Recently Added"
            }
            
            url = "https://devpost.com/api/hackathons"
            res = requests.get(url, params=params, headers=custom_headers, timeout=15)
            
            # 3. 응답 상태 확인 로그 추가
            print(f"Devpost Response Status: {res.status_code}")
            
            if res.status_code == 200:
                data = res.json()
                hackathons = data.get('hackathons', [])
                
                # 데이터가 비어있는지도 확인
                if not hackathons:
                    print("Devpost: 공고는 가져왔으나 목록이 비어있습니다.")
                
                return [{
                    "title": h['title'], 
                    "url": h['url'], 
                    "host": "Devpost", 
                    "date": h.get('submission_period_dates', 'N/A')
                } for h in hackathons]
            
            else:
                print(f"Devpost Error: {res.status_code} - {res.text[:100]}")
                return []
                
        except Exception as e:
            print(f"Devpost Exception: {e}")
            return []

def fetch_mlh(self):
        try:
            # 1. 쿼리 파라미터 없이 호출하면 보통 현재 시즌 데이터를 반환합니다.
            # 혹은 안전하게 현재 연도를 포함합니다.
            year = datetime.now().year
            url = f"https://mlh.io/api/v1/hackathons?year={year}"
            
            res = requests.get(url, headers=self.headers, timeout=15)
            print(f"MLH Response Status: {res.status_code}")

            if res.status_code == 200:
                data = res.json()
                # 리스트 형태인지 확인
                if not isinstance(data, list):
                    print("MLH: 예기치 않은 응답 형식입니다.")
                    return []

                now_str = datetime.now().strftime('%Y-%m-%d')
                upcoming_hackathons = []

                for h in data:
                    # 시작일이 오늘 이후이거나 종료일이 지나지 않은 것만 필터링
                    # MLH 데이터는 보통 '2026-02-23' 같은 문자열 형식입니다.
                    if h.get('start_date') >= now_str:
                        upcoming_hackathons.append({
                            "title": h['name'],
                            "url": h['url'],
                            "host": "MLH",
                            "date": f"{h['start_date']} ~ {h['end_date']}"
                        })
                
                # 너무 많으면 최신순 10개만 반환
                return upcoming_hackathons[:10]
            
            else:
                print(f"MLH Error: {res.status_code}")
                return []

        except Exception as e:
            print(f"MLH Exception: {e}")
            return []

def fetch_devfolio(self):
        try:
            # 1. Devfolio 전용 헤더 설정 (매우 중요)
            devfolio_headers = self.headers.copy()
            devfolio_headers.update({
                "Origin": "https://devfolio.co",
                "Referer": "https://devfolio.co/hackathons",
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest"
            })
            
            url = "https://api.devfolio.co/api/hackathons"
            # 2. 페이로드 설정 (현재 오픈된 대회 위주)
            payload = {
                "type": "open", 
                "limit": 15,
                "range": "upcoming" # 혹은 "open"
            }
            
            res = requests.post(url, json=payload, headers=devfolio_headers, timeout=15)
            print(f"Devfolio Response Status: {res.status_code}")

            if res.status_code == 200:
                data = res.json()
                results = data.get('result', [])
                
                # 리스트가 비어있지 않은지 확인
                if not isinstance(results, list):
                    return []

                parsed_data = []
                for h in results:
                    # Slug가 있어야 정확한 URL 생성이 가능함
                    slug = h.get('slug')
                    if not slug: continue
                    
                    parsed_data.append({
                        "title": h.get('name', 'Untitled Hackathon'),
                        "url": f"https://{slug}.devfolio.co",
                        "host": "Devfolio",
                        "date": h.get('start_date', 'See Website')
                    })
                return parsed_data
            
            else:
                print(f"Devfolio Error: {res.status_code} - {res.text[:100]}")
                return []

        except Exception as e:
            print(f"Devfolio Exception: {e}")
            return []

def fetch_dorahacks(self):
        try:
            # 1. DoraHacks 전용 헤더 및 파라미터 보강
            dorahacks_headers = self.headers.copy()
            dorahacks_headers.update({
                "Origin": "https://dorahacks.io",
                "Referer": "https://dorahacks.io/hackathon",
                "Accept": "application/json"
            })
            
            # 최신 순으로 가져오기 위한 파라미터 (v1 기준)
            url = "https://dorahacks.io/api/v1/hackathon"
            params = {"size": 10, "type": "all"} 
            
            res = requests.get(url, params=params, headers=dorahacks_headers, timeout=15)
            print(f"DoraHacks Response Status: {res.status_code}")

            if res.status_code == 200:
                data = res.json()
                # DoraHacks는 보통 data.items 또는 직접 items에 데이터가 있음
                items = data.get('data', {}).get('items', []) if 'data' in data else data.get('items', [])
                
                if not items:
                    print("DoraHacks: 데이터를 찾을 수 없습니다.")
                    return []

                parsed_data = []
                for h in items:
                    h_id = h.get('id')
                    h_name = h.get('name')
                    if not h_id or not h_name: continue
                    
                    parsed_data.append({
                        "title": h_name,
                        "url": f"https://dorahacks.io/hackathon/{h_id}",
                        "host": "DoraHacks",
                        "date": h.get('start_at', 'Check Website') # 시작 날짜 필드명 확인
                    })
                return parsed_data
            
            else:
                print(f"DoraHacks Error: {res.status_code}")
                return []
                
        except Exception as e:
            print(f"DoraHacks Exception: {e}")
            return []

def fetch_unstop(self):
        try:
            # 1. 페이징 및 필터 최적화
            # opportunity=hackathons 외에 status=open 등을 추가하여 불필요한 데이터 로드 방지 가능
            url = "https://unstop.com/api/public/opportunity/search-result?opportunity=hackathons&per_page=15"
            
            # 2. 타임아웃 확장 (인도 서버의 지연 시간 고려)
            res = requests.get(url, headers=self.headers, timeout=15)
            
            # 3. 상태 코드 확인
            if res.status_code != 200:
                print(f"Unstop Error: Status {res.status_code}")
                return []

            data_json = res.json()
            
            # 4. 안전한 데이터 추출 (get 메서드를 활용해 계층별 확인)
            # data -> data 순서로 접근하며, 중간에 키가 없으면 빈 리스트([])를 반환
            opportunities = data_json.get('data', {}).get('data', [])
            
            if not opportunities:
                return []

            parsed_results = []
            for h in opportunities:
                # 필수 데이터(제목, URL)가 있는지 확인
                title = h.get('title')
                public_url = h.get('public_url')
                
                if title and public_url:
                    parsed_results.append({
                        "title": title,
                        "url": f"https://unstop.com/p/{public_url}",
                        "host": "Unstop",
                        # 날짜 형식 정리 (T00:00:00 등의 불필요한 시간 문자열 제거)
                        "date": h.get('reg_end_date', 'N/A').split('T')[0]
                    })
            
            return parsed_results

        except requests.exceptions.Timeout:
            print("Unstop Error: Timeout occurred")
            return []
        except Exception as e:
            print(f"Unstop Exception: {e}")
            return []

def fetch_kaggle(self):
        try:
            # 1. Kaggle 전용 헤더 보강 (X-Requested-With 필수인 경우가 많음)
            kaggle_headers = self.base_headers.copy()
            kaggle_headers.update({
                "Referer": "https://www.kaggle.com/competitions",
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json"
            })
            
            # 2. 엔드포인트 및 파라미터 (최신 경향 반영)
            url = "https://www.kaggle.com/api/i/competitions.CompetitionService/ListCompetitions"
            params = {
                "category": "all",
                "listCompetitionsRequest.sort": "LATEST", # 최신순 정렬
            }
            
            res = requests.get(url, params=params, headers=kaggle_headers, timeout=15)
            
            if res.status_code != 200:
                print(f"Kaggle Error: Status {res.status_code}")
                return []

            data = res.json()
            # 3. 데이터 계층 확인 (Kaggle은 보통 'competitions' 키에 리스트가 있음)
            items = data.get('competitions', [])
            
            if not items:
                return []

            parsed_results = []
            for i in items:
                title = i.get('title', '')
                ref = i.get('ref', '')
                
                if not title or not ref:
                    continue
                
                # 4. 필터링 강화: 'Hackathon' 키워드 외에도 해커톤 성격의 대회 추출
                # rewardType이 'Knowledge'이거나 title에 특정 키워드가 포함된 경우
                is_hackathon = any(keyword in title.lower() for keyword in ['hackathon', 'challenge', 'marathon'])
                is_knowledge = i.get('rewardTypeName') == 'Knowledge' or i.get('rewardType') == 'KNOWLEDGE'

                if is_hackathon or is_knowledge:
                    parsed_results.append({
                        "title": title,
                        "url": f"https://www.kaggle.com/c/{ref}",
                        "host": "Kaggle",
                        "date": i.get('deadline', 'Ongoing').split('T')[0] # 마감 기한 표시
                    })
            
            # 상위 10개만 반환
            return parsed_results[:10]

        except Exception as e:
            print(f"Kaggle Exception: {e}")
            return []

def fetch_hack2skill(self):
        try:
            # 1. API 엔드포인트 호출 (최신 크롬 헤더 사용 권장)
            url = "https://api.hack2skill.com/gethackathons"
            res = requests.get(url, headers=self.headers, timeout=15)
            
            if res.status_code != 200:
                print(f"Hack2Skill Error: Status {res.status_code}")
                return []

            data_json = res.json()
            
            # 2. 데이터 계층 확인 (보통 'data' 키에 리스트가 존재)
            items = data_json.get('data', [])
            if not isinstance(items, list):
                print("Hack2Skill: 'data' field is not a list.")
                return []

            parsed_results = []
            for h in items:
                # 3. 필수 필드 및 상태 필터링
                # 'name'과 'slug'가 없으면 URL 생성이 불가능하므로 건너뜀
                title = h.get('name')
                slug = h.get('slug')
                if not title or not slug:
                    continue
                
                # 4. 종료된 해커톤 제외 로직 (상태값이 있다면 활용)
                # 'is_active'나 'status' 같은 필드가 있는지 확인하여 필터링 가능
                # 여기서는 단순히 수집된 목록을 가공합니다.
                
                parsed_results.append({
                    "title": title.strip(),
                    "url": f"https://hack2skill.com/hackathon/{slug}",
                    "host": "Hack2Skill",
                    # 날짜 데이터 형식 안정화
                    "date": h.get('start_date', 'N/A').split('T')[0] 
                })
            
            # 최신 공고 10개로 제한
            return parsed_results[:10]

        except Exception as e:
            print(f"Hack2Skill Exception: {e}")
            return []

def fetch_wevity(self):
    """국내 최대 공모전 사이트 '위비티' 크롤링"""
    results = []
    try:
        # IT/소프트웨어/해커톤 카테고리
        url = "https://www.wevity.com/?c=find&s=1&gub=1&cat=30"
        res = requests.get(url, headers=self.headers, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            # 공모전 목록 추출
            lists = soup.select('.list li')
            for item in lists:
                title_tag = item.select_one('.tit a')
                if title_tag:
                    title = title_tag.text.strip()
                    # '해커톤' 키워드 필터링
                    if '해커톤' in title or 'Hackathon' in title:
                        results.append({
                            "title": f"🇰🇷 [위비티] {title}",
                            "url": "https://www.wevity.com/" + title_tag['href'],
                            "host": "Wevity",
                            "date": item.select_one('.dday').text.strip() if item.select_one('.dday') else "기한확인"
                        })
    except Exception as e:
        print(f"Wevity Error: {e}")
    return results

def fetch_linkareer(self):
    """대학생 대외활동 플랫폼 '링커리어' 크롤링"""
    results = []
    try:
        # 공모전 전체 리스트에서 '해커톤' 검색 결과 페이지
        url = "https://linkareer.com/list/contest?filterType=category&filterValue=11" # 11은 IT/SW 카테고리 예시
        res = requests.get(url, headers=self.headers, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            # 링커리어는 CSR 방식이 강해 데이터가 안 잡힐 경우 API 경로를 써야 하지만, 
            # 기본적으로 제목 태그를 탐색합니다.
            items = soup.find_all('h5') # 실제 구조에 따라 클래스명 추가 필요
            for item in items:
                title = item.text.strip()
                if '해커톤' in title:
                    # 링크와 상세정보 추출 로직...
                    results.append({
                        "title": f"🇰🇷 [링커리어] {title}",
                        "url": "https://linkareer.com/list/contest", # 검색결과 페이지로 대체
                        "host": "Linkareer",
                        "date": "상세 확인"
                    })
    except Exception as e:
        print(f"Linkareer Error: {e}")
    return results

def fetch_campuspick(self):
    """대학생 커뮤니티 '캠퍼스픽' 공모전 섹션"""
    results = []
    try:
        url = "https://www.campuspick.com/contest"
        res = requests.get(url, headers=self.headers, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            # 캠퍼스픽의 IT/SW 섹션 아이템 추출
            articles = soup.select('a.item')
            for a in articles:
                title = a.select_one('h2').text.strip() if a.select_one('h2') else ""
                if '해커톤' in title:
                    results.append({
                        "title": f"🇰🇷 [캠퍼스픽] {title}",
                        "url": "https://www.campuspick.com" + a['href'],
                        "host": "Campuspick",
                        "date": a.select_one('.dday').text.strip() if a.select_one('.dday') else "진행중"
                    })
    except Exception as e:
        print(f"Campuspick Error: {e}")
    return results

    def run(self):
        print("🔍 해커톤 정보 수집을 시작합니다...")
        all_hackathons = []
        
        # 글로벌 플랫폼
        all_found.extend(self.fetch_devpost())
        all_found.extend(self.fetch_mlh())
        all_found.extend(self.fetch_devfolio())
        all_found.extend(self.fetch_unstop())
        all_found.extend(self.fetch_kaggle())
        all_found.extend(self.fetch_hack2skill())
        all_found.extend(self.fetch_dorahacks()) # 글로벌 도라핵스
        
        # 국내 전용 플랫폼 (세분화된 함수들)
        all_found.extend(self.fetch_wevity())
        all_found.extend(self.fetch_linkareer())
        all_found.extend(self.fetch_campuspick())

        # 중복 제거 (데이터베이스에 없는 제목만 추출)
        new_items = [h for h in all_hackathons if h['title'] not in self.sent_list]

        if not new_items:
            print("✅ 새로운 공고가 없습니다.")
            return

        print(f"🆕 {len(new_items)}개의 새로운 공고를 발견했습니다!")
        
        # Discord 전송
        self.send_to_discord(new_items)
        
        # 보낸 목록 저장
        self.save_sent_list(new_items)

    def send_to_discord(self, hackathons):
        # Embed 리스트 생성 (최대 10개씩 묶음 전송)
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
            res = requests.post(WEBHOOK_URL, json=payload)
            if res.status_code != 204:
                print(f"전송 실패: {res.status_code}")

if __name__ == "__main__":
    if not WEBHOOK_URL:
        print("❌ 오류: DISCORD_WEBHOOK_URL 환경 변수가 설정되지 않았습니다.")
    else:
        bot = HackathonBot()
        bot.run()
