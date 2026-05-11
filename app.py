import streamlit as st
import pdfplumber
import pandas as pd
import re
import io
import os

# ==========================================
# 頁面設定 / Page Configuration
# ==========================================
st.set_page_config(page_title="HKDSE Statistical Report Data Converter | HKDSE學校統計報告 數據轉換工具", page_icon="🔁", layout="wide")

st.title("📊 HKDSE學校統計報告 數據轉換工具")
st.markdown("本工具將自動提取考評局 PDF 報告中的數據，轉換為 Excel 格式，方便貼上至 CUHK QSIP 分析工具。")

# ==========================================
# 頂部：共用上傳區 / Top: Global Upload
# ==========================================
st.markdown("---")
st.subheader("📂 1. 上載檔案 | Upload File")
global_file = st.file_uploader("請上載包含學校成績數據的考評局 PDF 報告", type=["pdf"], key="global_file")
st.caption("🛡️ 本工具僅在記憶體中暫存 PDF，處理後立即刪除，不會儲存至硬碟或雲端。")
st.markdown("---")
st.subheader("📊 2. 選擇分析模式 | Select Analysis Mode")

# ==========================================
# 核心處理函數 1：項目分析報告 (Item Analysis)
# ==========================================
@st.cache_data
def extract_item_analysis(file_bytes):
    row_pattern = re.compile(
        r'^(.*?)\s+(\d+)\s+(\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)\s+(\d+%)\s+(\d+\.\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)\s+(\d+%)\s+(\d+\.\d+)\s*([+-]?\d+\.\d+)\s*'
    )
    extracted_data = []

    with pdfplumber.open(file_bytes) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for line in text.split('\n'):
                clean_line = " ".join(line.split())
                match = row_pattern.search(clean_line)
                if match:
                    extracted_data.append(match.groups()[:11])

    columns = [
        "Item", "Max Mark", "Your school Attm. No.", 
        "Your school Attem.  %", "Your school Mean", "Your school Mean %", 
        "Your school SD", "Day schools Attem.  %", "Day schools Mean", 
        "Day schools Mean %", "Day schools SD"
    ]
    df = pd.DataFrame(extracted_data, columns=columns)

    numeric_cols = [
        "Max Mark", "Your school Attm. No.",
        "Your school Attem.  %", "Your school Mean", "Your school SD", 
        "Day schools Attem.  %", "Day schools Mean", "Day schools SD"
    ]

    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    pct_cols = ["Your school Mean %", "Day schools Mean %"]
    for col in pct_cols:
        df[col] = df[col].str.replace('%', '').astype(float) / 100

    return df

# ==========================================
# 核心處理函數 2：多項選擇題報告 (MCQ Analysis)
# ==========================================
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
                q_match = re.match(r'^(\d+\([ivx]+\)|\d+)\s+貴校', line.strip())
                if q_match:
                    if current_question and question_answers:
                        row = {'Question Number': current_question, 'Corr. Ans': correct_answer}
                        for opt in ['A', 'B', 'C', 'D']:
                            row[f'Your school {opt}_No.'] = question_answers.get(f'{opt}_your', '0')
                            row[f'Day schools {opt}_No.'] = question_answers.get(f'{opt}_day', '0')
                        mcq_data.append(row)

                    current_question = q_match.group(1)
                    question_answers = {}
                    correct_answer = None

                answer_match = re.match(r'^([ABCD])\s+()?\s*(\d+)\s+[\d.]+\s+([\d,]+)', line.strip())
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
                row = {'Question Number': current_question, 'Corr. Ans': correct_answer}
                for opt in ['A', 'B', 'C', 'D']:
                    row[f'Your school {opt}_No.'] = question_answers.get(f'{opt}_your', '0')
                    row[f'Day schools {opt}_No.'] = question_answers.get(f'{opt}_day', '0')
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

# ==========================================
# 核心處理函數 3：總數分析 (Total Analysis)
# ==========================================
@st.cache_data
def extract_latest_dse_total_data(file_bytes):
    target_grades = ['5**', '5*+', '5+', '4+', '3+', '2+', '1+', 'UNCL', '出席 Sat']
    results = []
    subject_name = "未知科目"
    exam_year = "未知年份"

    with pdfplumber.open(file_bytes) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            if "總數" in text and "貴校" in text and "5**" in text:
                lines = text.split('\n')
                in_total_section = False

                for i, line in enumerate(lines):
                    if "HKDSE 20" in line and exam_year == "未知年份":
                        exam_year = line.replace("HKDSE", "").strip()

                for i, line in enumerate(lines):
                    if ("總數 Total" in line or "總數" in line) and subject_name == "未知科目":
                        if i >= 2 and "Category" not in lines[i-2] and "學科" not in lines[i-2] and "results" not in lines[i-2]:
                            subject_name = lines[i-2].strip()
                        elif i >= 1:
                            subject_name = lines[i-1].strip()

                for line in lines:
                    if "總數 Total" in line or "總數" in line:
                        in_total_section = True
                    elif "男生 Male" in line or "女生 Female" in line:
                        in_total_section = False

                    if in_total_section:
                        clean_line = line.replace(',', '')
                        for grade in target_grades:
                            if clean_line.startswith(grade + " "):
                                parts = clean_line.split(grade)

                                if len(parts) >= 3:
                                    ys_numbers = parts[1].strip().split()
                                    ds_numbers = parts[2].strip().split()

                                    if ys_numbers and ds_numbers:
                                        if not any(r['等級'] == grade for r in results):
                                            results.append({
                                                '等級': grade,
                                                '貴校': int(ys_numbers[-1]),
                                                '日校': int(ds_numbers[-1])
                                            })
                                break

                if len(results) == len(target_grades):
                    break

    df = pd.DataFrame(results)
    if not df.empty:
        df['等級'] = pd.Categorical(df['等級'], categories=target_grades, ordered=True)
        df = df.sort_values('等級').reset_index(drop=True)

    return df, subject_name, exam_year

# ==========================================
# 輔助函數：匯出 Excel / Export to Excel
# ==========================================
def convert_df_to_excel(df, sheet_name):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return output.getvalue()

# ==========================================
# 建立主畫面三個標籤頁 (Tabs) 入口
# ==========================================

# ==========================================
# 輔助函數：初始化自定義分類欄位 (Item)
# ==========================================
def prepare_item_analysis_for_custom(df):
    df = df.copy()
    if "題號" not in df.columns:
        df.insert(0, "題號", range(1, len(df) + 1))
    for col in ["考試範圍", "題目類型", "測試技能"]:
        if col not in df.columns:
            df[col] = ""
    return df

# ==========================================
# 輔助函數：初始化自定義分類欄位 (MCQ) + 計算最高票
# ==========================================
def prepare_mcq_analysis_for_custom(df):
    df = df.copy()
    if "題號" not in df.columns:
        df.insert(0, "題號", range(1, len(df) + 1))
    for col in ["考試範圍", "題目類型", "測試技能"]:
        if col not in df.columns:
            df[col] = ""

    def get_top_option(row, prefix):
        opts = {
            "A": pd.to_numeric(row.get(f"{prefix} A_No.", 0), errors='coerce') or 0,
            "B": pd.to_numeric(row.get(f"{prefix} B_No.", 0), errors='coerce') or 0,
            "C": pd.to_numeric(row.get(f"{prefix} C_No.", 0), errors='coerce') or 0,
            "D": pd.to_numeric(row.get(f"{prefix} D_No.", 0), errors='coerce') or 0,
        }
        return max(opts, key=opts.get)

    df["Your school 最高票"] = df.apply(lambda r: get_top_option(r, "Your school"), axis=1)
    df["Day schools 最高票"] = df.apply(lambda r: get_top_option(r, "Day schools"), axis=1)
    return df

# ==========================================
# 輔助函數：自定義過濾與排序
# ==========================================
def apply_custom_filters(df, scope, type_f, skill):
    res = df.copy()
    if scope: res = res[res["考試範圍"].isin(scope)]
    if type_f: res = res[res["題目類型"].isin(type_f)]
    if skill: res = res[res["測試技能"].isin(skill)]
    return res

def sort_custom_df(df, sort_by, sort_order):
    if sort_by == "預設 (按題號)":
        return df.sort_values("題號", ascending=True) if "題號" in df.columns else df
    return df.sort_values(sort_by, ascending=(sort_order == "由低至高"))

# ==========================================
# 輔助函數：MCQ 高亮邏輯
# ==========================================
def highlight_mcq_row(row):
    your_top = row.get("Your school 最高票")
    day_top = row.get("Day schools 最高票")
    corr_ans = row.get("Corr. Ans")

    # 移除打勾符號，確保乾淨比對
    if isinstance(corr_ans, str):
        corr_ans = corr_ans.replace("☑️", "").strip()

    cond1 = (your_top != corr_ans)
    cond2 = (your_top != day_top)

    if cond1 and cond2: color = "background-color: #f8d7da"  # 紅色
    elif cond1: color = "background-color: #fff2cc"  # 黃色
    elif cond2: color = "background-color: #cce5ff"  # 藍色
    else: color = ""
    return [color] * len(row)

tab0, tab1, tab2, tab3, tab4 = st.tabs([
    "📊 總數轉換 | Total Analysis", 
    "📝 項目分析轉換 | Item Analysis", 
    "✅ MCQ轉換 | MCQ Analysis",
    "📌 自定義項目分析 | Custom Item Analysis",
    "🎯 自定義MCQ分析 | Custom MCQ Analysis"
])

# -----------------
# 標籤頁 0 的內容 / Tab 0 Content
# -----------------
with tab0:
    st.subheader("📊 總數轉換 | Total Analysis Converter")

    col_t1, col_t2 = st.columns([2, 5])

    with col_t1:
        st.info("""
        💡 **本區功能：**
        自動提取最新年份的「總數」數據。

        **Function:**
        Automatically extracts the latest year's 'Total' data.
        """)
        if os.path.exists("example3_main.png"):
            st.image("example3_main.png", caption="總數表格示例 | Example of Total Table", use_column_width=True)
        else:
            st.warning("⚠️ (提示: 系統未找到 example3_main.png | Image not found)")

    with col_t2:
        if global_file is None:
            st.warning("👆 請先在上方上載 PDF 檔案 | Please upload a PDF file above first.")
        else:
            with st.spinner("系統正在處理檔案，請稍候... | Processing file, please wait..."):
                try:
                    global_file.seek(0)
                    df_total, subject_name, exam_year = extract_latest_dse_total_data(global_file)
                    if df_total.empty:
                        st.error("❌ 無法提取數據！請確認你上載的 PDF 包含「總數」表格。")
                    else:
                        st.success(f"✅ 提取成功！已取得 {exam_year} 年數據。")

                        st.subheader(f"📋 {subject_name} {exam_year} 數據概覽 | Data Preview")
                        with st.expander("✂️ 快速複製單列數據 (貼上至 Excel) | Quick Copy Columns"):
                            c1, c2 = st.columns(2)
                            with c1:
                                st.caption("貴校人數 (Your school)")
                                ys_text = "\n".join(df_total["貴校"].astype(str).tolist())
                                st.code(ys_text, language="text")
                            with c2:
                                st.caption("日校人數 (Day schools)")
                                ds_text = "\n".join(df_total["日校"].astype(str).tolist())
                                st.code(ds_text, language="text")

                        st.table(df_total.style.format(precision=2))


                except Exception as e:
                    st.error(f"❌ 處理檔案時發生錯誤：{str(e)}")

# -----------------
# 標籤頁 1 的內容 / Tab 1 Content
# -----------------
with tab1:
    st.subheader("📝 項目分析報告轉換 | Item Analysis Converter")

    col1, col2 = st.columns([2, 5])

    with col1:
        st.info("""
        💡 **本區適用於以下格式的報告：**
        表格橫向列出「平均分 Mean」、「標準差 S.D.」等數據。

        **Applicable for reports formatted like:**
        The table horizontally displays data such as 'Mean' and 'S.D.'.
        """)
        if os.path.exists("example1_item.png"):
            st.image("example1_item.png", caption="項目分析表格示例 | Example of Item Analysis Table", use_column_width=True)
        else:
            st.warning("⚠️ (提示: 系統未找到 example1_item.png | Image not found)")

    with col2:
        if global_file is None:
            st.warning("👆 請先在上方上載 PDF 檔案 | Please upload a PDF file above first.")
        else:
            with st.spinner("系統正在處理檔案，請稍候... | Processing file, please wait..."):
                try:
                    global_file.seek(0)
                    df_item = extract_item_analysis(global_file)
                    if df_item.empty:
                        st.error("❌ 無法提取數據！請確認你上載的是否為正確的「項目分析報告」。 \n *Failed to extract data! Please ensure you uploaded the correct 'Item Analysis Report'.*")
                    else:
                        st.success(f"✅ 提取成功！共獲取 {len(df_item)} 行數據。 \n *Extraction successful! {len(df_item)} rows retrieved.*")

                        st.subheader("📋 數據概覽 | Data Preview")
                        st.table(df_item.style.format(precision=2))

                        st.download_button(
                            label="📥 下載 Excel 檔案 | Download Excel File",
                            data=convert_df_to_excel(df_item, "Item Analysis"),
                            file_name=f"{global_file.name.replace('.pdf', '')}_ItemAnalysis.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="btn_item",
                            type="primary"
                        )
                except Exception as e:
                    st.error(f"❌ 處理檔案時發生錯誤 | Error processing file：{str(e)}")

# -----------------
# 標籤頁 2 的內容 / Tab 2 Content
# -----------------
with tab2:
    st.subheader("✅ 多項選擇題報告轉換 | MCQ Analysis Converter")

    col3, col4 = st.columns([2, 5])

    with col3:
        st.info("""
        💡 **本區適用於以下格式的報告：**
        表格列出「A, B, C, D」選項的選擇人數，並附有 ☑️ 標記顯示正確答案。

        **Applicable for reports formatted like:**
        The table lists the number of students for options 'A, B, C, D' and uses a ☑️ mark to indicate the correct answer.
        """)
        if os.path.exists("example2_mcq.png"):
            st.image("example2_mcq.png", caption="多項選擇題表格示例 | Example of MCQ Analysis Table", use_column_width=True)
        else:
            st.warning("⚠️ (提示: 系統未找到 example2_mcq.png | Image not found)")

    with col4:
        if global_file is None:
            st.warning("👆 請先在上方上載 PDF 檔案 | Please upload a PDF file above first.")
        else:
            with st.spinner("系統正在處理檔案，請稍候... | Processing file, please wait..."):
                try:
                    global_file.seek(0)
                    df_mcq = extract_mcq_analysis(global_file)
                    if df_mcq.empty:
                        st.error("❌ 無法提取數據！請確認你上載的是否為正確的「多項選擇題分析報告」。 \n *Failed to extract data! Please ensure you uploaded the correct 'MCQ Analysis Report'.*")
                    else:
                        st.success(f"✅ 提取成功！共獲取 {len(df_mcq)} 題的數據。 \n *Extraction successful! Data for {len(df_mcq)} questions retrieved. *")

                        st.subheader("📋 數據概覽 | Data Preview")
                        st.table(df_mcq.style.format(precision=2))

                        st.download_button(
                            label="📥 下載 Excel 檔案 | Download Excel File",
                            data=convert_df_to_excel(df_mcq, "MCQ Analysis"),
                            file_name=f"{global_file.name.replace('.pdf', '')}_MCQAnalysis.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="btn_mcq",
                            type="primary"
                        )
                except Exception as e:
                    st.error(f"❌ 處理檔案時發生錯誤 | Error processing file：{str(e)}")



# -----------------
# 標籤頁 3 的內容 / Tab 3 Content (自定義項目分析)
# -----------------
with tab3:
    st.subheader("📌 自定義項目分析 | Custom Item Analysis")
    if global_file is None:
        st.warning("👆 請先在上方上載 PDF 檔案 | Please upload a PDF file above first.")
    else:
        with st.spinner("正在載入數據..."):
            try:
                global_file.seek(0)
                df_item_custom = extract_item_analysis(global_file)
                if df_item_custom.empty:
                    st.error("❌ 無法提取數據！請確認 PDF 包含「項目分析報告」。")
                else:
                    df_item_custom = prepare_item_analysis_for_custom(df_item_custom)

                    st.info("✏️ **Step 1：自定義分類** - 請直接在下表的「考試範圍」、「題目類型」與「測試技能」點擊輸入。")
                    editable = ["考試範圍", "題目類型", "測試技能"]
                    disabled = [c for c in df_item_custom.columns if c not in editable]

                    edited_item = st.data_editor(
                        df_item_custom, disabled=disabled,
                        use_container_width=True, hide_index=True, key="item_editor"
                    )

                    st.markdown("---")
                    st.info("🔍 **Step 2：篩選與排序**")
                    c1, c2, c3 = st.columns(3)
                    with c1: scope = st.multiselect("考試範圍", [x for x in edited_item["考試範圍"].unique() if x], key="i_scope")
                    with c2: type_f = st.multiselect("題目類型", [x for x in edited_item["題目類型"].unique() if x], key="i_type")
                    with c3: skill = st.multiselect("測試技能", [x for x in edited_item["測試技能"].unique() if x], key="i_skill")

                    c4, c5 = st.columns(2)
                    sort_cols = ["預設 (按題號)"] + [c for c in edited_item.columns if "Mean %" in c]
                    with c4: sort_by = st.selectbox("排序依據", sort_cols, key="i_sort")
                    with c5: sort_order = st.radio("排序方式", ["由高至低", "由低至高"], horizontal=True, key="i_order")

                    filtered_item = apply_custom_filters(edited_item, scope, type_f, skill)
                    filtered_item = sort_custom_df(filtered_item, sort_by, sort_order)

                    st.subheader("📋 分析結果")
                    st.dataframe(filtered_item, use_container_width=True, hide_index=True)
                    st.download_button(
                        "📥 下載 Excel",
                        convert_df_to_excel(filtered_item, "Custom Item Analysis"),
                        f"{global_file.name.replace('.pdf', '')}_CustomItem.xlsx",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="btn_ci", type="primary"
                    )
            except Exception as e:
                st.error(f"❌ 錯誤：{str(e)}")

# -----------------
# 標籤頁 4 的內容 / Tab 4 Content (自定義MCQ分析)
# -----------------
with tab4:
    st.subheader("🎯 自定義MCQ分析 | Custom MCQ Analysis")
    if global_file is None:
        st.warning("👆 請先在上方上載 PDF 檔案 | Please upload a PDF file above first.")
    else:
        with st.spinner("正在載入數據..."):
            try:
                global_file.seek(0)
                df_mcq_custom = extract_mcq_analysis(global_file)
                if df_mcq_custom.empty:
                    st.error("❌ 無法提取數據！請確認 PDF 包含「MCQ分析報告」。")
                else:
                    df_mcq_custom = prepare_mcq_analysis_for_custom(df_mcq_custom)

                    st.info("✏️ **Step 1：自定義分類** - 請直接在下表的「考試範圍」、「題目類型」與「測試技能」點擊輸入。")
                    editable = ["考試範圍", "題目類型", "測試技能"]
                    disabled = [c for c in df_mcq_custom.columns if c not in editable]

                    edited_mcq = st.data_editor(
                        df_mcq_custom, disabled=disabled,
                        use_container_width=True, hide_index=True, key="mcq_editor"
                    )

                    st.markdown("---")
                    st.info("🔍 **Step 2：篩選與高亮分析**")
                    c1, c2, c3 = st.columns(3)
                    with c1: scope_m = st.multiselect("考試範圍", [x for x in edited_mcq["考試範圍"].unique() if x], key="m_scope")
                    with c2: type_m = st.multiselect("題目類型", [x for x in edited_mcq["題目類型"].unique() if x], key="m_type")
                    with c3: skill_m = st.multiselect("測試技能", [x for x in edited_mcq["測試技能"].unique() if x], key="m_skill")

                    filtered_mcq = apply_custom_filters(edited_mcq, scope_m, type_m, skill_m)

                    st.markdown('''
                    <div style='background-color:#f8f9fa; padding:12px; border-radius:8px; margin-bottom:12px;'>
                        <b>🎨 顏色說明：</b><br>
                        <span style='background-color:#fff2cc; padding:2px 6px;'>黃色</span>：Your school 最高票選項 ≠ Corr. Ans<br>
                        <span style='background-color:#cce5ff; padding:2px 6px;'>藍色</span>：Your school 最高票選項 ≠ Day schools 最高票選項<br>
                        <span style='background-color:#f8d7da; padding:2px 6px;'>紅色</span>：以上兩者同時成立
                    </div>
                    ''', unsafe_allow_html=True)

                    st.subheader("📋 分析結果")
                    st.dataframe(filtered_mcq.style.apply(highlight_mcq_row, axis=1), use_container_width=True, hide_index=True)
                    st.download_button(
                        "📥 下載 Excel",
                        convert_df_to_excel(filtered_mcq, "Custom MCQ Analysis"),
                        f"{global_file.name.replace('.pdf', '')}_CustomMCQ.xlsx",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="btn_cm", type="primary"
                    )
            except Exception as e:
                st.error(f"❌ 錯誤：{str(e)}")


# ==========================================
# 頁尾提示 / Footer Notes
# ==========================================
st.divider()
st.caption("""
📌 **小貼士 Tips:** 
下載 Excel 後，請打開檔案，選中並複製(Ctrl+C)轉換結果，然後直接貼上(Ctrl+V)至QSIP HKDSE分析工具。 \n
*After downloading the Excel file, please open it, select and copy (Ctrl+C) the conversion results, and then paste (Ctrl+V) them directly into the QSIP HKDSE Analysis Tool.*
""")
