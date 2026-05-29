import io
import re

import altair as alt
import pandas as pd
import pdfplumber
import streamlit as st


@st.cache_data
def extract_item_analysis(file_bytes):
    row_pattern = re.compile(
        r'^(.*?)\s+(\d+)\s+(\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)\s+(\d+%)\s+(\d+\.\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)\s+(\d+%)\s+(\d+\.\d+)\s*([+-]?\d+\.\d+)\s*'
    )
    extracted_data = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
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


@st.cache_data
def extract_mcq_analysis(file_bytes):
    mcq_data = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
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


@st.cache_data
def extract_latest_dse_total_data(file_bytes):
    target_grades = ['5**', '5*+', '5+', '4+', '3+', '2+', '1+', 'UNCL', '出席 Sat']
    results = []
    subject_name = "未知科目"
    exam_year = "未知年份"
    attendance_ys = None
    attendance_ds = None
    expected_grade_count = len(target_grades) - 1

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            if "總數" in text and "貴校" in text and "5**" in text:
                lines = text.split('\n')

                for i, line in enumerate(lines):
                    if "HKDSE 20" in line and exam_year == "未知年份":
                        exam_year = line.replace("HKDSE", "").strip()

                for i, line in enumerate(lines):
                    if ("總數 Total" in line or "總數" in line) and subject_name == "未知科目":
                        if i >= 2 and "Category" not in lines[i-2] and "學科" not in lines[i-2] and "results" not in lines[i-2]:
                            subject_name = lines[i-2].strip()
                        elif i >= 1:
                            subject_name = lines[i-1].strip()

                in_total_section = False
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
                                        if grade == '出席 Sat':
                                            attendance_ys = int(ys_numbers[-1])
                                            attendance_ds = int(ds_numbers[-1])
                                        elif not any(r['等級'] == grade for r in results):
                                            results.append({
                                                '等級': grade,
                                                '貴校': int(ys_numbers[-1]),
                                                '日校': int(ds_numbers[-1])
                                            })
                                break
                if len(results) == expected_grade_count and attendance_ys is not None and attendance_ds is not None:
                    break

    df = pd.DataFrame(results)
    if not df.empty:
        df['等級'] = pd.Categorical(df['等級'], categories=[g for g in target_grades if g != '出席 Sat'], ordered=True)
        df = df.sort_values('等級').reset_index(drop=True)
    return df, subject_name, exam_year, attendance_ys, attendance_ds


def convert_df_to_excel(df, sheet_name):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return output.getvalue()
