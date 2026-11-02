import asyncio
import hashlib
import hmac
import json
import os
import sqlite3
import time
from urllib.parse import parse_qsl

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
import uvicorn

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BOT_USERNAME = os.getenv("BOT_USERNAME", "")
WEBAPP_URL = os.getenv("WEBAPP_URL", "")
DB_PATH = os.getenv("DATABASE_PATH", "atx.sqlite3")
COOLDOWN = int(os.getenv("MINING_COOLDOWN_HOURS", "3")) * 3600
MINING_REWARD = int(os.getenv("MINING_REWARD", "25"))
REFERRAL_REWARD = int(os.getenv("REFERRAL_REWARD", "50"))
ADMIN_IDS = {int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
            balance INTEGER NOT NULL DEFAULT 0, last_claim INTEGER NOT NULL DEFAULT 0,
            referred_by INTEGER, created_at INTEGER NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS claims(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, claimed_at INTEGER)""")
        c.execute("""CREATE TABLE IF NOT EXISTS tasks(
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
            description TEXT NOT NULL, reward INTEGER NOT NULL,
            url TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1)""")
        c.execute("""CREATE TABLE IF NOT EXISTS task_completions(
            user_id INTEGER, task_id INTEGER, completed_at INTEGER,
            PRIMARY KEY(user_id, task_id))""")
        if c.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0:
            c.executemany(
                "INSERT INTO tasks(title,description,reward,url) VALUES(?,?,?,?)",
                [
                    ("Discover ATX", "Learn about the ATX project.", 10, "https://t.me/"),
                    ("Explore our video", "Visit our YouTube channel and explore its content.", 10, "https://youtube.com/"),
                ],
            )

def verify_init_data(init_data: str):
    if not BOT_TOKEN or not init_data:
        raise HTTPException(401, "Telegram authorization is not configured.")
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise HTTPException(401, "Missing Telegram signature.")
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, received_hash):
        raise HTTPException(401, "Invalid Telegram signature.")
    auth_date = int(parsed.get("auth_date", "0"))
    if time.time() - auth_date > 86400:
        raise HTTPException(401, "Telegram session expired. Reopen the app.")
    try:
        user = json.loads(parsed["user"])
    except Exception:
        raise HTTPException(401, "Invalid Telegram user data.")
    return user

def get_user(user):
    uid = int(user["id"])
    with db() as c:
        row = c.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
        if row is None:
            c.execute("""INSERT INTO users(user_id,username,first_name,created_at)
                         VALUES(?,?,?,?)""",
                      (uid, user.get("username"), user.get("first_name", "Miner"), int(time.time())))
            row = c.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
        else:
            c.execute("UPDATE users SET username=?,first_name=? WHERE user_id=?",
                      (user.get("username"), user.get("first_name", "Miner"), uid))
            row = c.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    return dict(row)

api = FastAPI(title="ATX Mini App API")

@api.on_event("startup")
async def startup():
    init_db()

@api.get("/")
async def home():
    return FileResponse("web/index.html")

def auth_user(authorization: str | None):
    if not authorization or not authorization.startswith("tma "):
        raise HTTPException(401, "Open ATX inside Telegram.")
    return verify_init_data(authorization[4:])

@api.get("/api/me")
async def me(authorization: str | None = Header(default=None)):
    u = get_user(auth_user(authorization))
    now = int(time.time())
    remaining = max(0, COOLDOWN - (now - u["last_claim"]))
    with db() as c:
        referrals = c.execute("SELECT COUNT(*) FROM users WHERE referred_by=?", (u["user_id"],)).fetchone()[0]
    return {"name": u["first_name"], "balance": u["balance"], "level": 1 + u["balance"] // 1000,
            "remaining": remaining, "referrals": referrals, "reward": MINING_REWARD}

@api.post("/api/claim")
async def claim(authorization: str | None = Header(default=None)):
    user = auth_user(authorization)
    u = get_user(user)
    now = int(time.time())
    with db() as c:
        row = c.execute("SELECT last_claim,balance FROM users WHERE user_id=?", (u["user_id"],)).fetchone()
        remaining = COOLDOWN - (now - row["last_claim"])
        if remaining > 0:
            raise HTTPException(429, f"Mining recharges in {remaining} seconds.")
        c.execute("UPDATE users SET balance=balance+?,last_claim=? WHERE user_id=?",
                  (MINING_REWARD, now, u["user_id"]))
        c.execute("INSERT INTO claims(user_id,amount,claimed_at) VALUES(?,?,?)",
                  (u["user_id"], MINING_REWARD, now))
        balance = row["balance"] + MINING_REWARD
    return {"ok": True, "balance": balance, "reward": MINING_REWARD}

@api.get("/api/tasks")
async def tasks(authorization: str | None = Header(default=None)):
    user = get_user(auth_user(authorization))
    with db() as c:
        rows = c.execute("""SELECT t.*, CASE WHEN tc.user_id IS NULL THEN 0 ELSE 1 END done
            FROM tasks t LEFT JOIN task_completions tc
            ON t.id=tc.task_id AND tc.user_id=? WHERE t.active=1 ORDER BY t.id""",
            (user["user_id"],)).fetchall()
    return [dict(r) for r in rows]

@api.post("/api/tasks/{task_id}/complete")
async def complete_task(task_id: int, authorization: str | None = Header(default=None)):
    user = get_user(auth_user(authorization))
    with db() as c:
        task = c.execute("SELECT * FROM tasks WHERE id=? AND active=1", (task_id,)).fetchone()
        if not task:
            raise HTTPException(404, "Task not found.")
        exists = c.execute("SELECT 1 FROM task_completions WHERE user_id=? AND task_id=?",
                           (user["user_id"], task_id)).fetchone()
        if exists:
            raise HTTPException(409, "Task already claimed.")
        # Starter tasks are self-attested. Add server-side checks before offering valuable rewards.
        c.execute("INSERT INTO task_completions(user_id,task_id,completed_at) VALUES(?,?,?)",
                  (user["user_id"], task_id, int(time.time())))
        c.execute("UPDATE users SET balance=balance+? WHERE user_id=?",
                  (task["reward"], user["user_id"]))
    return {"ok": True, "reward": task["reward"]}

@api.get("/api/referral")
async def referral(authorization: str | None = Header(default=None)):
    user = auth_user(authorization)
    uid = int(user["id"])
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{uid}" if BOT_USERNAME else "Set BOT_USERNAME in .env"
    return {"link": link}

@api.get("/health")
async def health():
    return {"ok": True, "app": "ATX"}

async def bot_main():
    if not BOT_TOKEN:
        print("BOT_TOKEN is empty. API can run, but Telegram bot is disabled.")
        return
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def start(message: Message):
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) > 1 and parts[1].startswith("ref_"):
            try:
                referrer = int(parts[1][4:])
                if referrer != message.from_user.id:
                    with db() as c:
                        existing = c.execute("SELECT referred_by FROM users WHERE user_id=?",
                                              (message.from_user.id,)).fetchone()
                        if existing is None:
                            c.execute("""INSERT INTO users(user_id,username,first_name,referred_by,created_at)
                                         VALUES(?,?,?,?,?)""",
                                      (message.from_user.id, message.from_user.username,
                                       message.from_user.first_name, referrer, int(time.time())))
                            c.execute("UPDATE users SET balance=balance+? WHERE user_id=?",
                                      (REFERRAL_REWARD, referrer))
            except ValueError:
                pass
        if WEBAPP_URL.startswith("https://"):
            keyboard = ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="🎮 Open ATX", web_app=WebAppInfo(url=WEBAPP_URL))]],
                resize_keyboard=True)
            await message.answer("Welcome to ATX! Tap below to open the mining game.", reply_markup=keyboard)
        else:
            await message.answer("ATX bot is running. Set WEBAPP_URL to your HTTPS Mini App address.")

    await dp.start_polling(bot)

async def main():
    config = uvicorn.Config(api, host="0.0.0.0", port=int(os.getenv("PORT", "8000")), log_level="info")
    server = uvicorn.Server(config)
    await asyncio.gather(server.serve(), bot_main())

if __name__ == "__main__":
    asyncio.run(main())
