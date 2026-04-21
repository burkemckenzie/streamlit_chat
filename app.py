import streamlit as st
import requests
import random

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


# --- 3. STATE & CALLBACKS ---
# Initialize the default backend if it doesn't exist yet
if "current_backend" not in st.session_state:
    st.session_state.current_backend = "TSC-MEC"

# Initialize memory on the very first load
if "messages" not in st.session_state:
    st.session_state.messages = [fetch_greeting(st.session_state.current_backend)]

def switch_backend():
    """This runs instantly when the user changes the dropdown."""
    # Grab the new value from the dropdown
    new_backend = st.session_state.backend_dropdown
    
    # Update the current backend memory
    st.session_state.current_backend = new_backend
    
    # Wipe the chat and fetch the new greeting
    st.session_state.messages = [fetch_greeting(new_backend)]


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
        st.rerun()

# --- 5. DISPLAY CHAT HISTORY ---
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])


# --- 6. THE CHAT INPUT AND BACKEND LOGIC ---
if user_input := st.chat_input("Type your message here..."):
    
    with st.chat_message("user"):
        st.markdown(user_input)
        
    history_for_backend = []
    for msg in st.session_state.messages:
        history_for_backend.append({
            "role": msg["role"],
            "content": msg["content"]
        })
        
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
        
        try:
            response = requests.post(backend_url, headers=headers, json=payload)
            
            if not response.ok:
                error_msg = f"Server Error {response.status_code}: {response.text}"
                st.error(error_msg)
                st.stop()
            
            backend_data = response.json()
            
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
        
    st.session_state.messages.append({"role": "assistant", "content": ai_response})