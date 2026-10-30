# DocuMind AI — Development & Troubleshooting Log

## 1. Project Overview

**Project Name:** DocuMind AI  
**Project Type:** AI-powered conversational chatbot  
**Current Status:** Phase 1 — Basic Gemini Chatbot  
**Tech Stack:** Python, Streamlit, Google Gemini API, `google-genai`, `python-dotenv`

### Objective

The objective of DocuMind AI is to build a conversational AI application and gradually extend it into a document intelligence assistant using Retrieval-Augmented Generation (RAG).

This document records the technical issues encountered during development, their root causes, debugging steps, resolutions, and lessons learned.

---

## 2. Development Environment

- Operating System: Windows
- Code Editor: Visual Studio Code
- Language: Python
- Virtual Environment: `.venv`
- Interface Framework: Streamlit
- AI Integration: Google Gemini API
- Configuration: `.env` file

---

## 3. Issues Encountered and Resolutions

### Issue 1: Gemini Model Not Found — HTTP 404

**Error:**

`404 models/gemini-pro is not found for API version v1beta, or is not supported for generateContent`

**Problem:**

The application initially used the `gemini-pro` model identifier. The API reported that the model was unavailable or unsupported for the requested API operation.

**Debugging and Resolution:**

1. Checked the model identifier used in the application.
2. Investigated compatibility with the installed Gemini SDK and API.
3. Changed the model identifier to another candidate model.
4. Verified that the selected model could successfully generate responses.

**Root Cause:**

The configured model identifier was not supported for the API operation being used.

**Learning:**

Model identifiers and API compatibility must be verified against the current official model documentation. A model name should not be assumed to be valid simply because it resembles a published model name.

---

### Issue 2: Migrating from the Legacy Gemini SDK

**Problem:**

The initial implementation used the older `google.generativeai` package.

**Resolution:**

Migrated to the newer Google Gen AI SDK:

```python
from google import genai
```

Installed the required dependencies:

```bash
pip install -U google-genai python-dotenv streamlit
```

Updated the implementation to use the newer client and chat interfaces.

**Learning:**

SDK migration may require changes to imports, client initialization, chat creation, request formats, and error handling—not just changing the package name.

---

### Issue 3: Client Closed Error

**Error:**

`Cannot send a request, as the client has been closed.`

**Problem:**

The application encountered a client lifecycle issue while interacting with the Gemini API.

**Resolution:**

Revised client initialization and resource management so that the client remained open while the request was being processed. Used a context manager for the API client.

**Learning:**

API clients manage resources and must remain available throughout the request. Context managers can help ensure proper initialization and cleanup.

---

### Issue 4: Chatbot Appeared to Load Indefinitely

**Problem:**

After sending a message such as `hi`, the application appeared to keep loading without displaying a response.

**Debugging Steps:**

1. Stopped and restarted the Streamlit application.
2. Investigated the API response and error messages.
3. Identified subsequent server-side HTTP 503 errors.

**Resolution:**

Restarting alone did not establish the root cause. Further debugging revealed that the selected model was returning a temporary service-unavailable response.

**Learning:**

An application that appears to hang may be waiting on an external API request. Inspecting terminal output and API errors helps distinguish frontend loading problems from backend service failures.

---

### Issue 5: Gemini API Returns HTTP 503 — Service Unavailable

**Error:**

`503 UNAVAILABLE`

The error message indicated that the selected model was experiencing high demand.

**Problem:**

The application was unable to receive a response because the API service temporarily returned an unavailable status.

**Resolution:**

1. Waited before retrying the request.
2. Tested another model identifier.
3. Obtained a successful response after changing the model configuration.

**Root Cause:**

The observed 503 response indicated temporary service unavailability or model overload.

**Learning:**

HTTP 503 errors are not necessarily caused by incorrect application code or API credentials. Production-oriented applications should use controlled retries with exponential backoff, handle timeouts, and show a useful error message when the service remains unavailable.

---

### Issue 6: Invalid Chat History Format

**Error:**

The API returned a validation error indicating that a content part expected a dictionary or object but received a string such as `'hi'`.

**Problem:**

The chat history was being constructed using a simplified structure:

```python
history.append({
    "role": role,
    "parts": [message["content"]]
})
```

The history representation did not match the content structure expected by the SDK version being used.

**Resolution:**

Imported the SDK's content types:

```python
from google.genai import types
```

Constructed history entries using `types.Content` and `types.Part`:

```python
history.append(
    types.Content(
        role=role,
        parts=[
            types.Part.from_text(
                text=message["content"]
            )
        ]
    )
)
```

**Learning:**

SDKs may validate nested request objects strictly. Structured types help represent messages in the expected format and reduce errors caused by incorrect serialization.

---

### Issue 7: Git Line-Ending Warning on Windows

**Warning:**

`LF will be replaced by CRLF the next time Git touches it`

**Problem:**

Git displayed a warning about line endings while staging `.gitignore`.

**Resolution:**

No corrective change was required for this warning. It indicated line-ending conversion between LF and CRLF, which is common in Windows environments.

**Learning:**

A Git warning is not necessarily a failed operation. Check the command's result and `git status` before treating a warning as an error.

---

## 4. Git and Repository Management

### Repository Setup

The project was prepared for publication on GitHub under the repository name `DocuMind-AI`.

### Secret Management

Added sensitive configuration files to `.gitignore`:

```gitignore
.env
.venv/
__pycache__/
*.pyc
.streamlit/secrets.toml
```

**Important:** `.gitignore` does not automatically remove a file that is already tracked by Git. Before pushing, verify that `.env` is not staged or tracked.

If an API key is accidentally exposed publicly, revoke or rotate it through the provider.

---

## 5. Current Status

### Completed

- Basic Streamlit chat interface
- Gemini API integration
- Session-based conversation history
- Migration to the Google Gen AI SDK
- Resolution of chat history formatting issues
- Successful response from the chatbot
- GitHub repository preparation
- Initial project README and development roadmap

### Planned

- PDF upload and text extraction
- Text chunking with page-level metadata
- Embeddings and vector storage
- Retrieval-Augmented Generation (RAG)
- Source citations
- Testing and retrieval evaluation
- Deployment and documentation improvements

---

## 6. Key Technical Lessons

1. **Read the actual error:** HTTP status codes and stack traces help identify whether a problem originates in the application, SDK, or external service.
2. **Verify model compatibility:** Use current official model documentation instead of guessing model names.
3. **Understand SDK changes:** Newer SDKs may use different client and request structures.
4. **Manage resources correctly:** API clients must remain open while requests are executing.
5. **Handle external service failures:** Temporary API errors should be handled separately from programming errors.
6. **Validate structured data:** Chat history and nested request objects must match the SDK's expected schema.
7. **Protect credentials:** API keys belong in environment variables, not source code or public repositories.
8. **Document the debugging process:** Record the original error, the actual fix, and the verification result for each issue.

---

## 7. Documentation Maintenance

This log will be updated as each development phase is completed.

For every new issue, record:

- Date encountered
- Error message or unexpected behaviour
- Steps taken to reproduce it
- Root cause, once verified
- Fix implemented
- Test used to confirm the fix
- Lessons learned

**Documentation principle:** Record verified fixes separately from suspected causes or proposed improvements. This keeps the troubleshooting history technically accurate and useful during interviews.
