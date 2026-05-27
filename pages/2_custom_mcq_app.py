import streamlit as st
import pandas as pd

st.set_page_config(page_title="自定義 MCQ 分析", page_icon="🎯", layout="wide")
st.title("🎯 自定義 MCQ 分析 app")
st.caption("此頁會讀取主 app 已處理好的資料。請先回主 app 上載 PDF，並按『處理檔案並啟用自定義分析 app』。")

if "custom_cols" not in st.session_state:
    st.session_state.custom_cols = []
if "col_options_history" not in st.session_state:
    st.session_state.col_options_history = {}
if "item_custom_values" not in st.session_state:
    st.session_state.item_custom_values = {}
if "mcq_custom_values" not in st.session_state:
    st.session_state.mcq_custom_values = {}

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
            except:
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

st.page_link("app.py", label="⬅️ 返回主 app", icon="⬅️")

if "processed_mcq_df" not in st.session_state:
    st.warning("尚未找到已處理好的 MCQ 資料。請先回主 app 完成前處理。")
    st.stop()

df_mcq_c = st.session_state.processed_mcq_df.copy()
source_name = st.session_state.get("source_pdf_name", "未命名檔案")
st.success(f"已載入主 app 處理完成的資料：{source_name}")

if not df_mcq_c.empty:
    df_mcq_c = prepare_mcq_analysis_for_custom(df_mcq_c)
    if "題號" not in df_mcq_c.columns:
        df_mcq_c.insert(0, "題號", df_mcq_c.get("Question Number", range(1, len(df_mcq_c) + 1)))

# ── 橫屏並排：Step 1 & Step 2 ──
    step_col1, step_col2 = st.columns([1, 1])

    # ══════════════ Step 1 ══════════════
    with step_col1:
        st.info("Step 1：建立自定義欄位 (最多 6 個)")
        c1, c2 = st.columns([3, 1])
        with c1:
            new_col = st.text_input(
                "輸入新自定義欄位名稱：",
                key=f"new_col_input_mcq_{st.session_state.new_col_input_counter}"
            )
        with c2:
            st.write("")
            st.write("")
            if st.button("➕ 新增欄位", key="add_col_btn_mcq"):
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

        questions = df_mcq_c["題號"].tolist()
        sel_q = st.selectbox("選擇要輸入標籤的題號：", questions, key="mcq_q_sel")
        current_values = st.session_state.mcq_custom_values.get(sel_q, {})

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
                    key=f"sel_mcq_{col}_{st.session_state.sel_input_counter}"
                )

                if sel_val == f"➕ 輸入新的{col}":
                    # 文字框放在同一行右邊
                    _, right = st.columns([1, 2])
                    with right:
                        new_val = st.text_input(
                            f"請在此輸入新的「{col}」:",
                            key=f"new_val_mcq_{col}_{st.session_state.new_val_input_counter}"
                        )
                    input_results[col] = new_val
                else:
                    input_results[col] = sel_val

            submit_btn = st.button("📥 儲存設定", key=f"save_mcq_{sel_q}")
            if submit_btn:
                if sel_q not in st.session_state.mcq_custom_values:
                    st.session_state.mcq_custom_values[sel_q] = {}
                for col, val in input_results.items():
                    if val:
                        st.session_state.mcq_custom_values[sel_q][col] = val
                        if val not in st.session_state.col_options_history[col]:
                            st.session_state.col_options_history[col].append(val)
                # 同時 +1，清空下拉框與文字框
                st.session_state.new_val_input_counter += 1
                st.session_state.sel_input_counter += 1
                st.success(f"第 {sel_q} 題設定已儲存！")
                st.rerun()

    # ══════════════ 總覽表 ══════════════
    df_mcq_display = df_mcq_c.copy()
    for col in st.session_state.custom_cols:
        df_mcq_display[col] = df_mcq_display["題號"].apply(
            lambda x: st.session_state.mcq_custom_values.get(x, {}).get(col, "")
        )

    st.write("📊 **總覽表 (自動更新)：**")
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

    st.markdown("""
    🔍 顏色說明：紅色 = 貴校最高選項既非正答亦不同於日校；黃色 = 非正答；藍色 = 與日校最高選項不同。
    """)
    st.dataframe(final_mcq_df.style.apply(highlight_mcq_row, axis=1), use_container_width=True, hide_index=True)
else:
    st.error("找不到可用的 MCQ 分析資料。"),
    "new_col_input_counter": 0,
    "sel_input_counter": 0,
    "new_val_input_counter": 0
