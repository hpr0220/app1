"""커플 다이어리 | 실행: streamlit run app.py

배포: 이 파일과 requirements.txt를 GitHub에 올리고 Streamlit Community Cloud에서
app.py를 실행하세요. QR에는 GitHub 주소가 아닌 배포된 앱 주소를 입력합니다.

중요: SQLite는 같은 실행 서버의 두 사람이 공유합니다. Community Cloud의 로컬
파일은 재배포/재시작 등으로 사라질 수 있습니다. 장기 보관용 서비스가 아니라
수행평가/시연용입니다. 영구 보관에는 외부 DB 연동이 필요합니다.
QR에는 커플 공간의 초대 코드가 포함됩니다. 모르는 사람에게 공유하지 마세요.
"""
import base64
import hashlib
import hmac
import io
import secrets
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import qrcode
import streamlit as st

st.set_page_config(page_title="둘의 하루", page_icon="💌", layout="centered", initial_sidebar_state="collapsed")
DB = Path(__file__).with_name("couple_diary.sqlite3")
KST = timezone(timedelta(hours=9))
MOODS = {"🥰": "행복", "🙂": "평온", "🥺": "그리움", "😔": "우울", "😤": "속상함", "😴": "피곤"}
NAMES = {"A": "🌙 달", "B": "⭐ 별"}

st.markdown("""<style>
.block-container{max-width:460px;padding:0.7rem 0.85rem 0.5rem!important}
header[data-testid="stHeader"]{display:none}
[data-testid="stAppViewContainer"]{background:linear-gradient(150deg,#fff8fa,#f5f2ff)}
[data-testid="stVerticalBlock"]{gap:0.42rem}
h1{font-size:1.5rem!important;padding:0!important;margin:0!important;color:#674563}
p{margin-bottom:0.25rem} .stCaption{font-size:0.73rem}
[data-testid="stTextArea"] textarea{font-size:16px!important;min-height:72px!important}
[data-testid="stTextInput"] input{font-size:16px!important}
.stButton button,.stFormSubmitButton button{border-radius:13px;min-height:40px}
[data-testid="stRadio"] [role="radiogroup"]{gap:0.3rem;flex-wrap:wrap}
[data-testid="stRadio"] label{margin-right:0!important}
.note{background:#fff;border:1px solid #efdfeb;border-radius:15px;padding:10px 13px;
font-size:14px;line-height:1.5;overflow-wrap:anywhere;white-space:pre-wrap}
.small{font-size:11px;color:#8c788a} .title{font-weight:700;color:#674563}
</style>""", unsafe_allow_html=True)


def connect():
    c = sqlite3.connect(str(DB), timeout=20)
    c.execute("PRAGMA foreign_keys=ON")
    return c


def init_db():
    with connect() as c:
        c.execute("CREATE TABLE IF NOT EXISTS rooms (code TEXT PRIMARY KEY, created TEXT NOT NULL)")
        c.execute("""CREATE TABLE IF NOT EXISTS members (
            room TEXT NOT NULL REFERENCES rooms(code), role TEXT NOT NULL,
            salt TEXT NOT NULL, pin_hash TEXT NOT NULL, PRIMARY KEY(room,role))""")
        c.execute("""CREATE TABLE IF NOT EXISTS entries (
            room TEXT NOT NULL REFERENCES rooms(code), role TEXT NOT NULL,
            mood TEXT NOT NULL, body TEXT NOT NULL, updated TEXT NOT NULL,
            version TEXT NOT NULL, read_at TEXT, PRIMARY KEY(room,role))""")


def now():
    return datetime.now(KST).isoformat(timespec="seconds")


def digest(pin, salt):
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), 200000).hex()


def authenticate(room, role, pin):
    # 역할의 첫 접속자가 PIN을 등록합니다. 트랜잭션으로 동시 등록 충돌을 막습니다.
    with connect() as c:
        c.execute("BEGIN IMMEDIATE")
        if not c.execute("SELECT 1 FROM rooms WHERE code=?", (room,)).fetchone():
            return False
        row = c.execute("SELECT salt,pin_hash FROM members WHERE room=? AND role=?", (room, role)).fetchone()
        if row:
            return hmac.compare_digest(digest(pin, row[0]), row[1])
        salt = secrets.token_hex(16)
        c.execute("INSERT INTO members VALUES (?,?,?,?)", (room, role, salt, digest(pin, salt)))
        return True


def entries(room):
    with connect() as c:
        rows = c.execute("SELECT role,mood,body,updated,version,read_at FROM entries WHERE room=?", (room,)).fetchall()
    return {r[0]: dict(zip(("mood", "body", "updated", "version", "read_at"), r[1:])) for r in rows}


def time_label(value):
    return datetime.fromisoformat(value).strftime("%m/%d %H:%M")


def qr_bytes(url):
    qr = qrcode.QRCode(box_size=7, border=3)
    qr.add_data(url)
    qr.make(fit=True)
    buf = io.BytesIO()
    qr.make_image(fill_color="#674563", back_color="white").save(buf, format="PNG")
    return buf.getvalue()


def share_panel(room):
    with st.expander("🔗 초대 · QR · 사용 안내", expanded=False):
        st.caption("배포한 앱 주소를 입력하세요. 이 QR로 상대도 같은 공간에 입장합니다.")
        base = st.text_input("앱 주소", placeholder="https://your-app.streamlit.app", label_visibility="collapsed")
        if base:
            parts = urlsplit(base.strip())
            if parts.scheme == "https" and parts.netloc:
                params = dict(parse_qsl(parts.query))
                params["room"] = room
                url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params), ""))
                png = qr_bytes(url)
                st.image(png, width=160)
                st.code(url, language=None)
                st.download_button("QR 이미지 저장", png, "couple-qr.png", "image/png", use_container_width=True)
            else:
                st.warning("https://로 시작하는 배포 주소를 넣어주세요.")
        st.code(room, language=None)
        st.caption("상대에게 링크 또는 초대 코드를 전달하세요. 서로 다른 역할을 선택하고 각자의 PIN을 등록합니다. QR은 초대용이지 로그인용이 아닙니다.")
        st.caption("각자 최신 일기 1개를 보관합니다. 다시 저장하면 이전 글은 교체되고 읽음 표시도 초기화됩니다. 긴 일기·과거 목록을 생략해 기본 화면을 작게 만들었습니다.")
        st.caption("⚠️ 시연용: 서버 재시작·재배포 시 일기가 사라질 수 있습니다. PIN 분실 복구 기능은 없습니다. 민감한 개인정보는 적지 마세요.")
        if st.button("로그아웃", use_container_width=True):
            st.session_state.pop("auth", None)
            st.rerun()


init_db()
st.markdown("# 💌 둘의 하루")
st.caption("짧은 마음 하나, 서로에게 남기는 하루")

query_room = str(st.query_params.get("room", ""))[:100]
auth = st.session_state.get("auth")
if auth and query_room and auth[0] != query_room:
    st.session_state.pop("auth", None)
    auth = None

if not auth:
    st.markdown("**우리 공간에 들어가기**")
    room_input = st.text_input("초대 코드", value=query_room, placeholder="QR로 입장하면 자동 입력돼요", max_chars=100)
    role = st.radio("나는", ["A", "B"], format_func=lambda x: NAMES[x], horizontal=True)
    pin = st.text_input("나만의 PIN", type="password", max_chars=12, placeholder="숫자 4~12자리 · 첫 입장 시 등록")
    st.caption("달과 별 중 서로 다른 역할을 선택하세요. 첫 접속 시 해당 역할의 PIN이 정해집니다.")
    c1, c2 = st.columns(2)
    with c1:
        login = st.button("입장하기", type="primary", use_container_width=True)
    with c2:
        create = st.button("새 커플 공간", use_container_width=True)
    if create or login:
        wait = st.session_state.get("retry_after", 0) - time.time()
        if wait > 0:
            st.error(f"잠시 후 다시 시도하세요. ({int(wait) + 1}초)")
        elif not (pin.isascii() and pin.isdigit() and 4 <= len(pin) <= 12):
            st.error("PIN은 숫자 4~12자리로 입력해주세요.")
        else:
            room = room_input.strip()
            if create:
                room = secrets.token_urlsafe(18)
                with connect() as c:
                    c.execute("INSERT INTO rooms VALUES (?,?)", (room, now()))
            if room and authenticate(room, role, pin):
                st.session_state["auth"] = (room, role)
                st.session_state["failures"] = 0
                st.query_params["room"] = room
                st.rerun()
            else:
                failures = st.session_state.get("failures", 0) + 1
                st.session_state["failures"] = failures
                st.session_state["retry_after"] = time.time() + min(60, failures * 2)
                st.error("초대 코드 또는 PIN을 확인해주세요.")
    st.caption("처음이라면 PIN을 입력한 뒤 ‘새 커플 공간’을 누르세요.")
    st.stop()

room, role = auth
other = "B" if role == "A" else "A"

# 상대가 누른 읽음 표시와 새 일기를 주기적으로 갱신합니다.
@st.fragment(run_every="10s")
def diary():
    import html
    data = entries(room)
    mine, theirs = data.get(role), data.get(other)
    top1, top2 = st.columns([3, 1])
    with top1:
        st.markdown(f"**{NAMES[role]}의 마음**")
    with top2:
        if st.button("↻", help="지금 새로고침", use_container_width=True):
            st.rerun(scope="fragment")
    with st.form("write", clear_on_submit=False, border=False):
        mood = st.radio("오늘 기분", list(MOODS), horizontal=True, label_visibility="collapsed",
                        index=list(MOODS).index(mine["mood"]) if mine and mine["mood"] in MOODS else 0,
                        help="왼쪽부터 행복 · 평온 · 그리움 · 우울 · 속상함 · 피곤")
        body = st.text_area("마음 한 줄", value=mine["body"] if mine else "", max_chars=120,
                            height=80, label_visibility="collapsed", placeholder="오늘의 마음을 120자 안에 남겨주세요")
        save = st.form_submit_button("💌 마음 보내기", type="primary", use_container_width=True)
    if save:
        if not body.strip():
            st.warning("마음을 한 줄 적어주세요.")
        else:
            with connect() as c:
                c.execute("""INSERT INTO entries(room,role,mood,body,updated,version,read_at)
                    VALUES (?,?,?,?,?,?,NULL) ON CONFLICT(room,role) DO UPDATE SET
                    mood=excluded.mood,body=excluded.body,updated=excluded.updated,
                    version=excluded.version,read_at=NULL""",
                    (room, role, mood, body.strip(), now(), secrets.token_hex(12)))
            st.rerun(scope="fragment")
    if mine:
        state = "✓ 상대가 확인했어요" if mine["read_at"] else "아직 상대가 읽기 전이에요"
        st.caption(f"내 일기 · {time_label(mine['updated'])} · {state}")
    else:
        st.caption("보낸 마음의 읽음 상태가 여기에 표시돼요.")
    st.markdown(f"**{NAMES[other]}에게서 온 마음**")
    if theirs:
        text = html.escape(theirs["body"])
        label = f"{theirs['mood']} {MOODS.get(theirs['mood'], '')} · {time_label(theirs['updated'])}"
        st.markdown(f'<div class="note"><span class="small">{html.escape(label)}</span><br>{text}</div>', unsafe_allow_html=True)
        if theirs["read_at"]:
            st.caption("✓ 확인 완료 · 상대에게도 표시됐어요")
        elif st.button("✓ 읽었어요 · 상대에게 알려주기", use_container_width=True):
            with connect() as c:
                # 화면에 보인 버전만 읽음 처리하여, 동시에 수정된 글을 오독 처리하지 않습니다.
                c.execute("UPDATE entries SET read_at=? WHERE room=? AND role=? AND version=? AND read_at IS NULL",
                          (now(), room, other, theirs["version"]))
            st.rerun(scope="fragment")
    else:
        st.markdown('<div class="note">아직 도착한 마음이 없어요 💭<br><span class="small">상대가 글을 쓰면 여기에 나타나요.</span></div>', unsafe_allow_html=True)
    st.caption("10초마다 자동 확인 · 각자 최신 글 1개")

diary()
share_panel(room)
