import urllib.parse
import requests
from difflib import SequenceMatcher
from .text_cleaner import clean_title, clean_title_for_remedial
import logging
import re

logger = logging.getLogger(__name__)

def search_crossref_by_doi(text, only_check=False):
    match = re.search(r'(10\\.\\d{4,9}/[-._;()/:A-Z0-9]+)', text, re.I)
    if match:
        doi = match.group(1).rstrip(".")
        try:
            r = requests.get(f"https://api.crossref.org/works/{doi}")
            if r.status_code == 200:
                return "found" if only_check else (r.json().get('message', {}).get('title', [''])[0], r.json().get('message', {}).get('URL'))
            return "not_found" if only_check else (None, None)
        except Exception as e:
            logger.exception("Crossref error")
            return "error" if only_check else (None, None)
    return "no_doi" if only_check else (None, None)

def search_scopus_by_title(title, scopus_key, threshold_equal=True):
    if not title:
        return None
    base_url = "https://api.elsevier.com/content/search/scopus"
    headers = {"Accept": "application/json", "X-ELS-APIKey": scopus_key}
    params = {"query": f'TITLE("{title}")', "count": 3}
    try:
        r = requests.get(base_url, headers=headers, params=params, timeout=15)
        if r.status_code == 200:
            data = r.json()
            entries = data.get('search-results', {}).get('entry', [])
            for entry in entries:
                doc_title = entry.get('dc:title', '')
                if threshold_equal and doc_title.strip().lower() == title.strip().lower():
                    return entry.get('prism:url', 'https://www.scopus.com')
            return None
        else:
            return None
    except Exception:
        logger.exception("Scopus API error")
        return None

def search_scholar_by_title(title, api_key, threshold=0.90):
    search_url = f"https://scholar.google.com/scholar?q={urllib.parse.quote(title)}"
    params = {
        "engine": "google_scholar",
        "q": title,
        "api_key": api_key,
        "num": 3
    }
    try:
        from serpapi import GoogleSearch
        results = GoogleSearch(params).get_dict()
        if "error" in results:
            return search_url, "error"
        organic = results.get("organic_results", [])
        if not organic:
            return search_url, "no_result"
        cleaned_query = clean_title(title)
        for result in organic:
            result_title = result.get("title", "")
            cleaned_result = clean_title(result_title)
            if not cleaned_query or not cleaned_result:
                continue
            if cleaned_query == cleaned_result:
                return search_url, "match"
            if SequenceMatcher(None, cleaned_query, cleaned_result).ratio() >= threshold:
                return search_url, "similar"
        return search_url, "no_result"
    except Exception:
        logger.exception("SerpAPI/Google Scholar error")
        return search_url, "error"

def search_scholar_by_ref_text(ref_text, api_key):
    search_url = f"https://scholar.google.com/scholar?q={urllib.parse.quote(ref_text)}"
    params = {"engine": "google_scholar", "q": ref_text, "api_key": api_key, "num": 1}
    try:
        from serpapi import GoogleSearch
        results = GoogleSearch(params).get_dict()
        organic = results.get("organic_results", [])
        if not organic:
            return search_url, "no_result"
        first_title = organic[0].get("title", "")
        cleaned_ref = clean_title_for_remedial(ref_text)
        cleaned_first = clean_title_for_remedial(first_title)
        if cleaned_first in cleaned_ref or cleaned_ref in cleaned_first:
            return search_url, "remedial"
        return search_url, "no_result"
    except Exception:
        logger.exception("SerpAPI remedial error")
        return search_url, "no_result"
