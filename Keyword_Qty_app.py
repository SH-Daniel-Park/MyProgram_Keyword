import os
import streamlit as st
import requests
import pandas as pd
from datetime import date
from dateutil.relativedelta import relativedelta

st.set_page_config(page_title="Naver 키워드 트렌드 & 요약", layout="wide")

# -------------------------------
# Secrets / Credentials Handling
# -------------------------------
def get_credentials():
    # 1) Try Streamlit Secrets
    naver = st.secrets.get("naver", {})
    cid = naver.get("client_id")
    csec = naver.get("client_secret")

    # 2) Fallback to environment variables
    if not cid:
        cid = os.environ.get("NAVER_CLIENT_ID")
    if not csec:
        csec = os.environ.get("NAVER_CLIENT_SECRET")

    # 3) As a last resort, allow user input (session-only; not persisted)
    with st.sidebar:
        st.markdown("### 🔐 자격 증명")
        if not cid:
            cid = st.text_input("Client ID (임시 입력)", type="password")
        if not csec:
            csec = st.text_input("Client Secret (임시 입력)", type="password")

        if cid and csec:
            st.caption("✅ 자격 증명이 설정되었습니다.")
        else:
            st.warning("Client ID/Secret이 설정되지 않았습니다. Streamlit Cloud에서는 **Settings → Secrets**에 입력하세요.\n"
                       "로컬에선 `.streamlit/secrets.toml` 또는 환경변수로 설정할 수 있습니다.")

    return cid, csec

NAVER_CLIENT_ID, NAVER_CLIENT_SECRET = get_credentials()

def naver_headers():
    return {
        "X-Naver-Client-Id": NAVER_CLIENT_ID or "",
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET or "",
        "Content-Type": "application/json; charset=UTF-8",
    }

# -------------------------------
# API Helpers
# -------------------------------
def fetch_trend(start_date, end_date, keywords, time_unit="week", device=None, gender=None, ages=None):
    url = "https://openapi.naver.com/v1/datalab/search"
    groups = [{"groupName": kw, "keywords": [kw]} for kw in keywords][:5]  # DataLab max 5 groups
    payload = {
        "startDate": start_date.strftime("%Y-%m-%d"),
        "endDate": end_date.strftime("%Y-%m-%d"),
        "timeUnit": time_unit,
        "keywordGroups": groups,
    }
    if device: payload["device"] = device
    if gender: payload["gender"] = gender
    if ages:   payload["ages"] = ages

    r = requests.post(url, headers=naver_headers(), json=payload, timeout=20)
    if r.status_code == 401 or r.status_code == 403:
        raise RuntimeError("인증 오류(401/403). Client ID/Secret을 확인하세요.")
    r.raise_for_status()
    return r.json()

def fetch_news_snippets(query, display=5, sort="date"):
    url = "https://openapi.naver.com/v1/search/news.json"
    params = {"query": query, "display": display, "sort": sort}
    r = requests.get(url, headers=naver_headers(), params=params, timeout=20)
    if r.status_code == 401 or r.status_code == 403:
        raise RuntimeError("인증 오류(401/403). Client ID/Secret을 확인하세요.")
    r.raise_for_status()
    return r.json().get("items", [])

# -------------------------------
# UI: Controls
# -------------------------------
st.title("네이버 키워드 트렌드 순위 & 핵심 요약")

with st.sidebar:
    st.subheader("조회 조건")
    end = st.date_input("종료일", value=date.today())
    start = st.date_input("시작일", value=end - relativedelta(months=1))
    time_unit = st.selectbox("집계 단위", ["date", "week", "month"], index=1)
    device = st.selectbox("기기", ["", "pc", "mo"], index=0)
    gender = st.selectbox("성별", ["", "m", "f"], index=0)
    ages = st.multiselect("연령대(옵션)", ["1","2","3","4","5","6","7","8","9","10","11"],
                          help="연령 코드(1:0-12, 2:13-18, ... 11:60+)")
    keywords_text = st.text_area("키워드(쉼표로 구분, 최대 5개)", "아이폰, 갤럭시, 에어팟, 무선이어폰, 폴더블폰")
    run = st.button("조회")

# Block running if credentials missing
if run and (not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET):
    st.error("Client ID/Secret이 필요합니다. 사이드바 또는 Secrets에 입력하세요.")
    st.stop()

# -------------------------------
# Main Action
# -------------------------------
if run:
    keywords = [k.strip() for k in keywords_text.split(",") if k.strip()]
    if not keywords:
        st.warning("키워드를 1개 이상 입력하세요.")
        st.stop()

    try:
        with st.spinner("검색 트렌드 불러오는 중..."):
            trend = fetch_trend(start, end, keywords, time_unit, device or None, gender or None, ages or None)
    except Exception as e:
        st.error(f"트렌드 API 호출 실패: {e}")
        st.stop()

    # Build ranking table
    rows = []
    for res in trend.get("results", []):
        title = res["title"]
        series = pd.DataFrame(res["data"])
        avg_ratio = float(series["ratio"].mean())
        max_ratio = float(series["ratio"].max())
        last_ratio = float(series["ratio"].iloc[-1])
        rows.append({"키워드": title, "평균지수": avg_ratio, "최대지수": max_ratio, "최근지수": last_ratio})

    if not rows:
        st.info("데이터가 없습니다. 기간/키워드 설정을 확인하세요.")
        st.stop()

    rank_df = pd.DataFrame(rows).sort_values("평균지수", ascending=False).reset_index(drop=True)
    rank_df.index = rank_df.index + 1

    st.subheader("기간 내 관심도 순위(상대지수 기반)")
    st.dataframe(rank_df, use_container_width=True)

    st.subheader("키워드별 최신 뉴스 요약")
    cols = st.columns(2)
    for i, kw in enumerate(rank_df["키워드"].tolist()):
        with cols[i % 2]:
            st.markdown(f"### 🔎 {kw}")
            try:
                news = fetch_news_snippets(kw, display=5, sort="date")
            except Exception as e:
                st.warning(f"뉴스 API 호출 실패({kw}): {e}")
                news = []
            if not news:
                st.write("관련 뉴스가 없습니다.")
            for item in news:
                # Clean simple <b> tags from Naver API and compose markdown safely
                title = item.get("title", "").replace("<b>", "").replace("</b>", "")
                link = item.get("link", "")
                desc = item.get("description", "").replace("<b>", "").replace("</b>", "")
                st.markdown(f"- [{title}]({link})  \n{desc}")
