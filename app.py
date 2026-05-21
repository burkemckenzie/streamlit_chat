import streamlit as st
import requests
import random
from datetime import datetime, timezone

# --- 0. PAGE CONFIG ---
# Drop your final avatar images into ./assets/ (same filenames) to replace the placeholders.
# We load via PIL because Streamlit's chat_message avatar can be unreliable with raw paths.
def _load_avatar(path, fallback_emoji):
    try:
        from PIL import Image
        img = Image.open(path)
        img.load()  # force-decode now so a bad file fails here, not mid-render
        # Reject tiny placeholder images so the page doesn't render with a blank avatar.
        if img.size[0] < 16 or img.size[1] < 16:
            return fallback_emoji
        return img
    except Exception:
        return fallback_emoji

USER_AVATAR = _load_avatar("assets/user.png", "🧑")
ASSISTANT_AVATAR = _load_avatar("assets/assistant.png", "🤖")

st.set_page_config(
    page_title="AviChat | ACA-MEC Sandbox",
    page_icon=ASSISTANT_AVATAR,
    layout="centered",
    initial_sidebar_state="collapsed",
)

# --- 0.5. AUTH GATE ---
def _require_login():
    if st.session_state.get("authenticated"):
        return

    st.title("AviChat | Tester Environment")
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign In")

        if submitted:
            users = st.secrets.get("users", {})
            expected = next(
                (p for u, p in users.items() if u.lower() == email.strip().lower()),
                None,
            )
            if expected is not None and password == expected:
                st.session_state.authenticated = True
                st.session_state.user_email = email.strip().lower()
                st.rerun()
            else:
                st.error("Invalid email or password.")

    st.stop()

_require_login()

# --- 1. BACKEND CONFIGURATION ---
BACKENDS = {
    "ACA-MEC": {
        "url": "https://air-canada.onrender.com",
        "key": st.secrets["ACA_API_KEY"]
    }
}

CHAT_TIMEOUT_SECONDS = 90
HISTORY_LIMIT = 20

# --- 2. GREETING + BACKEND HELPERS ---
def fetch_greeting(backend_name):
    """Fetches the greeting from the currently selected backend."""
    fallback_greetings = [
        "Welcome! How can I help you today?",
        "Hello! I'm here to assist you.",
        "Hi there! What can I do for you?",
    ]

    config = BACKENDS[backend_name]
    greeting_url = f"{config['url']}/greeting"
    headers = {
        "X-API-KEY": config['key'],
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(greeting_url, headers=headers, timeout=3)
        if response.ok:
            data = response.json()
            if "greeting" in data:
                return {"role": "assistant", "content": data["greeting"]}
    except Exception:
        pass

    return {"role": "assistant", "content": random.choice(fallback_greetings)}


def submit_feedback(backend_name, feedback_type, query, response, comment="", history=None):
    """POST feedback to the active backend's /feedback endpoint (fire-and-forget)."""
    config = BACKENDS[backend_name]
    url = f"{config['url']}/feedback"
    headers = {
        "X-API-KEY": config["key"],
        "Content-Type": "application/json",
    }
    # Workaround: backends don't read `comment`, so embed it in `response` so it
    # lands in the ClickUp task body alongside the other fields.
    response_with_comment = response
    if comment:
        response_with_comment = f"{response}\n\n---\n\n[User feedback comment: {comment}]"
    payload = {
        "feedback_type": feedback_type,
        "query": query,
        "response": response_with_comment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "comment": comment,
        "history": history or [],
    }
    try:
        requests.post(url, headers=headers, json=payload, timeout=5)
    except Exception:
        pass


def find_query_for(i):
    """Walk back from assistant message at index i to find the prompting user query."""
    for j in range(i - 1, -1, -1):
        if st.session_state.messages[j]["role"] == "user":
            return st.session_state.messages[j]["content"]
    return ""


def start_new_chat():
    st.session_state.messages = [fetch_greeting(st.session_state.current_backend)]
    st.session_state.pending_negative_idx = None
    st.session_state.pop("pending_retry", None)


# --- 3. STATE INIT ---
if "current_backend" not in st.session_state:
    st.session_state.current_backend = "ACA-MEC"

if "messages" not in st.session_state:
    st.session_state.messages = [fetch_greeting(st.session_state.current_backend)]

if "pending_negative_idx" not in st.session_state:
    st.session_state.pending_negative_idx = None

# --- 4. HEADER (title + always-visible New Chat) ---
# Override Streamlit's default <640px column stacking and let the title font
# scale down so the header stays on one line on small screens.
st.markdown(
    """
    <style>
    .st-key-header_row [data-testid="stHorizontalBlock"] {
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        align-items: center;
        gap: 0.5rem;
    }
    .st-key-header_row [data-testid="stColumn"] {
        min-width: 0 !important;
        width: auto !important;
        flex: 0 0 auto !important;
    }
    .st-key-header_row [data-testid="stColumn"]:first-child {
        flex: 1 1 auto !important;
    }
    .st-key-header_row h1 {
        font-size: clamp(1.1rem, 4.5vw, 2.5rem) !important;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        margin: 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.container(key="header_row"):
    header_left, header_right = st.columns([4, 1])
    with header_left:
        st.title("AviChat | ACA-MEC Sandbox")
    with header_right:
        if st.button("", icon=":material/add:", help="New Chat"):
            start_new_chat()
            st.rerun()

# --- 5. DISPLAY CHAT HISTORY ---
for i, message in enumerate(st.session_state.messages):
    avatar = ASSISTANT_AVATAR if message["role"] == "assistant" else USER_AVATAR
    with st.chat_message(message["role"], avatar=avatar):
        st.markdown(message["content"])

        # Failed assistant message → show Retry instead of feedback widgets.
        if message["role"] == "assistant" and message.get("failed"):
            if st.button("Retry", key=f"retry_{i}"):
                query = find_query_for(i)
                del st.session_state.messages[i]
                st.session_state["pending_retry"] = query
                st.rerun()
            continue

        # Feedback widgets only on assistant messages, skipping the initial greeting (i == 0)
        if message["role"] == "assistant" and i > 0:
            existing = message.get("feedback")

            if existing == "positive" or existing == "negative":
                st.caption("Thanks for your feedback.")
            else:
                rating = st.feedback("thumbs", key=f"fb_{i}")
                if rating == 1:
                    submit_feedback(
                        st.session_state.current_backend,
                        "positive",
                        find_query_for(i),
                        message["content"],
                    )
                    st.session_state.messages[i]["feedback"] = "positive"
                    if st.session_state.pending_negative_idx == i:
                        st.session_state.pending_negative_idx = None
                    st.rerun()
                elif rating == 0 and st.session_state.pending_negative_idx != i:
                    st.session_state.pending_negative_idx = i
                    st.rerun()

            if st.session_state.pending_negative_idx == i:
                with st.form(key=f"fb_form_{i}", clear_on_submit=True):
                    comment = st.text_area(
                        "Why was this response bad? (optional)",
                        key=f"fb_comment_{i}",
                    )
                    submitted = st.form_submit_button("Submit feedback")
                    if submitted:
                        history_slice = [
                            {"role": m["role"], "content": m["content"]}
                            for m in st.session_state.messages[: i - 1]
                        ][-5:]
                        submit_feedback(
                            st.session_state.current_backend,
                            "negative",
                            find_query_for(i),
                            message["content"],
                            comment=comment or "",
                            history=history_slice,
                        )
                        st.session_state.messages[i]["feedback"] = "negative"
                        st.session_state.pending_negative_idx = None
                        st.rerun()


# --- 6. CHAT INPUT (handles both fresh sends and retries) ---
typed_input = st.chat_input("Type your message here...")
pending_retry = st.session_state.pop("pending_retry", None)

# Retry path reuses the existing user message at the tail of history.
is_retry = pending_retry is not None
user_input = pending_retry if is_retry else typed_input

if user_input:
    if not is_retry:
        with st.chat_message("user", avatar=USER_AVATAR):
            st.markdown(user_input)

    # On a retry, the user message is already the last entry in history; exclude it
    # from history_for_backend (it goes in `query`). On a fresh send, history is
    # everything currently in session_state.messages (user message not yet appended).
    history_source = st.session_state.messages[:-1] if is_retry else st.session_state.messages
    history_for_backend = []
    for msg in history_source[-HISTORY_LIMIT:]:
        item = {"role": msg["role"], "content": msg["content"]}
        if msg["role"] == "assistant" and msg.get("chunks_used"):
            item["chunks_used"] = msg["chunks_used"]
        history_for_backend.append(item)

    if not is_retry:
        st.session_state.messages.append({"role": "user", "content": user_input})

    config = BACKENDS[st.session_state.current_backend]
    backend_url = f"{config['url']}/query"
    headers = {
        "X-API-KEY": config['key'],
        "Content-Type": "application/json",
    }
    payload = {"query": user_input, "history": history_for_backend}

    ai_response = None
    chunks_used = []
    failed = False

    with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
        message_placeholder = st.empty()
        with st.spinner("Thinking…"):
            try:
                response = requests.post(
                    backend_url,
                    headers=headers,
                    json=payload,
                    timeout=CHAT_TIMEOUT_SECONDS,
                )
                if response.ok:
                    backend_data = response.json()
                    chunks_used = backend_data.get("chunks_used") or []
                    if "response" in backend_data:
                        ai_response = backend_data["response"]
                    elif "answer" in backend_data:
                        ai_response = backend_data["answer"]
                    elif "result" in backend_data:
                        ai_response = backend_data["result"]
                    else:
                        failed = True
                else:
                    failed = True
            except Exception:
                failed = True

        if failed:
            ai_response = "Sorry, I couldn't reach the assistant. Please try again."
        message_placeholder.markdown(ai_response)

    assistant_msg = {
        "role": "assistant",
        "content": ai_response,
        "chunks_used": chunks_used,
    }
    if failed:
        assistant_msg["failed"] = True
    st.session_state.messages.append(assistant_msg)
    st.rerun()
