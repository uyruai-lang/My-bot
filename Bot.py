import os
import requests
from typing import Optional
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import psycopg2

# ===== Database Connection =====
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise Exception("❌ DATABASE_URL not found!")

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# ===== Admins =====
ADMINS = {5094439626}  # Telegram ID مالك البوت

HEADERS = {"User-Agent": "MyChessBot/1.0"}

# ===== Database Setup =====
def init_db():
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id BIGINT PRIMARY KEY,
            chess_username TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS banned_users (
            telegram_id BIGINT PRIMARY KEY
        )
    """)
    conn.commit()

init_db()

# ===== Helpers =====
def is_admin(user_id: int) -> bool:
    return user_id in ADMINS

def is_banned(user_id: int) -> bool:
    cur.execute("SELECT 1 FROM banned_users WHERE telegram_id=%s", (user_id,))
    return cur.fetchone() is not None

async def banned_guard(update: Update) -> bool:
    if is_banned(update.effective_user.id):
        await update.message.reply_text("🚫 أنت محظور من استخدام البوت.")
        return True
    return False

def resolve_target_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message and update.message.reply_to_message:
        return update.message.reply_to_message.from_user.id
    return update.effective_user.id

# ===== Chess.com API =====
def fetch_stats(username: str) -> Optional[dict]:
    try:
        r = requests.get(
            f"https://api.chess.com/pub/player/{username}/stats",
            headers=HEADERS,
            timeout=15
        )
        if r.status_code == 200:
            return r.json()
    except requests.RequestException:
        pass
    return None

# ===== Bot Commands =====
async def sign(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await banned_guard(update):
        return
    if len(context.args) != 1:
        await update.message.reply_text("❌ /sign <username>")
        return
    username = context.args[0].lower()
    if not fetch_stats(username):
        await update.message.reply_text("❌ حساب Chess.com غير موجود")
        return
    telegram_id = update.effective_user.id
    cur.execute("""
        INSERT INTO users (telegram_id, chess_username)
        VALUES (%s, %s)
        ON CONFLICT (telegram_id) DO UPDATE SET chess_username = EXCLUDED.chess_username
    """, (telegram_id, username))
    conn.commit()
    await update.message.reply_text(f"✅ تم تسجيل الحساب: {username}")

async def signout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await banned_guard(update):
        return
    telegram_id = update.effective_user.id
    cur.execute("DELETE FROM users WHERE telegram_id=%s", (telegram_id,))
    conn.commit()
    await update.message.reply_text("✅ تم تسجيل خروجك من الحساب.")

async def user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await banned_guard(update):
        return
    target_id = resolve_target_user(update, context)
    cur.execute("SELECT chess_username FROM users WHERE telegram_id=%s", (target_id,))
    result = cur.fetchone()
    if result:
        await update.message.reply_text(f"👤 الحساب المسجل: {result[0]}")
    else:
        await update.message.reply_text("❌ ماكو حساب مسجل لهذا المستخدم.")

async def elo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await banned_guard(update):
        return
    target_id = resolve_target_user(update, context)
    cur.execute("SELECT chess_username FROM users WHERE telegram_id=%s", (target_id,))
    result = cur.fetchone()
    if not result:
        await update.message.reply_text("❌ ماكو حساب مسجل لهذا المستخدم.")
        return
    username = result[0]
    stats = fetch_stats(username)
    rapid_rating = stats.get("chess_rapid", {}).get("last", {}).get("rating") if stats else None
    tg_user = update.message.reply_to_message.from_user if update.message and update.message.reply_to_message else update.effective_user
    tg_name = f"@{tg_user.username}" if tg_user.username else tg_user.full_name
    if rapid_rating:
        await update.message.reply_text(f"{tg_name} ({rapid_rating} ELO)\nRapid")
    else:
        await update.message.reply_text("❌ لا يوجد تقييم Rapid لهذا الحساب.")

async def topelo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await banned_guard(update):
        return
    modes = ["rapid", "blitz", "bullet"]
    results = {m: [] for m in modes}
    cur.execute("SELECT chess_username FROM users")
    usernames = [row[0] for row in cur.fetchall()]
    if not usernames:
        await update.message.reply_text("❌ ماكو لاعبين مسجلين.")
        return
    for username in set(usernames):
        stats = fetch_stats(username)
        if not stats:
            continue
        for mode in modes:
            rating = stats.get(f"chess_{mode}", {}).get("last", {}).get("rating")
            if rating:
                results[mode].append((username, rating))
    msg = "🏆 Top 5 Players (المسجلين)\n\n"
    has_data = False
    for mode in modes:
        players = sorted(results[mode], key=lambda x: x[1], reverse=True)[:5]
        msg += f"{mode.capitalize()}:\n"
        if not players:
            msg += "  لا يوجد لاعبين\n\n"
            continue
        has_data = True
        for i, (u, r) in enumerate(players, 1):
            msg += f"  {i}. {u} — {r}\n"
        msg += "\n"
    if not has_data:
        await update.message.reply_text("❌ لا يوجد تقييمات متاحة.\nتأكد اللاعبين لعبوا Ranked games.")
        return
    await update.message.reply_text(msg)

# ===== Admin Commands =====
def get_target_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    if update.message and update.message.reply_to_message:
        return update.message.reply_to_message.from_user.id
    if context.args:
        return int(context.args[0])
    return None

async def tasfeer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ هذا الأمر للأدمن فقط.")
        return
    target = get_target_id(update, context)
    if not target:
        await update.message.reply_text("❌ حدد مستخدم بالرد أو ID.")
        return
    cur.execute("INSERT INTO banned_users (telegram_id) VALUES (%s) ON CONFLICT DO NOTHING", (target,))
    cur.execute("DELETE FROM users WHERE telegram_id=%s", (target,))
    conn.commit()
    await update.message.reply_text(f"🚫 تم حظر المستخدم {target}")

async def untasfeer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ هذا الأمر للأدمن فقط.")
        return
    target = get_target_id(update, context)
    if not target:
        await update.message.reply_text("❌ حدد مستخدم.")
        return
    cur.execute("DELETE FROM banned_users WHERE telegram_id=%s", (target,))
    conn.commit()
    await update.message.reply_text(f"✅ تم رفع الحظر عن {target}")

# ===== Run Bot =====
def main():
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN:
        print("❌ BOT_TOKEN not found!")
        return

    app = Application.builder().token(TOKEN).build()

    # User commands
    app.add_handler(CommandHandler("sign", sign))
    app.add_handler(CommandHandler("signout", signout))
    app.add_handler(CommandHandler("user", user))
    app.add_handler(CommandHandler("elo", elo))
    app.add_handler(CommandHandler("topelo", topelo))

    # Admin commands
    app.add_handler(CommandHandler("tasfeer", tasfeer))
    app.add_handler(CommandHandler("untasfeer", untasfeer))

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
