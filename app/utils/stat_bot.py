import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv
import os

load_dotenv()

bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
chat_id = os.getenv('TELEGRAM_CHAT_ID')
BASEDIR = os.path.abspath(os.path.dirname(__file__))
database_path = os.path.abspath(os.path.join(BASEDIR, '..', 'database', 'database.db'))

print(f"Database path: {database_path}")  # Проверка правильности пути

# Проверка доступности файла базы данных
if not os.path.exists(database_path):
    print(f"Database file does not exist: {database_path}")
else:
    print(f"Database file found: {database_path}")

# Подключение к базе данных
try:
    cnx = sqlite3.connect(database_path)
    print("Database connection successful")
except sqlite3.OperationalError as e:
    print(f"Database connection failed: {e}")

df = pd.read_sql_query("SELECT * FROM Users", cnx)

if 'date_created' in df.columns:
    df['date_created'] = pd.to_datetime(df['date_created'])
if 'last_active' in df.columns:
    df['last_active'] = pd.to_datetime(df['last_active'])

now = datetime.now()

total_users = len(df)

new_users_last_day = df[df['date_created'] >= (now - timedelta(days=1))]

new_users_last_week = df[df['date_created'] >= (now - timedelta(days=7))]

active_users_last_week = df[df['last_active'] >= (now - timedelta(days=7))]

active_users_last_day = df[df['last_active'] >= (now - timedelta(days=1))]

message = (
    f"📊 *User Statistics*\n\n"
    f"👥 *Total amount of Users:* {total_users}\n\n"
    f"🆕 *New Users*\n"
    f" - Last 24 Hours: {len(new_users_last_day)}\n"
    f" - Last 7 Days: {len(new_users_last_week)}\n\n"
    f"🔄 *Active Users*\n"
    f" - Last 24 Hours: {len(active_users_last_day)}\n"
    f" - Last 7 Days: {len(active_users_last_week)}"
)

def send_telegram_message(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'Markdown'
    }
    response = requests.post(url, json=payload)
    return response

response = send_telegram_message(bot_token, chat_id, message)

if response.status_code == 200:
    print("Message sent successfully.")
else:
    print("Failed to send message. Error:", response.text)