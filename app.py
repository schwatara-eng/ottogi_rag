import csv
import re
from pathlib import Path
from openai import OpenAI

import streamlit as st
from pypdf import PdfReader

st.set_page_config(page_title="오뚜기 기업 규정 Q&A")

st.title("오뚜기 기업 규정 Q&A")
st.write("오뚜기 기업 규정과 사실표, 안내서를 바탕으로 질문에 답하는 앱입니다.")

if st.secrets.get("OPENAI_API_KEY"):
    st.success("API 키를 읽었어요.")
else:
    st.error("API 키 설정을 확인해 주세요.")

data_dir = Path(__file__).resolve().parent / "data"

st.header("주제별 핵심 근거")

facts_path = data_dir / "ottogi_facts.csv"

if facts_path.is_file():
    with facts_path.open(encoding="utf-8-sig", newline="") as file:
        facts = list(csv.DictReader(file))

    if facts:
        topics = list(dict.fromkeys(fact["분야"] for fact in facts))

        selected_topic = st.selectbox(
            "분야 선택",
            topics,
            key="policy_dashboard_topic",
        )

        selected_facts = [
            fact for fact in facts if fact["분야"] == selected_topic
        ]

        st.caption(f"ottogi_facts.csv에서 뽑은 대표 근거 {len(selected_facts)}개")

        for fact in selected_facts:
            summary_column, source_column = st.columns([3, 2])

            with summary_column:
                st.markdown(f"**{fact['근거ID']} · 핵심 내용**")
                st.write(fact["내용"])
                st.caption(f"적용 범위 · {fact['적용 범위']}")

            with source_column:
                st.markdown("**원문 위치**")
                st.write(fact["출처 파일"])
                st.caption(f"PDF {fact['PDF 쪽']}쪽 · {fact['조항']}")

            st.divider()
    else:
        st.info("사실표에 표시할 근거가 없어.")
else:
    st.info("data 폴더에 ottogi_facts.csv를 넣으면 핵심 근거를 볼 수 있어.")

pdf_paths = sorted(data_dir.glob("*.pdf"))

csv_paths = sorted(data_dir.glob("*.csv"))
md_paths = sorted(data_dir.glob("*.md"))

if not (pdf_paths or csv_paths or md_paths):
    st.error("data 폴더에 PDF, CSV 또는 MD 자료를 넣어 주세요.")
    st.stop()

pages = []
document_counts = {}

for pdf_path in pdf_paths:
    try:
        reader = PdfReader(pdf_path)
        document_pages = []

        for page_number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()

            if text:
                document_pages.append({
                    "source": pdf_path.name,
                    "location": f"PDF {page_number}쪽",
                    "text": text,
                })
    except Exception:
        st.warning(f"읽기 실패 · {pdf_path.name}")
        continue

    if not document_pages:
        st.warning(f"추출할 수 있는 글자가 없어요 · {pdf_path.name}")
        continue

    pages.extend(document_pages)
    document_counts[pdf_path.name] = len(document_pages)

for path in csv_paths + md_paths:
    try:
        entries = []
        if path.suffix == ".csv":
            with path.open(encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    if path.name == "ottogi_policy_index.csv":
                        entries.append({
                            "source": row["출처 파일"],
                            "location": f"PDF {row['PDF 쪽']}쪽 · {row['제목']} · {row['추출 방식']}",
                            "text": f"{row['제목']}\n{row['본문']}",
                        })
                    else:
                        entries.append({
                            "source": path.name,
                            "location": row["근거ID"],
                            "text": "\n".join(f"{key} {value}" for key, value in row.items()),
                        })
        else:
            markdown = path.read_text(encoding="utf-8-sig")
            for section in re.split(r"(?m)(?=^## )", markdown):
                if section.strip():
                    entries.append({
                        "source": path.name,
                        "location": section.splitlines()[0].lstrip("# ").strip(),
                        "text": section.strip(),
                    })
    except (OSError, UnicodeError, csv.Error, KeyError):
        st.warning(f"읽기 실패 · {path.name}")
        continue
    if entries:
        pages.extend(entries)
        document_counts[path.name] = len(entries)

st.write(f"읽어온 문서 {len(document_counts)}개")

if not pages:
    st.stop()

with st.expander("읽어온 문서 목록"):
    for filename, page_count in document_counts.items():
        st.write(f"{filename} · 검색 단위 {page_count}개")

keyword = st.text_input("검색할 단어를 입력해 주세요", placeholder="예: 접대").strip()

if keyword:
    matches = []

    for page in pages:
        text = page["text"]
        position = text.find(keyword)
        if position < 0 and re.sub(r"\s+", "", keyword) in re.sub(r"\s+", "", text):
            position = 0

        if position >= 0:
            start = max(0, position - 80)
            end = position + len(keyword) + 160
            matches.append((page, text[start:end]))

    if matches:
        st.write(f"검색어가 포함된 근거를 {len(matches)}개 찾았어요.")

        for page, excerpt in matches:
            with st.expander(f"{page['source']} · {page['location']}"):
                st.text(excerpt)
    else:
        st.info("검색어가 들어 있는 근거를 찾지 못했어요.")
question = st.text_input(
    "기업 규정에 대해 궁금한 점을 입력해 주세요",
    placeholder="예: 규정에서 접대에 해당하는 행위는 무엇인가요?",
)

if st.button("답변 받기"):
    if not keyword or not question.strip():
        st.warning("검색어와 질문을 모두 입력해 주세요.")
    elif not matches:
        st.info("제공된 자료로는 확인할 수 없습니다.")
    else:
        context = "\n\n".join(
            f"[{page['source']}, {page['location']}]\n{page['text']}"
            for page, _ in matches
        )

        client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

        with st.spinner("찾은 규정을 바탕으로 답변을 만드는 중이에요."):
            response = client.responses.create(
                model="gpt-4.1-mini",
                instructions=(
                    "제공된 문서 본문을 근거로 한국어로 답하세요. "
                    "각 판단 바로 뒤에 원문 PDF 파일명과 쪽수를 출처로 붙이세요. CSV나 안내서의 내용을 사용하면 해당 자료에 표시된 원문 근거를 인용하세요. "
                    "OCR 자료의 숫자나 글자가 불명확하면 원문 확인이 필요하다고 알리세요. 행위의 정의, 금지 조건, 승인 예외를 구분하세요. "
                    "근거가 부족하면 '제공된 자료로는 확인할 수 없습니다.'라고 답하세요."
                ),
                input=f"질문:\n{question}\n\n문서 본문:\n{context}",
            )

        st.subheader("답변")
        st.write(response.output_text)