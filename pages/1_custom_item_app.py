import pandas as pd
import streamlit as st

from pdf_utils import extract_item_analysis

st.set_page_config(page_title="自定義項目分析", page_icon="📌", layout="wide")
st.title("📌 自定義項目分析 app")
st.caption("此頁會讀取主 app 已處理好的資料。請先回主 app 上載 PDF，並按『處理檔案並啟用自定義分析 app』。")

if "custom_cols" not in st.session_state:
    st.session_state.custom_cols = []
if "col_options_history" not in st.session_state:
    st.session_state.col_options_history = {}
if "item_custom_values" not in st.session_state:
    st.session_state.item_custom_values = {}
if "mcq_custom_values" not in st.session_state:
    st.session_state.mcq_custom_values = {}

st.page_link("app.py", label="⬅️ 返回主 app", icon="⬅️")

if "processed_item_df" not in st.session_state or st.session_state.processed_item_df is None:
    source_pdf_bytes = st.session_state.get("source_pdf_bytes")
    if isinstance(source_pdf_bytes, (bytes, bytearray)) and source_pdf_bytes:
        st.session_state.processed_item_df = extract_item_analysis(source_pdf_bytes)

if "processed_item_df" not in st.session_state or st.session_state.processed_item_df is None:
    st.warning("尚未找到已處理好的項目分析資料。請先回主 app 完成前處理。")
    st.stop()

df_item_c = st.session_state.processed_item_df.copy()
source_name = st.session_state.get("source_pdf_name", "未命名檔案")
st.success(f"已載入主 app 處理完成的資料：{source_name}")

if not df_item_c.empty:
    if "題號" not in df_item_c.columns:
        df_item_c.insert(0, "題號", df_item_c.get("Item", range(1, len(df_item_c) + 1)))

    st.info("Step 1：建立自定義欄位 (最多 6 個)")
    c1, c2 = st.columns([3, 1])
    with c1:
        new_col = st.text_input("輸入新自定義欄位名稱：", key="new_col_input_item")
    with c2:
        st.write("")
        st.write("")
        if st.button("➕ 新增欄位", key="add_col_btn_item"):
            if new_col and new_col not in st.session_state.custom_cols and len(st.session_state.custom_cols) < 6:
                st.session_state.custom_cols.append(new_col)
                st.session_state.col_options_history[new_col] = []
                st.rerun()

    if st.session_state.custom_cols:
        st.success(f"目前建立的欄位：{', '.join(st.session_state.custom_cols)}")

    st.markdown("---")
    st.info("Step 2：為每一題設定分類 (下拉聯想與新增)")

    questions = df_item_c["題號"].tolist()
    sel_q = st.selectbox("選擇要輸入標籤的題號：", questions, key="item_q_sel")
    current_values = st.session_state.item_custom_values.get(sel_q, {})

    with st.container():
        st.write(f"**正在編輯：第 {sel_q} 題**")
        input_results = {}
        for col in st.session_state.custom_cols:
            history_opts = st.session_state.col_options_history.get(col, [])
            options = [""] + history_opts + ["➕ 輸入新文本..."]
            default_idx = 0
            curr_val = current_values.get(col, "")
            if curr_val in options:
                default_idx = options.index(curr_val)
            sel_val = st.selectbox(f"{col}:", options=options, index=default_idx, key=f"sel_item_{col}")
            if sel_val == "➕ 輸入新文本...":
                new_val = st.text_input(f"請輸入新的「{col}」:", key=f"new_val_item_{col}")
                input_results[col] = new_val
            else:
                input_results[col] = sel_val

        submit_btn = st.button("📥 儲存設定", key=f"save_item_{sel_q}")
        if submit_btn:
            if sel_q not in st.session_state.item_custom_values:
                st.session_state.item_custom_values[sel_q] = {}
            for col, val in input_results.items():
                if val:
                    st.session_state.item_custom_values[sel_q][col] = val
                    if val not in st.session_state.col_options_history[col]:
                        st.session_state.col_options_history[col].append(val)
            st.success(f"第 {sel_q} 題設定已儲存！")
            st.rerun()

    df_display = df_item_c.copy()
    for col in st.session_state.custom_cols:
        df_display[col] = df_display["題號"].apply(lambda x: st.session_state.item_custom_values.get(x, {}).get(col, ""))

    st.write("📊 **總覽表 (自動更新)：**")
    st.dataframe(df_display, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.info("Step 3：篩選與排序結果")

    f_cols = st.columns(max(len(st.session_state.custom_cols), 1))
    active_filters = {}
    for i, col in enumerate(st.session_state.custom_cols):
        with f_cols[i]:
            u_vals = [x for x in df_display[col].unique() if str(x).strip()]
            active_filters[col] = st.multiselect(f"篩選 {col}", u_vals, key=f"filter_item_{col}")

    c4, c5 = st.columns([2, 1])
    with c4:
        sort_by = st.selectbox("排序依據", ["預設（按題號）", "Your school Mean %", "Day schools Mean %"], key="sort_item")
    with c5:
        sort_order = st.radio("排序方式", ["由高至低", "由低至高"], horizontal=True, key="order_item")

    final_df = df_display.copy()
    for col, s_filters in active_filters.items():
        if s_filters:
            final_df = final_df[final_df[col].isin(s_filters)]

    if sort_by != "預設（按題號）":
        try:
            final_df[sort_by] = pd.to_numeric(final_df[sort_by], errors='coerce')
            final_df = final_df.sort_values(sort_by, ascending=(sort_order == "由低至高"))
        except:
            pass

    st.dataframe(final_df, use_container_width=True, hide_index=True)
else:
    st.error("找不到可用的項目分析資料。")
