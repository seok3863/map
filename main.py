
import streamlit as st
import requests
from datetime import datetime, timedelta
from urllib.parse import quote

st.set_page_config(
    page_title="지각 방지 등교 계산기",
    page_icon="⏰",
    layout="centered",
)

st.title("⏰ 지각 방지 등교 시간 계산기")
st.caption("카카오맵으로 경로를 확인하고 여유 있게 등교해요!")

# Streamlit Cloud → Settings → Secrets에 등록한 키
API_KEY = st.secrets.get("KAKAO_REST_KEY", "")
API_KEY = API_KEY.strip() if API_KEY else ""

BASE_URL = "https://dapi.kakao.com"


def kakao_get(url, params):
    """카카오 API 요청 및 오류 확인"""
    if not API_KEY:
        raise ValueError(
            "Secrets에 KAKAO_REST_KEY가 설정되지 않았어요."
        )

    try:
        response = requests.get(
            url,
            headers={"Authorization": f"KakaoAK {API_KEY}"},
            params=params,
            timeout=20,
        )
    except requests.RequestException as e:
        raise ValueError(
            f"카카오 서버에 연결하지 못했어요: {e}"
        ) from e

    try:
        data = response.json()
    except ValueError:
        data = {}

    if not response.ok:
        message = (
            data.get("msg")
            or data.get("message")
            or response.text[:500]
            or "상세 오류 내용 없음"
        )
        raise ValueError(
            f"카카오 API HTTP {response.status_code}: {message}"
        )

    if data.get("errorType") or data.get("error"):
        raise ValueError(
            data.get("message")
            or data.get("msg")
            or str(data)
        )

    return data


def address_to_xy(address):
    """주소 또는 장소명을 경도, 위도로 변환"""

    # 먼저 도로명/지번 주소 검색
    data = kakao_get(
        f"{BASE_URL}/v2/local/search/address.json",
        {"query": address, "size": 1},
    )

    docs = data.get("documents", [])

    if docs:
        item = docs[0]
        return (
            float(item["x"]),
            float(item["y"]),
            item.get("address_name", address),
        )

    # 주소 검색 결과가 없으면 장소명으로 검색
    data = kakao_get(
        f"{BASE_URL}/v2/local/search/keyword.json",
        {"query": address, "size": 1},
    )

    docs = data.get("documents", [])

    if not docs:
        raise ValueError(
            f"주소 또는 장소를 찾지 못했어요: {address}\n"
            "도로명 주소나 정확한 장소명을 입력해 주세요."
        )

    item = docs[0]
    return (
        float(item["x"]),
        float(item["y"]),
        item.get("place_name", address),
    )


def route_minutes(start, end, mode):
    """도보 또는 대중교통 경로의 예상 소요 시간 계산"""

    sx, sy, _ = start
    ex, ey, _ = end

    if mode == "도보":
        url = f"{BASE_URL}/v2/routing/walk"
    elif mode == "대중교통":
        url = f"{BASE_URL}/v2/routing/publictraffic"
    else:
        raise ValueError("지원하지 않는 이동 수단이에요.")

    data = kakao_get(
        url,
        {
            "start_x": sx,
            "start_y": sy,
            "end_x": ex,
            "end_y": ey,
            "input_coord": "WGS84",
        },
    )

    # 도보 API 응답 확인
    if mode == "도보":
        status = data.get("status")

        if status != "OK":
            messages = {
                "SAME_POINT": "출발지와 도착지가 같아요.",
                "START_LINK_NOT_FOUND": "출발지 주변의 도보 경로를 찾지 못했어요.",
                "END_LINK_NOT_FOUND": "도착지 주변의 도보 경로를 찾지 못했어요.",
                "TOO_MANY_SEARCH_LINK": "경로 탐색 범위가 너무 복잡해요.",
                "TOO_FAR_AWAY": "출발지와 도착지의 거리가 너무 멀어요.",
                "ROUTE_RESULT_NOT_FOUND": "도보 경로 결과가 없어요.",
            }
            raise ValueError(
                messages.get(
                    status,
                    f"도보 경로 탐색 실패: {status or data}",
                )
            )

        route = data.get("route", {})
        properties = route.get("properties", {})
        duration = properties.get("totalTime")

    # 대중교통 API 응답 확인
    else:
        status = data.get("status")

        if status != "OK":
            messages = {
                "STARTNODES_NULL": "출발지 주변의 대중교통 정류장이나 노드를 찾지 못했어요.",
                "ENDNODES_NULL": "학교 주변의 대중교통 정류장이나 노드를 찾지 못했어요.",
                "EQUAL_POINTS": "출발지와 도착지가 같아요.",
                "INVALID_REQUEST": "대중교통 경로 요청 형식이 올바르지 않아요.",
                "NO_RESULTS": "검색 가능한 대중교통 경로가 없어요.",
            }
            raise ValueError(
                messages.get(
                    status,
                    f"대중교통 경로 탐색 실패: {status or data}",
                )
            )

        routes = data.get("routes", [])

        if not routes:
            raise ValueError(
                "대중교통 경로가 반환되지 않았어요."
            )

        # 가장 먼저 반환된 경로의 예상 소요 시간
        properties = routes[0].get("properties", {})
        duration = properties.get("totalTime")

    if duration is None:
        raise ValueError(
            "경로는 검색됐지만 소요 시간 정보가 없어요."
        )

    return max(1, round(float(duration) / 60))


if not API_KEY:
    st.warning(
        "카카오 REST API 키가 설정되지 않았어요.\n\n"
        "Streamlit Cloud → Settings → Secrets에서 다음을 설정해 주세요."
    )
    st.code('KAKAO_REST_KEY = "발급받은 REST API 키"')


with st.form("school_form"):
    home = st.text_input(
        "🏠 집 주소",
        placeholder="예: 경기도 수원시 ...",
    )

    school = st.text_input(
        "🏫 학교 주소",
        placeholder="예: 학교의 정확한 도로명 주소",
    )

    mode = st.radio(
        "🚶 이동 수단",
        ["도보", "대중교통", "자동차"],
        horizontal=True,
    )

    target = st.time_input(
        "⏰ 학교 도착 목표 시각",
        value=datetime.strptime("08:30", "%H:%M").time(),
    )

    prep = st.number_input(
        "🧼 씻기·옷 입기·아침 식사 시간(분)",
        min_value=0,
        max_value=180,
        value=40,
        step=5,
    )

    buffer = st.number_input(
        "🛟 추가 여유 시간(분)",
        min_value=0,
        max_value=60,
        value=10,
        step=5,
    )

    if mode == "자동차":
        drive_minutes = st.number_input(
            "🚗 자동차 예상 이동 시간(분)",
            min_value=1,
            max_value=300,
            value=20,
        )
    else:
        drive_minutes = 0

    submitted = st.form_submit_button(
        "등교 시간 계산하기",
        type="primary",
    )


if submitted:
    if not home.strip() or not school.strip():
        st.error("집 주소와 학교 주소를 모두 입력해 주세요.")

    elif not API_KEY:
        st.error(
            "카카오 REST API 키를 Secrets에 등록해 주세요."
        )

    else:
        try:
            with st.spinner("주소와 경로를 확인하고 있어요..."):
                start = address_to_xy(home.strip())
                end = address_to_xy(school.strip())

                if mode == "자동차":
                    # 자동차 경로 시간은 사용자가 직접 입력
                    travel = int(drive_minutes)
                else:
                    travel = route_minutes(start, end, mode)

            # 목표 도착 시각에서 이동 시간과 여유 시간 빼기
            today = datetime.now().date()
            arrival = datetime.combine(today, target)
            leave = arrival - timedelta(
                minutes=travel + buffer
            )
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

            if wake.date() < today:
                st.warning(
                    "기상 시각이 전날로 계산됐어요. "
                    "목표 시각과 준비 시간을 확인해 주세요."
                )

            # 학교 위치를 카카오맵에서 열기
            map_url = (
                "https://map.kakao.com/link/to/"
                + quote(end[2], safe="")
                + f",{end[1]},{end[0]}"
            )

            st.link_button(
                "🗺️ 카카오맵에서 학교 위치 보기",
                map_url,
            )

            # 실제 길찾기는 카카오맵에서 확인
            mode_link = {
                "도보": "walk",
                "대중교통": "traffic",
                "자동차": "car",
            }[mode]

            route_url = (
                "https://map.kakao.com/link/by/"
                + mode_link
                + "/"
                + quote(start[2], safe="")
                + f",{start[1]},{start[0]}/"
                + quote(end[2], safe="")
                + f",{end[1]},{end[0]}"
            )

            st.link_button(
                "🧭 카카오맵에서 길찾기 열기",
                route_url,
            )

            if mode == "자동차":
                st.caption(
                    "자동차 이동 시간은 직접 입력한 값이에요. "
                    "출발 전에 실제 교통 상황을 확인해 주세요."
                )

            elif mode == "대중교통":
                st.caption(
                    "대중교통 시간은 API가 반환한 경로의 "
                    "예상 시간이며, 실제 운행 상황에 따라 달라질 수 있어요."
                )

        except requests.RequestException as e:
            st.error(f"네트워크 요청 오류: {e}")

        except ValueError as e:
            st.error(f"계산 중 문제가 발생했어요: {e}")

        except Exception as e:
            st.error(
                f"예상하지 못한 오류가 발생했어요: "
                f"{type(e).__name__}: {e}"
            )
