import streamlit as st
import pdfplumber
import pandas as pd
import re
import io
import os


def retain_session_state():
    safe_keys = [
        "source_pdf_bytes",
        "source_pdf_name",
        "processed_item_df",
        "processed_mcq_df",
        "processed_total_df",
        "processed_subject_name",
        "processed_exam_year",
        "custom_cols",
        "col_options_history",
        "item_custom_values",
        "mcq_custom_values",
    ]
    for k in safe_keys:
        if k in st.session_state:
            st.session_state[k] = st.session_state[k]


retain_session_state()

st.set_page_config(
    page_title="HKDSE Statistical Report Data Converter | HKDSE學校統計報告 數據轉換工具",
    page_icon="🔁",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📊 HKDSE學校統計報告 數據轉換工具")
st.markdown("本工具將自動提取考評局 PDF 報告中的數據，轉換為 Excel 格式，方便貼上至 CUHK QSIP 分析工具。")

# ==========================================
# Session defaults
# ==========================================
def init_state():
    defaults = {
        "source_pdf_bytes": None,
        "source_pdf_name": None,
        "processed_item_df": None,
        "processed_mcq_df": None,
        "processed_total_df": None,
        "processed_subject_name": None,
        "processed_exam_year": None,
        "custom_cols": [],
        "col_options_history": {},
        "item_custom_values": {},
        "mcq_custom_values": {},
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()

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
        "Item", "Max Mark", "Your school Attm. No.", "Your school Attem. %", "Your school Mean",
        "Your school Mean %", "Your school SD", "Day schools Attem. %", "Day schools Mean",
        "Day schools Mean %", "Day schools SD"
    ]
    df = pd.DataFrame(extracted_data, columns=columns)
    numeric_cols = [
        "Max Mark", "Your school Attm. No.", "Your school Attem. %", "Your school Mean",
        "Your school SD", "Day schools Attem. %", "Day schools Mean", "Day schools SD"
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


def process_and_store_pdf(file_bytes, file_name):
    st.session_state.source_pdf_bytes = file_bytes
    st.session_state.source_pdf_name = file_name
    st.session_state.processed_item_df = extract_item_analysis(io.BytesIO(file_bytes))
    st.session_state.processed_mcq_df = extract_mcq_analysis(io.BytesIO(file_bytes))
    total_df, subject_name, exam_year = extract_latest_dse_total_data(io.BytesIO(file_bytes))
    st.session_state.processed_total_df = total_df
    st.session_state.processed_subject_name = subject_name
    st.session_state.processed_exam_year = exam_year


st.markdown("---")
st.subheader("📂 1. 上載檔案 | Upload File")
global_file = st.file_uploader("請上載包含學校成績數據的考評局 PDF 報告", type=["pdf"], key="global_file")
st.caption("🛡️ 本工具僅在記憶體中暫存 PDF，處理後立即刪除，不會儲存至硬碟或雲端。")

if global_file is not None:
    current_bytes = global_file.getvalue()
    current_name = global_file.name
    if (
        st.session_state.source_pdf_bytes is None
        or st.session_state.source_pdf_name != current_name
        or st.session_state.source_pdf_bytes != current_bytes
    ):
        with st.spinner("偵測到新檔案，正在預先處理資料..."):
            process_and_store_pdf(current_bytes, current_name)
        st.success(f"已載入並保存檔案：{current_name}")
elif st.session_state.source_pdf_name:
    st.success(f"目前已保存檔案：{st.session_state.source_pdf_name}")
    st.info("你現在可以直接切換到其他分頁，已處理資料會沿用目前 session。")
else:
    st.warning("尚未上載 PDF 檔案。")

st.markdown("---")
st.subheader("📊 2. 選擇分析模式 | Select Analysis Mode")
st.info("完成上載後，可從左側 Sidebar 的 Pages 選單進入兩個獨立 app：自定義項目分析 / 自定義 MCQ 分析。")

if st.button("🗑️ 清除目前已保存的 PDF 與分析結果"):
    for k in [
        "source_pdf_bytes", "source_pdf_name", "processed_item_df", "processed_mcq_df",
        "processed_total_df", "processed_subject_name", "processed_exam_year"
    ]:
        st.session_state[k] = None
    st.rerun()

# ==========================================
# 建立主畫面三個標籤頁 (Tabs) 入口
# ==========================================
tab0, tab1, tab2 = st.tabs([
    "📊 總數分析 Total Analysis",
    "📝 項目分析報告 Item Analysis Report",
    "✅ 多項選擇題報告 MCQ Analysis Report"
])

with tab0:
    st.subheader("📊 總數轉換 | Total Analysis Converter")
    col_t1, col_t2 = st.columns([2, 5])
    with col_t1:
        st.info("""
        💡 **本區功能：** 自動提取最新年份的「總數」數據。
        **Function:** Automatically extracts the latest year's 'Total' data.
        """)
        if os.path.exists("example3_main.png"):
            st.image("example3_main.png", caption="總數表格示例 | Example of Total Table", use_container_width=True)
        else:
            st.warning("⚠️ (提示: 系統未找到 example3_main.png | Image not found)")
    with col_t2:
        df_total = st.session_state.processed_total_df
        subject_name = st.session_state.processed_subject_name
        exam_year = st.session_state.processed_exam_year
        if df_total is None:
            st.warning("👆 請先在上方上載 PDF 檔案 | Please upload a PDF file above first.")
        elif df_total.empty:
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

with tab1:
    st.subheader("📝 項目分析報告轉換 | Item Analysis Converter")
    col1, col2 = st.columns([2, 5])
    with col1:
        st.info("""
        💡 **本區適用於以下格式的報告：**
        表格橫向列出「平均分 Mean」、「標準差 S.D.」等數據。
        **Applicable for reports formatted like:** The table horizontally displays data such as 'Mean' and 'S.D.'.
        """)
        if os.path.exists("example1_item.png"):
            st.image("example1_item.png", caption="項目分析表格示例 | Example of Item Analysis Table", use_container_width=True)
        else:
            st.warning("⚠️ (提示: 系統未找到 example1_item.png | Image not found)")
    with col2:
        df_item = st.session_state.processed_item_df
        if df_item is None:
            st.warning("👆 請先在上方上載 PDF 檔案 | Please upload a PDF file above first.")
        elif df_item.empty:
            st.error("❌ 無法提取數據！請確認你上載的是否為正確的「項目分析報告」。")
        else:
            st.success(f"✅ 提取成功！共獲取 {len(df_item)} 行數據。")
            st.subheader("📋 數據概覽 | Data Preview")
            st.table(df_item.style.format(precision=2))
            file_name = (st.session_state.source_pdf_name or 'output.pdf').replace('.pdf', '')
            st.download_button(
                label="📥 下載 Excel 檔案 | Download Excel File",
                data=convert_df_to_excel(df_item, "Item Analysis"),
                file_name=f"{file_name}_ItemAnalysis.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="btn_item",
                type="primary"
            )

with tab2:
    st.subheader("✅ 多項選擇題報告轉換 | MCQ Analysis Converter")
    col3, col4 = st.columns([2, 5])
    with col3:
        st.info("""
        💡 **本區適用於以下格式的報告：**
        表格列出「A, B, C, D」選項的選擇人數，並附有 ☑️ 標記顯示正確答案。
        **Applicable for reports formatted like:** The table lists the number of students for options 'A, B, C, D' and uses a ☑️ mark to indicate the correct answer.
        """)
        if os.path.exists("example2_mcq.png"):
            st.image("example2_mcq.png", caption="多項選擇題表格示例 | Example of MCQ Analysis Table", use_container_width=True)
        else:
            st.warning("⚠️ (提示: 系統未找到 example2_mcq.png | Image not found)")
    with col4:
        df_mcq = st.session_state.processed_mcq_df
        if df_mcq is None:
            st.warning("👆 請先在上方上載 PDF 檔案 | Please upload a PDF file above first.")
        elif df_mcq.empty:
            st.error("❌ 無法提取數據！請確認你上載的是否為正確的「多項選擇題分析報告」。")
        else:
            st.success(f"✅ 提取成功！共獲取 {len(df_mcq)} 題的數據。")
            st.subheader("📋 數據概覽 | Data Preview")
            st.table(df_mcq.style.format(precision=2))
            file_name = (st.session_state.source_pdf_name or 'output.pdf').replace('.pdf', '')
            st.download_button(
                label="📥 下載 Excel 檔案 | Download Excel File",
                data=convert_df_to_excel(df_mcq, "MCQ Analysis"),
                file_name=f"{file_name}_MCQAnalysis.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="btn_mcq",
                type="primary"
            )
