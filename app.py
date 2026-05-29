import io
import os

import altair as alt
import pandas as pd
import streamlit as st

from pdf_utils import convert_df_to_excel, extract_item_analysis, extract_latest_dse_total_data, extract_mcq_analysis

# ==========================================
# 頁面設定 / Page Configuration
# ==========================================
st.set_page_config(page_title="HKDSE Statistical Report Data Converter | HKDSE學校統計報告 數據轉換工具", page_icon="🔁", layout="wide")
st.title("📊 HKDSE學校統計報告 數據轉換與分析工具")
st.markdown("本工具將自動提取考評局 PDF 報告中的數據，並提供題目標記與分析功能。")

# ==========================================
# 頂部：共用上傳區 / Top: Global Upload
# ==========================================
st.markdown("---")
st.subheader("📂 1. 上載檔案 | Upload File")
global_file = st.file_uploader("請上載包含學校成績數據的考評局 PDF 報告", type=["pdf"], key="global_file")
if global_file is not None:
    st.session_state['last_uploaded_file'] = global_file
    st.session_state['source_pdf_name'] = global_file.name
    st.session_state['source_pdf_bytes'] = global_file.getvalue()

current_file = global_file if global_file is not None else st.session_state.get('last_uploaded_file')
st.caption("🛡️ 本工具僅在記憶體中暫存 PDF，處理後立即刪除，不會儲存至硬碟或雲端。")
st.markdown("---")
st.subheader("📊 2. 選擇分析模式 | Select Analysis Mode")


# ==========================================
# 把已處理數據存入 session_state，供其他 app 使用
# ==========================================
def cache_processed_data(uploaded_file):
    if uploaded_file is None:
        uploaded_file = st.session_state.get('last_uploaded_file')
    if uploaded_file is None:
        return False
    file_name = getattr(uploaded_file, 'name', st.session_state.get('source_pdf_name', 'uploaded.pdf'))
    file_bytes = uploaded_file.getvalue() if hasattr(uploaded_file, 'getvalue') else bytes(uploaded_file)
    st.session_state['source_pdf_name'] = file_name
    st.session_state['source_pdf_bytes'] = file_bytes
    st.session_state['processed_item_df'] = extract_item_analysis(file_bytes)
    st.session_state['processed_mcq_df'] = extract_mcq_analysis(file_bytes)
    total_df, subject_name, exam_year, attendance_ys, attendance_ds = extract_latest_dse_total_data(file_bytes)
    st.session_state['processed_total_df'] = total_df
    st.session_state['processed_total_attendance_ys'] = attendance_ys
    st.session_state['processed_total_attendance_ds'] = attendance_ds
    st.session_state['processed_subject_name'] = subject_name
    st.session_state['processed_exam_year'] = exam_year
    return True

# ==========================================
# 導航入口：前處理完成後可跳轉到其他 app
# ==========================================
col_nav1, col_nav2 = st.columns(2)
with col_nav1:
    if st.button("🚀 處理檔案並啟用自定義分析 app", type="primary"):
        if current_file is None:
            st.warning("請先上載 PDF 檔案。")
        else:
            with st.spinner("正在處理資料並準備自定義分析 app..."):
                cache_processed_data(current_file)
            st.success("已完成資料處理。現在可打開下方兩個獨立 app。")
with col_nav2:
    st.caption("完成一次前處理後，自定義項目分析與自定義 MCQ 分析會直接使用已處理好的資料。")

st.page_link("pages/1_custom_item_app.py", label="打開：自定義項目分析 app", icon="📌")
st.page_link("pages/2_custom_mcq_app.py", label="打開：自定義 MCQ 分析 app", icon="🎯")

# ==========================================
# 建立主畫面三個標籤頁 (Tabs) 入口
# ==========================================
tab0, tab1, tab2 = st.tabs(["📊 總數分析 Total Analysis", "📝 項目分析報告 Item Analysis Report", "✅ 多項選擇題報告 MCQ Analysis Report"])

# -----------------
# 標籤頁 0 的內容 / Tab 0 Content
# -----------------
with tab0:
    st.subheader("📊 總數轉換 | Total Analysis Converter")
    col_t1, col_t2 = st.columns([2, 5])
    with col_t1:
        st.info("""
        💡 **本區功能：** 自動提取最新年份的「總數」數據。
        **Function:** Automatically extracts the latest year's 'Total' data.
        """)
        if os.path.exists("example3_main.png"):
            st.image("example3_main.png", caption="總數表格示例 | Example of Total Table", use_column_width=True)
        else:
            st.warning("⚠️ (提示: 系統未找到 example3_main.png | Image not found)")
    with col_t2:
        if current_file is None:
            st.warning("👆 請先在上方上載 PDF 檔案 | Please upload a PDF file above first.")
        else:
            with st.spinner("系統正在處理檔案，請稍候... | Processing file, please wait..."):
                try:
                    current_file.seek(0)
                    file_bytes = current_file.getvalue()
                    df_total, subject_name, exam_year, attendance_ys, attendance_ds = extract_latest_dse_total_data(file_bytes)
                    if df_total.empty:
                        st.error("❌ 無法提取數據！請確認你上載的 PDF 包含「總數」表格。")
                    else:
                        st.success(f"✅ 提取成功！已取得 {exam_year} 年數據。")
                        st.subheader(f"📋 {subject_name} {exam_year} 數據概覽 | Data Preview")
                        st.table(df_total.style.format(precision=2))

                        if attendance_ys is not None and attendance_ds is not None:
                            # 分離 UNCL 與其他等級
                            df_without_uncl = df_total[df_total["等級"] != "UNCL"].reset_index(drop=True)
                            df_uncl = df_total[df_total["等級"] == "UNCL"].reset_index(drop=True)
                            
                            # 處理非 UNCL 等級（使用累計差值）
                            chart_df = df_without_uncl.melt(
                                id_vars=["等級"],
                                value_vars=["貴校", "日校"],
                                var_name="學校類別",
                                value_name="人數"
                            )
                            chart_df["出席"] = chart_df["學校類別"].map({
                                "貴校": attendance_ys,
                                "日校": attendance_ds
                            })
                            chart_df = chart_df.sort_values(["學校類別", "等級"])
                            chart_df["累計差值"] = chart_df.groupby("學校類別")["人數"].diff().fillna(chart_df["人數"])
                            chart_df["累計差值"] = chart_df["累計差值"].clip(lower=0)
                            chart_df["百分比"] = (chart_df["累計差值"] / chart_df["出席"]) * 100
                            chart_df["百分比標籤"] = chart_df["百分比"].apply(lambda x: f"{x:.1f}%")
                            
                            # 處理 UNCL（直接用原始數字計算百分比，不參與減法）
                            if not df_uncl.empty:
                                uncl_row = df_uncl.iloc[0]
                                uncl_ys_count = int(uncl_row["貴校"])
                                uncl_ds_count = int(uncl_row["日校"])
                                uncl_ys_pct = (uncl_ys_count / attendance_ys) * 100
                                uncl_ds_pct = (uncl_ds_count / attendance_ds) * 100
                                
                                uncl_chart_data = pd.DataFrame({
                                    "等級": ["UNCL", "UNCL"],
                                    "學校類別": ["貴校", "日校"],
                                    "人數": [uncl_ys_count, uncl_ds_count],
                                    "出席": [attendance_ys, attendance_ds],
                                    "累計差值": [uncl_ys_count, uncl_ds_count],
                                    "百分比": [uncl_ys_pct, uncl_ds_pct],
                                    "百分比標籤": [f"{uncl_ys_pct:.1f}%", f"{uncl_ds_pct:.1f}%"]
                                })
                                chart_df = pd.concat([chart_df, uncl_chart_data], ignore_index=True)

                            bar = alt.Chart(chart_df).mark_bar().encode(
                                x=alt.X("等級:N", title="等級", sort=list(df_total["等級"]), axis=alt.Axis(labelFontSize=14, titleFontSize=14)),
                                xOffset="學校類別:N",
                                y=alt.Y("百分比:Q", title="佔出席百分比 (%)", axis=alt.Axis(labelFontSize=14, titleFontSize=14)),
                                color=alt.Color(
                                    "學校類別:N",
                                    scale=alt.Scale(domain=["貴校", "日校"], range=["#7BA8E0", "#FF9999"]),
                                    title="學校類別"
                                ),
                                tooltip=["等級", "學校類別", "累計差值", alt.Tooltip("百分比:Q", format=".1f")]
                            )

                            labels = alt.Chart(chart_df).mark_text(dy=-8, color="black", fontSize=16).encode(
                                x=alt.X("等級:N", sort=list(df_total["等級"])),
                                xOffset="學校類別:N",
                                y=alt.Y("百分比:Q"),
                                text=alt.Text("百分比標籤:N")
                            )

                            chart = (bar + labels).properties(height=420)
                            st.subheader("📈 等級佔出席人數百分比柱狀圖 | Percentage of Attendance by Grade")
                            st.altair_chart(chart, use_container_width=True)
                            
                            st.subheader("📊 數據表 | Data Table")
                            pivot_df = pd.DataFrame()
                            
                            # 處理非 UNCL 等級
                            for grade in df_without_uncl["等級"]:
                                grade_data = chart_df[chart_df["等級"] == grade]
                                ys_row = grade_data[grade_data["學校類別"] == "貴校"]
                                ds_row = grade_data[grade_data["學校類別"] == "日校"]
                                
                                if not ys_row.empty:
                                    ys_count = int(ys_row["累計差值"].values[0])
                                    ys_pct = f"{ys_row['百分比'].values[0]:.1f}%"
                                else:
                                    ys_count = 0
                                    ys_pct = "0.0%"
                                
                                if not ds_row.empty:
                                    ds_count = int(ds_row["累計差值"].values[0])
                                    ds_pct = f"{ds_row['百分比'].values[0]:.1f}%"
                                else:
                                    ds_count = 0
                                    ds_pct = "0.0%"
                                
                                pivot_df = pd.concat([pivot_df, pd.DataFrame({
                                    "等級": [grade],
                                    "貴校人數": [ys_count],
                                    "貴校百分比": [ys_pct],
                                    "日校人數": [ds_count],
                                    "日校百分比": [ds_pct]
                                })], ignore_index=True)
                            
                            # 處理 UNCL - 直接使用原始數字，計算百分比（不參與減法）
                            if not df_uncl.empty:
                                uncl_row = df_uncl.iloc[0]
                                uncl_ys_count = int(uncl_row["貴校"])
                                uncl_ds_count = int(uncl_row["日校"])
                                uncl_ys_pct = f"{(uncl_ys_count / attendance_ys) * 100:.1f}%"
                                uncl_ds_pct = f"{(uncl_ds_count / attendance_ds) * 100:.1f}%"
                                
                                pivot_df = pd.concat([pivot_df, pd.DataFrame({
                                    "等級": ["UNCL"],
                                    "貴校人數": [uncl_ys_count],
                                    "貴校百分比": [uncl_ys_pct],
                                    "日校人數": [uncl_ds_count],
                                    "日校百分比": [uncl_ds_pct]
                                })], ignore_index=True)
                            
                            # 轉置數據表
                            transposed_df = pivot_df.set_index("等級").T
                            st.dataframe(transposed_df, use_container_width=True)
                        else:
                            st.warning("⚠️ 無法計算百分比，缺少出席人數資料。")
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
        **Applicable for reports formatted like:** The table horizontally displays data such as 'Mean' and 'S.D.'.
        """)
        if os.path.exists("example1_item.png"):
            st.image("example1_item.png", caption="項目分析表格示例 | Example of Item Analysis Table", use_column_width=True)
        else:
            st.warning("⚠️ (提示: 系統未找到 example1_item.png | Image not found)")
    with col2:
        if current_file is None:
            st.warning("👆 請先在上方上載 PDF 檔案 | Please upload a PDF file above first.")
        else:
            with st.spinner("系統正在處理檔案，請稍候... | Processing file, please wait..."):
                try:
                    current_file.seek(0)
                    file_bytes = current_file.getvalue()
                    df_item = extract_item_analysis(file_bytes)
                    if df_item.empty:
                        st.error("❌ 無法提取數據！請確認你上載的是否為正確的「項目分析報告」。 \n *Failed to extract data! Please ensure you uploaded the correct 'Item Analysis Report'.*")
                    else:
                        st.success(f"✅ 提取成功！共獲取 {len(df_item)} 行數據。 \n *Extraction successful! {len(df_item)} rows retrieved.*")
                        st.subheader("📋 數據概覽 | Data Preview")
                        st.table(df_item.style.format(precision=2))
                        st.download_button(
                            label="📥 下載 Excel 檔案 | Download Excel File",
                            data=convert_df_to_excel(df_item, "Item Analysis"),
                            file_name=f"{current_file.name.replace('.pdf', '')}_ItemAnalysis.xlsx",
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
        **Applicable for reports formatted like:** The table lists the number of students for options 'A, B, C, D' and uses a ☑️ mark to indicate the correct answer.
        """)
        if os.path.exists("example2_mcq.png"):
            st.image("example2_mcq.png", caption="多項選擇題表格示例 | Example of MCQ Analysis Table", use_column_width=True)
        else:
            st.warning("⚠️ (提示: 系統未找到 example2_mcq.png | Image not found)")
    with col4:
        if current_file is None:
            st.warning("👆 請先在上方上載 PDF 檔案 | Please upload a PDF file above first.")
        else:
            with st.spinner("系統正在處理檔案，請稍候... | Processing file, please wait..."):
                try:
                    current_file.seek(0)
                    file_bytes = current_file.getvalue()
                    df_mcq = extract_mcq_analysis(file_bytes)
                    if df_mcq.empty:
                        st.error("❌ 無法提取數據！請確認你上載的是否為正確的「多項選擇題分析報告」。 \n *Failed to extract data! Please ensure you uploaded the correct 'MCQ Analysis Report'.*")
                    else:
                        st.success(f"✅ 提取成功！共獲取 {len(df_mcq)} 題的數據。 \n *Extraction successful! Data for {len(df_mcq)} questions retrieved. *")
                        st.subheader("📋 數據概覽 | Data Preview")
                        st.table(df_mcq.style.format(precision=2))
                        st.download_button(
                            label="📥 下載 Excel 檔案 | Download Excel File",
                            data=convert_df_to_excel(df_mcq, "MCQ Analysis"),
                            file_name=f"{current_file.name.replace('.pdf', '')}_MCQAnalysis.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="btn_mcq",
                            type="primary"
                        )
                except Exception as e:
                    st.error(f"❌ 處理檔案時發生錯誤 | Error processing file：{str(e)}")
