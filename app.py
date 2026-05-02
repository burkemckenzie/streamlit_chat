import streamlit as st
import requests
import random
from datetime import datetime, timezone

# Set up the page title
st.title("My Simple AI Chatbot")

# --- 1. BACKEND CONFIGURATION ---
BACKENDS = {
    "TSC-MEC": {
        "url": "https://george-ixfp.onrender.com",
        "key": st.secrets["TSC_API_KEY"]
    },
    "ACA-MEC": {
        "url": "https://air-canada.onrender.com",
        "key": st.secrets["ACA_API_KEY"]
    }
}

# --- 2. GREETING LOGIC ---
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


# --- 3. STATE & CALLBACKS ---
# Initialize the default backend if it doesn't exist yet
if "current_backend" not in st.session_state:
    st.session_state.current_backend = "TSC-MEC"

# Initialize memory on the very first load
if "messages" not in st.session_state:
    st.session_state.messages = [fetch_greeting(st.session_state.current_backend)]

if "pending_negative_idx" not in st.session_state:
    st.session_state.pending_negative_idx = None

def switch_backend():
    """This runs instantly when the user changes the dropdown."""
    # Grab the new value from the dropdown
    new_backend = st.session_state.backend_dropdown

    # Update the current backend memory
    st.session_state.current_backend = new_backend

    # Wipe the chat and fetch the new greeting
    st.session_state.messages = [fetch_greeting(new_backend)]
    st.session_state.pending_negative_idx = None


# --- 4. THE SIDEBAR UI ---
with st.sidebar:
    # We add a 'key' and 'on_change' to trigger the wipe instantly
    selected_backend = st.selectbox(
        "Select Organization", 
        ["TSC-MEC", "ACA-MEC"], 
        key="backend_dropdown",
        on_change=switch_backend
    )
    
    if st.button("New Chat", use_container_width=True):
        st.session_state.messages = [fetch_greeting(st.session_state.current_backend)]
        st.session_state.pending_negative_idx = None
        st.rerun()

# --- 5. DISPLAY CHAT HISTORY ---
for i, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

        if message["role"] == "assistant" and message.get("chunks_used"):
            chunks = message["chunks_used"]
            with st.expander(f"Chunks used ({len(chunks)})"):
                st.write(chunks)

        if message["role"] == "assistant" and message.get("_debug") is not None:
            with st.expander("DEBUG: request sent + response received"):
                st.markdown("**Request payload sent to backend:**")
                st.json(message["_debug"]["request"])
                st.markdown("**Raw response from backend:**")
                st.json(message["_debug"]["response"])

        # Feedback widgets only on assistant messages, skipping the initial greeting (i == 0)
        if message["role"] == "assistant" and i > 0:
            existing = message.get("feedback")

            if existing == "positive":
                st.caption("Thanks for your feedback.")
            elif existing == "negative":
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
                            for m in st.session_state.messages[: i + 1]
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


# --- 6. THE CHAT INPUT AND BACKEND LOGIC ---
if user_input := st.chat_input("Type your message here..."):
    
    with st.chat_message("user"):
        st.markdown(user_input)
        
    history_for_backend = []
    for msg in st.session_state.messages:
        item = {"role": msg["role"], "content": msg["content"]}
        if msg["role"] == "assistant" and msg.get("chunks_used"):
            item["chunks_used"] = msg["chunks_used"]
        history_for_backend.append(item)
        
    st.session_state.messages.append({"role": "user", "content": user_input})

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        
        # Pull the routing info from the currently active backend in memory
        config = BACKENDS[st.session_state.current_backend]
        backend_url = f"{config['url']}/query"
        
        headers = {
            "X-API-KEY": config['key'],
            "Content-Type": "application/json"
        }
        
        payload = {
            "query": user_input,
            "history": history_for_backend
        }
        
        chunks_used = []
        debug_response = None
        try:
            response = requests.post(backend_url, headers=headers, json=payload)

            if not response.ok:
                error_msg = f"Server Error {response.status_code}: {response.text}"
                st.error(error_msg)
                st.stop()

            backend_data = response.json()
            debug_response = backend_data
            chunks_used = backend_data.get("chunks_used") or []

            if "response" in backend_data:
                ai_response = backend_data["response"]
            elif "answer" in backend_data:
                ai_response = backend_data["answer"]
            elif "result" in backend_data:
                ai_response = backend_data["result"]
            else:
                ai_response = f"Connection successful, but text missing. Received: {backend_data}"
                
        except Exception as e:
            ai_response = f"Python Execution Error: {e}"
            
        message_placeholder.markdown(ai_response)

    st.session_state.messages.append({
        "role": "assistant",
        "content": ai_response,
        "chunks_used": chunks_used,
        "_debug": {"request": payload, "response": debug_response},
    })
    st.rerun()