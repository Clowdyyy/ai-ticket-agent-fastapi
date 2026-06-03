# AI Ticket Agent (FastAPI & Gemini)

An automated AI agent for classifying and processing incoming customer support tickets with seamless Telegram integration.

🌐 **Live Demo (API Docs):** [https://ai-ticket-agent-fastapi.onrender.com/docs](https://ai-ticket-agent-fastapi.onrender.com/docs)

An asynchronous AI agent (microservice) built with FastAPI, designed to automate the processing of incoming support requests (tickets). 
The system is fully transitioned to a Webhook architecture, enabling instant (real-time) message processing without idle server polling.

## 🔥 Key Features

* **FastAPI Webhook Architecture:** The `/webhook/new-ticket` endpoint accepts JSON payloads from external CRM systems (Zendesk, HubSpot, Shopify, etc.).
* **Intelligent Analysis (Gemini API):** The AI automatically translates the ticket text, identifies the category (e.g., Complaint, Pricing Question), and assigns an urgency level.
* **Fault Tolerance (Model Fallbacks):** The code automatically fetches a list of available models from the Google API and features a fallback system (if one model is overloaded, another picks up the request).
* **Duplicate Protection:** An integrated SQLite database checks the `message_id` before sending it to the AI, saving you money on redundant API requests.
* **Real-time Telegram Alerts:** Upon detecting critical categories (like "Complaint") or high urgency, the system instantly notifies a human manager via the Telegram Bot API.

## 🛠️ Tech Stack

* **Python 3.10+** (Asyncio)
* **FastAPI / Uvicorn** (REST API)
* **Pydantic v2** (Data Validation)
* **SQLite3** (Relational Database)
* **Requests** (Interaction with Gemini & Telegram APIs)

---

## 📦 Local Installation & Setup

1. **Clone the repository from GitHub:**
```bash
git clone https://github.com/clowdyyy/ai-ticket-agent-fastapi.git
cd ai-ticket-agent-fastapi
```

2. **Install the required dependencies:**
```bash
pip install -r requirements.txt
```

3. **Configure environment variables** (see the section below).

4. **Launch the FastAPI server:**
```bash
python app.py
```

---

## ⚙️ Environment Variables Configuration (API Keys)

For the AI agent to work and send notifications, you need to configure three environment variables. You can do this in two ways:

### Method 1: Directly via PowerShell Console (Before launch)
Run the following commands in your terminal, replacing the placeholders with your actual data:

```powershell
$env:GOOGLE_API_KEY="your_long_gemini_api_key"
$env:TELEGRAM_BOT_TOKEN="your_bot_token_from_botfather"
$env:TELEGRAM_CHAT_ID="your_telegram_chat_or_channel_id"
```

### Method 2: Via `.env` file (Recommended for development)
1. Create a file named `.env` in the root folder of the project.
2. Add the following lines to it:

```env
GOOGLE_API_KEY=your_long_gemini_api_key
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
TELEGRAM_CHAT_ID=your_telegram_chat_or_channel_id
```

> ⚠️ **Note:** The `.env` file is already added to `.gitignore` and will never be pushed to your public GitHub repository, keeping your credentials secure.

---

## 🎯 How to Test and Use the Project

Once the server successfully starts and you see `Application startup complete` in the console, the project is ready to go. You can test it using the following methods:

### 1. Interactive API Documentation (Swagger UI)
FastAPI automatically generates a user-friendly web interface for testing endpoints:
* Open your browser and go to: `http://127.0.0.1:8000/docs` (or specify port 8080 if you changed it in the code).
* Find the `POST /webhook/new-ticket` endpoint, click **"Try it out"**, paste a test JSON payload, and hit **"Execute"**.

### 2. Simulating an Incoming Webhook via PowerShell
To simulate sending a ticket from an external CRM system (e.g., Zendesk), open a new (parallel) PowerShell window and run the following command:

```powershell
Invoke-RestMethod -Uri "[http://127.0.0.1:8000/webhook/new-ticket](http://127.0.0.1:8000/webhook/new-ticket)" -Method Post -ContentType "application/json" -Body '{"message_id": "ticket_free_001", "text": "Hello! I paid for a subscription yesterday, but my account is still locked. Refund my money or fix it!"}'
```

**What happens after sending:**
1. The working server's console will display a request processing log.
2. The Gemini neural network will automatically translate the text, identify the category as "Complaint / Payment Issue", and set the status to "High Urgency".
3. The data will be saved to the local SQLite database (with duplicate protection via `message_id`).
4. An emergency notification containing ticket details will instantly arrive in your Telegram chat for the manager to review.

---

## 📸 System Demonstration
Upon detecting a critical request (such as a complaint or a high-urgency issue), the AI agent automatically classifies the ticket, and the bot instantly sends a structured notification to the managers in Telegram:

<img src="images/tg_alert.png" width="350" alt="Telegram Alert Demo">