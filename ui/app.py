import os
import uuid
import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(page_title="Kubernetes Docs Assistant")
st.title("Kubernetes Docs Assistant")

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
    st.session_state.messages = []

with st.sidebar:
    if st.button("New chat"):
        st.session_state.thread_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()
    st.caption(f"Thread: {st.session_state.thread_id[:8]}")


def show_sources(sources):
    if not sources:
        return
    with st.expander(f"Sources ({len(sources)})"):
        for s in sources:
            page = f", page {s['page']}" if s["page"] else ""
            st.write(f"`{s['score']:.2f}`  {s['source']}{page}")


for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        show_sources(msg.get("sources"))

if prompt := st.chat_input("Ask about Kubernetes..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                resp = requests.post(
                    f"{API_URL}/chat",
                    json={"thread_id": st.session_state.thread_id, "message": prompt},
                    timeout=120,
                )
                resp.raise_for_status()
                data = resp.json()
            except requests.RequestException as e:
                st.error(f"API error: {e}")
                st.stop()
        if data.get("blocked"):
            st.warning(data["answer"])
        else:
            st.markdown(data["answer"])            
            show_sources(data["sources"])

    st.session_state.messages.append(
        {"role": "assistant", "content": data["answer"], "sources": data["sources"]}
    )
