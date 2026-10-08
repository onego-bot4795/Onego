"""
Simple Starter Telegram Bot
============================

Setup:
1. Install the library:
   pip install python-telegram-bot --break-system-packages

2. Create a bot on Telegram:
   - Telegram app kholo, search karo "BotFather"
   - Usse /newbot command bhejo
   - Bot ka naam aur username set karo
   - BotFather aapko ek API TOKEN dega — usse copy karke neeche BOT_TOKEN mein daalo

3. Run karo:
   python telegram_bot.py
"""

import os
import html
import types
import asyncio
import json
import math
import logging
from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")  # server chahe kahin bhi ho (Railway = UTC), hamesha India time use karo


def now_ist():
    return datetime.now(IST)
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ChatJoinRequestHandler,
    ContextTypes,
    filters,
)

# ---- Bot ka username (group welcome button ke liye) ----
BOT_USERNAME = "One_gotask_bot"

# ---- Permanent (persistent) keyboard buttons ----
MAIN_MENU = [
    ["📩 SMS Task", "💬 WhatsApp Task"],
    ["🎁 Referral", "🆘 Help Center"],
    ["📢 Channel", "🎧 Customer Service"],
    ["📝 Report Problem"],
]
MAIN_MENU_MARKUP = ReplyKeyboardMarkup(
    MAIN_MENU,
    resize_keyboard=True,   # buttons ko screen ke hisaab se chhota rakhta hai
    is_persistent=True,     # keyboard hamesha screen par dikhta rahega
)

# ---- Admin settings ----
# Apni Telegram User ID yahan daalo (bot ko /myid bhej kar pata karo)
ADMIN_ID = 7330058637

# Task videos ke file_id yahan save honge (khud-ba-khud, Telegram se)
SMS_VIDEO_ID_FILE = "sms_video_id.txt"
WHATSAPP_VIDEO_ID_FILE = "whatsapp_video_id.txt"


def get_video_id(file_path):
    """Saved file_id ko file se padhta hai"""
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            return f.read().strip()
    return None


def save_video_id(file_path, file_id: str):
    """file_id ko file mein save karta hai (permanent rehta hai, bot restart hone par bhi)"""
    with open(file_path, "w") as f:
        f.write(file_id)

# ---- Yahan apna BotFather se mila hua token daalo ----
BOT_TOKEN = "8743073709:AAHEPgulzz0kFRk0mHrGcYxRVBTBTimL9eI"

# Logging setup (taaki errors/console mein activity dikhe)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# httpx/telegram library ka har API call INFO-log hota tha (getUpdates, sendMessage, etc.) —
# active group mein yeh sab CPU/disk time le rahe the aur bot ko slow kar rahe the.
# Warning level pe rakhne se noise kam ho jaata hai, sirf real errors dikhenge.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)


# ---- Command Handlers ----

PENDING_WELCOMES_FILE = "pending_welcomes.json"
RECENT_WELCOMES_FILE = "recent_welcome_msgs.json"  # last 5 welcome message_ids track karne ke liye (per chat)
MAX_WELCOME_MESSAGES = 1  # naya welcome aate hi turant pichla wala delete ho jaata hai, sirf latest 1 rehta hai


def load_pending_welcomes():
    if os.path.exists(PENDING_WELCOMES_FILE):
        with open(PENDING_WELCOMES_FILE, "r") as f:
            return json.load(f)
    return []


def save_pending_welcomes(items):
    with open(PENDING_WELCOMES_FILE, "w") as f:
        json.dump(items, f)


def queue_pending_welcome(chat_id: int, text: str, user_id: int = None):
    items = load_pending_welcomes()
    items.append({"chat_id": chat_id, "text": text, "user_id": user_id})
    save_pending_welcomes(items)


def load_recent_welcomes():
    if os.path.exists(RECENT_WELCOMES_FILE):
        with open(RECENT_WELCOMES_FILE, "r") as f:
            return json.load(f)
    return {}


def save_recent_welcomes(data):
    with open(RECENT_WELCOMES_FILE, "w") as f:
        json.dump(data, f)


async def track_new_welcome_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    """Pehle purane welcome messages delete kiye jaate the, ab yeh band kar diya gaya hai —
    sabhi welcome messages hamesha group mein rahenge, kuch bhi delete nahi hota."""
    pass


GROUP_WELCOME_FILE = "group_welcome_texts.json"  # har group ka apna custom welcome text (chat_id ke hisaab se)


def load_group_welcome_texts():
    if os.path.exists(GROUP_WELCOME_FILE):
        with open(GROUP_WELCOME_FILE, "r") as f:
            return json.load(f)
    return {}


def save_group_welcome_texts(data):
    with open(GROUP_WELCOME_FILE, "w") as f:
        json.dump(data, f)


async def setwelcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin group mein '/setwelcome <text>' bhejega — yehi text ab se us group ke
    naye members ko welcome karne ke liye use hoga (member ke mention ke saath)."""
    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:
        await update.message.reply_text(
            "⚠️ Text bhejein. Jaise: /setwelcome Welcome to 1Go Task"
        )
        return

    custom_text = " ".join(context.args)
    chat_id = update.effective_chat.id

    data = load_group_welcome_texts()
    data[str(chat_id)] = custom_text
    save_group_welcome_texts(data)

    await update.message.reply_text(f"✅ Is group ka welcome message set ho gaya:\n\n{custom_text}")


import random

INVISIBLE_VARIANTS = ["", "\u200b", "\u200c", " "]  # tiny invisible-ish variation taaki har message thoda unique lage


def build_welcome_text(new_member, chat_id=None):
    """Welcome text (HTML format mein): username ho to @username, warna @FirstName
    (real mention link ke saath, taaki user ko tag/notification mile)."""
    if new_member.username:
        tag = f"@{new_member.username}"
    else:
        name = html.escape(new_member.first_name or "Dost")
        tag = f'<a href="tg://user?id={new_member.id}">@{name}</a>'
    return f"{tag} Welcome to 1GoTask 🙏🏻"


async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Jab group mein koi naya member add ho, use welcome karta hai — group mein sirf yehi karta hai.
    Agar group band ho (messaging restricted), to welcome ko queue mein daal deta hai — jaise hi
    group khulega, ye automatically bhej diya jayega (retry_pending_welcomes job dwara).
    Sirf latest MAX_WELCOME_MESSAGES welcome messages hi group mein rakhta hai, purane delete ho jaate hain."""
    chat_id = update.effective_chat.id
    for new_member in update.message.new_chat_members:
        # Agar bot khud add hua hai, to use skip karo
        if new_member.id == context.bot.id:
            continue

        text = build_welcome_text(new_member, chat_id)

        try:
            sent = await update.message.reply_text(text, parse_mode="HTML")
            await track_new_welcome_message(context, chat_id, sent.message_id)
        except Exception as e:
            logger.error(f"Welcome bhejne mein error (group band ho sakta hai): {e}")
            queue_pending_welcome(chat_id, text)


JOIN_REQUEST_WELCOME_TEXT = (
    "👋 Hey Dear! Welcome to 1 Go Task! 🚀\n\n"
    "💰 Complete 300+ simple tasks & earn rewards\n"
    "👥 2-Level Referral – Earn commission from friends And  Get 2,000 Points too 😜\n\n"
    "🔥 Start earning today!\n\n"
    "👉 Register Now:\n"
    "https://1gotask.com/login?mode=register&i=VNAXmPk8"
)

JOIN_REQUEST_TASK_HINT_TEXT = "✅ Task karne ke liye niche 📩 SMS Task pe click karein 👇"

# Group ki working hours — inke bahar join requests approve nahi hongi, queue mein rukengi
WORK_HOURS_WINDOWS = [
    (dtime(10, 30), dtime(15, 30)),
    (dtime(17, 0), dtime(21, 30)),
]
PENDING_JOIN_REQUESTS_FILE = "pending_join_requests.json"


def is_within_work_hours():
    now_t = now_ist().time()
    return any(start <= now_t <= end for start, end in WORK_HOURS_WINDOWS)


def load_pending_join_requests():
    if os.path.exists(PENDING_JOIN_REQUESTS_FILE):
        with open(PENDING_JOIN_REQUESTS_FILE, "r") as f:
            return json.load(f)
    return []


def save_pending_join_requests(items):
    with open(PENDING_JOIN_REQUESTS_FILE, "w") as f:
        json.dump(items, f)


async def approve_and_welcome(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user):
    """User ko DM (welcome + task menu) bhejta hai, GROUP mein bhi (mention ke saath)
    welcome bolta hai, aur join request approve karta hai."""
    user_id = user.id

    # Bot ko use karne wale/known users mein add karo (broadcast ke liye)
    await save_user(user_id)

    try:
        await context.bot.send_message(chat_id=user_id, text=JOIN_REQUEST_WELCOME_TEXT)
        await context.bot.send_message(
            chat_id=user_id,
            text=JOIN_REQUEST_TASK_HINT_TEXT,
            reply_markup=MAIN_MENU_MARKUP,
        )
    except Exception as e:
        logger.error(f"Join request DM bhejne mein error (user ne bot block kiya ho sakta hai): {e}")

    try:
        await context.bot.approve_chat_join_request(chat_id=chat_id, user_id=user_id)
    except Exception as e:
        logger.error(f"Join request approve karne mein error: {e}")
        return  # approve fail hua to group welcome ka koi matlab nahi

    # Group mein bhi welcome bolo (username/naam ke saath)
    try:
        group_text = build_welcome_text(user, chat_id)
        sent = await context.bot.send_message(chat_id=chat_id, text=group_text, parse_mode="HTML")
        await track_new_welcome_message(context, chat_id, sent.message_id)
    except Exception as e:
        logger.error(f"Group welcome bhejne mein error: {e}")


async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Jab group mein 'Approve New Members' setting ON ho, to koi bhi join request bhejta hai
    to yeh handler chalta hai. Agar abhi group ki working hours chal rahi hain, to turant
    approve + DM kar deta hai. Agar working hours ke bahar hai, to request ko queue mein
    daal deta hai — jaise hi working hours shuru hongi, retry_pending_join_requests job
    use automatically approve + DM kar dega."""
    request = update.chat_join_request
    user = request.from_user
    chat_id = request.chat.id

    if not is_within_work_hours():
        items = load_pending_join_requests()
        items.append({
            "chat_id": chat_id,
            "user_id": user.id,
            "username": user.username,
            "first_name": user.first_name,
        })
        save_pending_join_requests(items)
        return

    await approve_and_welcome(context, chat_id, user)


async def retry_pending_join_requests(context: ContextTypes.DEFAULT_TYPE):
    """Har 5 minute mein check karta hai — agar ab working hours chal rahi hain, to
    queue mein pade saare join requests approve + DM kar deta hai."""
    items = load_pending_join_requests()
    if not items:
        return
    if not is_within_work_hours():
        return


    for item in items:
        fake_user = types.SimpleNamespace(
            id=item["user_id"],
            username=item.get("username"),
            first_name=item.get("first_name") or "Dost",
        )
        await approve_and_welcome(context, item["chat_id"], fake_user)

    save_pending_join_requests([])



async def retry_pending_welcomes(context: ContextTypes.DEFAULT_TYPE):
    """Har 5 minute mein queue mein pade welcomes ko dobara bhejne ki koshish karta hai —
    jaise hi group khulta hai (Send Messages permission wapas milti hai), ye chal jata hai"""
    items = load_pending_welcomes()
    if not items:
        return

    remaining = []
    for item in items:
        try:
            sent = await context.bot.send_message(chat_id=item["chat_id"], text=item["text"], parse_mode="HTML")
            await track_new_welcome_message(context, item["chat_id"], sent.message_id)
        except Exception as e:
            logger.error(f"Pending welcome abhi bhi fail ho raha hai: {e}")
            remaining.append(item)  # abhi bhi fail hua, list mein rakho

    save_pending_welcomes(remaining)




async def track_group_silently(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Group ko track karta hai (leaveallgroups ke liye) — koi reply nahi bhejta, sirf background mein save karta hai.
    In-memory cache use karta hai taaki har single message pe disk read/write na ho (jo active
    groups mein bot ko slow kar deta tha) — file sirf tab likhi jaati hai jab group NAYA ho."""
    chat = update.effective_chat
    if chat.id not in _known_groups_cache:
        save_known_group(chat.id, chat.title or "")
        _known_groups_cache.add(chat.id)


# ---- Group tracking (bot kaunse groups mein hai) ----
KNOWN_GROUPS_FILE = "known_groups.json"
_known_groups_cache = set()  # RAM mein cache — disk I/O sirf naye group pe hoti hai


def load_known_groups():
    if os.path.exists(KNOWN_GROUPS_FILE):
        with open(KNOWN_GROUPS_FILE, "r") as f:
            return json.load(f)
    return {}


def save_known_group(chat_id: int, title: str):
    groups = load_known_groups()
    groups[str(chat_id)] = title
    with open(KNOWN_GROUPS_FILE, "w") as f:
        json.dump(groups, f)


async def mygroups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: bot kaunse groups mein hai, uski list dikhata hai (bina kisi ko leave kiye)"""
    if update.effective_user.id != ADMIN_ID:
        return

    groups = load_known_groups()
    if not groups:
        await update.message.reply_text("📭 Koi tracked group nahi mila.")
        return

    lines = [f"📋 Bot {len(groups)} group(s) mein hai:\n"]
    for chat_id_str, title in groups.items():
        lines.append(f"• {title or '(no name)'} — ID: {chat_id_str}")

    await update.message.reply_text("\n".join(lines))


async def leaveallgroups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: bot ko saare tracked groups se nikal deta hai"""
    if update.effective_user.id != ADMIN_ID:
        return

    groups = load_known_groups()
    if not groups:
        await update.message.reply_text("📭 Koi tracked group nahi mila.")
        return

    left = 0
    failed = 0
    for chat_id_str, title in groups.items():
        try:
            await context.bot.leave_chat(int(chat_id_str))
            left += 1
        except Exception as e:
            logger.error(f"Group {chat_id_str} leave karne mein error: {e}")
            failed += 1

    # Sab list se clear kar do
    with open(KNOWN_GROUPS_FILE, "w") as f:
        json.dump({}, f)

    await update.message.reply_text(
        f"✅ {left} group(s) se nikal gaya.\n⚠️ {failed} group(s) mein error aayi."
    )



# ---- User tracking (kitne unique users ne bot use kiya) ----
USERS_FILE = "bot_users.json"
_users_lock = asyncio.Lock()  # taaki bahut saare users ek saath aane par file corrupt/overwrite na ho


def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return set(json.load(f))
    return set()


async def save_user(user_id: int):
    """Async + lock-protected — jab bahut saare users ek saath /start karte hain (ya join
    requests aati hain), tab bhi koi entry lost nahi hoti (race condition fix)."""
    async with _users_lock:
        users = load_users()
        if user_id not in users:
            users.add(user_id)
            with open(USERS_FILE, "w") as f:
                json.dump(list(users), f)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Jab user /start command bhejta hai"""
    await save_user(update.effective_user.id)
    await update.message.reply_text(
        "🌟 Hey! Welcome to 1Gotask\n\n"
        "Want to earn ₹200–₹300 daily without any investment? 💰\n\n"
        "📲 Get started:\n"
        "✅ Create your account\n"
        "✅ Complete SMS & WhatsApp tasks\n"
        "💸 Earn ₹13 per 100 SMS\n"
        "🚀 Stay active for more earning opportunities\n\n"
        "⚠️ Note: Registration alone doesn't earn money. You must complete tasks.\n\n"
        "🔗 Register Now:\n"
        "https://1gotask.com/login?mode=register&i=VNAXmPk8\n\n"
        "📢 Join the Official Group:\n"
        "https://t.me/onegotaskcommunicationgroup\n\n"
        "✨ Register & start completing tasks today!",
        reply_markup=MAIN_MENU_MARKUP,
    )


async def userscount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: total kitne unique users ne bot start kiya hai"""
    if update.effective_user.id != ADMIN_ID:
        return
    users = load_users()
    await update.message.reply_text(f"👥 Total users jinhone bot use kiya: {len(users)}")


async def do_broadcast(context: ContextTypes.DEFAULT_TYPE, reply_target, text: str = "", photo_id: str = None, video_id: str = None):
    """Saare tracked users ko diya gaya text/photo/video bhejta hai — status message reply_target
    (jo bhi message object) ke through wapas bhejta hai."""
    users = load_users()
    if not users:
        await reply_target.reply_text("⚠️ Abhi koi users nahi hain broadcast karne ke liye.")
        return

    await reply_target.reply_text(f"🚀 Broadcast shuru ho raha hai... ({len(users)} users)")

    sent = 0
    failed = 0
    for user_id in users:
        try:
            if video_id:
                await context.bot.send_video(chat_id=user_id, video=video_id, caption=text)
            elif photo_id:
                await context.bot.send_photo(chat_id=user_id, photo=photo_id, caption=text)
            else:
                await context.bot.send_message(chat_id=user_id, text=text)
            sent += 1
        except Exception as e:
            logger.error(f"Broadcast fail user {user_id}: {e}")
            failed += 1

    await reply_target.reply_text(
        f"✅ Broadcast complete!\nSuccessfully bheja: {sent}\nFail hua: {failed}"
    )


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin isse 2 tarah se use kar sakta hai:
    1) Ek-shot: '/broadcast <message>' (ya photo/video ke caption mein '/broadcast <caption>')
       — turant sabko chala jayega.
    2) Sirf '/broadcast' bhej ke — bot agla message (text/photo/video) maangega, jo bhejega
       wo broadcast ho jayega."""
    if update.effective_user.id != ADMIN_ID:
        return

    msg = update.message

    # Photo/video ke saath caption mein "/broadcast <text>" bheja gaya ho
    if msg.photo:
        text = " ".join(context.args) if context.args else ""
        await do_broadcast(context, msg, text=text, photo_id=msg.photo[-1].file_id)
        return
    if msg.video:
        text = " ".join(context.args) if context.args else ""
        await do_broadcast(context, msg, text=text, video_id=msg.video.file_id)
        return

    # Sirf text ke saath "/broadcast <message>" bheja gaya ho — turant bhej do
    if context.args:
        text = " ".join(context.args)
        await do_broadcast(context, msg, text=text)
        return

    # Kuch bhi args/media nahi diya — two-step flow shuru karo
    context.user_data["awaiting_broadcast"] = True
    await update.message.reply_text(
        "📢 Ab jo bhi bhejenge (text, photo, ya video — caption ke saath), "
        "wo sabhi users ko broadcast ho jayega."
    )


async def receive_broadcast_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Jab admin awaiting_broadcast state mein kuch bhejta hai (text/photo/video), sabko bhej deta hai"""
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.user_data.get("awaiting_broadcast"):
        return

    context.user_data["awaiting_broadcast"] = False
    msg = update.message

    if msg.video:
        await do_broadcast(context, msg, text=msg.caption or "", video_id=msg.video.file_id)
    elif msg.photo:
        await do_broadcast(context, msg, text=msg.caption or "", photo_id=msg.photo[-1].file_id)
    else:
        await do_broadcast(context, msg, text=msg.text or "")




async def getemojipack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /getemojipack <pack_shortname>
    Emoji pack ke saare emojis aur unke custom_emoji_id ki list deta hai."""
    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: /getemojipack <pack_shortname>\n\n"
            "Example: /getemojipack sti_eebea_by_TgEmojis_bot\n"
            "(Ye naam aapke diye link ke aakhri part se milta hai: "
            "t.me/addemoji/<yahi_naam>)"
        )
        return

    pack_name = context.args[0]
    try:
        sticker_set = await context.bot.get_sticker_set(pack_name)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Pack fetch nahi hua: {e}")
        return

    lines = [f"📦 Pack: {sticker_set.name} ({len(sticker_set.stickers)} emojis)\n"]
    for sticker in sticker_set.stickers:
        emoji_id = sticker.custom_emoji_id
        lines.append(f"{sticker.emoji}  →  {emoji_id}")

    # Telegram message length limit ke hisaab se chunks mein bhejo
    text = "\n".join(lines)
    for i in range(0, len(text), 3500):
        await update.message.reply_text(text[i:i + 3500])


ANNOUNCE_GROUP_FILE = "announce_group_id.txt"


async def groupid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Is command ko group mein bhejein — group ki chat ID save ho jayegi.
    Sirf admin ki request par kaam karega."""
    if update.effective_user.id != ADMIN_ID:
        return
    chat_id = update.effective_chat.id
    with open(ANNOUNCE_GROUP_FILE, "w") as f:
        f.write(str(chat_id))
    await update.message.reply_text(
        f"✅ Is group ki ID save ho gayi: {chat_id}\n"
        f"Ab yahan /announce se message bhej sakte hain."
    )


async def announce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin isse bhejega (kahin se bhi, DM se bhi) — message announcement
    group mein 'Start Bot' button ke saath chala jayega."""
    if update.effective_user.id != ADMIN_ID:
        return

    if not os.path.exists(ANNOUNCE_GROUP_FILE):
        await update.message.reply_text(
            "⚠️ Pehle announcement group set karein: us group mein /groupid bhejein."
        )
        return

    if not context.args:
        await update.message.reply_text("Usage: /announce <message>")
        return

    with open(ANNOUNCE_GROUP_FILE, "r") as f:
        group_id = int(f.read().strip())

    message_text = " ".join(context.args)
    button = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Start Bot", url=f"https://t.me/{BOT_USERNAME}?start=announce")]
    ])

    try:
        await context.bot.send_message(chat_id=group_id, text=message_text, reply_markup=button)
        await update.message.reply_text("✅ Announcement group mein bhej diya gaya!")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Bhejne mein error: {e}")


async def announcephoto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin isse bhejega (photo ke saath, caption mein command) — turant photo announcement
    group mein chala jayega, koi time-window restriction nahi. Photo ke caption mein
    '/announcephoto <message>' likhna hoga."""
    if update.effective_user.id != ADMIN_ID:
        return

    if not os.path.exists(ANNOUNCE_GROUP_FILE):
        await update.message.reply_text(
            "⚠️ Pehle announcement group set karein: us group mein /groupid bhejein."
        )
        return

    if not update.message.photo:
        await update.message.reply_text(
            "⚠️ Photo ke saath bhejein. Photo attach karke caption mein likhein:\n"
            "/announcephoto Aapka message yahan"
        )
        return

    with open(ANNOUNCE_GROUP_FILE, "r") as f:
        group_id = int(f.read().strip())

    caption_text = " ".join(context.args) if context.args else ""
    photo_file_id = update.message.photo[-1].file_id

    button = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Start Bot", url=f"https://t.me/{BOT_USERNAME}?start=announce")]
    ])

    try:
        await context.bot.send_photo(
            chat_id=group_id,
            photo=photo_file_id,
            caption=caption_text,
            reply_markup=button,
        )
        await update.message.reply_text("✅ Photo announcement group mein bhej diya gaya!")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Bhejne mein error: {e}")


# ---- Auto-Announcement System ----
ANNOUNCEMENTS_FILE = "announcements.json"
ANNOUNCE_INDEX_FILE = "announcement_index.txt"

# Time windows jinke andar announcements bheji jayengi (24-hour format)
ANNOUNCE_WINDOWS = [
    (dtime(10, 40), dtime(15, 20)),
    (dtime(17, 10), dtime(21, 20)),
]
ANNOUNCE_INTERVAL_SECONDS = 11 * 60  # 11 minute
ANNOUNCE_ALIGN_MINUTES = 10  # clock-aligned marks: :00, :10, :20, :30, :40, :50


def seconds_until_next_quarter_hour():
    """Agla clock-aligned mark (har ANNOUNCE_ALIGN_MINUTES minute pe) kitni second door hai,
    wo calculate karta hai — isse announcement hamesha clock-aligned time pe hi jayega,
    bot chahe kabhi bhi restart ho."""
    now = now_ist()
    step = ANNOUNCE_ALIGN_MINUTES
    minute_block = math.ceil((now.minute + now.second / 60) / step) * step
    if minute_block >= 60:
        next_mark = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:
        next_mark = now.replace(minute=minute_block, second=0, microsecond=0)
    return (next_mark - now).total_seconds()


def load_announcements():
    if os.path.exists(ANNOUNCEMENTS_FILE):
        with open(ANNOUNCEMENTS_FILE, "r") as f:
            return json.load(f)
    return []


def save_announcements(items):
    with open(ANNOUNCEMENTS_FILE, "w") as f:
        json.dump(items, f)


def load_announce_index():
    if os.path.exists(ANNOUNCE_INDEX_FILE):
        with open(ANNOUNCE_INDEX_FILE, "r") as f:
            return int(f.read().strip() or 0)
    return 0


def save_announce_index(i):
    with open(ANNOUNCE_INDEX_FILE, "w") as f:
        f.write(str(i))


async def addannouncement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin isse bhejega, uske baad agli photo (caption ke saath) announcement list mein add ho jayegi"""
    if update.effective_user.id != ADMIN_ID:
        return
    context.user_data["awaiting_announcement_photo"] = True
    await update.message.reply_text(
        "📸 Ab ek photo bhejein (caption ke saath) — wo announcement list mein add ho jayegi.\n"
        "Jitni chahen utni photos ek-ek karke bhej sakte hain."
    )


async def receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Jab admin awaiting_announcement_photo state mein photo bhejta hai, use list mein save karta hai.
    Agar broadcast ka wait ho raha hai, to usी ko handle karta hai."""
    if update.effective_user.id != ADMIN_ID:
        return

    if context.user_data.get("awaiting_broadcast"):
        await receive_broadcast_content(update, context)
        return

    if not context.user_data.get("awaiting_announcement_photo"):
        return  # is state mein nahi hai, ignore karo

    photo_file_id = update.message.photo[-1].file_id  # sabse badi size wali
    caption = update.message.caption or ""

    items = load_announcements()
    items.append({"photo": photo_file_id, "caption": caption})
    save_announcements(items)

    await update.message.reply_text(
        f"✅ Announcement add ho gaya! Total announcements: {len(items)}\n\n"
        f"Aur add karni hai to photo bhejte rahein, ya /stopadding likhein."
    )


async def stopadding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    context.user_data["awaiting_announcement_photo"] = False
    await update.message.reply_text("✅ Photo add karna band kar diya.")


async def listannouncements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    items = load_announcements()
    if not items:
        await update.message.reply_text("📭 Abhi koi announcement saved nahi hai.")
        return
    lines = [f"📋 Total announcements: {len(items)}\n"]
    for i, item in enumerate(items, 1):
        preview = item["caption"][:40] + ("..." if len(item["caption"]) > 40 else "")
        lines.append(f"{i}. {preview or '(no caption)'}")
    await update.message.reply_text("\n".join(lines))


async def clearannouncements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    save_announcements([])
    save_announce_index(0)
    await update.message.reply_text("🗑️ Saari announcements clear kar di gayi.")


async def removeannouncement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ek specific announcement delete karta hai number se — /listannouncements mein
    jo number dikhta hai, wahi yahan use karein. Jaise: /removeannouncement 4"""
    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            "⚠️ Number bhejein jo delete karna hai. Jaise: /removeannouncement 4\n"
            "Pehle /listannouncements se number check kar lein."
        )
        return

    num = int(context.args[0])
    items = load_announcements()

    if num < 1 or num > len(items):
        await update.message.reply_text(f"⚠️ Invalid number. Total announcements: {len(items)}")
        return

    removed = items.pop(num - 1)  # list 0-indexed hai, user 1-indexed number deta hai
    save_announcements(items)

    # Index ko bhi adjust karo taaki cycle sahi se chalta rahe
    idx = load_announce_index()
    if idx >= len(items) and len(items) > 0:
        save_announce_index(0)
    elif len(items) == 0:
        save_announce_index(0)

    preview = removed["caption"][:40] + ("..." if len(removed["caption"]) > 40 else "")
    await update.message.reply_text(f"🗑️ Announcement #{num} delete ho gaya: {preview or '(no caption)'}")


async def send_scheduled_announcement(context: ContextTypes.DEFAULT_TYPE):
    """Har 15 minute mein chalta hai — sirf set time-windows ke andar announcement bhejta hai"""
    now = now_ist().time()
    in_window = any(start <= now <= end for start, end in ANNOUNCE_WINDOWS)
    if not in_window:
        return

    if not os.path.exists(ANNOUNCE_GROUP_FILE):
        return

    items = load_announcements()
    if not items:
        return

    with open(ANNOUNCE_GROUP_FILE, "r") as f:
        group_id = int(f.read().strip())

    idx = load_announce_index() % len(items)
    item = items[idx]

    try:
        await context.bot.send_photo(
            chat_id=group_id,
            photo=item["photo"],
            caption=item["caption"],
        )
    except Exception as e:
        logger.error(f"Announcement bhejne mein error: {e}")

    save_announce_index(idx + 1)


# ---- 30-minute Welcome Reminder (poore din, koi time-window restriction nahi) ----
WELCOME_REMINDER_TEXT = (
    "Welcome everyone! Start using the bot provided to you and begin earning daily. "
    "You can earn around 200–300 every day"
)
WELCOME_REMINDER_INTERVAL_SECONDS = 30 * 60  # 30 minute


async def send_welcome_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Har 30 minute mein group ko ye reminder bhejta hai, sirf set time-windows ke andar"""
    now = now_ist().time()
    in_window = any(start <= now <= end for start, end in ANNOUNCE_WINDOWS)
    if not in_window:
        return

    if not os.path.exists(ANNOUNCE_GROUP_FILE):
        return

    with open(ANNOUNCE_GROUP_FILE, "r") as f:
        group_id = int(f.read().strip())

    button = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Start Bot", url=f"https://t.me/{BOT_USERNAME}?start=announce")]
    ])

    try:
        await context.bot.send_message(
            chat_id=group_id,
            text=WELCOME_REMINDER_TEXT,
            reply_markup=button,
        )
    except Exception as e:
        logger.error(f"Welcome reminder bhejne mein error: {e}")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Jab user /help command bhejta hai"""
    await update.message.reply_text(
        "📋 Available commands:\n"
        "/start - Bot ko start karo (menu dikhega)\n"
        "/help - Ye help message dekho\n\n"
        "Ya neeche diye buttons use karo.",
        reply_markup=MAIN_MENU_MARKUP,
    )


# ---- Menu button handlers ----

async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User ki Telegram ID batata hai"""
    user = update.effective_user
    await update.message.reply_text(f"🆔 Aapki Telegram User ID: {user.id}")


async def setsmsvideo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin isse bhejega, uske baad agli video SMS Task ke liye set hogi"""
    if update.effective_user.id != ADMIN_ID:
        return
    context.user_data["awaiting_video"] = "sms"
    await update.message.reply_text("📩 Ab agli jo video bhejenge, wo SMS Task ke liye set ho jayegi.")


async def setwhatsappvideo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin isse bhejega, uske baad agli video WhatsApp Task ke liye set hogi"""
    if update.effective_user.id != ADMIN_ID:
        return
    context.user_data["awaiting_video"] = "whatsapp"
    await update.message.reply_text("💬 Ab agli jo video bhejenge, wo WhatsApp Task ke liye set ho jayegi.")


async def receive_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Jab admin bot ko video bhejta hai, uska file_id save karta hai (ya broadcast karta hai)"""
    user = update.effective_user
    if user.id != ADMIN_ID:
        return  # sirf admin ki video accept karo

    # Agar broadcast ka wait ho raha hai, to usी ko handle karo
    if context.user_data.get("awaiting_broadcast"):
        await receive_broadcast_content(update, context)
        return

    target = context.user_data.get("awaiting_video")
    file_id = update.message.video.file_id

    if target == "sms":
        save_video_id(SMS_VIDEO_ID_FILE, file_id)
        await update.message.reply_text("✅ SMS Task video set ho gayi!")
    elif target == "whatsapp":
        save_video_id(WHATSAPP_VIDEO_ID_FILE, file_id)
        await update.message.reply_text("✅ WhatsApp Task video set ho gayi!")
    else:
        await update.message.reply_text(
            "⚠️ Pehle batayein ye video kiske liye hai:\n"
            "/setsmsvideo — SMS Task ke liye\n"
            "/setwhatsappvideo — WhatsApp Task ke liye\n"
            "/broadcast — Sabhi users ko bhejne ke liye\n\n"
            "Command bhejne ke baad ye video dobara bhej dein."
        )
        return

    context.user_data["awaiting_video"] = None


EARNING_INFO_TEXT = (
    "😀Without Investment Earning Opportunities\n"
    "⏰ Just 2–4 hours of simple work\n"
    "💵 Earn up to ₹200–₹300\n"
    "Link 🔗 https://1gotask.com/login?mode=register&i=VNAXmPk8"
)


async def earning_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Group mein koi 'kaise earn kare', 'how to start', 'link' jaisa message bheje to
    yeh earning info + registration link reply karta hai."""
    await update.message.reply_text(EARNING_INFO_TEXT)


async def sms_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caption = (
        "📩 SMS Task\n\n"
        "✅ The complete SMS task is explained in the video. "
        "Please watch it carefully before getting started.\n\n"
        "Steps:\n"
        "1️⃣ Download and install the SMS App\n"
        "2️⃣ Copy the invitation code and paste/bind it in the app\n"
        "3️⃣ Click \"I understand\" and wait for a while"
    )
    video_id = get_video_id(SMS_VIDEO_ID_FILE)
    if video_id:
        await update.message.reply_video(video=video_id, caption=caption)
    else:
        await update.message.reply_text(
            caption + "\n\n⚠️ (Abhi tak koi video set nahi hui hai)"
        )


async def whatsapp_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caption = (
        "💬 WhatsApp Task\n\n"
        "✅ The complete WhatsApp task is explained in the video. "
        "Please watch it carefully before getting started.\n\n"
        "Steps:\n"
        "1️⃣ Download and install the WhatsApp App/tool\n"
        "2️⃣ Copy the invitation code and bind it\n"
        "3️⃣ Log in to WhatsApp and confirm — after that a message will be sent, "
        "wait until the timer ends"
    )
    video_id = get_video_id(WHATSAPP_VIDEO_ID_FILE)
    if video_id:
        await update.message.reply_video(video=video_id, caption=caption)
    else:
        await update.message.reply_text(
            caption + "\n\n⚠️ (Abhi tak koi video set nahi hui hai)"
        )


REFERRAL_LINK = "https://1gotask.com/login?mode=register&i=VNAXmPk8"

REFERRAL_PROMO_TEXT = (
    "☄ Invite Friends to 1GO.TASK and Earn Rewards!\n\n"
    "Invite your friends to 1GO.TASK, have them register using your referral link, "
    "and earn commissions + rewards when they complete tasks. 💝💰\n\n"
    "🩶 REWARD STRUCTURE\n\n"
    "✅ 1st Level Direct Commission – 10%\n"
    "Earn 10% commission on the task earnings of your directly invited users.\n\n"
    "✅ 2nd Level Commission – 10%\n"
    "Earn 10% commission on the task earnings of users invited by your first-level members.\n\n"
    "🎁 TREASURE CHEST REWARDS\n"
    "500 | 600 | 1,000 | 1,500 | 2,000 | 3,000 | 5,000 | 10,000 Points\n\n"
    "📲 HOW TO INVITE?\n\n"
    "1️⃣ Copy your referral link\n"
    "2️⃣ Share it with your friends\n"
    "3️⃣ Help them register and complete tasks\n"
    "4️⃣ Earn Rewards & Commission! 💰\n\n"
    "🔥 MORE INVITES = MORE REWARDS = MORE EARNINGS!\n\n"
    "👉 Join 1GO.TASK today and start your earning journey!\n\n"
    f"🔗 Your Referral Link:\n{REFERRAL_LINK}"
)


async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(REFERRAL_PROMO_TEXT)


async def help_center(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🆘 1Go.Task Support Center 💬\n\n"
        "Facing any problem or need help? Contact our official admin. 🤝\n\n"
        "📩 Support: @G_one_77\n\n"
        "🛠️ Account • Tasks • Rewards • Withdrawals\n\n"
        "⚡ Any issue? Just contact us — we're here to help! ❤️"
    )


async def channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📢 Official Group Link 🔗\n"
        "https://t.me/onegotaskcommunicationgroup\n\n"
        "📢 Official Channel Link 🔗\n"
        "https://t.me/onegotask"
    )


async def customer_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅Official Customer Service Contacts\n\n"
        "Username @banana04270327\n\n"
        "Thank u 🙏🏻"
    )


async def report_problem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["awaiting_problem_report"] = True
    await update.message.reply_text(
        "📝 Apni problem yahan likh kar bhej dein — hum jaldi hi contact karenge."
    )


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Baaki normal text messages ka reply deta hai"""
    if update.effective_user.id == ADMIN_ID and context.user_data.get("awaiting_broadcast"):
        await receive_broadcast_content(update, context)
        return

    if context.user_data.get("awaiting_problem_report"):
        user = update.effective_user
        username = f"@{user.username}" if user.username else "(no username)"
        problem_text = update.message.text

        # Admin ko forward karo
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"📩 Naya Problem Report\n\n"
                    f"👤 User: {user.first_name} {username}\n"
                    f"🆔 ID: {user.id}\n\n"
                    f"💬 Problem:\n{problem_text}"
                ),
            )
        except Exception as e:
            logger.error(f"Problem report admin ko bhejne mein error: {e}")

        context.user_data["awaiting_problem_report"] = False
        await update.message.reply_text(
            "✅ Aapki problem admin ko bhej di gayi hai. Jaldi hi contact kiya jayega."
        )
        return

    await update.message.reply_text(
        "⚠️ Please neeche diye menu/tools se koi option choose karein.",
        reply_markup=MAIN_MENU_MARKUP,
    )


async def setup_commands(application):
    """Bot start hote hi ye commands list set kar deta hai — isse chat mein
    'tools' menu icon (4 boxes) show hone lagta hai"""
    await application.bot.set_my_commands([
        ("start", "Bot shuru karein"),
        ("help", "Help dekhein"),
    ])


def main():
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("⚠️  Pehle BOT_TOKEN daalo file mein (BotFather se lo)!")
        return

    # Known groups cache ko file se pre-load karo (restart ke baad bhi turant pata ho)
    for gid in load_known_groups().keys():
        _known_groups_cache.add(int(gid))

    app = ApplicationBuilder().token(BOT_TOKEN).post_init(setup_commands).build()

    # Handlers register karo
    app.add_handler(CommandHandler("start", start, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("help", help_command, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("myid", myid, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("userscount", userscount, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("mygroups", mygroups, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("leaveallgroups", leaveallgroups, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("broadcast", broadcast, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("setsmsvideo", setsmsvideo, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("setwhatsappvideo", setwhatsappvideo, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("getemojipack", getemojipack, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("groupid", groupid))
    app.add_handler(CommandHandler("announce", announce, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("announcephoto", announcephoto, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("addannouncement", addannouncement, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("stopadding", stopadding, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("listannouncements", listannouncements, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("clearannouncements", clearannouncements, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("removeannouncement", removeannouncement, filters=filters.ChatType.PRIVATE))

    # Admin photo bhejega (announcement ke liye) to yahan capture hoga
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.PHOTO, receive_photo))

    # Har 11 minute mein ek announcement (one by one, rotation mein) bhejo — time windows ke andar
    app.job_queue.run_repeating(
        send_scheduled_announcement,
        interval=ANNOUNCE_INTERVAL_SECONDS,
        first=30,  # bot start hone ke 30 sec baad pehla check, phir har 11 min
    )

    # "Welcome everyone!" wala 30-min reminder band kar diya gaya (user ki request par)
    # app.job_queue.run_repeating(send_welcome_reminder, interval=WELCOME_REMINDER_INTERVAL_SECONDS, first=20)

    # Welcome feature poori tarah band — pending-welcome retry job bhi zaroori nahi
    # app.job_queue.run_repeating(retry_pending_welcomes, interval=5 * 60, first=30)

    # Admin video bhejega to file_id yahan capture hoga
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.VIDEO, receive_video))

    # Jab koi group mein 'join request' bheje (agar group mein "Approve New Members" ON hai),
    # bot use turant private DM karega aur approve kar dega
    app.add_handler(ChatJoinRequestHandler(handle_join_request))

    # Har 5 minute mein check karo — working hours shuru ho gayi hon to pending
    # join requests ko approve + DM kar do
    app.job_queue.run_repeating(retry_pending_join_requests, interval=5 * 60, first=15)

    # Welcome message feature band kar diya gaya (user ki request par)
    # app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    # app.add_handler(CommandHandler("setwelcome", setwelcome, filters=filters.ChatType.GROUPS | filters.ChatType.SUPERGROUP))

    # DEBUG: group ke saare messages log karo (testing ke liye, group=1 taaki dono chalein)
    # Groups ko silently track karo (koi reply nahi, sirf list ke liye) — /leaveallgroups ke liye
    app.add_handler(MessageHandler(filters.ChatType.GROUPS | filters.ChatType.SUPERGROUP, track_group_silently), group=1)

    # Menu button handlers (exact text match, command ke pehle register karo)
    # Sirf private chat mein kaam karenge — group mein nahi dikhenge
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.Regex("^📩 SMS Task$"), sms_task))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.Regex("^💬 WhatsApp Task$"), whatsapp_task))

    # Group mein 'task' / 'sms task' / 'whatsapp task' / 'ws task' bolne par video NAHI jayega (band kiya gaya)

    # Group mein "kaise earn kare", "how to start", "link" jaisa message aaye to
    # earning info + registration link bhejo (exact match, beech mein kahin word aane se nahi)
    app.add_handler(MessageHandler(
        (filters.ChatType.GROUPS | filters.ChatType.SUPERGROUP)
        & filters.Regex(
            r"(?i)^\s*("
            r"kaise\s*earn\s*kare|kese\s*earn\s*kare|earn\s*kaise\s*kare|"
            r"how\s*to\s*earn|how\s*to\s*start|link"
            r")\s*[?.!]*\s*$"
        ),
        earning_info
    ))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.Regex("^🎁 Referral$"), referral))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.Regex("^🆘 Help Center$"), help_center))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.Regex("^📢 Channel$"), channel))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.Regex("^🎧 Customer Service$"), customer_service))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.Regex("^📝 Report Problem$"), report_problem))

    # Baaki sab text ke liye generic echo (sabse aakhir mein) — sirf private chat mein
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, echo))

    print("🤖 Bot start ho raha hai... (Ctrl+C se rokein)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    import sys
    try:
        main()
    except KeyboardInterrupt:
        pass  # Ctrl+C se normal band hua
    except Exception as e:
        print(f"⚠️ Bot crash ho gaya: {e}")
        print("🔄 Bot process dobara (fresh) start ho raha hai...")
        import time
        time.sleep(5)
        # Poora process restart karo (fresh event loop ke saath) — isse
        # "Event loop is closed" jaisi errors nahi aati
        os.execv(sys.executable, [sys.executable] + sys.argv)
