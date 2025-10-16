import re
from typing import List
from .year_rules import find_apa_matches, find_apalike_matches

def detect_reference_style(ref_text: str) -> str:
    if re.match(r'^\[\d+\]', ref_text) or '"' in ref_text:
        return "IEEE"
    if find_apa_matches(ref_text):
        return "APA"
    if find_apalike_matches(ref_text):
        return "APA_LIKE"
    return "Unknown"

def is_reference_head(para: str) -> bool:
    if find_apa_matches(para):
        return True
    if re.match(r'^\[\d+\]', para.strip()):
        return True
    if re.match(r'^\d{1,3}[.)、．]\s+', para.strip()):
        if len(para.strip()) > 25:
            return True
    if find_apalike_matches(para):
        return True
    return False

def detect_and_split_ieee(paragraphs: List[str]) -> List[str] or None:
    if not paragraphs:
        return None
    first_line = paragraphs[0].strip()
    if not re.match(r'^\[\d+\]', first_line):
        return None
    full_text = ' '.join(paragraphs)
    refs = re.split(r'(?=\[\d+\])', full_text)
    return [r.strip() for r in refs if r.strip()]

def split_multiple_apa_in_paragraph(paragraph: str) -> List[str]:
    apa_matches = find_apa_matches(paragraph)
    apalike_matches = find_apalike_matches(paragraph)
    all_matches = apa_matches + apalike_matches
    all_matches.sort(key=lambda m: m.start())
    if len(all_matches) < 2:
        return [paragraph]
    split_indices = []
    for match in all_matches[1:]:
        cut_index = max(0, match.start() - 5)
        split_indices.append(cut_index)
    segments = []
    start = 0
    for idx in split_indices:
        segments.append(paragraph[start:idx].strip())
        start = idx
    segments.append(paragraph[start:].strip())
    return [s for s in segments if s]

def merge_references_by_heads(paragraphs: List[str]) -> List[str]:
    merged = []
    for para in paragraphs:
        apa_count = 1 if find_apa_matches(para) else 0
        apalike_count = len(find_apalike_matches(para))
        if apa_count >= 2 or apalike_count >= 2:
            sub_refs = split_multiple_apa_in_paragraph(para)
            merged.extend([s.strip() for s in sub_refs if s.strip()])
        else:
            if is_reference_head(para):
                merged.append(para.strip())
            else:
                if merged:
                    merged[-1] += " " + para.strip()
                else:
                    merged.append(para.strip())
    return merged
