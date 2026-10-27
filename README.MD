# DocuMind AI 🤖

An AI-powered conversational chatbot built with **Python, Streamlit, and Google Gemini API**. DocuMind AI currently provides an interactive chat interface for asking questions and receiving AI-generated responses. The project is being developed in phases into a document intelligence assistant using Retrieval-Augmented Generation (RAG).

## ✨ Current Features

- 💬 **AI-Powered Conversations** — Ask questions and receive responses using Google Gemini.
- 🧠 **Session-Based Chat History** — Maintain conversation context during the current session.
- ⚡ **Interactive Chat Interface** — Chat interface built with Streamlit.
- 🔐 **Environment Variables** — Store API credentials in a local `.env` file.
- ⚠️ **Basic Error Handling** — Display API errors when requests fail.

## 🛠️ Tech Stack

- **Language:** Python
- **UI Framework:** Streamlit
- **LLM:** Google Gemini API
- **SDK:** Google Gen AI SDK (`google-genai`)
- **Configuration:** `python-dotenv`
- **Version Control:** Git and GitHub

## 🚀 Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/DocuMind-AI.git
cd DocuMind-AI
```

Replace `YOUR_USERNAME` with your GitHub username.

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate it on Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure the API key

Create a `.env` file in the project root:

```env
GOOGLE_API_KEY=your_gemini_api_key
```

Get your API key from [Google AI Studio](https://aistudio.google.com/apikey).

**Security:** Never commit your `.env` file or expose your API key publicly.

### 5. Run the application

```bash
streamlit run app.py
```

The application will open in your browser.

## 🗺️ Development Roadmap

The project is being developed in six phases.

### Phase 1: Basic Gemini Chatbot — Completed

- [x] Build a conversational interface using Streamlit.
- [x] Integrate the Google Gemini API.
- [x] Maintain session-based chat history.
- [x] Configure API credentials using environment variables.
- [x] Add basic API error handling.

### Phase 2: PDF Upload and Document Processing — Planned

- [ ] Upload PDF documents through the interface.
- [ ] Extract text and preserve page numbers.
- [ ] Split extracted text into manageable chunks.
- [ ] Validate uploaded files and handle extraction errors.
- [ ] Preview extracted document content.

### Phase 3: Retrieval-Augmented Generation (RAG) — Planned

- [ ] Generate embeddings for document chunks.
- [ ] Store embeddings in a vector database such as ChromaDB.
- [ ] Retrieve relevant passages based on user questions.
- [ ] Generate answers using retrieved context and Gemini.
- [ ] Display source references and page numbers.

### Phase 4: Advanced Document Chat — Planned

- [ ] Support questions across multiple PDF documents.
- [ ] Add document summarization.
- [ ] Improve conversation management and reset functionality.
- [ ] Handle questions that cannot be answered from the uploaded documents.
- [ ] Improve source previews and the user experience.

### Phase 5: Testing and Evaluation — Planned

- [ ] Add unit tests for document processing and chunking.
- [ ] Evaluate retrieval relevance using sample questions.
- [ ] Test answer quality and citation correctness.
- [ ] Handle API failures, rate limits, and invalid inputs.
- [ ] Measure response latency and other relevant performance metrics.

### Phase 6: Deployment and Resume Polish — Planned

- [ ] Improve the interface, loading states, and error messages.
- [ ] Deploy the application.
- [ ] Configure deployment secrets securely.
- [ ] Document the architecture and add screenshots.
- [ ] Publish setup instructions and evaluation results.
- [ ] Prepare resume bullets based on implemented features and measured results.

## 📂 Project Structure

```text
DocuMind-AI/
├── app.py
├── requirements.txt
├── .gitignore
├── README.md
└── .env
```

The `.env` file is for local use only and must not be committed to GitHub.

As development progresses, additional modules for document processing, embeddings, retrieval, and evaluation will be added.

## 🎯 Project Objective

The objective is to evolve a basic conversational chatbot into a reliable document intelligence assistant while developing practical skills in:

- Large Language Model (LLM) integration
- Document processing and text chunking
- Embeddings and semantic search
- Retrieval-Augmented Generation (RAG)
- Testing and evaluation of AI applications
- Secure configuration and application deployment

## 👩‍💻 Author

**YOUR NAME**

- GitHub: [YOUR_USERNAME](https://github.com/KhC13)
- LinkedIn: www.linkedIn.com/khushi-chhakara

---

*Built with Python, Streamlit, and Google Gemini API.*
