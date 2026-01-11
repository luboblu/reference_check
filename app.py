# app.py (一鍵報表自動化版 - 標題補強地端版)

import streamlit as st
import pandas as pd
import time
import os
import re
import ast 
from concurrent.futures import ThreadPoolExecutor, as_completed

# 導入自定義模組
from modules.parsers import parse_references_with_anystyle
from modules.local_db import load_csv_data, search_local_database
from modules.api_clients import (
    get_scopus_key,
    get_serpapi_key,
    search_crossref_by_doi,
    search_crossref_by_text,
    search_scopus_by_title,
    search_scholar_by_title,
    search_scholar_by_ref_text,
    search_s2_by_title,
    search_openalex_by_title,
    check_url_availability
)

# ========== 頁面設定與樣式 ==========
st.set_page_config(page_title="引文查核報表工具", page_icon="📊", layout="wide")

st.markdown("""
<style>
    .main-header { font-size: 2.2rem; font-weight: bold; text-align: center; color: #4F46E5; margin-bottom: 5px; }
    .sub-header { text-align: center; color: #6B7280; margin-bottom: 2rem; }
    .status-badge { padding: 4px 10px; border-radius: 12px; font-size: 0.85em; font-weight: bold; }
    .ref-box { background-color: #F9FAFB; padding: 12px; border-radius: 8px; font-family: 'Courier New', monospace; font-size: 0.9em; border: 1px solid #E5E7EB; margin-top: 5px; }
    .report-card { background-color: #FFFFFF; padding: 20px; border-radius: 10px; border: 1px solid #E5E7EB; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
</style>
""", unsafe_allow_html=True)

# ========== Session State ==========
if "results" not in st.session_state: st.session_state.results = []

# ========== [核心工具函數] ==========
def format_name_field(data):
    if not data: return None
    try:
        if isinstance(data, str):
            if not (data.startswith('[') or data.startswith('{')): return data
            try: data = ast.literal_eval(data)
            except: return data
        names_list = []
        data_list = data if isinstance(data, list) else [data]
        for item in data_list:
            if isinstance(item, dict):
                parts = [item.get('family', ''), item.get('given', '')]
                names_list.append(", ".join([p for p in parts if p]))
            else: names_list.append(str(item))
        return "; ".join(names_list)
    except: return str(data)

# --- 這裡已替換為您指定的加強版 refine_parsed_data ---
def refine_parsed_data(parsed_item):
    item = parsed_item.copy()
    raw_text = item.get('text', '').strip()

    # 1. 基礎符號清洗
    for key in ['doi', 'url', 'title', 'date']:
        if item.get(key) and isinstance(item[key], str):
            item[key] = item[key].strip(' ,.;)]}>')

    title = item.get('title', '')
    
    # 2. 標題補救機制
    if not title or len(title) < 5:
        # [Pattern A] 針對 "縮寫: 完整標題" (如 StyleTTS 2)
        abbr_match = re.search(r'^([A-Z0-9\-\.\s]{2,12}:\s*.+?)(?=\s*[,\[]|\s*Available|\s*\(|\bhttps?://|\.|$)', raw_text)
        if abbr_match:
            item['title'] = abbr_match.group(1).strip()
        else:
            # [Pattern B] AnyStyle 誤判為出版商或期刊
            for backup_key in ['publisher', 'container-title', 'journal']:
                val = item.get(backup_key)
                if val and len(str(val)) > 15:
                    item['title'] = str(val).strip()
                    break

        # [Pattern C] 新增補救：年份定位法
        if (not item.get('title') or item['title'] == 'N/A') and item.get('date'):
            year_str = str(item['date'])[0:4] 
            if year_str.isdigit():
                fallback_match = re.search(rf'{year_str}\W+\s*(.+)', raw_text)
                if fallback_match:
                    candidate = fallback_match.group(1).strip()
                    candidate = re.sub(r'(?i)\.?\s*arXiv.*$', '', candidate)
                    candidate = re.sub(r'(?i)\.?\s*Available.*$', '', candidate)
                    
                    if len(candidate) > 5:
                        item['title'] = candidate.strip(' .')

    if item.get('url'):
        doi_match = re.search(r'(10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+)', item['url'])
        if doi_match: item['doi'] = doi_match.group(1).strip('.')

    item['authors'] = format_name_field(item.get('authors'))
    return item

def check_single_task(idx, raw_ref, local_df, target_col, scopus_key, serpapi_key):
    ref = refine_parsed_data(raw_ref)
    title, text = ref.get('title', ''), ref.get('text', '')
    search_query = title if (title and len(title) > 8) else text[:120]
    doi, parsed_url = ref.get('doi'), ref.get('url')
    first_author = ref['authors'].split(';')[0].split(',')[0].strip() if ref.get('authors') else ""

    res = {"id": idx, "title": title, "text": text, "parsed": ref, "sources": {}, "found_at_step": None, "suggestion": None}

    # 1. Local DB
    if bool(re.search(r'[\u4e00-\u9fff]', search_query)) and local_df is not None and title:
        match_row, _ = search_local_database(local_df, target_col, title, threshold=0.85)
        if match_row is not None:
            res.update({"sources": {"Local DB": "匹配成功"}, "found_at_step": "0. Local Database"})
            return res

    # 2. Crossref
    if doi:
        _, url, _ = search_crossref_by_doi(doi, target_title=title if title else None)
        if url: 
            res.update({"sources": {"Crossref": url}, "found_at_step": "1. Crossref (DOI)"})
            return res
    
    url, _ = search_crossref_by_text(search_query, first_author)
    if url:
        res.update({"sources": {"Crossref": url}, "found_at_step": "1. Crossref (Search)"})
        return res

    # 3. Scopus & Others
    if scopus_key:
        url, _ = search_scopus_by_title(search_query, scopus_key)
        if url:
            res.update({"sources": {"Scopus": url}, "found_at_step": "2. Scopus"})
            return res

    for api_func, step_name in [(lambda: search_openalex_by_title(search_query, first_author), "3. OpenAlex"),
                                (lambda: search_s2_by_title(search_query, first_author), "4. Semantic Scholar"),
                                (lambda: search_scholar_by_title(search_query, serpapi_key), "5. Google Scholar")]:
        try:
            url, _ = api_func()
            if url:
                res.update({"sources": {step_name.split(". ")[1]: url}, "found_at_step": step_name})
                return res
        except: pass

    # 4. Suggestion (Scholar Text Search)
    if serpapi_key:
        url_r, _ = search_scholar_by_ref_text(text, serpapi_key, target_title=title)
        if url_r: res["suggestion"] = url_r

    # 5. Website Check
    if parsed_url and parsed_url.startswith('http'):
        if check_url_availability(parsed_url):
            res.update({"sources": {"Direct Link": parsed_url}, "found_at_step": "6. Website / Direct URL"})
        else:
            res.update({"sources": {"Direct Link (Dead)": parsed_url}, "found_at_step": "6. Website (Link Failed)"})
    
    return res

# ========== 側邊欄設定 ==========
with st.sidebar:
    st.header("⚙️ 系統設定")
    DEFAULT_CSV_PATH = "112ndltd.csv"
    local_df, target_col = None, None
    if os.path.exists(DEFAULT_CSV_PATH):
        local_df = load_csv_data(DEFAULT_CSV_PATH)
        if local_df is not None:
            st.success(f"✅ 已載入本地庫: {len(local_df)} 筆")
            target_col = "論文名稱" if "論文名稱" in local_df.columns else local_df.columns[0]
    
    scopus_key = get_scopus_key()
    serpapi_key = get_serpapi_key()
    st.divider()
    st.caption("API 狀態確認:")
    st.write(f"Scopus: {'✅' if scopus_key else '❌'} | SerpAPI: {'✅' if serpapi_key else '❌'}")

# ========== 主頁面流程 ==========
st.markdown('<div class="main-header">📚 學術引用自動化查核報表</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">整合多方資料庫 API，一鍵產出引文驗證結果與下載 CSV</div>', unsafe_allow_html=True)

# 1. 輸入區
st.markdown("### 📥 第一步：輸入引文內容")
raw_input = st.text_area("請直接貼上參考文獻列表：", height=250, placeholder="例如：\nStyleTTS 2: Towards Human-Level Text-to-Speech...\nAIOS: LLM Agent Operating System...")

# 2. 執行區
if st.button("🚀 開始全自動核對並生成報表", type="primary", use_container_width=True):
    if not raw_input:
        st.warning("⚠️ 請先貼上文獻內容再執行。")
    else:
        st.session_state.results = []
        with st.status("🔍 正在進行查核作業...", expanded=True) as status:
            status.write("正在解析引用格式...")
            _, struct_list = parse_references_with_anystyle(raw_input)
            
            if struct_list:
                status.write(f"正在連線各大學術資料庫 (共 {len(struct_list)} 筆)...")
                progress_bar = st.progress(0)
                results_buffer = []
                with ThreadPoolExecutor(max_workers=5) as executor:
                    futures = {executor.submit(check_single_task, i+1, r, local_df, target_col, scopus_key, serpapi_key): i for i, r in enumerate(struct_list)}
                    for i, future in enumerate(as_completed(futures)):
                        results_buffer.append(future.result())
                        progress_bar.progress((i + 1) / len(struct_list))
                
                st.session_state.results = sorted(results_buffer, key=lambda x: x['id'])
                status.update(label="✅ 核對作業完成！", state="complete", expanded=False)
            else:
                st.error("❌ AnyStyle 解析異常，請檢查輸入內容。")

# 3. 報表顯示與下載區
if st.session_state.results:
    st.divider()
    st.markdown("### 📊 第二步：查核結果與報表下載")
    
    # 統計卡片
    total_refs = len(st.session_state.results)
    verified_db = sum(1 for r in st.session_state.results if r.get('found_at_step') and "6." not in r.get('found_at_step'))
    failed_refs = total_refs - verified_db
    
    col1, col2, col3 = st.columns(3)
    col1.metric("總查核筆數", total_refs)
    col2.metric("資料庫匹配成功", verified_db)
    col3.metric("需人工確認/修正", failed_refs, delta_color="inverse")

    # 下載報表（維持原樣）
    df_export = pd.DataFrame([{
        "ID": r['id'],
        "狀態": r['found_at_step'] if r['found_at_step'] else "未找到",
        "抓取標題": r['title'],
        "原始文獻內容": r['text'],
        "驗證來源連結": next(iter(r['sources'].values()), "N/A") if r['sources'] else "N/A"
    } for r in st.session_state.results])

    csv_data = df_export.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        label="📥 下載完整查核報告 (Excel 可開 CSV)",
        data=csv_data,
        file_name=f"Citation_Check_{time.strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
        use_container_width=True
    )

    # ========== 4. 查核清單明細 (新增過濾功能) ==========
    st.markdown("---")
    st.markdown("#### 🔍 查核清單明細")
    
    # 同學要求的五種過濾狀態
    filter_option = st.radio(
        "顯示篩選項目：",
        ["全部顯示", "✅ 資料庫驗證", "🌐 網站有效來源", "⚠️ 網站 (連線失敗)", "❌ 未找到結果"],
        horizontal=True
    )

    # 執行過濾邏輯
    filtered_results = []
    for r in st.session_state.results:
        step = r.get('found_at_step', '')
        if filter_option == "全部顯示":
            filtered_results.append(r)
        elif filter_option == "✅ 資料庫驗證" and step and "6." not in step and "Failed" not in step:
            filtered_results.append(r)
        elif filter_option == "🌐 網站有效來源" and "6." in step and "Failed" not in step:
            filtered_results.append(r)
        elif filter_option == "⚠️ 網站 (連線失敗)" and "Failed" in step:
            filtered_results.append(r)
        elif filter_option == "❌ 未找到結果" and not step:
            filtered_results.append(r)

    # 顯示列表
    if not filtered_results:
        st.info(f"目前沒有符合「{filter_option}」的項目。")
    else:
        for item in filtered_results:
            step = item.get('found_at_step', '')
            # 根據狀態決定圖示
            if not step:
                status_icon = "❌"
            elif "Failed" in step:
                status_icon = "⚠️"
            elif "6." in step:
                status_icon = "🌐"
            else:
                status_icon = "✅"

            with st.expander(f"{status_icon} ID {item['id']}：{item['text'][:80]}..."):
                st.markdown(f"**查核結果：** `{step if step else '資料庫未匹配'}`")
                st.markdown(f"**原始內容：**")
                st.markdown(f"<div class='ref-box'>{item['text']}</div>", unsafe_allow_html=True)
                
                if item['sources']:
                    st.markdown("**來源連結：**")
                    for src, link in item['sources'].items():
                        st.write(f"- {src}: {link}")
                
                if (not step or "Failed" in step) and item.get("suggestion"):
                    st.warning(f"💡 模糊搜尋建議：[請點此手動確認相似文獻]({item['suggestion']})")

else:
    st.info("💡 目前尚無結果。請在上方輸入框貼上文獻，並點擊按鈕開始。")
