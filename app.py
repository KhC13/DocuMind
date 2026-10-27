
import streamlit as st
import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

st.set_page_config(
    page_title="Gemini Chatbot",
    page_icon="🤖",
    layout="wide"
)

api_key = os.getenv("GOOGLE_API_KEY")

if not api_key:
    st.error("GOOGLE_API_KEY missing hai. Apni .env file check karo.")
    st.stop()

st.title("Gemini Chatbot")

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Ask me anything..."):
    with st.chat_message("user"):
        st.markdown(prompt)

    history = []

    for message in st.session_state.messages:
        role = "user" if message["role"] == "user" else "model"

        history.append(
            types.Content(
                role=role,
                parts=[
                    types.Part.from_text(text=message["content"])
                ]
            )
        )

    try:
        with genai.Client(api_key=api_key) as client:
            chat = client.chats.create(
                model="gemini-3.6-flash",
                history=history
            )

            response = chat.send_message(prompt)
            answer = response.text or "No text response received."

        st.session_state.messages.append(
            {"role": "user", "content": prompt}
        )
        st.session_state.messages.append(
            {"role": "assistant", "content": answer}
        )

        with st.chat_message("assistant"):
            st.markdown(answer)

    except Exception as e:
        st.error(f"Gemini API error: {e}")
