import streamlit as st
import pandas as pd
import pdfplumber
import re
import io

# ==========================================
# 設定頁面配置
# ==========================================
st.set_page_config(page_title="PDF 數據分析工具", layout="wide")

# ==========================================
# 輔助函數與狀態：自定義欄位與選項記憶
# ==========================================
if "custom_columns" not in st.session_state:
    st.session_state.custom_columns = []  # 儲存用戶定義的欄位名稱
if "column_options" not in st.session_state:
    st.session_state.column_options = {}  # 儲存每個欄位歷史輸入過的選項
if "item_custom_data" not in st.session_state:
    st.session_state.item_custom_data = {} # 儲存 {題號: {欄位1: 值1, 欄位2: 值2}}
if "mcq_custom_data" not in st.session_state:
    st.session_state.mcq_custom_data = {} # 儲存 MCQ 的 {題號: {欄位1: 值1}}

def add_custom_column(col_name):
    if col_name and col_name not in st.session_state.custom_columns:
        if len(st.session_state.custom_columns) < 6:
            st.session_state.custom_columns.append(col_name)
            st.session_state.column_options[col_name] = []
        else:
            st.warning("最多只能新增 6 個自定義欄位！")

def update_custom_data(target_dict, q_num, col_name, value):
    # 儲存該題的值
    if q_num not in target_dict:
        target_dict[q_num] = {}
    target_dict[q_num][col_name] = value

    # 將新值加入歷史選項記憶中
    if value and value not in st.session_state.column_options[col_name]:
        st.session_state.column_options[col_name].append(value)

# ==========================================
# 輔助函數：初始化 MCQ 自定義欄位 + 計算最高票
# ==========================================
def prepare_mcq_analysis_for_custom(df):
    df = df.copy()

    def get_top_option(row, prefix):
        opts = {
            "A": row.get(f"{prefix} A_No.", 0),
            "B": row.get(f"{prefix} B_No.", 0),
            "C": row.get(f"{prefix} C_No.", 0),
            "D": row.get(f"{prefix} D_No.", 0),
        }
        for k in opts:
            try:
                opts[k] = float(opts[k])
            except (ValueError, TypeError):
                opts[k] = 0
        return max(opts, key=opts.get)

    df["Your school Top Option"] = df.apply(lambda r: get_top_option(r, "Your school"), axis=1)
    df["Day schools Top Option"] = df.apply(lambda r: get_top_option(r, "Day schools"), axis=1)

    return df

# ==========================================
# 輔助函數：MCQ 高亮規則
# ==========================================
def highlight_mcq_row(row):
    your_top = str(row.get("Your school Top Option", "")).strip()
    day_top = str(row.get("Day schools Top Option", "")).strip()
    corr_ans = str(row.get("Corr. Ans", "")).replace("☑️", "").strip()

    cond1 = (your_top != corr_ans)
    cond2 = (your_top != day_top)

    if cond1 and cond2:
        color = "background-color: #f8d7da"  # 紅
    elif cond1:
        color = "background-color: #fff3cd"  # 黃
    elif cond2:
        color = "background-color: #d1ecf1"  # 藍
    else:
        color = ""

    return [color] * len(row)

# ==========================================
# 提取 PDF 函數 (保留原代碼邏輯)
# ==========================================
def extract_total_analysis(pdf_file):
    with pdfplumber.open(pdf_file) as pdf:
        data = []
        for page in pdf.pages:
            text = page.extract_text()
            if not text: continue

            lines = text.split('\n')
            for line in lines:
                if line.startswith('1 '):
                    parts = line.split()
                    if len(parts) >= 8:
                        data.append({
                            'Item': parts[0],
                            'No. of sat.': parts[1],
                            'Mean Score': parts[2],
                            'Max. Score': parts[3],
                            'Mean %': parts[4],
                            'SD %': parts[5],
                            'Day schools Mean %': parts[6],
                            'Day schools SD %': parts[7]
                        })
        return pd.DataFrame(data)

def extract_item_analysis(pdf_file):
    with pdfplumber.open(pdf_file) as pdf:
        data = []
        for page in pdf.pages:
            text = page.extract_text()
            if not text: continue

            lines = text.split('\n')
            for line in lines:
                if re.match(r'^\d+\s', line):
                    parts = line.split()
                    if len(parts) >= 6:
                        data.append({
                            'Item No': parts[0],
                            'Max Score': parts[1],
                            'Your school Mean Score': parts[2],
                            'Your school Mean %': parts[3],
                            'Day schools Mean Score': parts[4],
                            'Day schools Mean %': parts[5]
                        })
        return pd.DataFrame(data)

def extract_mcq_analysis(pdf_file):
    with pdfplumber.open(pdf_file) as pdf:
        data = []
        for page in pdf.pages:
            text = page.extract_text()
            if not text: continue

            lines = text.split('\n')
            for line in lines:
                if re.match(r'^\d+\s+[A-D]\s+', line):
                    parts = line.split()
                    if len(parts) >= 11:
                        data.append({
                            'Item No': parts[0],
                            'Corr. Ans': parts[1],
                            'Your school A_No.': parts[2],
                            'Your school B_No.': parts[3],
                            'Your school C_No.': parts[4],
                            'Your school D_No.': parts[5],
                            'Day schools A_No.': parts[6],
                            'Day schools B_No.': parts[7],
                            'Day schools C_No.': parts[8],
                            'Day schools D_No.': parts[9],
                            'Omit / Inv.': parts[10] if len(parts) > 10 else "0"
                        })
        return pd.DataFrame(data)

def convert_df_to_excel(df, sheet_name):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    processed_data = output.getvalue()
    return processed_data

# ==========================================
# UI 介面
# ==========================================
st.title("📄 PDF 數據分析與自定義分類工具")

st.markdown("""
**使用說明：**
1. 在下方上傳您的 PDF 檔案。
2. 切換不同的標籤頁 (Tabs) 來查看分析結果或進行自定義分類。
3. 可將結果下載為 Excel 檔案。
""")

global_file = st.file_uploader("📥 請上載 PDF 檔案 | Upload PDF file", type=["pdf"])

tab0, tab1, tab2, tab3, tab4 = st.tabs([
    "📊 總數分析 Total Analysis",
    "📝 項目分析報告 Item Analysis Report",
    "✅ 多項選擇題報告 MCQ Analysis Report",
    "📌 自定義項目分析",
    "🎯 自定義MCQ分析"
])

# -----------------
# 標籤頁 0, 1, 2 (原功能)
# -----------------
with tab0:
    st.subheader("📊 總數分析 | Total Analysis")
    if global_file:
        try:
            global_file.seek(0)
            df0 = extract_total_analysis(global_file)
            st.dataframe(df0, use_container_width=True)
        except Exception as e:
            st.error(f"錯誤: {e}")

with tab1:
    st.subheader("📝 項目分析 | Item Analysis")
    if global_file:
        try:
            global_file.seek(0)
            df1 = extract_item_analysis(global_file)
            st.dataframe(df1, use_container_width=True)
        except Exception as e:
            st.error(f"錯誤: {e}")

with tab2:
    st.subheader("✅ 多項選擇題 | MCQ Analysis")
    if global_file:
        try:
            global_file.seek(0)
            df2 = extract_mcq_analysis(global_file)
            st.dataframe(df2, use_container_width=True)
        except Exception as e:
            st.error(f"錯誤: {e}")

# -----------------
# 標籤頁 3: 自定義項目分析
# -----------------
with tab3:
    st.subheader("📌 自定義項目分析 | Custom Item Analysis")

    if global_file is None:
        st.warning("👆 請先在上載 PDF 檔案")
    else:
        with st.spinner("載入中..."):
            try:
                global_file.seek(0)
                df_item_custom = extract_item_analysis(global_file)

                if not df_item_custom.empty:
                    if "題號" not in df_item_custom.columns:
                        df_item_custom.insert(0, "題號", df_item_custom.get("Item No", range(1, len(df_item_custom) + 1)))

                    st.info("Step 0：建立自定義分類欄位（最多 6 個）")
                    c1, c2 = st.columns([3, 1])
                    with c1:
                        new_col_name = st.text_input("輸入自定義欄位名稱：", key="new_col_item")
                    with c2:
                        st.write("") 
                        st.write("")
                        if st.button("➕ 新增欄位", key="btn_add_col_item"):
                            add_custom_column(new_col_name)
                            st.rerun()

                    if st.session_state.custom_columns:
                        st.success(f"目前欄位：{', '.join(st.session_state.custom_columns)}")
                        st.markdown("---")

                        st.info("Step 1：為每一題設定分類")
                        q_nums = df_item_custom["題號"].tolist()
                        selected_q = st.selectbox("選擇要定義的題號：", q_nums, key="sel_q_item")
                        current_q_data = st.session_state.item_custom_data.get(selected_q, {})

                        with st.form(key=f"form_item_{selected_q}"):
                            st.write(f"**正在編輯：第 {selected_q} 題**")
                            input_results = {}
                            for col in st.session_state.custom_columns:
                                options = [""] + st.session_state.column_options[col] + ["➕ 新增..."]
                                default_idx = options.index(current_q_data.get(col)) if current_q_data.get(col) in options else 0
                                selected_val = st.selectbox(f"{col}：", options=options, index=default_idx, key=f"sel_item_{col}_{selected_q}")

                                if selected_val == "➕ 新增...":
                                    new_val = st.text_input(f"輸入新的「{col}」：", key=f"new_item_{col}_{selected_q}")
                                    input_results[col] = new_val
                                else:
                                    input_results[col] = selected_val

                            if st.form_submit_button("💾 儲存此題設定"):
                                for col, val in input_results.items():
                                    if val: 
                                        update_custom_data(st.session_state.item_custom_data, selected_q, col, val)
                                st.success("設定已儲存！")
                                st.rerun()

                        for col in st.session_state.custom_columns:
                            df_item_custom[col] = df_item_custom["題號"].apply(
                                lambda x: st.session_state.item_custom_data.get(x, {}).get(col, "")
                            )

                        st.write("📊 **目前所有題目的分類總覽：**")
                        st.dataframe(df_item_custom, use_container_width=True, hide_index=True)
                        st.markdown("---")

                        st.info("Step 2：篩選與排序")
                        filter_cols = st.columns(max(len(st.session_state.custom_columns), 1))
                        active_filters = {}
                        for i, col in enumerate(st.session_state.custom_columns):
                            with filter_cols[i]:
                                unique_vals = [x for x in df_item_custom[col].unique() if x]
                                active_filters[col] = st.multiselect(f"篩選 {col}", unique_vals, key=f"filter_item_{col}")

                        c4, c5 = st.columns([2, 1])
                        with c4:
                            sort_by = st.selectbox("排序依據", ["預設（按題號）", "Your school Mean %", "Day schools Mean %"], key="sort_by_item")
                        with c5:
                            sort_order = st.radio("排序方式", ["由高至低", "由低至高"], horizontal=True, key="sort_order_item")

                        filtered_item_df = df_item_custom.copy()
                        for col, s_filters in active_filters.items():
                            if s_filters:
                                filtered_item_df = filtered_item_df[filtered_item_df[col].isin(s_filters)]

                        if sort_by != "預設（按題號）":
                            ascending = (sort_order == "由低至高")
                            try:
                                filtered_item_df[sort_by] = pd.to_numeric(filtered_item_df[sort_by], errors='coerce')
                            except: pass
                            filtered_item_df = filtered_item_df.sort_values(sort_by, ascending=ascending)

                        st.subheader("📋 最終分析結果")
                        st.dataframe(filtered_item_df, use_container_width=True, hide_index=True)

                        st.download_button(
                            label="📥 下載自定義項目分析 Excel",
                            data=convert_df_to_excel(filtered_item_df, "Custom Item Analysis"),
                            file_name="Custom_Item_Analysis.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="btn_dl_item"
                        )
            except Exception as e:
                st.error(f"錯誤：{str(e)}")

# -----------------
# 標籤頁 4: 自定義 MCQ 分析
# -----------------
with tab4:
    st.subheader("🎯 自定義MCQ分析 | Custom MCQ Analysis")

    if global_file is None:
        st.warning("👆 請先在上載 PDF 檔案")
    else:
        with st.spinner("載入中..."):
            try:
                global_file.seek(0)
                df_mcq_custom = extract_mcq_analysis(global_file)

                if not df_mcq_custom.empty:
                    df_mcq_custom = prepare_mcq_analysis_for_custom(df_mcq_custom)

                    if "題號" not in df_mcq_custom.columns:
                        df_mcq_custom.insert(0, "題號", df_mcq_custom.get("Item No", range(1, len(df_mcq_custom) + 1)))

                    st.info("Step 0：建立自定義分類欄位（與 Tab 3 共用名稱與歷史選項）")
                    c1, c2 = st.columns([3, 1])
                    with c1:
                        new_col_name_mcq = st.text_input("輸入自定義欄位名稱：", key="new_col_mcq")
                    with c2:
                        st.write("")
                        st.write("")
                        if st.button("➕ 新增欄位", key="btn_add_col_mcq"):
                            add_custom_column(new_col_name_mcq)
                            st.rerun()

                    if st.session_state.custom_columns:
                        st.success(f"目前欄位：{', '.join(st.session_state.custom_columns)}")
                        st.markdown("---")

                        st.info("Step 1：為每一題設定分類")
                        q_nums_mcq = df_mcq_custom["題號"].tolist()
                        selected_q_mcq = st.selectbox("選擇要定義的題號：", q_nums_mcq, key="sel_q_mcq")
                        current_q_data_mcq = st.session_state.mcq_custom_data.get(selected_q_mcq, {})

                        with st.form(key=f"form_mcq_{selected_q_mcq}"):
                            st.write(f"**正在編輯：第 {selected_q_mcq} 題**")
                            input_results_mcq = {}
                            for col in st.session_state.custom_columns:
                                options = [""] + st.session_state.column_options[col] + ["➕ 新增..."]
                                default_idx = options.index(current_q_data_mcq.get(col)) if current_q_data_mcq.get(col) in options else 0
                                selected_val = st.selectbox(f"{col}：", options=options, index=default_idx, key=f"sel_mcq_{col}_{selected_q_mcq}")

                                if selected_val == "➕ 新增...":
                                    new_val = st.text_input(f"輸入新的「{col}」：", key=f"new_mcq_{col}_{selected_q_mcq}")
                                    input_results_mcq[col] = new_val
                                else:
                                    input_results_mcq[col] = selected_val

                            if st.form_submit_button("💾 儲存此題設定"):
                                for col, val in input_results_mcq.items():
                                    if val:
                                        update_custom_data(st.session_state.mcq_custom_data, selected_q_mcq, col, val)
                                st.success("設定已儲存！")
                                st.rerun()

                        for col in st.session_state.custom_columns:
                            df_mcq_custom[col] = df_mcq_custom["題號"].apply(
                                lambda x: st.session_state.mcq_custom_data.get(x, {}).get(col, "")
                            )

                        st.write("📊 **目前所有題目的分類總覽：**")
                        st.dataframe(df_mcq_custom, use_container_width=True, hide_index=True)
                        st.markdown("---")

                        st.info("Step 2：篩選與高亮分析結果")
                        filter_cols = st.columns(max(len(st.session_state.custom_columns), 1))
                        active_filters_mcq = {}
                        for i, col in enumerate(st.session_state.custom_columns):
                            with filter_cols[i]:
                                unique_vals = [x for x in df_mcq_custom[col].unique() if x]
                                active_filters_mcq[col] = st.multiselect(f"篩選 {col}", unique_vals, key=f"filter_mcq_{col}")

                        filtered_mcq_df = df_mcq_custom.copy()
                        for col, s_filters in active_filters_mcq.items():
                            if s_filters:
                                filtered_mcq_df = filtered_mcq_df[filtered_mcq_df[col].isin(s_filters)]

                        st.markdown("""
                        <div style='background-color:#f8f9fa; padding:12px; border-radius:8px; margin-bottom:12px;'>
                            <b>顏色說明：</b><br>
                            <span style='background-color:#fff3cd; padding:2px 6px;'>黃色</span>：
                            Your school 最高票選項 ≠ Corr. Ans<br>
                            <span style='background-color:#d1ecf1; padding:2px 6px;'>藍色</span>：
                            Your school 最高票選項 ≠ Day schools 最高票選項<br>
                            <span style='background-color:#f8d7da; padding:2px 6px;'>紅色</span>：
                            以上兩者同時成立
                        </div>
                        """, unsafe_allow_html=True)

                        st.subheader("📋 分析結果")
                        st.dataframe(
                            filtered_mcq_df.style.apply(highlight_mcq_row, axis=1),
                            use_container_width=True,
                            hide_index=True
                        )

                        st.download_button(
                            label="📥 下載自定義MCQ分析 Excel",
                            data=convert_df_to_excel(filtered_mcq_df, "Custom MCQ Analysis"),
                            file_name="Custom_MCQ_Analysis.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="btn_dl_mcq"
                        )
            except Exception as e:
                st.error(f"錯誤：{str(e)}")
