import os
import json
import requests
from typing import Optional
from datetime import datetime

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ===== ملفات التخزين =====
USERS_FILE = "tahsee.json"
BANNED_FILE = "banned.json"
ADMINS = {5094439626}  # ← Telegram ID مالك البوت

HEADERS = {"User-Agent": "MyChessBot/1.0"}

# ===== تحميل / حفظ JSON =====
def load_json(file):
    if os.path.exists(file):
        with open(file, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

user_data = load_json(USERS_FILE)
banned_users = load_json(BANNED_FILE)

# ===== أدوات =====
def is_admin(user_id: int) -> bool:
    return user_id in ADMINS

def is_banned(user_id: int) -> bool:
    return str(user_id) in banned_users

async def banned_guard(update: Update) -> bool:
    if is_banned(update.effective_user.id):
        await update.message.reply_text("🚫 أنت محظور من استخدام البوت.")
        return True
    return False

def resolve_target_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    if update.message and update.message.reply_to_message:
        return str(update.message.reply_to_message.from_user.id)
    return str(update.effective_user.id)

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

# ===== أوامر البوت =====
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
    user_data[str(update.effective_user.id)] = username
    save_json(USERS_FILE, user_data)
    await update.message.reply_text(f"✅ تم تسجيل الحساب: {username}")

async def signout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await banned_guard(update):
        return
    uid = str(update.effective_user.id)
    if uid in user_data:
        del user_data[uid]
        save_json(USERS_FILE, user_data)
        await update.message.reply_text("✅ تم تسجيل خروجك من الحساب.")
    else:
        await update.message.reply_text("❌ ما عندك حساب مسجل.")

async def user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await banned_guard(update):
        return
    target_id = resolve_target_user(update, context)
    username = user_data.get(target_id)
    if username:
        await update.message.reply_text(f"👤 الحساب المسجل: {username}")
    else:
        await update.message.reply_text("❌ ماكو حساب مسجل لهذا المستخدم.")

async def elo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await banned_guard(update):
        return
    target_id = resolve_target_user(update, context)
    username = user_data.get(target_id)
    if not username:
        await update.message.reply_text("❌ ماكو حساب مسجل لهذا المستخدم.")
        return
    stats = fetch_stats(username)
    rapid_rating = stats.get("chess_rapid", {}).get("last", {}).get("rating")
    tg_user = update.message.reply_to_message.from_user if update.message and update.message.reply_to_message else update.effective_user
    tg_name = f"@{tg_user.username}" if tg_user.username else tg_user.full_name
    if rapid_rating:
        await update.message.reply_text(f"{tg_name} ({rapid_rating} ELO)\nRapid")
    else:
        await update.message.reply_text("❌ لا يوجد تقييم Rapid لهذا الحساب.")

async def topelo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await banned_guard(update):
        return
    if not user_data:
        await update.message.reply_text("❌ ماكو لاعبين مسجلين.")
        return
    modes = ["rapid", "blitz", "bullet"]
    results = {m: [] for m in modes}
    for username in set(user_data.values()):
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

# ===== أوامر الحظر =====
def get_target_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
    if update.message and update.message.reply_to_message:
        return str(update.message.reply_to_message.from_user.id)
    if context.args:
        return str(context.args[0])
    return None

async def tasfeer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ هذا الأمر للأدمن فقط.")
        return
    target = get_target_id(update, context)
    if not target:
        await update.message.reply_text("❌ حدد مستخدم بالرد أو ID.")
        return
    banned_users[target] = True
    user_data.pop(target, None)
    save_json(USERS_FILE, user_data)
    save_json(BANNED_FILE, banned_users)
    await update.message.reply_text(f"🚫 تم حظر المستخدم {target}")

async def untasfeer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ هذا الأمر للأدمن فقط.")
        return
    target = get_target_id(update, context)
    if not target:
        await update.message.reply_text("❌ حدد مستخدم.")
        return
    if target in banned_users:
        banned_users.pop(target)
        save_json(BANNED_FILE, banned_users)
        await update.message.reply_text(f"✅ تم رفع الحظر عن {target}")
    else:
        await update.message.reply_text("ℹ️ المستخدم غير محظور.")

# ===== تشغيل البوت =====
def main():
    TOKEN = os.getenv("BOT_TOKEN")

    if not TOKEN:
        print("❌ BOT_TOKEN not found!")
        return

    app = Application.builder().token(TOKEN).build()
    # أوامر المستخدم
    app.add_handler(CommandHandler("sign", sign))
    app.add_handler(CommandHandler("signout", signout))
    app.add_handler(CommandHandler("user", user))
    app.add_handler(CommandHandler("elo", elo))
    app.add_handler(CommandHandler("topelo", topelo))

    # أوامر الأدمن
    app.add_handler(CommandHandler("tasfeer", tasfeer))
    app.add_handler(CommandHandler("untasfeer", untasfeer))

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
