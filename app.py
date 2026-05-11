
import streamlit as st
import pandas as pd
import pdfplumber
import re
import io
import os

# ==========================================
# 設定頁面配置
# ==========================================
st.set_page_config(page_title="HKDSE Statistical Report Data Converter", page_icon="📊", layout="wide")

st.title("📊 HKDSE 統計報告數據轉換器")
st.markdown("這是一個將考評局發佈的 PDF 報告轉換為 Excel 數據表的工具，方便直接貼入 CUHK QSIP 的分析表內。")

st.markdown("---")
st.subheader("1️⃣ 上傳檔案 | Upload File")
global_file = st.file_uploader("請上傳需要轉換的 PDF 檔案", type=["pdf"], key="global_file")
st.caption("⚠️ 支援的檔案類型：考評局下發的 PDF 報告。")

st.markdown("---")
st.subheader("2️⃣ 選擇分析模式 | Select Analysis Mode")

# ==========================================
# 提取函數
# ==========================================
@st.cache_data
def extract_item_analysis(file_bytes):
    row_pattern = re.compile(r'^\s*\d+\s+.*?\d+\.\d+\s+\d+\.\d+\s*$')
    extracted_data = []

    with pdfplumber.open(file_bytes) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for line in text.split('\n'):
                clean_line = ' '.join(line.split())
                match = row_pattern.search(clean_line)

                if match:
                    extracted_data.append(match.group().split())

    columns = [
        'Item', 'Max Mark', 
        'Your school Attm. No.', 'Your school Attem. %', 'Your school Mean', 'Your school Mean %', 'Your school SD',
        'Day schools Attem. %', 'Day schools Mean', 'Day schools Mean %', 'Day schools SD'
    ]
    df = pd.DataFrame(extracted_data, columns=columns)

    numeric_cols = ['Max Mark', 'Your school Attm. No.', 'Your school Attem. %', 'Your school Mean', 'Your school SD',
                    'Day schools Attem. %', 'Day schools Mean', 'Day schools SD']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    pct_cols = ['Your school Mean %', 'Day schools Mean %']
    for col in pct_cols:
        df[col] = df[col].str.replace('%', '').astype(float) / 100

    return df

@st.cache_data
def extract_mcq_analysis(file_bytes):
    mcq_data = []
    with pdfplumber.open(file_bytes) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            lines = text.split('\n')
            current_question = None
            correct_answer = None
            question_answers = {}

            for line in lines:
                q_match = re.match(r'^(\d+)\s*\(v\)\s*x', line.strip())
                if q_match:
                    if current_question and question_answers:
                        row = {
                            'Question Number': current_question,
                            'Corr. Ans': correct_answer
                        }
                        for opt in ['A', 'B', 'C', 'D']:
                            row[f'Your school {opt}_No.'] = question_answers.get(f'{opt}_your', 0)
                            row[f'Day schools {opt}_No.'] = question_answers.get(f'{opt}_day', 0)
                        mcq_data.append(row)

                    current_question = q_match.group(1)
                    question_answers = {}
                    correct_answer = None

                answer_match = re.match(r'^([A-D])(☑️)?\s+(\d+\.\d+)\s*,\s+(\d+\.\d+)', line.strip())
                if answer_match and current_question:
                    option = answer_match.group(1)
                    has_marker = answer_match.group(2) is not None
                    your_no = answer_match.group(3)
                    day_no = answer_match.group(4).replace(',', '')

                    if has_marker:
                        correct_answer = option

                    question_answers[f'{option}_your'] = your_no
                    question_answers[f'{option}_day'] = day_no

            if current_question and question_answers:
                row = {
                    'Question Number': current_question,
                    'Corr. Ans': correct_answer
                }
                for opt in ['A', 'B', 'C', 'D']:
                    row[f'Your school {opt}_No.'] = question_answers.get(f'{opt}_your', 0)
                    row[f'Day schools {opt}_No.'] = question_answers.get(f'{opt}_day', 0)
                mcq_data.append(row)

    df = pd.DataFrame(mcq_data)
    if not df.empty:
        column_order = [
            'Question Number', 'Corr. Ans',
            'Your school A_No.', 'Your school B_No.', 'Your school C_No.', 'Your school D_No.',
            'Day schools A_No.', 'Day schools B_No.', 'Day schools C_No.', 'Day schools D_No.'
        ]
        df = df[column_order]

        for col in df.columns:
            if '_No.' in col:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)

    return df

@st.cache_data
def extract_latest_dse_total_data(file_bytes):
    target_grades = ['5**', '5*', '5', '4', '3', '2', '1', 'UNCL', 'Sat']
    results = []
    subject_name = ""
    exam_year = ""

    with pdfplumber.open(file_bytes) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            if '香港考試及評核局' in text and '統計報告' in text and '5**' in text:
                lines = text.split('\n')
                in_total_section = False

                for i, line in enumerate(lines):
                    if 'HKDSE 20' in line and not exam_year:
                        exam_year = line.replace('HKDSE', '').strip()

                    for i, line in enumerate(lines):
                        if 'Total' in line or '總數' in line and not subject_name:
                            if i >= 2 and 'Category' not in lines[i-2] and '甲類' not in lines[i-2] and not results:
                                subject_name = lines[i-2].strip()
                            elif i >= 1:
                                subject_name = lines[i-1].strip()

                    for line in lines:
                        if 'Total' in line or '總數' in line:
                            in_total_section = True
                        elif 'Male' in line or 'Female' in line:
                            in_total_section = False

                        if in_total_section:
                            clean_line = line.replace(',', '')

                            for grade in target_grades:
                                if clean_line.startswith(grade):
                                    parts = clean_line.split(grade)
                                    if len(parts) >= 3:
                                        ys_numbers = parts[1].strip().split()
                                        ds_numbers = parts[2].strip().split()

                                        if ys_numbers and ds_numbers:
                                            if not any(r[0] == grade for r in results):
                                                results.append((grade, int(ys_numbers[-1]), int(ds_numbers[-1])))
                                                break

                if len(results) == len(target_grades):
                    break

    df = pd.DataFrame(results, columns=['等級', 'Your school (Cum. %)', 'Day schools (Cum. %)'])

    if not df.empty:
        df['等級'] = pd.Categorical(df['等級'], categories=target_grades, ordered=True)
        df = df.sort_values('等級').reset_index(drop=True)

    return df, subject_name, exam_year

def convert_df_to_excel(df, sheet_name):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return output.getvalue()

# ==========================================
# 輔助函數：MCQ 高亮與準備
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

def highlight_mcq_row(row):
    your_top = str(row.get("Your school Top Option", "")).strip()
    day_top = str(row.get("Day schools Top Option", "")).strip()
    corr_ans = str(row.get("Corr. Ans", "")).replace("☑️", "").strip()

    cond1 = (your_top != corr_ans)
    cond2 = (your_top != day_top)

    if cond1 and cond2:
        return ["background-color: #f8d7da"] * len(row)
    elif cond1:
        return ["background-color: #fff3cd"] * len(row)
    elif cond2:
        return ["background-color: #d1ecf1"] * len(row)
    else:
        return [""] * len(row)

# 初始化外置輸入區的狀態
if "custom_cols" not in st.session_state:
    st.session_state.custom_cols = []
if "col_options_history" not in st.session_state:
    st.session_state.col_options_history = {} # 記錄曾經輸入過的文本
if "item_custom_values" not in st.session_state:
    st.session_state.item_custom_values = {} # 記錄 {題號: {欄位: 值}}
if "mcq_custom_values" not in st.session_state:
    st.session_state.mcq_custom_values = {}

tab0, tab1, tab2, tab3, tab4 = st.tabs(["📊 總數分析 Total Analysis", "📝 項目分析報告 Item Analysis Report", "✅ 多項選擇題報告 MCQ Analysis Report", "📌 自定義項目分析", "🎯 自定義MCQ分析"])

# -----------------
# 標籤頁 0, 1, 2
# -----------------
with tab0:
    st.subheader("📊 總數分析轉換器 | Total Analysis Converter")
    col_t1, col_t2 = st.columns([2, 5])

    with col_t1:
        st.info("💡 適用報告：含有「5**... Sat」統計表的數據。")
        if os.path.exists("example_3_main.png"):
            st.image("example_3_main.png", caption="Example of Total Table", use_column_width=True)

    with col_t2:
        if global_file is None:
            st.warning("👆 請先在上方上傳 PDF 檔案 | Please upload a PDF file above first.")
        else:
            with st.spinner("⏳ 正在處理檔案，請稍候..."):
                try:
                    global_file.seek(0)
                    df_total, subject_name, exam_year = extract_latest_dse_total_data(global_file)

                    if df_total.empty:
                        st.error("❌ 無法提取數據！")
                    else:
                        st.success(f"✅ 提取成功！科目：{subject_name} ({exam_year})")
                        st.subheader(f"📋 數據預覽")

                        with st.expander("📝 點擊展開可供快速複製的欄位 | Excel Quick Copy Columns"):
                            c1, c2 = st.columns(2)
                            with c1:
                                st.caption("Your school")
                                ys_text = '\n'.join(df_total['Your school (Cum. %)'].astype(str).tolist())
                                st.code(ys_text, language='text')
                            with c2:
                                st.caption("Day schools")
                                ds_text = '\n'.join(df_total['Day schools (Cum. %)'].astype(str).tolist())
                                st.code(ds_text, language='text')

                        st.table(df_total.style.format(precision=2))
                except Exception as e:
                    st.error(f"❌ 處理檔案時發生錯誤：{str(e)}")

with tab1:
    st.subheader("📝 項目分析轉換器 | Item Analysis Converter")
    col1, col2 = st.columns([2, 5])

    with col1:
        st.info("💡 適用報告：橫向排列 Mean 數據的報告。")
        if os.path.exists("example_1_item.png"):
            st.image("example_1_item.png", caption="Example of Item Analysis Table", use_column_width=True)

    with col2:
        if global_file is None:
            st.warning("👆 請先在上方上傳 PDF 檔案")
        else:
            with st.spinner("⏳ 正在處理檔案，請稍候..."):
                try:
                    global_file.seek(0)
                    df_item = extract_item_analysis(global_file)

                    if df_item.empty:
                        st.error("❌ 無法提取數據！")
                    else:
                        st.success(f"✅ 提取成功！共取得 {len(df_item)} 題數據。")
                        st.subheader("📋 數據預覽 | Data Preview")
                        st.table(df_item.style.format(precision=2))

                        st.download_button(
                            label="📥 下載 Excel 檔案",
                            data=convert_df_to_excel(df_item, "Item Analysis"),
                            file_name=f"{global_file.name.replace('.pdf', '')}_ItemAnalysis.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="btn_item",
                            type="primary"
                        )
                except Exception as e:
                    st.error(f"❌ 處理檔案時發生錯誤：{str(e)}")

with tab2:
    st.subheader("✅ MCQ 分析轉換器 | MCQ Analysis Converter")
    col3, col4 = st.columns([2, 5])

    with col3:
        st.info("💡 適用報告：列出 A, B, C, D 人數的報告。")
        if os.path.exists("example_2_mcq.png"):
            st.image("example_2_mcq.png", caption="Example of MCQ Analysis Table", use_column_width=True)

    with col4:
        if global_file is None:
            st.warning("👆 請先在上方上傳 PDF 檔案")
        else:
            with st.spinner("⏳ 正在處理檔案，請稍候..."):
                try:
                    global_file.seek(0)
                    df_mcq = extract_mcq_analysis(global_file)

                    if df_mcq.empty:
                        st.error("❌ 無法提取數據！")
                    else:
                        st.success(f"✅ 提取成功！共取得 {len(df_mcq)} 題數據。")
                        st.subheader("📋 數據預覽 | Data Preview")
                        st.table(df_mcq.style.format(precision=2))

                        st.download_button(
                            label="📥 下載 Excel 檔案",
                            data=convert_df_to_excel(df_mcq, "MCQ Analysis"),
                            file_name=f"{global_file.name.replace('.pdf', '')}_MCQAnalysis.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="btn_mcq",
                            type="primary"
                        )
                except Exception as e:
                    st.error(f"❌ 處理檔案時發生錯誤：{str(e)}")

# -----------------
# 標籤頁 3: 自定義項目分析 (外置輸入框方案)
# -----------------
with tab3:
    st.subheader("📌 自定義項目分析")
    if global_file is None:
        st.warning("👆 請先在上載 PDF 檔案")
    else:
        try:
            global_file.seek(0)
            df_item_c = extract_item_analysis(global_file)
            if not df_item_c.empty:
                if "題號" not in df_item_c.columns:
                    df_item_c.insert(0, "題號", df_item_c.get("Item No", df_item_c.get("Item", range(1, len(df_item_c) + 1))))

                st.info("Step 1：建立與管理自定義欄位 (最多 6 個)")
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
                    st.info("Step 2：為每一題設定分類 (外置輸入模塊)")

                    # 選擇題號
                    questions = df_item_c["題號"].tolist()
                    sel_q = st.selectbox("選擇要輸入標籤的題號：", questions, key="item_q_sel")

                    # 獲取該題目前的輸入值
                    current_values = st.session_state.item_custom_values.get(sel_q, {})

                    with st.form(f"item_input_form_{sel_q}"):
                        st.write(f"**正在編輯：第 {sel_q} 題**")

                        input_results = {}
                        for col in st.session_state.custom_cols:
                            # 合併歷史記錄與新增選項
                            history_opts = st.session_state.col_options_history.get(col, [])
                            options = [""] + history_opts + ["➕ 輸入新文本..."]

                            # 預設選中現有值
                            default_idx = 0
                            curr_val = current_values.get(col, "")
                            if curr_val in options:
                                default_idx = options.index(curr_val)

                            sel_val = st.selectbox(f"{col}:", options=options, index=default_idx, key=f"sel_{col}")

                            # 如果選擇了新增文本
                            if sel_val == "➕ 輸入新文本...":
                                new_val = st.text_input(f"請輸入新的「{col}」:", key=f"new_val_{col}")
                                input_results[col] = new_val
                            else:
                                input_results[col] = sel_val

                        submit_btn = st.form_submit_button("📥 儲存並寫入表格")
                        if submit_btn:
                            if sel_q not in st.session_state.item_custom_values:
                                st.session_state.item_custom_values[sel_q] = {}

                            for col, val in input_results.items():
                                if val:
                                    st.session_state.item_custom_values[sel_q][col] = val
                                    # 記錄歷史文本
                                    if val not in st.session_state.col_options_history[col]:
                                        st.session_state.col_options_history[col].append(val)

                            st.success(f"第 {sel_q} 題資料已成功寫入表格！歷史文本已記錄。")
                            st.rerun()

                    # 將 session_state 裡的值套用到 dataframe 上預覽
                    df_display = df_item_c.copy()
                    for col in st.session_state.custom_cols:
                        df_display[col] = df_display["題號"].apply(lambda x: st.session_state.item_custom_values.get(x, {}).get(col, ""))

                    st.write("📊 **目前各題分類總覽表：**")
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
                        except: pass

                    st.dataframe(final_df, use_container_width=True, hide_index=True)

                    st.download_button(
                        label="📥 下載自定義項目分析 Excel",
                        data=convert_df_to_excel(final_df, "Custom Item Analysis"),
                        file_name="Custom_Item_Analysis.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="btn_custom_item"
                    )

        except Exception as e:
            st.error(f"錯誤：{str(e)}")

# -----------------
# 標籤頁 4: 自定義 MCQ 分析 (外置輸入框方案)
# -----------------
with tab4:
    st.subheader("🎯 自定義 MCQ 分析")
    if global_file is None:
        st.warning("👆 請先在上載 PDF 檔案")
    else:
        try:
            global_file.seek(0)
            df_mcq_c = extract_mcq_analysis(global_file)
            if not df_mcq_c.empty:
                df_mcq_c = prepare_mcq_analysis_for_custom(df_mcq_c)
                if "題號" not in df_mcq_c.columns:
                    df_mcq_c.insert(0, "題號", df_mcq_c.get("Question Number", range(1, len(df_mcq_c) + 1)))

                st.info("Step 1：與 Tab 3 共用欄位名稱")

                if st.session_state.custom_cols:
                    st.success(f"目前建立的欄位：{', '.join(st.session_state.custom_cols)}")

                    st.markdown("---")
                    st.info("Step 2：為每一題設定分類 (外置輸入模塊)")

                    # 選擇題號
                    q_mcq = df_mcq_c["題號"].tolist()
                    sel_q_mcq = st.selectbox("選擇要輸入標籤的題號：", q_mcq, key="mcq_q_sel")

                    # 獲取該題目前的輸入值
                    curr_vals_mcq = st.session_state.mcq_custom_values.get(sel_q_mcq, {})

                    with st.form(f"mcq_input_form_{sel_q_mcq}"):
                        st.write(f"**正在編輯：第 {sel_q_mcq} 題**")

                        input_results_m = {}
                        for col in st.session_state.custom_cols:
                            # 合併歷史記錄與新增選項
                            history_opts = st.session_state.col_options_history.get(col, [])
                            options = [""] + history_opts + ["➕ 輸入新文本..."]

                            # 預設選中現有值
                            default_idx = 0
                            curr_val = curr_vals_mcq.get(col, "")
                            if curr_val in options:
                                default_idx = options.index(curr_val)

                            sel_val = st.selectbox(f"{col}:", options=options, index=default_idx, key=f"sel_mcq_{col}")

                            # 如果選擇了新增文本
                            if sel_val == "➕ 輸入新文本...":
                                new_val = st.text_input(f"請輸入新的「{col}」:", key=f"new_val_mcq_{col}")
                                input_results_m[col] = new_val
                            else:
                                input_results_m[col] = sel_val

                        submit_btn_m = st.form_submit_button("📥 儲存並寫入表格")
                        if submit_btn_m:
                            if sel_q_mcq not in st.session_state.mcq_custom_values:
                                st.session_state.mcq_custom_values[sel_q_mcq] = {}

                            for col, val in input_results_m.items():
                                if val:
                                    st.session_state.mcq_custom_values[sel_q_mcq][col] = val
                                    # 記錄歷史文本
                                    if val not in st.session_state.col_options_history[col]:
                                        st.session_state.col_options_history[col].append(val)

                            st.success(f"第 {sel_q_mcq} 題資料已成功寫入表格！歷史文本已記錄。")
                            st.rerun()

                    # 將 session_state 裡的值套用到 dataframe 上預覽
                    df_mcq_display = df_mcq_c.copy()
                    for col in st.session_state.custom_cols:
                        df_mcq_display[col] = df_mcq_display["題號"].apply(lambda x: st.session_state.mcq_custom_values.get(x, {}).get(col, ""))

                    st.write("📊 **目前各題分類總覽表：**")
                    st.dataframe(df_mcq_display, use_container_width=True, hide_index=True)

                    st.markdown("---")
                    st.info("Step 3：篩選與高亮分析")
                    f_cols_mcq = st.columns(max(len(st.session_state.custom_cols), 1))
                    active_filters_mcq = {}
                    for i, col in enumerate(st.session_state.custom_cols):
                        with f_cols_mcq[i]:
                            u_vals_mcq = [x for x in df_mcq_display[col].unique() if str(x).strip()]
                            active_filters_mcq[col] = st.multiselect(f"篩選 {col}", u_vals_mcq, key=f"filter_mcq_{col}")

                    final_mcq_df = df_mcq_display.copy()
                    for col, s_filters in active_filters_mcq.items():
                        if s_filters:
                            final_mcq_df = final_mcq_df[final_mcq_df[col].isin(s_filters)]

                    st.markdown('''
                    <div style='background-color:#f8f9fa; padding:12px; border-radius:8px; margin-bottom:12px;'>
                        <b>顏色說明：</b><br>
                        <span style='background-color:#fff3cd; padding:2px 6px;'>黃色</span>：本校最高票 ≠ 正確答案<br>
                        <span style='background-color:#d1ecf1; padding:2px 6px;'>藍色</span>：本校最高票 ≠ 全港最高票<br>
                        <span style='background-color:#f8d7da; padding:2px 6px;'>紅色</span>：以上兩點皆成立
                    </div>
                    ''', unsafe_allow_html=True)

                    st.dataframe(
                        final_mcq_df.style.apply(highlight_mcq_row, axis=1),
                        use_container_width=True,
                        hide_index=True
                    )

                    st.download_button(
                        label="📥 下載自定義 MCQ 分析 Excel",
                        data=convert_df_to_excel(final_mcq_df, "Custom MCQ Analysis"),
                        file_name="Custom_MCQ_Analysis.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="btn_custom_mcq"
                    )
                else:
                    st.warning("請先在上方 (或 Tab 3) 新增自定義欄位！")

        except Exception as e:
            st.error(f"錯誤：{str(e)}")

st.divider()
st.caption("💡 提示：導出 Excel 後可直接複製數據貼上至 QSIP 系統。")
