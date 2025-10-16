import re
from typing import List, Tuple
from .style_detector import detect_and_split_ieee, merge_references_by_heads

APPENDIX_REGEX = re.compile(
    r'^([【〔（(]?\\s*)?((\\d+|[IVXLCDM]+|[一二三四五六七八九十壹貳參肆伍陸柒捌玖拾]+)[、．. ]?)?\\s*(附錄|APPENDIX)(\\s*[】〕）)]?)?$',
    re.IGNORECASE
)

def is_appendix_heading(text: str) -> bool:
    text = (text or "").strip()
    return bool(APPENDIX_REGEX.match(text))

def clip_until_stop(paragraphs_after: List[str]) -> List[str]:
    result = []
    for para in paragraphs_after:
        if is_appendix_heading(para):
            break
        result.append(para)
    return result

def extract_reference_section_from_bottom(paragraphs: List[str], start_keywords: List[str]=None) -> Tuple[List[str], str]:
    if start_keywords is None:
        start_keywords = [
            "參考文獻", "參考資料", "references", "reference",
            "bibliography", "works cited", "literature cited",
            "references and citations"
        ]
    for i in reversed(range(len(paragraphs))):
        para = paragraphs[i].strip()
        if len(para) > 30 or re.search(r'[.,;:]', para):
            continue
        normalized = para.lower()
        if normalized in start_keywords:
            result = []
            for p in paragraphs[i + 1:]:
                if is_appendix_heading(p):
                    break
                result.append(p)
            return result, para
    return [], None

def extract_reference_section_improved(paragraphs: List[str]) -> Tuple[List[str], str, str]:
    def is_reference_format(text: str) -> bool:
        text = text.strip()
        if len(text) < 10:
            return False
        if re.search(r'\\(\\d{4}[a-c]?\\)', text):
            return True
        if re.match(r'^\\[\\d+\\]', text):
            return True
        if re.search(r'[A-Z][a-z]+,\\s*[A-Z]\\.', text):
            return True
        return False

    reference_keywords = [
        "參考文獻", "references", "reference",
        "bibliography", "works cited", "literature cited",
        "references and citations", "參考文獻格式"
    ]

    for i in reversed(range(len(paragraphs))):
        para = paragraphs[i].strip()
        para_lower = para.lower()

        if para_lower in reference_keywords:
            return clip_until_stop(paragraphs[i + 1:]), para, "純標題識別（底部）"

        if re.match(
            r'^((第?[一二三四五六七八九十百千萬壹貳參肆伍陸柒捌玖拾佰仟萬]+章[、．.︑,，]?)|(\\d+|[IVXLCDM]+|[一二三四五六七八九十壹貳參肆伍陸柒捌玖拾]+)?[、．.︑,， ]?)?\\s*(參考文獻|參考資料|references?|bibliography|works cited|literature cited|references and citations)\\s*$',
            para_lower
        ):
            return clip_until_stop(paragraphs[i + 1:]), para.strip(), "章節標題識別（底部）"

        fuzzy_keywords = ["reference", "參考", "bibliography", "文獻", " REFERENCES AND CITATIONS"]
        if any(para_lower.strip() == k for k in fuzzy_keywords):
            if i + 1 < len(paragraphs):
                next_paras = paragraphs[i+1:i+6]
                if sum(1 for p in next_paras if is_reference_format(p)) >= 1:
                    return clip_until_stop(paragraphs[i + 1:]), para.strip(), "模糊標題+內容識別"

    last_idx = None
    for i in reversed(range(len(paragraphs))):
        if is_reference_format(paragraphs[i]):
            last_idx = i
            break
    if last_idx is not None:
        section = clip_until_stop(paragraphs[last_idx:])
        return section, paragraphs[last_idx], "bottom_guess_by_format"

    return [], None, "未找到參考文獻區段"

def post_process_pdf_references(paragraphs: List[str]) -> List[str]:
    ieee_split = detect_and_split_ieee(paragraphs)
    if ieee_split:
        return ieee_split
    return merge_references_by_heads(paragraphs)
