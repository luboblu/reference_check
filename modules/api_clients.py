# modules/api_clients.py
import streamlit as st
import requests
import time
from difflib import SequenceMatcher
from serpapi import GoogleSearch
import urllib3
import re

# 導入標題清洗函式
from .parsers import clean_title

# --- 全域 API 設定 ---
S2_API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
OPENALEX_API_URL = "https://api.openalex.org/works"

MAX_RETRIES = 2
TIMEOUT = 10

# ========== API Key 管理 ==========
def get_scopus_key():
    return st.secrets.get("scopus_api_key") or _read_key_file("scopus_key.txt")

def get_serpapi_key():
    return st.secrets.get("serpapi_key") or _read_key_file("serpapi_key.txt")

def _read_key_file(filename):
    try:
        with open(filename, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None

# ========== [核心] 1. 作者比對邏輯 (新增) ==========
def _check_author_match(query_author, result_authors_list):
    """
    寬鬆比對作者姓氏
    :param query_author: 使用者輸入的作者字串 (例如 "Smith, J." 或 "Li")
    :param result_authors_list: API 回傳的作者列表 (List of strings or dicts)
    """
    # 如果使用者沒提供作者，或是輸入的作者字串太短(可能解析失敗)，就跳過檢查(視為通過)
    if not query_author or len(query_author) < 2:
        return True
    
    # 提取查詢作者的姓氏 (假設格式為 "Family, Given" 或 "Family Given")
    # 簡單策略：取逗號前或空格前的第一個詞作為姓氏
    q_family = re.split(r'[, ]', query_author.strip())[0].lower().strip()
    
    # 如果姓氏太短 (例如 "Li", "Ng")，比對時要小心，但這裡先採寬鬆策略
    if not q_family: return True

    # 處理 API 回傳的作者列表
    formatted_results = []
    for auth in result_authors_list:
        if isinstance(auth, dict):
            # 針對 Crossref/Scopus 常見的 dict 結構 {'family': 'Smith', 'given': 'John'}
            family = auth.get('family') or auth.get('surname') or auth.get('ce:surname') or ''
            name = auth.get('name') or auth.get('authname') or '' # Semantic Scholar 有時是 'name'
            formatted_results.append(str(family).lower())
            formatted_results.append(str(name).lower())
        else:
            # 純字串
            formatted_results.append(str(auth).lower())
    
    # 檢查：只要查詢的姓氏出現在 API 結果的任何一個作者名字中，就算 Pass
    for res_str in formatted_results:
        if q_family in res_str:
            return True
            
    return False

# ========== [核心] 2. 標題比對邏輯 (包含您之前的寬鬆優化) ==========
def _is_match(query, result):
    if not query or not result: return False
    c_q = clean_title(query)
    c_r = clean_title(result)
    
    # 1. 針對 Query 是長段落，而 Result 是短標題的情況
    if len(c_q) > len(c_r) * 1.5:
        if c_r in c_q: return True

    # 2. 相似度比對
    ratio = SequenceMatcher(None, c_q, c_r).ratio()
    if ratio >= 0.9: return True 
    
    # 3. 關鍵字比對
    q_words = set(c_q.split())
    r_words = set(c_r.split())
    stop_words = {'a', 'an', 'the', 'of', 'in', 'for', 'with', 'on', 'at', 'by', 'and'}
    
    # 正向檢查 (Result 的重要單字都在 Query 裡)
    missing_important_in_query = [w for w in r_words if w not in stop_words and w not in q_words]
    if len(missing_important_in_query) == 0:
        return True

    # 反向檢查 (Query 的重要單字都在 Result 裡 - 針對不完整標題)
    missing_important_in_result = [w for w in q_words if w not in stop_words and w not in r_words]
    if len(missing_important_in_result) == 0:
        # 長度保護：輸入長度至少要是完整標題的 30%
        if len(c_q) > len(c_r) * 0.3:
            return True

    return False

# --- API 呼叫輔助 ---
def _call_external_api_with_retry(url: str, params: dict, headers=None):
    if not headers: headers = {'User-Agent': 'ReferenceChecker/1.0'}
    for _ in range(MAX_RETRIES):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
            if response.status_code == 200: return response.json(), "OK"
            if response.status_code in [401, 403]: return None, f"Auth Error ({response.status_code})"
        except: pass
    return None, "Error"

# ========== 1. Crossref (含作者比對) ==========

def search_crossref_by_doi(doi, target_title=None):
    if not doi: return None, None, "Empty DOI"
    clean_doi = doi.strip(' ,.;)]}>')
    url = f"https://api.crossref.org/works/{clean_doi}"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            item = response.json().get("message", {})
            titles = item.get("title", [])
            res_title = titles[0] if titles else ""
            
            if target_title and not _is_match(target_title, res_title):
                return None, None, f"DOI Title Mismatch: {res_title[:40]}..."
                
            return res_title, item.get("URL") or f"https://doi.org/{clean_doi}", "OK"
        return None, None, f"HTTP {response.status_code}"
    except: return None, None, "Conn Error"

def search_crossref_by_text(title, author=None):
    if not title: return None, "Empty Title"
    params = {'query.bibliographic': title, 'rows': 2} # 抓前2筆增加機會
    if author:
        params['query.author'] = author # Crossref 支援直接搜作者
        
    data, status = _call_external_api_with_retry("https://api.crossref.org/works", params)
    
    if status == "OK" and data and data.get('message', {}).get('items'):
        for item in data['message']['items']:
            res_title = item.get('title', [''])[0]
            res_authors = item.get('author', []) # 取得作者列表
            
            # 雙重檢查：標題要對 + 作者要對
            if _is_match(title, res_title):
                if _check_author_match(author, res_authors):
                    return item.get('URL') or f"https://doi.org/{item.get('DOI')}", "OK"
                else:
                    # 如果標題對但作者不對，繼續找下一筆 (可能剛好是同名文章)
                    continue 
                    
        return None, "Match failed (Title or Author mismatch)"
    return None, status

# ========== 2. Scopus (新增作者比對) ==========

def search_scopus_by_title(title, api_key, author=None):
    """
    注意：app.py 呼叫此函式時，建議更新傳入 author 參數
    """
    if not api_key: return None, "No API Key"
    url = "https://api.elsevier.com/content/search/scopus"
    headers = {"Accept": "application/json", "X-ELS-APIKey": api_key}
    params = {"query": f'TITLE("{title}")', "count": 1}
    
    data, status = _call_external_api_with_retry(url, params, headers)
    
    if status == "OK" and data:
        entries = data.get('search-results', {}).get('entry', [])
        if not entries or 'error' in entries[0]:
            return None, "(No results found)"
        
        match = entries[0]
        res_title = match.get('dc:title', '')
        
        # Scopus 的作者通常在 'dc:creator' (第一作者) 或需要另外解析
        # Search API 的簡單回應通常只給 'dc:creator'
        res_creator = match.get('dc:creator', '')
        
        if _is_match(title, res_title):
            if _check_author_match(author, [res_creator]):
                return match.get('prism:url', 'https://www.scopus.com'), "OK"
            else:
                return None, f"Author Mismatch (Found: {res_creator})"
        else:
            return None, f"Title Mismatch: {res_title[:30]}..."
            
    return None, "Error"

# ========== 3. Google Scholar (無作者欄位，維持原樣) ==========

def search_scholar_by_title(title, api_key):
    if not api_key: return None, "No API Key"
    # Scholar API 結果通常很雜，且不一定有結構化作者，這裡維持僅標題比對
    params = {"engine": "google_scholar", "q": title, "api_key": api_key, "num": 3}
    try:
        results = GoogleSearch(params).get_dict()
        organic = results.get("organic_results", [])
        for res in organic:
            if _is_match(title, res.get("title", "")):
                return res.get("link"), "match"
        return None, "No exact match found"
    except Exception as e: return None, str(e)

def search_scholar_by_ref_text(ref_text, api_key, target_title=None):
    if not api_key: return None, "No API Key"
    params = {"engine": "google_scholar", "q": ref_text, "api_key": api_key, "num": 1}
    try:
        results = GoogleSearch(params).get_dict()
        organic = results.get("organic_results", [])
        if organic:
            res_title = organic[0].get("title", "")
            if target_title and not _is_match(target_title, res_title):
                return None, "Title mismatch in fallback"
            return organic[0].get("link"), "similar"
    except: pass
    return None, "No results"

# ========== 4. Semantic Scholar & OpenAlex (含作者比對) ==========

def search_s2_by_title(title, author=None):
    # 增加請求 'authors' 欄位
    params = {'query': title, 'limit': 1, 'fields': 'title,url,authors'}
    data, status = _call_external_api_with_retry(S2_API_URL, params)
    if status == "OK" and data.get('data'):
        match = data['data'][0]
        res_title = match.get('title')
        res_url = match.get('url')
        res_authors = match.get('authors', []) # S2 回傳 [{'authorId':..., 'name': '...'}]

        if _is_match(title, res_title):
            if _check_author_match(author, res_authors):
                return res_url, "OK"
            return None, "Author mismatch"
            
        return None, "Match failed"
    return None, status

def search_openalex_by_title(title, author=None):
    params = {'search': title, 'per_page': 1}
    data, status = _call_external_api_with_retry(OPENALEX_API_URL, params)
    
    if status == "OK" and data.get('results'):
        match = data['results'][0]
        res_title = match.get('title')
        # OpenAlex 作者結構: 'authorships': [{'author': {'display_name': '...'}}]
        res_authors = []
        for authorship in match.get('authorships', []):
            if 'author' in authorship:
                res_authors.append(authorship['author'].get('display_name', ''))

        if _is_match(title, res_title):
            if _check_author_match(author, res_authors):
                url = match.get('doi') or match.get('id')
                if url: return url, "OK"
                return None, "No Link"
            return None, "Author mismatch"
            
        return None, "Title mismatch"
            
    return None, status if status != "OK" else "No results found"

def check_url_availability(url):
    # 這裡加入您提過的：過濾純首頁 (例如 https://www.sans.org)
    if not url or not url.startswith("http"): return False
    
    # 簡單過濾：如果路徑只有 domain，極大機率是首頁而非論文頁
    # 邏輯：計算 '/' 的數量。https://abc.com 只有 2 個 '/'。https://abc.com/paper 有 3 個。
    if url.count('/') < 3: 
        return False
        
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    try:
        resp = requests.head(url, timeout=5, allow_redirects=True, verify=False)
        return 200 <= resp.status_code < 400
    except: return False