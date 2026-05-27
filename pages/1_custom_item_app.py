import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from io import BytesIO

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

# ── 禁用 Streamlit 的 'c' 鍵 (Clear Cache) 快捷鍵 ──
# 需要通過 iframe 的 window.parent 注入到主頁面 document
components.html("""
<script>
(function() {
    function blockClearCache(e) {
        // 攔截單鍵 'c' / 'C'（Streamlit 的 clear cache 快捷鍵）
        // 但保留 Ctrl+C / Cmd+C（正常複製）
        if (!e.ctrlKey && !e.metaKey && !e.altKey &&
            (e.key === 'c' || e.key === 'C')) {
            var tag = document.activeElement ? document.activeElement.tagName : '';
            // 只在非輸入框時攔截（避免影響正常輸入）
            if (tag !== 'INPUT' && tag !== 'TEXTAREA' && tag !== 'SELECT') {
                e.stopImmediatePropagation();
            }
        }
    }
    // 注入到父頁面
    try {
        window.parent.document.addEventListener('keydown', blockClearCache, true);
    } catch(err) {
        document.addEventListener('keydown', blockClearCache, true);
    }
})();
</script>
""", height=0)

st.set_page_config(page_title="自定義項目分析", page_icon="📌", layout="wide", initial_sidebar_state="expanded")
st.title("📌 自定義項目分析 app")
st.caption("此頁會讀取主 app 已處理好的資料。")

for k, v in {
    "custom_cols": [],
    "col_options_history": {},
    "item_custom_values": {},
    "mcq_custom_values": {},
    "processed_item_df": None,
    "source_pdf_name": None,
    "new_col_input_counter": 0,
    "new_val_input_counter": 0,
    # 用來清空 Step 2 下拉選擇框的 counter
    "sel_input_counter": 0,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

if st.session_state.source_pdf_name:
    st.success(f"已載入主 app 保存的資料：{st.session_state.source_pdf_name}")
else:
    st.warning("尚未找到已處理好的資料。請先回主 app 上載 PDF。")

if st.session_state.processed_item_df is None:
    st.stop()

df_item_c = st.session_state.processed_item_df.copy()
if not df_item_c.empty:
    if "題號" not in df_item_c.columns:
        df_item_c.insert(0, "題號", df_item_c.get("Item", range(1, len(df_item_c) + 1)))

    # ── 橫屏並排：Step 1 & Step 2 ──
    step_col1, step_col2 = st.columns([1, 1])

    # ══════════════ Step 1 ══════════════
    with step_col1:
        st.info("Step 1：建立自定義欄位 (最多 6 個)")
        c1, c2 = st.columns([3, 1])
        with c1:
            new_col = st.text_input(
                "輸入新自定義欄位名稱：",
                key=f"new_col_input_item_{st.session_state.new_col_input_counter}"
            )
        with c2:
            st.write("")
            st.write("")
            if st.button("➕ 新增欄位", key="add_col_btn_item"):
                if len(st.session_state.custom_cols) >= 6:
                    # 已達上限，提示用戶
                    st.error("已達上限！最多只能建立 6 個自定義欄位。")
                elif not new_col:
                    st.warning("請先輸入欄位名稱。")
                elif new_col in st.session_state.custom_cols:
                    st.warning(f"欄位「{new_col}」已存在。")
                else:
                    st.session_state.custom_cols.append(new_col)
                    st.session_state.col_options_history[new_col] = []
                    st.session_state.new_col_input_counter += 1
                    st.rerun()

        if st.session_state.custom_cols:
            st.success(f"目前建立的欄位：{', '.join(st.session_state.custom_cols)}")

    # ══════════════ Step 2 ══════════════
    with step_col2:
        st.info("Step 2：為每一題設定分類 (下拉聯想與新增)")

        questions = df_item_c["題號"].tolist()
        sel_q = st.selectbox("選擇要輸入標籤的題號：", questions, key="item_q_sel")
        current_values = st.session_state.item_custom_values.get(sel_q, {})

        with st.container():
            st.write(f"**正在編輯：第 {sel_q} 題**")
            input_results = {}
            for col in st.session_state.custom_cols:
                history_opts = st.session_state.col_options_history.get(col, [])
                options = [""] + history_opts + [f"➕ 輸入新的{col}"]
                default_idx = 0
                curr_val = current_values.get(col, "")
                if curr_val in options:
                    default_idx = options.index(curr_val)

                # 下拉框也用 counter 控制，儲存後清空
                sel_val = st.selectbox(
                    f"{col}:",
                    options=options,
                    index=default_idx,
                    key=f"sel_item_{col}_{st.session_state.sel_input_counter}"
                )

                if sel_val == f"➕ 輸入新的{col}":
                    # 文字框放在同一行右邊
                    _, right = st.columns([1, 2])
                    with right:
                        new_val = st.text_input(
                            f"請在此輸入新的「{col}」:",
                            key=f"new_val_item_{col}_{st.session_state.new_val_input_counter}"
                        )
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
                # 同時 +1，清空下拉框與文字框
                st.session_state.new_val_input_counter += 1
                st.session_state.sel_input_counter += 1
                st.success(f"第 {sel_q} 題設定已儲存！")
                st.rerun()

    # ══════════════ 總覽表 ══════════════
    df_display = df_item_c.copy()
    for col in st.session_state.custom_cols:
        df_display[col] = df_display["題號"].apply(
            lambda x: st.session_state.item_custom_values.get(x, {}).get(col, "")
        )

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

    # --- 1. 批量調節欄寬 ---
    wide_cols = st.multiselect("選擇要調寬的欄位 (批量變寬)：", options=final_df.columns.tolist())

    col_config_dict = {}
    for col in wide_cols:
        col_config_dict[col] = st.column_config.Column(width="large")

    # --- 2. 設定 Highlight 邏輯 ---
    def highlight_rows(row):
        # 預設範例：如果第一欄(Item)或特定欄位符合條件，整列上黃底。
        # 你可以隨時修改這段邏輯，例如：if row.get("Topic") == "重點":
        # 目前先假設如果該題目已經在自訂欄位有任何填寫，就給予一點 highlight 提示
        has_custom = False
        for c in st.session_state.custom_cols:
            if pd.notna(row.get(c)) and str(row.get(c)).strip() != "":
                has_custom = True
                break

        if has_custom:
            return ["background-color: #FFF59D; color: black"] * len(row)
        return [""] * len(row)

    # 產生套用顏色格式的 DataFrame
    styled_df = final_df.style.apply(highlight_rows, axis=1)

    # 顯示加上欄寬設定與顏色的表格
    st.dataframe(styled_df, use_container_width=True, hide_index=True, column_config=col_config_dict)

    # --- 3. 準備並顯示帶 Highlight 的 Excel 下載按鈕 ---
    def get_excel_with_style(styler_obj):
        output = BytesIO()
        # 注意: 需要安裝 openpyxl
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            styler_obj.to_excel(writer, index=False, sheet_name="Result")
        return output.getvalue()

    excel_data = get_excel_with_style(styled_df)

    st.download_button(
        label="📥 下載含 Highlight 的 Excel (xlsx)",
        data=excel_data,
        file_name="styled_result.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

else:
    st.error("找不到可用的項目分析資料。")
