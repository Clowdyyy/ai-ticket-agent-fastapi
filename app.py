import datetime as dt
import json
import os
import sqlite3
from typing import Dict, List, Optional

import requests
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


def get_available_models(api_key: str) -> List[str]:
    """Возвращает список model_id, доступных для generateContent в API v1beta."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    response = requests.get(url, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f"Не удалось получить список моделей: {response.status_code} {response.text}")

    data = response.json()
    models = data.get("models", [])
    available: List[str] = []

    for model in models:
        name = model.get("name", "")  # формат: models/xxx
        methods = model.get("supportedGenerationMethods", [])
        if "generateContent" in methods and name.startswith("models/"):
            available.append(name.replace("models/", ""))

    return available


def analyze_ticket_with_gemini_direct(api_key: str, ticket_text: str, model_name: str) -> Dict[str, str]:
    """Отправляет запрос к Gemini напрямую через REST API v1beta."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"

    prompt = f"""
You are a support analyst.
Task:
1) Translate the customer message to Russian.
2) Classify category using one of:
   - Жалоба
   - Вопрос по цене
   - Благодарность
   - Другое
3) Classify urgency using one of:
   - Высокая
   - Средняя
   - Низкая

Return ONLY valid JSON with these keys:
{{
  "translation_ru": "...",
  "category": "...",
  "urgency": "..."
}}

Customer message:
\"\"\"{ticket_text}\"\"\"
""".strip()

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }
    
    headers = {"Content-Type": "application/json"}
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    
    if response.status_code != 200:
        raise RuntimeError(f"API Error {response.status_code}: {response.text}")
        
    response_data = response.json()
    
    try:
        raw_text = response_data['candidates'][0]['content']['parts'][0]['text'].strip()
    except (KeyError, IndexError):
        raise RuntimeError(f"Не удалось прочитать ответ от ИИ: {response_data}")

    if raw_text.startswith("```"):
        raw_text = raw_text.replace("```json", "").replace("```", "").strip()

    return json.loads(raw_text)


def init_db(db_path: str) -> sqlite3.Connection:
    """Создает базу/таблицу при первом запуске."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tickets (
            message_id TEXT PRIMARY KEY,
            tema TEXT,
            original_text TEXT,
            translated_text TEXT,
            category TEXT,
            urgency TEXT,
            model TEXT,
            status TEXT,
            created_at TEXT
        )
        """
    )
    conn.commit()
    return conn


def ticket_exists(conn: sqlite3.Connection, message_id: str) -> bool:
    cursor = conn.execute("SELECT 1 FROM tickets WHERE message_id = ? LIMIT 1", (message_id,))
    return cursor.fetchone() is not None


def save_ticket(
    conn: sqlite3.Connection,
    message_id: str,
    subject: str,
    original_text: str,
    translated_text: str,
    category: str,
    urgency: str,
    model_name: str,
    status: str,
) -> None:
    now_iso = dt.datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO tickets (
            message_id, tema, original_text, translated_text, category, urgency, model, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            message_id,
            subject,
            original_text,
            translated_text,
            category,
            urgency,
            model_name,
            status,
            now_iso,
        ),
    )
    conn.commit()


def escape_markdown_v2(text: str) -> str:
    """Экранирует текст для Telegram MarkdownV2."""
    special_chars = r"_*[]()~`>#+-=|{}.!"
    escaped = text
    for char in special_chars:
        escaped = escaped.replace(char, f"\\{char}")
    return escaped


def send_telegram_alert(
    bot_token: str,
    chat_id: str,
    subject: str,
    original_text: str,
    translated_text: str,
    category: str,
    urgency: str,
) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    message = (
        "🚨 *Новый важный тикет*\n\n"
        f"*Тема:* {escape_markdown_v2(subject or '(без темы)')}\n"
        f"*Категория:* {escape_markdown_v2(category)}\n"
        f"*Срочность:* {escape_markdown_v2(urgency)}\n\n"
        f"*Перевод:*\n{escape_markdown_v2(translated_text[:1200])}\n\n"
        f"*Оригинал:*\n{escape_markdown_v2(original_text[:1200])}"
    )
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "MarkdownV2",
    }
    response = requests.post(url, json=payload, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f"Telegram API error {response.status_code}: {response.text}")


def build_model_candidates(available_models: List[str]) -> List[str]:
    preferred_model = os.getenv("GEMINI_MODEL", "").strip()
    fallback_models = [
        "gemini-2.0-flash",
        "gemini-1.5-flash-latest",
        "gemini-1.5-pro-latest",
    ]
    preferred_candidates = [preferred_model] if preferred_model else []
    preferred_candidates.extend([m for m in fallback_models if m and m != preferred_model])
    model_candidates = [m for m in preferred_candidates if m in available_models]
    model_candidates.extend([m for m in available_models if m not in model_candidates])
    return model_candidates


class TicketWebhookIn(BaseModel):
    message_id: str = Field(..., min_length=1)
    subject: str = Field(default="")
    text: str = Field(..., min_length=1)


app = FastAPI(title="Tickets AI Agent", version="1.0.0")


@app.on_event("startup")
def startup_event() -> None:
    print("🚀 Starting FastAPI ticket agent...")
    conn = init_db("tickets_system.db")
    conn.close()
    print("✅ SQLite initialized: tickets_system.db")


@app.post("/webhook/new-ticket")
async def new_ticket_webhook(payload: TicketWebhookIn) -> Dict[str, str]:
    api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not api_key:
        raise HTTPException(status_code=500, detail="Missing GOOGLE_API_KEY")
    if not telegram_bot_token or not telegram_chat_id:
        raise HTTPException(status_code=500, detail="Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

    print(f"📥 Webhook received: message_id={payload.message_id}")

    conn = init_db("tickets_system.db")
    try:
        if ticket_exists(conn, payload.message_id):
            print(f"⏭️ Duplicate ticket skipped: {payload.message_id}")
            return {"status": "skip", "message": "Ticket already exists", "message_id": payload.message_id}

        try:
            available_models = get_available_models(api_key)
        except Exception as e:
            error_text = f"ERROR: Model list failed: {e}"
            save_ticket(
                conn=conn,
                message_id=payload.message_id,
                subject=payload.subject,
                original_text=payload.text,
                translated_text="Ошибка анализа",
                category="Другое",
                urgency="Средняя",
                model_name="",
                status=error_text[:300],
            )
            raise HTTPException(status_code=502, detail="Failed to fetch available models")

        if not available_models:
            save_ticket(
                conn=conn,
                message_id=payload.message_id,
                subject=payload.subject,
                original_text=payload.text,
                translated_text="Ошибка анализа",
                category="Другое",
                urgency="Средняя",
                model_name="",
                status="ERROR: No models with generateContent",
            )
            raise HTTPException(status_code=503, detail="No available Gemini models")

        model_candidates = build_model_candidates(available_models)
        result: Optional[Dict[str, str]] = None
        used_model = ""
        last_error: Optional[Exception] = None

        for model_name in model_candidates:
            try:
                result = analyze_ticket_with_gemini_direct(api_key, payload.text, model_name)
                used_model = model_name
                break
            except Exception as model_error:
                last_error = model_error

        if result is None:
            error_text = f"ERROR: Analysis failed on all models. Last error: {last_error}"
            save_ticket(
                conn=conn,
                message_id=payload.message_id,
                subject=payload.subject,
                original_text=payload.text,
                translated_text="Ошибка анализа",
                category="Другое",
                urgency="Средняя",
                model_name=used_model,
                status=error_text[:300],
            )
            raise HTTPException(status_code=502, detail="Gemini analysis failed")

        translated_text = result.get("translation_ru", "")
        category = result.get("category", "Другое")
        urgency = result.get("urgency", "Средняя")

        save_ticket(
            conn=conn,
            message_id=payload.message_id,
            subject=payload.subject,
            original_text=payload.text,
            translated_text=translated_text,
            category=category,
            urgency=urgency,
            model_name=used_model,
            status="OK",
        )
        print(f"✅ Ticket stored: {payload.message_id}, model={used_model}")

        if urgency == "Высокая" or category == "Жалоба":
            try:
                send_telegram_alert(
                    bot_token=telegram_bot_token,
                    chat_id=telegram_chat_id,
                    subject=payload.subject,
                    original_text=payload.text,
                    translated_text=translated_text,
                    category=category,
                    urgency=urgency,
                )
                print(f"📣 Telegram alert sent: {payload.message_id}")
            except Exception as tg_error:
                print(f"⚠️ Telegram alert failed: {tg_error}")

        return {
            "status": "ok",
            "message_id": payload.message_id,
            "model": used_model,
            "category": category,
            "urgency": urgency,
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Unexpected webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        conn.close()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port)