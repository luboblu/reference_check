import re
from typing import List

def is_valid_year(year_str: str) -> bool:
    try:
        year = int(year_str[:4])
        return 1000 <= year <= 2050
    except Exception:
        return False

APA_PATTERN = re.compile(r'[（(](\d{4}[a-c]?|n\.d\.)[）)]?[。\.]?', re.IGNORECASE)

def find_apa_matches(ref_text: str) -> List[re.Match]:
    matches = []
    for m in re.finditer(APA_PATTERN, ref_text):
        year_str = m.group(1)[:4]
        year_pos = m.start(1)
        pre_context = ref_text[max(0, year_pos - 5):year_pos]
        if re.search(r'\d', pre_context):
            continue
        if year_str.isdigit() and is_valid_year(year_str):
            matches.append(m)
        elif m.group(1).lower() == "n.d.":
            matches.append(m)
    return matches

def find_apalike_matches(ref_text: str) -> List[re.Match]:
    matches = []
    pattern1 = re.compile(r'[,，.。]\\s*(\\d{4}[a-c]?)[.。，]', re.IGNORECASE)
    for m in re.finditer(pattern1, ref_text):
        year_str = m.group(1)
        year_pos = m.start(1)
        year_core = year_str[:4]
        if not is_valid_year(year_core):
            continue
        pre_context = ref_text[max(0, year_pos - 5):year_pos]
        if re.search(r'\\d', pre_context):
            continue
        after_context = ref_text[m.end(1):m.end(1) + 5]
        if re.match(r'\\.(\\d{1,2}|[a-z0-9]{2,})', after_context, re.IGNORECASE):
            continue
        arxiv_pattern = re.compile(
            r'arxiv:\\d{4}\\.\\d{5}[^a-zA-Z0-9]{0,3}\\s*[,，]?\\s*' + re.escape(year_str),
            re.IGNORECASE
        )
        if arxiv_pattern.search(ref_text) and arxiv_pattern.search(ref_text).start() < year_pos:
            continue
        matches.append(m)

    pattern2 = re.compile(r'，\\s*(\\d{4}[a-c]?)\\s*，\\s*。')
    for m in re.finditer(pattern2, ref_text):
        year_str = m.group(1)
        year_pos = m.start(1)
        year_core = year_str[:4]
        pre_context = ref_text[max(0, year_pos - 5):year_pos]
        if re.search(r'\\d', pre_context):
            continue
        if is_valid_year(year_core):
            matches.append(m)

    return matches

def match_apa_title_section(ref_text: str):
    return re.search(
        r'[（(](\\d{4}[a-c]?|n\\.d\\.)[）)]\\s*[\\.,，。]?\\s*(.+?)(?:(?<!\\d)[,，.。](?!\\d)|$)',
        ref_text,
        re.IGNORECASE
    )

def match_apalike_title_section(ref_text: str):
    match = re.search(
        r'[,，.。]\\s*(\\d{4}[a-c]?)(?:[.。，])+\\s*(.*?)(?:(?<!\\d)[,，.。](?!\\d)|$)',
        ref_text
    )
    if match:
        return match
    return re.search(
        r'，\\s*(\\d{4}[a-c]?)\\s*，\\s*。[ \\t]*(.+?)(?:[，。]|$)',
        ref_text
    )
