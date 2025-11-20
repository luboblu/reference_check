# modules/gemini_client.py

import streamlit as st
import google.generativeai as genai
import json
import re

# --- 金鑰管理 ---
def get_gemini_key():
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
            'gemini-2.5-flash',
            safety_settings=safety_settings,
            generation_config=generation_config
        )
        return model
    except Exception as e:
        st.error(f"❌ 初始化 Gemini 模型失敗：{e}")
        st.stop()

# --- 核心 Prompt ---
PROMPT_PARSE_REFERENCES = """
你是一個精確的學術引用解析器。我將提供一段從 PDF/Word 提取的參考文獻原始文本，其中可能包含錯誤的換行。

你的任務是：
1. 將跨越多行的引用合併為單一條目。
2. 識別每一筆獨立的參考文獻。
3. 對於每一筆文獻，提取以下欄位：
   - "text": 完整的參考文獻字符串。
   - "title": 文獻標題，若無正式標題請使用主要描述。
   - "authors": 文獻的作者列表或主要作者。
   - "venue": 文獻出現的期刊名稱或研討會名稱，如果找不到則為 null。
   - "year": 文獻發表年份，如果找不到則為 null。
   - "doi": 文獻的 DOI (如果沒有則為 null)。
   - "url": 文獻的主要 URL (如果沒有則為 null)。
   - "style": 文獻類型，只允許以下四種："Journal Article", "Conference Paper", "Website", "Other"。
   - "citation_format": 文獻引用格式，判斷是 APA、IEEE、Chicago、MLA 或 Other。
4. 請以 JSON 陣列的形式返回所有獨立參考文獻物件。

這是原始文本：
---
{reference_text}
---
"""

def parse_document_with_gemini(model, paragraphs):
    """
    單階段解析參考文獻段落為結構化資料。
    
    返回: (list[dict] | None, str) -> (解析結果, 除錯訊息)
    """
    reference_text = "\n".join(paragraphs)

    try:
        prompt = PROMPT_PARSE_REFERENCES.format(reference_text=reference_text)
        response = model.generate_content(prompt)
        clean_json_text = re.sub(r'```json\n(.*?)\n```', r'\1', response.text, flags=re.DOTALL)

        parsed_refs = json.loads(clean_json_text)

        if isinstance(parsed_refs, list) and len(parsed_refs) > 0:
            return parsed_refs, "解析成功"
        else:
            return None, "Gemini 返回了空的或無效的 JSON 列表。"

    except json.JSONDecodeError:
        return None, f"Gemini 返回了無效的 JSON 格式。原始回應：\n{response.text}"
    except Exception as e:
        return None, f"Gemini 呼叫失敗: {e}"
