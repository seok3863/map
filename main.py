
import streamlit as st
import requests
from datetime import datetime, timedelta
from urllib.parse import quote

st.set_page_config(page_title="지각 방지 등교 계산기", page_icon="⏰", layout="centered")

st.title("⏰ 지각 방지 등교 시간 계산기")
st.caption("카카오맵으로 경로를 확인하고 여유 있게 등교해요!")

try:
    API_KEY = st.secrets["KAKAO_REST_KEY"]
except Exception:
    API_KEY = ""

def kakao_get(url, params):
    headers = {"Authorization": f"KakaoAK {API_KEY}"}
    response = requests.get(url, headers=headers, params=params, timeout=15)
    response.raise_for_status()
    data = response.json()
    if data.get("errorType") or data.get("error"):
        raise ValueError(data.get("message", "카카오 API 오류"))
    return data

def address_to_xy(address):
    data = kakao_get(
        "https://dapi.kakao.com/v2/local/search/address.json",
        {"query": address, "size": 1}
    )
    docs = data.get("documents", [])
    if not docs:
        raise ValueError(f"주소를 찾을 수 없어요: {address}")
    return float(docs[0]["x"]), float(docs[0]["y"])

def route_minutes(start, end, mode):
    sx, sy = start
    ex, ey = end

    if mode == "도보":
        url = "https://dapi.kakao.com/v2/routing/walk"
    else:
        url = "https://dapi.kakao.com/v2/routing/publictraffic"

    data = kakao_get(url, {
        "start_x": sx, "start_y": sy,
        "end_x": ex, "end_y": ey,
        "input_coord": "WGS84"
    })

    routes = data.get("routes", [])
    if not routes:
        raise ValueError("경로를 찾지 못했어요. 주소를 확인해 주세요.")

    summary = routes[0].get("summary", {})
    duration = summary.get("duration")
    if duration is None:
        raise ValueError("응답에서 소요 시간을 확인할 수 없어요.")
    return max(1, round(float(duration) / 60))

if not API_KEY:
    st.warning(
        "카카오 REST API 키가 설정되지 않았어요. "
        "Streamlit Cloud의 Settings → Secrets에 "
        'KAKAO_REST_KEY = "발급받은 REST API 키"를 추가해 주세요.'
    )

with st.form("school_form"):
    home = st.text_input("🏠 집 주소", placeholder="예: 경기도 수원시 ...")
    school = st.text_input("🏫 학교 주소", placeholder="예: 경기도 수원시 ...")
    mode = st.radio("🚶 이동 수단", ["도보", "대중교통", "자동차"], horizontal=True)

    target = st.time_input("⏰ 학교 도착 목표 시각", value=datetime.strptime("08:30", "%H:%M").time())
    prep = st.number_input("🧼 씻기·옷 입기·아침 식사 시간(분)", 0, 180, 40, 5)
    buffer = st.number_input("🛟 추가 여유 시간(분)", 0, 60, 10, 5)

    if mode == "자동차":
        drive_minutes = st.number_input("자동차 예상 이동 시간(분)", 1, 300, 20)
    else:
        drive_minutes = 0

    submitted = st.form_submit_button("등교 시간 계산하기", type="primary")

if submitted:
    if not home.strip() or not school.strip():
        st.error("집 주소와 학교 주소를 모두 입력해 주세요.")
    elif not API_KEY:
        st.error("먼저 카카오 REST API 키를 Streamlit Secrets에 등록해 주세요.")
    else:
        try:
            with st.spinner("주소와 경로를 확인하고 있어요..."):
                start_xy = address_to_xy(home.strip())
                end_xy = address_to_xy(school.strip())

                if mode == "자동차":
                    travel = int(drive_minutes)
                else:
                    travel = route_minutes(start_xy, end_xy, mode)

            arrival = datetime.combine(datetime.today().date(), target)
            leave = arrival - timedelta(minutes=travel + buffer)
            wake = leave - timedelta(minutes=prep)

            st.success("등교 시간 계산 완료!")
            a, b, c = st.columns(3)
            a.metric("🌅 일어날 시각", wake.strftime("%H:%M"))
            b.metric("🚪 출발 시각", leave.strftime("%H:%M"))
            c.metric("🏫 이동 시간", f"{travel}분")

            st.info(
                f"목표 도착: {target.strftime('%H:%M')}\n\n"
                f"준비 시간: {prep}분 · 추가 여유: {buffer}분"
            )

            if wake.date() < arrival.date():
                st.warning("기상 시각이 전날로 계산됐어요. 목표 시각과 준비 시간을 확인해 주세요.")

            map_url = (
                "https://map.kakao.com/link/to/"
                + quote(school.strip(), safe="")
                + f",{end_xy[1]},{end_xy[0]}"
            )
            st.link_button("🗺️ 카카오맵에서 학교 위치 보기", map_url)

            route_url = (
                "https://map.kakao.com/link/by/"
                + {"도보": "walk", "대중교통": "traffic", "자동차": "car"}[mode]
                + "/"
                + quote(home.strip(), safe="")
                + f",{start_xy[1]},{start_xy[0]}/"
                + quote(school.strip(), safe="")
                + f",{end_xy[1]},{end_xy[0]}"
            )
            st.link_button("🧭 카카오맵에서 길찾기 열기", route_url)

            if mode == "자동차":
                st.caption("자동차 시간은 입력한 값이에요. 출발 전 카카오맵에서 교통 상황을 확인해 주세요.")

        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                st.error("카카오 API 무료 사용량 한도에 도달했어요. 나중에 다시 시도해 주세요.")
            elif e.response is not None and e.response.status_code in (401, 403):
                st.error("API 키가 잘못됐거나 카카오맵 API 설정이 완료되지 않았어요.")
            else:
                st.error("카카오 API 요청에 실패했어요. 잠시 후 다시 시도해 주세요.")
        except Exception as e:
            st.error(f"계산 중 문제가 발생했어요: {e}")
