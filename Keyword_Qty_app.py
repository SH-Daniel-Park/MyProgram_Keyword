import streamlit as st
import requests
import pandas as pd
from datetime import date
from dateutil.relativedelta import relativedelta

# ✅ Streamlit Community Cloud / Local: read secrets from st.secrets
# Put these in Streamlit Cloud: Settings → Secrets
# [naver]
# client_id = "YOUR_CLIENT_ID"
# client_secret = "YOUR_CLIENT_SECRET"
NAVER_CLIENT_ID = st.secrets["naver"]["client_id"]
NAVER_CLIENT_SECRET = st.secrets["naver"]["client_secret"]

def naver_headers():
    return {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
        "Content-Type": "application/json; charset=UTF-8",
    }

def fetch_trend(start_date, end_date, keywords, time_unit="week", device=None, gender=None, ages=None):
    """Call Naver DataLab Search API for keyword trend data."""
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
    r.raise_for_status()
    return r.json()

def fetch_news_snippets(query, display=5, sort="date"):
    """Call Naver Search API (news) for short previews."""
    url = "https://openapi.naver.com/v1/search/news.json"
    params = {"query": query, "display": display, "sort": sort}
    r = requests.get(url, headers={
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }, params=params, timeout=20)
    r.raise_for_status()
    return r.json().get("items", [])

st.set_page_config(page_title="Naver 키워드 트렌드 & 요약", layout="wide")
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

if run:
    keywords = [k.strip() for k in keywords_text.split(",") if k.strip()]
    if not keywords:
        st.warning("키워드를 1개 이상 입력하세요.")
        st.stop()

    with st.spinner("검색 트렌드 불러오는 중..."):
        trend = fetch_trend(start, end, keywords, time_unit, device or None, gender or None, ages or None)

    # Build ranking table from trend ratios
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
            news = fetch_news_snippets(kw, display=5, sort="date")
            if not news:
                st.write("관련 뉴스가 없습니다.")
            for item in news:
                # Clean simple <b> tags from Naver API and compose markdown safely
                title = item.get("title", "").replace("<b>", "").replace("</b>", "")
                link = item.get("link", "")
                desc = item.get("description", "").replace("<b>", "").replace("</b>", "")
                # ✅ IMPORTANT: use \n inside f-string instead of raw newlines
                st.markdown(f"- [{title}]({link})  \n{desc}")
