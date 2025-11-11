# modules/gemini_client.py

import streamlit as st
import google.generativeai as genai
import time
import json
import re

# --- 金鑰管理 ---
def get_gemini_key():
    """從 Streamlit secrets 或本地檔案獲取 Gemini API 金鑰"""
    try:
        return st.secrets["gemini_api_key"]
    except (KeyError, FileNotFoundError):
        try:
            with open("gemini_key.txt", "r") as f:
                return f.read().strip()
        except FileNotFoundError:
            st.error("❌ 找不到 Gemini API 金鑰，請確認已設定 secrets 或提供 gemini_key.txt")
            st.stop()

def get_gemini_model():
    """初始化並返回 Gemini Pro 模型實例"""
    try:
        api_key = get_gemini_key()
        genai.configure(api_key=api_key)
        
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        
        generation_config = {
            "response_mime_type": "application/json",
        }
        
        model = genai.GenerativeModel(
            'gemini-2.5-flash', # 使用 Free Tier 支援的 Flash 模型
            safety_settings=safety_settings,
            generation_config=generation_config
        )
        return model
    except Exception as e:
        st.error(f"❌ 初始化 Gemini 模型失敗：{e}")
        st.stop()

# --- 核心 Prompt ---

# 任務 1: 從全文中找出參考文獻區段
PROMPT_TASK_1_LOCATE = """
你是一個學術文件解析器。你的任務是從以下提供的文件全文段落中，準確找到「參考文獻」(References) 區段的起始位置。

規則：
1. 參考文獻區段通常在文件的最後 30%。
2. 區段標題可能是 "References", "參考文獻", "REFERENCE", "Bibliography" 等。
3. 你的**唯一**輸出必須是參考文獻區段（包含其標題）之後的所有原始文本。
4. 如果找不到，請返回空字符串。

這是文件段落 (使用 "---" 分隔)：
---
{full_text}
---
"""

# [!!! 修改這裡 !!!]
# 任務 2 & 3: 解析參考文獻區段為結構化 JSON
PROMPT_TASK_2_PARSE = """
你是一個精確的學術引用解析器。我將提供一段從 PDF/Word 提取的參考文獻原始文本，其中可能包含錯誤的換行。

你的任務是：
1. 閱讀所有文本，將跨越多行的引用合併為一個單一的條目。
2. 識別每一筆獨立的參考文獻。
3. 對於**每一筆**文獻，提取以下五個欄位：
    - "text": 完整的參考文獻字符串（合併換行後）。
    - "title": 該文獻的標題。對於沒有正式標題的網站，請使用其主要描述 (例如 "clumsy, an utility...")。
    - "doi": 該文獻的 DOI (如果沒有則為 null)。
    - "url": 該文獻的主要 URL (例如來自 "Available: ..." 或 "https://...") (如果沒有則為 null)。
    - "style": 偵測到的格式。範例："Journal Article", "Conference Paper", "Website", "Book", "Report", "Unknown"。
4. 最終，以一個 JSON 陣列 (array) 的形式返回所有獨立的參考文獻物件。

這是原始文本：
---
{reference_text}
---
"""

def parse_document_with_gemini(model, paragraphs):
    """
    使用 Gemini 執行兩階段解析：
    1. 找出參考文獻區段 (Task 1)
    2. 解析該區段為結構化資料 (Task 2+3)
    
    返回: (list[dict] | None, str) -> (解析結果, 除錯訊息)
    """
    
    # --- 階段 1：定位參考文獻區段 ---
    total_paras = len(paragraphs)
    start_index = max(0, int(total_paras * 0.6))
    search_text = "\n---\n".join(paragraphs[start_index:])
    
    try:
        prompt1 = PROMPT_TASK_1_LOCATE.format(full_text=search_text)
        response1 = model.generate_content(prompt1)
        refs_raw_text = response1.text.strip()
        
        if not refs_raw_text:
            return None, "Gemini 未能定位到參考文獻區段。"
            
    except Exception as e:
        return None, f"Gemini 呼叫失敗 (階段 1): {e}"

    # --- 階段 2：解析參考文獻 ---
    try:
        prompt2 = PROMPT_TASK_2_PARSE.format(reference_text=refs_raw_text)
        response2 = model.generate_content(prompt2)
        
        clean_json_text = re.sub(r'```json\n(.*?)\n```', r'\1', response2.text, flags=re.DOTALL)
        
        parsed_refs = json.loads(clean_json_text)
        
        if isinstance(parsed_refs, list) and len(parsed_refs) > 0:
            return parsed_refs, "解析成功"
        else:
            return None, "Gemini 返回了空的或無效的 JSON 列表。"

    except json.JSONDecodeError:
        return None, f"Gemini 返回了無效的 JSON 格式。原始回應：\n{response2.text}"
    except Exception as e:
        return None, f"Gemini 呼叫失敗 (階段 2): {e}"