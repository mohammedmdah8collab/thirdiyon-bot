import asyncio
import html
import logging
import os
import re
import sqlite3
import time
from datetime import datetime

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputMediaDocument,
    InputMediaPhoto,
    InputTextMessageContent,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, RetryAfter, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    InlineQueryHandler,
    MessageHandler,
    filters,
)

# ============================================================
# الإعدادات
# ============================================================
# متغيرات البيئة:
#   BOT_TOKEN        توكن البوت (إلزامي)
#   THIRD_CHANNEL    قناة ثالثيون، مثل @name أو رقمها -100... (إلزامي للاشتراك الإجباري)
#   FOURTH_CHANNEL   قناة رابعيون (اختياري، الافتراضي @Kii_8i)
#   THIRD_CHANNEL_LINK / FOURTH_CHANNEL_LINK  رابط الدعوة إن كانت القناة خاصة (اختياري)
#   DB_FILE          اسم ملف القاعدة (اختياري، الافتراضي thirdiyon_bot.db)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()  # ضعه في متغيرات البيئة في الاستضافة
OWNER_ID = 7683201905
DB_FILE = os.getenv("DB_FILE", "thirdiyon_bot.db").strip() or "thirdiyon_bot.db"
THIRD_CHANNEL = os.getenv("THIRD_CHANNEL", "").strip()
FOURTH_CHANNEL = os.getenv("FOURTH_CHANNEL", "@Kii_8i").strip()
THIRD_CHANNEL_LINK = os.getenv("THIRD_CHANNEL_LINK", "").strip()
FOURTH_CHANNEL_LINK = os.getenv("FOURTH_CHANNEL_LINK", "").strip()
DEFAULT_FOOTER = (
    (f"#ثالثيون : {THIRD_CHANNEL}" if THIRD_CHANNEL.startswith("@") else "#ثالثيون")
    + "\n\n🕊️ شارك فربما تكون سبباً في تغيير مستقبل ."
)

SUB_CACHE_SECONDS = 300
MEDIA_GROUP_MAX = 10
BROADCAST_BATCH = 25          # عدد الرسائل بالثانية الواحدة أثناء الإعلان
TEXT_LIMIT = 4096
CAPTION_LIMIT = 1024
PAGE_SIZE = 30                # أقصى عدد أزرار بالصفحة الواحدة (حد تلغرام 100)
SEARCH_LIMIT = 20
TOP_LIMIT = 10

HOME_TEXT = (
    "هلا بيك ببوت ثالثيون 🎓\n"
    "اختر من الأزرار بالأسفل.\n\n"
    "🔎 للبحث عن ملف أرسل اسمه.\n"
    "🔥 الملفات الأكثر تحميلاً: /top"
)
GATE_TEXT = "حتى تستخدم البوت، اشترك بقناتي ثالثيون ورابعيون أولاً، ثم اضغط التحقق من الاشتراك."
GATE_ERR_TEXT = "تعذر التحقق من اشتراكك حالياً، حاول بعد قليل. تم إبلاغ المالك."
MAINT_TEXT = "البوت تحت الصيانة، سيتم اضافة مميزات جديدة."
BACK = "🔙 رجوع"
CANCEL = "❌ إلغاء"
CONFIRM = "✅ تأكيد"
SKIP = "⏭ تخطي"
DONE = "✅ تم"
PAUSE_ON = "⏸ إيقاف البوت مؤقتاً"
PAUSE_OFF = "▶️ تشغيل البوت"
SUB_LABEL = "🔒 الاشتراك الإجباري"
COLORS = {"🟢 أخضر": "success", "🔵 أزرق": "primary", "🔴 أحمر": "danger"}
COLOR_ROW = [("🟢 أخضر", "success"), ("🔵 أزرق", "primary"), ("🔴 أحمر", "danger")]
MEMBER_OK = ("member", "administrator", "creator")
FILE_STYLES = ("primary", "success", "primary")   # تنويع ألوان أزرار الملفات (الأزرق يغلب)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("bot")

# ============================================================
# البيانات الثابتة
# ============================================================

# الاسم، الإيموجي، اللون، النوع
SUBJECTS = [
    ("التربية الإسلامية", "🕌", "primary", "unit"),
    ("اللغة العربية", "📚", "success", "unit"),
    ("اللغة الإنكليزية", "🇬🇧", "danger", "unit"),
    ("الرياضيات", "📐", "primary", "ch"),
    ("الاجتماعيات", "🌍", "success", "ch"),
    ("الأحياء", "🧬", "primary", "ch"),
    ("الكيمياء", "🧪", "danger", "ch"),
    ("الفيزياء", "⚡", "primary", "ch"),
]

ROUND_LABELS = {"1": "الدور الأول", "2": "الدور الثاني", "3": "الدور الثالث"}
KIND_NAMES = {"book": "كتاب", "note": "ملزمة", "summary": "ملخص", "question": "أسئلة وزارية"}
KIND_ICON = {"book": "📘", "note": "📙", "summary": "🧾", "question": "📄"}
# اختصار النوع في الـ callback_data
KIND_CODE = {"b": "book", "n": "note", "s": "summary", "q": "question"}
KIND_TITLE = {"book": "📘 الكتب", "note": "📙 الملازم", "summary": "🧾 الملخصات",
              "question": "📄 الأسئلة الوزارية"}
KIND_HIDE_KEY = {"book": "book", "note": "note", "summary": "summary", "question": "questions"}
FILE_KINDS = {"📘 كتاب": "book", "📙 ملزمة": "note", "🧾 ملخص": "summary", "📄 أسئلة وزارية": "question"}

OWNER_ACTIONS = {
    "🛠 لوحة المالك": ("panel",),
    "🏠 القائمة الرئيسية": ("home",),
    "🆔 جميع الـ IDs": ("ids",),
    "🔗 جميع الروابط": ("links",),
    "📊 الإحصائيات": ("stats",),
    PAUSE_ON: ("pause",),
    PAUSE_OFF: ("pause",),
    SUB_LABEL: ("flow", "subs"),
    "➕ إضافة ملف": ("flow", "addfile"),
    "🆔 إضافة ملف بـ ID": ("flow", "addfile"),
    "➕ إضافة زر للأسئلة": ("flow", "addqbtn"),
    "➕ إضافة زر للملخصات": ("flow", "addsumbtn"),
    "➕ إضافة ملخصات": ("flow", "addsummary"),
    "➕ إضافة قسم جديد": ("flow", "addsection"),
    "🧩 تعديل الأزرار": ("flow", "edit"),
    "✏️ تعديل ملف": ("flow", "editfile"),
    "🔁 استبدال ملف": ("flow", "replacefile"),
    "🗑 حذف ملف": ("flow", "deletefile"),
    "👁 إخفاء/إظهار ملف": ("flow", "togglefile"),
    "➕ إضافة مادة": ("flow", "addsubject"),
    "✏️ تعديل مادة": ("flow", "editsubject"),
    "🗑 حذف مادة": ("flow", "delsubject"),
    "🗑 حذف قسم": ("flow", "delsection"),
    "🔎 التعرف على ID": ("flow", "identify"),
    "🔗 إنشاء رابط": ("flow", "genlink"),
    "📝 تعديل الوصف": ("flow", "footer"),
    "📢 إعلان": ("flow", "broadcast"),
    "👥 إدارة المشرفين": ("flow", "admins"),
}
OWNER_ONLY = {"📢 إعلان", "👥 إدارة المشرفين", PAUSE_ON, PAUSE_OFF}

FLOW_FIRST = {
    "addfile": "target", "addqbtn": "qsubj", "addsummary": "subj", "addsumbtn": "subj",
    "addsection": "cname", "addsubject": "sname", "editsubject": "subj", "delsubject": "subj",
    "delsection": "csec", "editfile": "file", "replacefile": "file", "deletefile": "file",
    "togglefile": "file", "identify": "wait", "genlink": "file", "footer": "ftext",
    "broadcast": "btext", "admins": "amenu", "edit": "root", "subs": "smenu",
}

NAV_KEYS = ("step", "kind", "id", "bid", "ptype", "pid", "field")

# ============================================================
# قاعدة البيانات
# ============================================================

SCHEMA_TABLES = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY, joined TEXT, blocked INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS admins (
    user_id INTEGER PRIMARY KEY, added TEXT);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ref TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL DEFAULT '', link TEXT NOT NULL DEFAULT '', added TEXT);
CREATE TABLE IF NOT EXISTS subjects (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
    emoji TEXT NOT NULL DEFAULT '', color TEXT NOT NULL DEFAULT 'success',
    stype TEXT NOT NULL DEFAULT 'ch', pos INTEGER NOT NULL DEFAULT 0,
    visible INTEGER NOT NULL DEFAULT 1, hidden TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS csections (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
    emoji TEXT NOT NULL DEFAULT '📁', color TEXT NOT NULL DEFAULT 'success',
    pos INTEGER NOT NULL DEFAULT 0, visible INTEGER NOT NULL DEFAULT 1,
    message TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS cbuttons (
    id INTEGER PRIMARY KEY AUTOINCREMENT, section_id INTEGER,
    ptype TEXT NOT NULL DEFAULT 'c', pid INTEGER, name TEXT NOT NULL,
    color TEXT NOT NULL DEFAULT 'success', pos INTEGER NOT NULL DEFAULT 0,
    visible INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS content (
    id INTEGER PRIMARY KEY AUTOINCREMENT, cbutton_id INTEGER NOT NULL,
    ctype TEXT NOT NULL, body TEXT, file_id TEXT, pos INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS sumsec (
    id INTEGER PRIMARY KEY AUTOINCREMENT, subject_id INTEGER NOT NULL,
    name TEXT NOT NULL, pos INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT, subject_id INTEGER, cbutton_id INTEGER,
    kind TEXT NOT NULL DEFAULT 'book', section TEXT, month TEXT,
    title TEXT NOT NULL DEFAULT '', teacher TEXT, file_id TEXT UNIQUE,
    ftype TEXT NOT NULL DEFAULT 'document', visible INTEGER NOT NULL DEFAULT 1,
    created TEXT, downloads INTEGER NOT NULL DEFAULT 0);
"""

# أعمدة تُضاف للقاعدة إن كانت ناقصة (لا تُحذف أي بيانات)
MIGRATIONS = {
    "users": {"joined": "TEXT", "blocked": "INTEGER NOT NULL DEFAULT 0"},
    "admins": {"added": "TEXT"},
    "subjects": {
        "emoji": "TEXT NOT NULL DEFAULT ''", "color": "TEXT NOT NULL DEFAULT 'success'",
        "stype": "TEXT NOT NULL DEFAULT 'ch'", "pos": "INTEGER NOT NULL DEFAULT 0",
        "visible": "INTEGER NOT NULL DEFAULT 1", "hidden": "TEXT NOT NULL DEFAULT ''",
    },
    "csections": {
        "color": "TEXT NOT NULL DEFAULT 'success'", "pos": "INTEGER NOT NULL DEFAULT 0",
        "visible": "INTEGER NOT NULL DEFAULT 1", "message": "TEXT NOT NULL DEFAULT ''",
        "emoji": "TEXT NOT NULL DEFAULT '📁'",
    },
    "cbuttons": {
        "section_id": "INTEGER", "ptype": "TEXT NOT NULL DEFAULT 'c'", "pid": "INTEGER",
        "color": "TEXT NOT NULL DEFAULT 'success'", "pos": "INTEGER NOT NULL DEFAULT 0",
        "visible": "INTEGER NOT NULL DEFAULT 1",
    },
    "files": {
        "subject_id": "INTEGER", "cbutton_id": "INTEGER", "kind": "TEXT NOT NULL DEFAULT 'book'",
        "section": "TEXT", "month": "TEXT", "teacher": "TEXT", "file_id": "TEXT",
        "title": "TEXT NOT NULL DEFAULT ''", "ftype": "TEXT NOT NULL DEFAULT 'document'",
        "visible": "INTEGER NOT NULL DEFAULT 1", "created": "TEXT",
        "downloads": "INTEGER NOT NULL DEFAULT 0",
    },
}

SCHEMA_INDEXES = """
CREATE INDEX IF NOT EXISTS ix_files_subject ON files(subject_id, kind, section, month);
CREATE INDEX IF NOT EXISTS ix_files_listing ON files(kind, subject_id, visible, id);
CREATE INDEX IF NOT EXISTS ix_files_downloads ON files(downloads DESC) WHERE downloads > 0;
CREATE INDEX IF NOT EXISTS ix_files_cbutton ON files(cbutton_id);
CREATE INDEX IF NOT EXISTS ix_cbuttons_parent ON cbuttons(ptype, pid, visible, pos);
CREATE INDEX IF NOT EXISTS ix_content_button ON content(cbutton_id, pos);
CREATE INDEX IF NOT EXISTS ix_sumsec_subject ON sumsec(subject_id, pos);
CREATE INDEX IF NOT EXISTS ix_users_blocked ON users(blocked);
"""

DB = sqlite3.connect(DB_FILE, check_same_thread=False)
DB.row_factory = sqlite3.Row
for _pragma in (
    "PRAGMA foreign_keys=OFF",
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA temp_store=MEMORY",
    "PRAGMA cache_size=-32000",
    "PRAGMA mmap_size=268435456",
    "PRAGMA busy_timeout=5000",
):
    DB.execute(_pragma)

SETTINGS = {}        # كاش للإعدادات
ADMIN_IDS = set()    # كاش للمشرفين
USERS_SEEN = set()   # كاش للمستخدمين
SUB_CACHE = {}       # كاش نتيجة الاشتراك لكل مستخدم
CHANNELS = []        # كاش قنوات الاشتراك الإجباري
LAST_WARN = {}       # آخر تحذير للمالك عن كل قناة
CACHE = {}           # كاش الشاشات والبحث (يُفرَّغ تلقائياً عند أي تعديل على المحتوى)
BCAST = {"running": False}
BG_TASKS = set()


def q(sql, p=()):
    return DB.execute(sql, p).fetchall()


def q1(sql, p=()):
    return DB.execute(sql, p).fetchone()


def invalidate():
    """يفرّغ كاش الشاشات حتى لا تظهر معلومات قديمة بعد أي تعديل."""
    CACHE.clear()


def x(sql, p=(), inval=True):
    cur = DB.execute(sql, p)
    DB.commit()
    if inval:
        invalidate()
    return cur


def cached(key, fn):
    v = CACHE.get(key)
    if v is None:
        v = CACHE[key] = fn()
    return v


def now():
    return datetime.now().isoformat(timespec="seconds")


def setting(key, default=""):
    v = SETTINGS.get(key)
    return default if v is None else v


def set_setting(key, value):
    x(
        "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value), inval=False,
    )
    SETTINGS[key] = value


def spawn(coro):
    """تشغيل مهمة بالخلفية بدون ما ينتظرها الطلب الحالي."""
    task = asyncio.create_task(coro)
    BG_TASKS.add(task)
    task.add_done_callback(BG_TASKS.discard)
    return task


def get_or_create_sumsec(sid, name):
    r = q1("SELECT id FROM sumsec WHERE subject_id=? AND name=?", (sid, name))
    if r:
        return r["id"]
    pos = q1("SELECT COALESCE(MAX(pos), 0) + 1 AS p FROM sumsec WHERE subject_id=?", (sid,))["p"]
    return DB.execute("INSERT INTO sumsec(subject_id, name, pos) VALUES(?, ?, ?)", (sid, name, pos)).lastrowid


def load_channels():
    CHANNELS[:] = [dict(r) for r in q("SELECT id, ref, title, link FROM channels ORDER BY id")]


def purge_legacy_fourth():
    """حماية: لو القاعدة جاية من بوت رابعيون (علامات اللقطة القديمة) تُمسح ملفاته ومحتوياته.
    لا يُلمس المالك ولا المشرفون ولا القنوات ولا الإعدادات."""
    if not (setting("files_snap_v4") or setting("seed_v3")):
        return
    log.warning("Legacy fourth-scientific data detected; purging files and content.")
    for table in ("files", "content", "cbuttons", "sumsec", "csections", "subjects"):
        DB.execute(f"DELETE FROM {table}")
    DB.execute("DELETE FROM settings WHERE key IN ('files_snap_v4','seed_v3','sum_mig_v1','ch_mig_v1','story')")
    DB.commit()
    for k in ("files_snap_v4", "seed_v3", "sum_mig_v1", "ch_mig_v1", "story"):
        SETTINGS.pop(k, None)


def seed_required_channels():
    """يضمن وجود قناتي ثالثيون ورابعيون بالاشتراك الإجباري."""
    for name, ref, link in (("قناة ثالثيون", THIRD_CHANNEL, THIRD_CHANNEL_LINK),
                            ("قناة رابعيون", FOURTH_CHANNEL, FOURTH_CHANNEL_LINK)):
        ref = parse_ref(ref)
        if not ref:
            log.warning("Required channel for '%s' is missing or invalid; set the environment variable.", name)
            continue
        if not link and ref.startswith("@"):
            link = f"https://t.me/{ref.lstrip('@')}"
        x("INSERT OR IGNORE INTO channels(ref, title, link, added) VALUES(?, ?, ?, ?)",
          (ref, name, link, now()), inval=False)


def init_db():
    DB.executescript(SCHEMA_TABLES)
    for table, cols in MIGRATIONS.items():
        have = {r["name"] for r in q(f"PRAGMA table_info({table})")}
        for col, definition in cols.items():
            if col not in have:
                DB.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")
    DB.commit()
    DB.executescript(SCHEMA_INDEXES)
    x("UPDATE cbuttons SET ptype='c', pid=section_id WHERE pid IS NULL AND section_id IS NOT NULL")
    for key, value in (("sub_on", "1"), ("bot_on", "1"), ("footer", DEFAULT_FOOTER)):
        x("INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (key, value))
    SETTINGS.update({r["key"]: r["value"] for r in q("SELECT key, value FROM settings")})
    purge_legacy_fourth()
    if not setting("seed_third_v1"):
        for i, (name, emoji, color, stype) in enumerate(SUBJECTS, 1):
            x("INSERT OR IGNORE INTO subjects(name, emoji, color, stype, pos) VALUES(?, ?, ?, ?, ?)",
              (name, emoji, color, stype, i))
        set_setting("seed_third_v1", "1")
    seed_required_channels()
    load_channels()
    ADMIN_IDS.update(r["user_id"] for r in q("SELECT user_id FROM admins"))
    log.info("Database ready.")


# ============================================================
# مساعدات عامة
# ============================================================

def is_staff(uid):
    return uid == OWNER_ID or uid in ADMIN_IDS


def upsert_user(uid):
    if uid in USERS_SEEN:
        return
    x("INSERT INTO users(user_id, joined, blocked) VALUES(?, ?, 0) "
      "ON CONFLICT(user_id) DO UPDATE SET blocked=0", (uid, now()), inval=False)
    USERS_SEEN.add(uid)


def subject_label(s):
    return f"{s['emoji']} {s['name']}" if s["emoji"] else s["name"]


def csec_label(c):
    return f"{c['emoji']} {c['name']}"


def label_of_subject(text):
    for s in q("SELECT * FROM subjects ORDER BY pos, id"):
        if subject_label(s) == text:
            return s
    return None


def hidden_set(raw):
    return {h for h in (raw or "").split(",") if h}


def pair(items):
    return [items[i:i + 2] for i in range(0, len(items), 2)]


def style_for(label):
    return "danger" if any(w in label for w in ("حذف", "رجوع", "إلغاء")) else "primary"


def kb(rows):
    out = []
    for row in rows:
        line = []
        for item in row:
            text, style = item if isinstance(item, tuple) else (item, "success")
            line.append(KeyboardButton(text, style=style))
        out.append(line)
    return ReplyKeyboardMarkup(out, resize_keyboard=True, is_persistent=True)


def tg_len(s):
    """طول النص بوحدات تلغرام (UTF-16)."""
    return len(s.encode("utf-16-le")) // 2


def make_caption(head, footer):
    """يقص العنوان فقط ويحافظ على التذييل كاملاً."""
    if not footer:
        return head[:CAPTION_LIMIT]
    room = CAPTION_LIMIT - tg_len(footer) - 2
    if room < 1:
        return footer[:CAPTION_LIMIT]
    return f"{head[:room]}\n\n{footer}"


def footer_caption():
    footer = setting("footer", DEFAULT_FOOTER)
    return footer[:CAPTION_LIMIT] if footer else None


def gate_markup(token=""):
    rows = [[InlineKeyboardButton(f"📢 {c['title'] or c['ref']}"[:60], url=c["link"], style="primary")]
            for c in CHANNELS if c["link"]]
    rows.append([InlineKeyboardButton("✅ التحقق من الاشتراك", callback_data=f"chk:{token}", style="success")])
    return InlineKeyboardMarkup(rows)


def media_payload(msg):
    if msg.photo:
        return msg.photo[-1].file_id, "photo"
    if msg.document:
        return msg.document.file_id, "document"
    return None, None


def media_name(msg):
    if msg.document and msg.document.file_name:
        return msg.document.file_name
    if msg.photo:
        return "صورة"
    return "ملف"


def looks_like_id(text):
    return len(text) >= 20 and re.fullmatch(r"[A-Za-z0-9_\-]+", text) is not None


def ftype_from_id(fid):
    return "photo" if fid.startswith("AgAC") else "document"


def read_file_payload(text, media):
    if media[0]:
        return media
    if looks_like_id(text):
        return text, ftype_from_id(text)
    return None, None


def resolve_file(f, text):
    if text in f.get("map", {}):
        return f["map"][text]
    m = re.match(r"#(\d+)", text)
    if m and q1("SELECT 1 FROM files WHERE id=?", (int(m.group(1)),)):
        return int(m.group(1))
    return None


def insert_file(sid, kind, section, month, title, teacher, fid, ftype):
    try:
        x(
            "INSERT INTO files(subject_id, kind, section, month, title, teacher, file_id, ftype, created) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, kind, section, month, title, teacher, fid, ftype, now()),
        )
        return True, None
    except sqlite3.IntegrityError:
        return False, "هذا الملف موجود مسبقاً."


def chat_arg(ref):
    return int(ref) if re.fullmatch(r"-?\d+", ref) else ref


def parse_ref(text):
    t = (text or "").strip()
    if "t.me/" in t:
        t = t.split("t.me/", 1)[1].split("?", 1)[0].strip("/")
        if not t or t.startswith("+"):
            return None
        t = "@" + t
    if re.fullmatch(r"@[A-Za-z][A-Za-z0-9_]{3,}", t):
        return t
    if re.fullmatch(r"-100\d+", t):
        return t
    return None


def parse_round(text):
    """يحوّل نص الدور (1/2/3 أو الأول/الثاني/الثالث) إلى رمز، أو None."""
    t = (text or "").strip()
    if t in ROUND_LABELS:
        return t
    for code, label in ROUND_LABELS.items():
        if t == label or t == label.replace("الدور ", ""):
            return code
    return None


def file_name_of(r):
    return r["teacher"] if r["kind"] == "note" and r["teacher"] else r["title"]


def question_meta(r):
    """السنة والدور لملف الأسئلة (من الحقول، وإلا من العنوان إن وُجدت)."""
    year = (r["section"] or "").strip()
    if not year:
        m = re.search(r"(?<!\d)(20\d\d)(?!\d)", r["title"] or "")
        year = m.group(1) if m else ""
    rnd = r["month"] or ""
    if not rnd:
        t = r["title"] or ""
        rnd = "1" if "الأول" in t else "2" if "الثاني" in t else "3" if "الثالث" in t else ""
    return year, rnd


def file_label(r):
    name = file_name_of(r)
    if r["kind"] == "question":
        year, rnd = question_meta(r)
        tag = " - ".join(p for p in (year, ROUND_LABELS.get(rnd, "")) if p)
        if tag and tag not in name:
            name = f"{tag} | {name}"
    return f"{KIND_ICON.get(r['kind'], '📄')} {name}"


def question_sort_key(r):
    year, rnd = question_meta(r)
    y = int(year) if year.isdigit() else 0
    return (-y, int(rnd) if rnd.isdigit() else 9, r["id"])


_AR_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"})


def norm(s):
    s = re.sub(r"[\u064B-\u065F\u0670\u0640]", "", (s or "").lower())
    return s.translate(_AR_FOLD)


# ============================================================
# الأزرار والمحتوى والملخصات
# ============================================================

def children(ptype, pid, visible_only=True):
    sql = "SELECT * FROM cbuttons WHERE ptype=? AND pid=?"
    if visible_only:
        sql += " AND visible=1"
    return q(sql + " ORDER BY pos, id", (ptype, pid))


def insert_content(cbid, ctype, body, fid):
    x(
        "INSERT INTO content(cbutton_id, ctype, body, file_id, pos) VALUES(?, ?, ?, ?, "
        "(SELECT COALESCE(MAX(pos), 0) + 1 FROM content WHERE cbutton_id=?))",
        (cbid, ctype, body, fid, cbid),
    )


def content_step(cbid, text, media):
    if text == DONE:
        return "done"
    if text in (BACK, CANCEL):
        return "bad"
    if media[0]:
        insert_content(cbid, media[1], None, media[0])
        return "added"
    if text.startswith("ID:"):
        fid = text[3:].strip()
        if not looks_like_id(fid):
            return "bad"
        insert_content(cbid, ftype_from_id(fid), None, fid)
        return "added"
    if looks_like_id(text):
        insert_content(cbid, ftype_from_id(text), None, text)
        return "added"
    if text:
        insert_content(cbid, "text", text, None)
        return "added"
    return "bad"


def content_items(cbid):
    """المحتوى بالترتيب: أولاً محتوى الزر، ثم الملفات القديمة المرتبطة به."""
    items = [(r["ctype"], r["body"], r["file_id"])
             for r in q("SELECT * FROM content WHERE cbutton_id=? ORDER BY pos, id", (cbid,))]
    for r in q("SELECT * FROM files WHERE cbutton_id=? AND visible=1 ORDER BY id", (cbid,)):
        items.append(("photo" if r["ftype"] == "photo" else "document", None, r["file_id"]))
    return items


def purge_button(cid):
    """يحذف الزر وكل ما تحته، ولا يحذف الملفات (يفصلها فقط)."""
    for ch in q("SELECT id FROM cbuttons WHERE ptype='b' AND pid=?", (cid,)):
        purge_button(ch["id"])
    x("UPDATE files SET cbutton_id=NULL WHERE cbutton_id=?", (cid,))
    x("DELETE FROM content WHERE cbutton_id=?", (cid,))
    x("DELETE FROM cbuttons WHERE id=?", (cid,))


def button_path(cid):
    parts, cur = [], cid
    for _ in range(10):
        b = q1("SELECT * FROM cbuttons WHERE id=?", (cur,))
        if not b:
            break
        parts.append(b["name"])
        if b["ptype"] == "b":
            cur = b["pid"]
            continue
        if b["ptype"] == "s":
            s = q1("SELECT name FROM subjects WHERE id=?", (b["pid"],))
            parts.append(s["name"] if s else "")
        elif b["ptype"] == "c":
            c = q1("SELECT name FROM csections WHERE id=?", (b["pid"],))
            parts.append(c["name"] if c else "")
        elif b["ptype"] == "q":
            s = q1("SELECT name FROM subjects WHERE id=?", (b["pid"],))
            parts.append(f"أسئلة {s['name']}" if s else "أسئلة")
        break
    return " › ".join(p for p in reversed(parts) if p)


def button_parent_cb(cbid):
    """callback_data للصفحة الأم للزر (للرجوع)."""
    b = q1("SELECT ptype, pid FROM cbuttons WHERE id=?", (cbid,))
    if not b:
        return "h"
    return {
        "b": f"bt:{b['pid']}", "c": f"cs:{b['pid']}", "q": f"l:q:{b['pid']}",
    }.get(b["ptype"], "h")


def sum_list(sid):
    return q("SELECT * FROM sumsec WHERE subject_id=? ORDER BY pos, id", (sid,))


def sum_name(key):
    if not key or not str(key).isdigit():
        return str(key or "")
    r = q1("SELECT name FROM sumsec WHERE id=?", (int(key),))
    return r["name"] if r else ""


def create_subject(name, emoji, names):
    """ينشئ المادة وفصولها كعملية واحدة، فإذا فشلت شي ما يبقى ناقص."""
    try:
        pos = q1("SELECT COALESCE(MAX(pos), 0) + 1 AS p FROM subjects")["p"]
        cur = DB.execute(
            "INSERT INTO subjects(name, emoji, color, stype, pos) VALUES(?, ?, 'success', 'ch', ?)",
            (name, emoji, pos))
        sid = cur.lastrowid
        for i, n in enumerate(names, 1):
            DB.execute("INSERT INTO sumsec(subject_id, name, pos) VALUES(?, ?, ?)", (sid, n, i))
        DB.commit()
        invalidate()
        return sid
    except Exception:
        DB.rollback()
        raise


# ============================================================
# إرسال الملفات والمحتوى (الصور المتتالية تُرسل ألبوماً واحداً)
# ============================================================

def split_text(body, limit=3900):
    body = body or ""
    parts = [body[i:i + limit] for i in range(0, len(body), limit)]
    return [p for p in parts if p.strip()]


async def tg_retry(fn, *args, **kwargs):
    """ينفّذ طلب تلغرام، وإذا طلب الانتظار (RetryAfter) ينتظر مرة واحدة بدون حجب الباقين."""
    try:
        return await fn(*args, **kwargs)
    except RetryAfter as e:
        await asyncio.sleep(min(e.retry_after, 30) + 0.5)
        return await fn(*args, **kwargs)


async def _send_single(ctx, chat, ctype, fid, caption=None):
    if ctype == "photo":
        await tg_retry(ctx.bot.send_photo, chat, fid, caption=caption)
    else:
        await tg_retry(ctx.bot.send_document, chat, fid, caption=caption)


async def send_group(ctx, chat, ctype, values, caption=None):
    if ctype == "text":
        for body in values:
            for part in split_text(body):
                try:
                    await ctx.bot.send_message(chat, part)
                except TelegramError as e:
                    log.error("Text send failed: %s", e)
        return
    if len(values) == 1:
        try:
            await _send_single(ctx, chat, ctype, values[0], caption)
        except TelegramError as e:
            log.error("Single send failed: %s", e)
        return
    cls = InputMediaPhoto if ctype == "photo" else InputMediaDocument
    media = [cls(v) for v in values]
    if caption:
        media[0] = cls(values[0], caption=caption)
    try:
        await ctx.bot.send_media_group(chat, media)
    except TelegramError as e:
        log.error("Media group failed, sending one by one: %s", e)
        for i, v in enumerate(values):
            try:
                await _send_single(ctx, chat, ctype, v, caption if i == 0 else None)
            except TelegramError as e2:
                log.error("Fallback send failed: %s", e2)


async def send_items(ctx, chat, items, caption=None):
    """items: قائمة (النوع، النص، الـ file_id) بالترتيب المطلوب."""
    groups = []
    for ctype, body, fid in items:
        if ctype == "text":
            groups.append(("text", [body]))
        elif groups and groups[-1][0] == ctype and len(groups[-1][1]) < MEDIA_GROUP_MAX:
            groups[-1][1].append(fid)
        else:
            groups.append((ctype, [fid]))
    cap_left = caption
    for ctype, values in groups:
        cap = None
        if ctype != "text" and cap_left:
            cap, cap_left = cap_left, None
        await send_group(ctx, chat, ctype, values, cap)


def count_download(row_id):
    """يزيد عدد التحميلات الحقيقي (بدون إفراغ كاش الشاشات)."""
    try:
        x("UPDATE files SET downloads = downloads + 1 WHERE id=?", (row_id,), inval=False)
    except sqlite3.Error:
        log.exception("Download count failed for %s", row_id)


async def send_file(ctx, chat, row_id, uid):
    row = q1("SELECT * FROM files WHERE id=?", (row_id,))
    if not row or (not row["visible"] and not is_staff(uid)):
        await ctx.bot.send_message(chat, "الملف غير متاح حالياً.")
        return False
    caption = make_caption(file_name_of(row), setting("footer", DEFAULT_FOOTER))
    try:
        await _send_single(ctx, chat, row["ftype"], row["file_id"], caption)
    except Forbidden:
        return False
    except TelegramError as e:
        log.error("Send failed for file %s: %s", row["id"], e)
        try:
            await ctx.bot.send_message(chat, "تعذر إرسال الملف. أبلغ المالك.")
        except TelegramError:
            pass
        return False
    if not is_staff(uid):
        count_download(row["id"])
    return True


async def deliver(ctx, chat, token, uid):
    """فتح الرابط العميق: f = ملف، c = زر."""
    if not re.fullmatch(r"[fc]\d+", token or ""):
        return
    n = int(token[1:])
    if token[0] == "f":
        await send_file(ctx, chat, n, uid)
        return
    row = q1("SELECT * FROM cbuttons WHERE id=?", (n,))
    if not row or (not row["visible"] and not is_staff(uid)):
        await ctx.bot.send_message(chat, "المحتوى غير متاح حالياً.")
        return
    items = content_items(n)
    if not items:
        await ctx.bot.send_message(chat, "لا يوجد محتوى حالياً.")
        return
    await send_items(ctx, chat, items, caption=footer_caption())



# ============================================================
# شاشات الطالب (أزرار Inline، والتنقل بتعديل الرسالة نفسها)
# ============================================================
# كل شاشة تُبنى كـ (نص، أسطر أزرار)، وكل زر = (النص، اللون، callback_data).
# الرجوع بلا حالة محفوظة: كل شاشة تعرف أمها من callback_data نفسه، فلا يتعطل شي بعد إعادة التشغيل.
#
#   h              الرئيسية
#   k:<b|n|s|q>    صفحة المواد لنوع معين (كتب/ملازم/ملخصات/أسئلة وزارية)
#   l:<k>:<sid>[:<page>]  محتوى مادة معينة ضمن النوع
#   sm:<sid>:<secid>  إرسال ملخصات فصل/وحدة
#   f:<id>         إرسال ملف
#   bt:<id>        زر محتوى (أسئلة/قسم)
#   cs:<id>        قسم مخصص بالرئيسية
#   t              الأكثر تحميلاً

def inline_markup(rows):
    out = []
    for row in rows:
        out.append([InlineKeyboardButton(label[:60], callback_data=data, style=style)
                    for label, style, data in row])
    return InlineKeyboardMarkup(out)


def back_row(data):
    return [(BACK, "danger", data)]


def file_rows(files, label_fn=file_label):
    """أزرار الملفات: واحد بكل سطر، بألوان متنوعة."""
    return [[(label_fn(r), FILE_STYLES[i % len(FILE_STYLES)], f"f:{r['id']}")] for i, r in enumerate(files)]


def paged(rows, page, base):
    """تقسيم الأزرار إلى صفحات إذا زادت عن PAGE_SIZE، مع أزرار ◀ ▶ عند الحاجة فقط."""
    if len(rows) <= PAGE_SIZE:
        return rows
    pages = (len(rows) + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(0, min(page, pages - 1))
    out = rows[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    nav = []
    if page > 0:
        nav.append(("◀️", "primary", f"{base}:{page - 1}"))
    nav.append((f"{page + 1}/{pages}", "primary", f"{base}:{page}"))
    if page < pages - 1:
        nav.append(("▶️", "primary", f"{base}:{page + 1}"))
    out.append(nav)
    return out


def build_home(staff):
    def make():
        rows = [
            [("📘 كتب", "primary", "k:b"), ("📙 ملازم", "success", "k:n")],
            [("🧾 ملخصات", "primary", "k:s"), ("📄 الأسئلة الوزارية", "danger", "k:q")],
        ]
        for c in q("SELECT * FROM csections WHERE visible=1 ORDER BY pos, id"):
            rows.append([(csec_label(c), c["color"], f"cs:{c['id']}")])
        return rows
    rows = list(cached("home", make))
    if staff:
        rows.append([("🛠 لوحة المالك", "primary", "panel")])
    return HOME_TEXT, inline_markup(rows)


def build_kind(kind):
    """صفحة المواد لنوع معين، بنفس ألوان المواد."""
    def make():
        key = KIND_HIDE_KEY[kind]
        items = []
        for s in q("SELECT * FROM subjects WHERE visible=1 ORDER BY pos, id"):
            if key in hidden_set(s["hidden"]):
                continue
            items.append((subject_label(s), s["color"], f"l:{kind[0] if kind != 'question' else 'q'}:{s['id']}"))
        rows = pair(items)
        rows.append(back_row("h"))
        text = KIND_TITLE[kind] + ("\nاختر المادة:" if items else "\nلا توجد مواد حالياً.")
        return text, inline_markup(rows)
    return cached(("kind", kind), make)


def build_list(kcode, sid, page=0):
    """محتوى مادة ضمن نوع: ملفات الكتب/الملازم، فصول الملخصات، أو الأسئلة الوزارية."""
    kind = KIND_CODE[kcode]

    def make():
        s = q1("SELECT * FROM subjects WHERE id=?", (sid,))
        if not s:
            return "المادة غير متاحة حالياً.", inline_markup([back_row(f"k:{kcode}")])
        title = f"{KIND_TITLE[kind]} — {s['name']}"
        back = back_row(f"k:{kcode}")
        if kind in ("book", "note"):
            files = q("SELECT * FROM files WHERE subject_id=? AND kind=? AND visible=1 ORDER BY id", (sid, kind))
            rows = file_rows(files)
            if not rows:
                title += "\nلا توجد ملفات حالياً."
            else:
                title += "\nاختر الملف:"
            return title, inline_markup(paged(rows, page, f"l:{kcode}:{sid}") + [back])
        if kind == "summary":
            rows = [[(r["name"], FILE_STYLES[i % len(FILE_STYLES)], f"sm:{sid}:{r['id']}")]
                    for i, r in enumerate(sum_list(sid))]
            title += "\nاختر:" if rows else "\nسيتم إضافة الملخصات لاحقاً."
            return title, inline_markup(paged(rows, page, f"l:{kcode}:{sid}") + [back])
        # الأسئلة الوزارية: أزرار الأسئلة التي يضيفها المالك ثم ملفات PDF مرتبة بالسنة والدور
        rows = [[(b["name"], b["color"], f"bt:{b['id']}")] for b in children("q", sid)]
        files = sorted(q("SELECT * FROM files WHERE subject_id=? AND kind='question' AND visible=1", (sid,)),
                       key=question_sort_key)
        rows += file_rows(files)
        title += "\nاختر:" if rows else "\nسيتم إضافة الأسئلة الوزارية لاحقاً."
        return title, inline_markup(paged(rows, page, f"l:{kcode}:{sid}") + [back])
    return cached(("list", kcode, sid, page), make)


def build_csec(cid):
    def make():
        c = q1("SELECT * FROM csections WHERE id=?", (cid,))
        back = back_row("h")
        if not c:
            return "القسم غير متاح حالياً.", inline_markup([back])
        rows = [[(b["name"], b["color"], f"bt:{b['id']}")] for b in children("c", cid)]
        if not rows:
            return (c["message"] or "لا يوجد محتوى حالياً."), inline_markup([back])
        return f"{csec_label(c)}\nاختر:", inline_markup(rows + [back])
    return cached(("csec", cid), make)


def build_button_children(cbid):
    """أزرار الداخلية لزر محتوى، أو None إذا ما عنده أزرار."""
    kids = children("b", cbid)
    if not kids:
        return None
    row = q1("SELECT name FROM cbuttons WHERE id=?", (cbid,))
    rows = [[(k["name"], k["color"], f"bt:{k['id']}")] for k in kids]
    return f"{row['name'] if row else ''}\nاختر:", inline_markup(rows + [back_row(button_parent_cb(cbid))])


def top_files():
    return q(
        "SELECT * FROM files WHERE visible=1 AND downloads > 0 "
        "ORDER BY downloads DESC, id LIMIT ?", (TOP_LIMIT,))


def build_top():
    """الأكثر تحميلاً: فقط ملفات لها تحميلات حقيقية، مرتبة بعددها الفعلي."""
    files = top_files()
    if not files:
        return "🔥 الأكثر تحميلاً\nلا توجد تحميلات بعد.", inline_markup([back_row("h")])
    rows = [[(f"{file_label(r)} ({r['downloads']})", FILE_STYLES[i % len(FILE_STYLES)], f"f:{r['id']}")]
            for i, r in enumerate(files)]
    return "🔥 الملفات الأكثر تحميلاً:", inline_markup(rows + [back_row("h")])


def search_index():
    def make():
        out = []
        for r in q("SELECT f.*, s.name AS sn FROM files f LEFT JOIN subjects s ON s.id=f.subject_id "
                   "WHERE f.visible=1 ORDER BY f.id"):
            hay = norm(" ".join(p for p in (r["title"], r["teacher"], r["sn"], KIND_NAMES.get(r["kind"], ""),
                                            r["section"] if r["kind"] == "question" else "") if p))
            out.append((hay, r))
        return out
    return cached("search", make)


def build_search(text):
    words = [w for w in norm(text).split() if w]
    found = []
    if words:
        for hay, r in search_index():
            if all(w in hay for w in words):
                found.append(r)
                if len(found) >= SEARCH_LIMIT:
                    break
    if not found:
        return "🔎 ما لقيت ملفاً بهذا الاسم. جرّب كلمة ثانية.", inline_markup([back_row("h")])
    rows = [[(f"{file_label(r)}"[:56], FILE_STYLES[i % len(FILE_STYLES)], f"f:{r['id']}")]
            for i, r in enumerate(found)]
    return f"🔎 نتائج البحث ({len(found)}):", inline_markup(rows + [back_row("h")])


def parent_cb(data):
    """callback_data للصفحة الأم (للتوثيق والاختبار)."""
    p = data.split(":")
    if p[0] == "l":
        return f"k:{p[1]}"
    if p[0] == "bt":
        return button_parent_cb(int(p[1]))
    return "h"


async def show(cb, ctx, text, markup):
    """يعدّل نفس الرسالة. إذا تعذر التعديل (رسالة قديمة/محذوفة) يرسل رسالة جديدة بدون تعطيل البوت."""
    for attempt in (1, 2):
        try:
            await cb.edit_message_text(text, reply_markup=markup)
            return
        except BadRequest as e:
            if "not modified" in str(e).lower():
                return
            log.info("Edit failed (%s); sending a new message.", e)
            break
        except RetryAfter as e:
            if attempt == 2:
                return
            await asyncio.sleep(min(e.retry_after, 10) + 0.3)
        except Forbidden:
            return
        except TelegramError as e:
            log.warning("Edit error: %s", e)
            break
    try:
        await ctx.bot.send_message(cb.from_user.id if cb.message is None else cb.message.chat_id,
                                   text, reply_markup=markup)
    except TelegramError as e:
        log.warning("Fallback send failed: %s", e)


async def send_home(chat, ctx, uid):
    text, markup = build_home(is_staff(uid))
    await tg_retry(ctx.bot.send_message, chat, text, reply_markup=markup)


async def open_button(cb, ctx, cbid, uid):
    """زر محتوى: يرسل محتواه (إن وُجد)، ثم يعرض أزراره الداخلية بنفس الرسالة."""
    row = q1("SELECT * FROM cbuttons WHERE id=?", (cbid,))
    if not row or (not row["visible"] and not is_staff(uid)):
        await show(cb, ctx, "هذا القسم غير متاح حالياً.", inline_markup([back_row("h")]))
        return
    items = content_items(cbid)
    chat = cb.message.chat_id if cb.message else uid
    if items:
        await send_items(ctx, chat, items, caption=footer_caption())
    page = build_button_children(cbid)
    if page:
        await show(cb, ctx, *page)
    elif not items:
        await show(cb, ctx, "لا يوجد محتوى حالياً.", inline_markup([back_row(button_parent_cb(cbid))]))


async def send_summaries(cb, ctx, secid, uid):
    chat = cb.message.chat_id if cb.message else uid
    rows = q("SELECT id FROM files WHERE kind='summary' AND section=? AND visible=1 ORDER BY id", (str(secid),))
    if not rows:
        await ctx.bot.send_message(chat, "سيتم إضافة الملخصات لاحقاً.")
        return
    for r in rows:
        await send_file(ctx, chat, r["id"], uid)


async def do_nav(cb, ctx, data, uid):
    """ينفّذ ضغطة زر من أزرار الطالب."""
    p = data.split(":")
    k = p[0]
    chat = cb.message.chat_id if cb.message else uid
    if k == "h":
        return await show(cb, ctx, *build_home(is_staff(uid)))
    if k == "k" and len(p) == 2 and p[1] in KIND_CODE:
        return await show(cb, ctx, *build_kind(KIND_CODE[p[1]]))
    if k == "l" and len(p) >= 3 and p[1] in KIND_CODE and p[2].isdigit():
        page = int(p[3]) if len(p) > 3 and p[3].isdigit() else 0
        return await show(cb, ctx, *build_list(p[1], int(p[2]), page))
    if k == "cs" and len(p) == 2 and p[1].isdigit():
        return await show(cb, ctx, *build_csec(int(p[1])))
    if k == "bt" and len(p) == 2 and p[1].isdigit():
        return await open_button(cb, ctx, int(p[1]), uid)
    if k == "t":
        return await show(cb, ctx, *build_top())
    if k == "f" and len(p) == 2 and p[1].isdigit():
        return await send_file(ctx, chat, int(p[1]), uid)
    if k == "sm" and len(p) == 3 and p[2].isdigit():
        return await send_summaries(cb, ctx, int(p[2]), uid)
    if k == "panel" and is_staff(uid):
        return await open_panel(chat, ctx, uid == OWNER_ID)


# ============================================================
# الاشتراك الإجباري (قناتا ثالثيون ورابعيون، فحص متوازٍ مع كاش)
# ============================================================

async def warn_owner(bot, ref, err):
    log.warning("Subscription check failed for %s: %s", ref, err)
    t = time.time()
    if t - LAST_WARN.get(ref, 0) < 3600:
        return
    LAST_WARN[ref] = t
    try:
        await bot.send_message(
            OWNER_ID,
            f"⚠️ تعذر فحص الاشتراك في القناة {ref}.\n"
            f"الطلاب ممنوعون من استخدام البوت مؤقتاً (لا يُتجاوز الاشتراك عند الخطأ).\n"
            f"تأكد أن البوت أدمن فيها.\nالسبب: {err}",
        )
    except TelegramError:
        pass


async def _check_one(bot, ref, uid):
    """True = مشترك، False = غير مشترك، None = تعذر الفحص."""
    try:
        m = await tg_retry(bot.get_chat_member, chat_arg(ref), uid)
    except TelegramError as e:
        spawn(warn_owner(bot, ref, e))   # لا ينتظر الطالب التحذير
        return None
    return m.status in MEMBER_OK or (m.status == "restricted" and bool(getattr(m, "is_member", False)))


async def member_state(bot, uid):
    """'ok' مشترك بكل القنوات، 'no' ناقص اشتراك، 'err' تعذر فحص قناة (لا نتجاوزها)."""
    if is_staff(uid) or setting("sub_on") != "1" or not CHANNELS:
        return "ok"
    if SUB_CACHE.get(uid, 0) > time.time():
        return "ok"
    results = await asyncio.gather(*(_check_one(bot, c["ref"], uid) for c in CHANNELS))
    if any(r is False for r in results):
        return "no"
    if any(r is None for r in results):
        return "err"
    if len(SUB_CACHE) > 50000:
        SUB_CACHE.clear()
    SUB_CACHE[uid] = time.time() + SUB_CACHE_SECONDS
    return "ok"


async def is_member(bot, uid):
    return await member_state(bot, uid) == "ok"


def gate_text(state):
    return GATE_ERR_TEXT if state == "err" else GATE_TEXT


# ============================================================
# لوحة المالك
# ============================================================

def owner_markup(is_owner):
    pause = PAUSE_OFF if setting("bot_on") == "0" else PAUSE_ON
    rows = [
        [("➕ إضافة ملف", "success"), ("🆔 إضافة ملف بـ ID", "success")],
        [("➕ إضافة زر للأسئلة", "success"), ("➕ إضافة زر للملخصات", "success")],
        [("➕ إضافة ملخصات", "success"), ("➕ إضافة قسم جديد", "success")],
        [("🧩 تعديل الأزرار", "success"), ("✏️ تعديل ملف", "success")],
        [("🔁 استبدال ملف", "success"), ("🗑 حذف ملف", "danger")],
        [("👁 إخفاء/إظهار ملف", "primary"), ("➕ إضافة مادة", "success")],
        [("✏️ تعديل مادة", "success"), ("🗑 حذف مادة", "danger")],
        [("🗑 حذف قسم", "danger"), ("🆔 جميع الـ IDs", "primary")],
        [("🔗 جميع الروابط", "primary"), ("🔎 التعرف على ID", "primary")],
        [("🔗 إنشاء رابط", "success"), ("📊 الإحصائيات", "primary")],
        [("📝 تعديل الوصف", "primary"), (SUB_LABEL, "primary")],
    ]
    if is_owner:
        rows.append([("📢 إعلان", "primary"), (pause, "primary")])
        rows.append([("👥 إدارة المشرفين", "primary")])
    rows.append([("🏠 القائمة الرئيسية", "danger")])
    return kb(rows)


async def open_panel(chat, ctx, is_owner):
    ctx.user_data.pop("flow", None)
    await ctx.bot.send_message(chat, "🛠 لوحة المالك", reply_markup=owner_markup(is_owner))


def section_text(r):
    """نص القسم لأي ملف: فصل الملخص، أو سنة ودور الأسئلة الوزارية."""
    if r["kind"] == "summary" and r["section"]:
        return sum_name(r["section"])
    if r["kind"] == "question":
        year, rnd = question_meta(r)
        return " ".join(p for p in (year, ROUND_LABELS.get(rnd, "")) if p)
    return ""


def all_ids_lines():
    lines = []
    for r in q("SELECT f.*, s.name AS sn FROM files f LEFT JOIN subjects s ON s.id=f.subject_id ORDER BY f.id"):
        parts = [r["sn"] or "-", KIND_NAMES.get(r["kind"], r["kind"]), section_text(r)]
        name = r["teacher"] if r["kind"] == "note" and r["teacher"] else r["title"]
        lines.append(f"#{r['id']} | " + " | ".join(html.escape(p) for p in parts if p)
                     + f" | {html.escape(name)}\n<code>{r['file_id']}</code>")
    for it in q(
        "SELECT ct.id, ct.file_id, cb.name AS bn FROM content ct JOIN cbuttons cb ON cb.id=ct.cbutton_id "
        "WHERE ct.ctype<>'text' ORDER BY ct.id"
    ):
        lines.append(f"C#{it['id']} | محتوى زر | {html.escape(it['bn'])}\n<code>{it['file_id']}</code>")
    return lines


async def send_lines(chat, ctx, lines, parse_mode=None, markup=None):
    chunk = ""
    for line in lines:
        block = line + "\n\n"
        if len(chunk) + len(block) > 3500:
            await ctx.bot.send_message(chat, chunk, parse_mode=parse_mode)
            chunk = ""
        chunk += block
    if chunk.strip():
        await ctx.bot.send_message(chat, chunk, parse_mode=parse_mode, reply_markup=markup)


async def send_all_ids(chat, ctx, is_owner):
    lines = all_ids_lines()
    if not lines:
        await ctx.bot.send_message(chat, "لا توجد ملفات.", reply_markup=owner_markup(is_owner))
        return
    await send_lines(chat, ctx, lines, parse_mode=ParseMode.HTML, markup=owner_markup(is_owner))


async def send_all_links(chat, ctx, is_owner):
    username = ctx.bot.username
    lines, seen = [], set()
    for r in q("SELECT f.*, s.name AS sn FROM files f LEFT JOIN subjects s ON s.id=f.subject_id "
               "WHERE f.visible=1 ORDER BY f.id"):
        name = r["teacher"] if r["kind"] == "note" and r["teacher"] else r["title"]
        parts = [r["sn"] or "بدون مادة", KIND_NAMES.get(r["kind"], r["kind"]), section_text(r)]
        link = f"https://t.me/{username}?start=f{r['id']}"
        if link in seen:
            continue
        seen.add(link)
        lines.append(f"{name}\n{' | '.join(p for p in parts if p)}\n{link}")
    for cb in q("SELECT * FROM cbuttons WHERE visible=1 ORDER BY id"):
        has_content = q1("SELECT 1 FROM content WHERE cbutton_id=? LIMIT 1", (cb["id"],)) or \
            q1("SELECT 1 FROM files WHERE cbutton_id=? AND visible=1 LIMIT 1", (cb["id"],))
        if not has_content:
            continue
        link = f"https://t.me/{username}?start=c{cb['id']}"
        if link in seen:
            continue
        seen.add(link)
        lines.append(f"📦 {cb['name']}\n{button_path(cb['id'])}\n{link}")
    if not lines:
        await ctx.bot.send_message(chat, "لا توجد روابط.", reply_markup=owner_markup(is_owner))
        return
    await ctx.bot.send_message(chat, f"🔗 جميع الروابط ({len(lines)})")
    await send_lines(chat, ctx, lines, markup=owner_markup(is_owner))


async def send_stats(chat, ctx, is_owner):
    def count(sql, p=()):
        return q1(sql, p)[0]

    text = (
        "📊 الإحصائيات\n\n"
        f"المستخدمون: {count('SELECT COUNT(*) FROM users')}\n"
        f"المحظورون: {count('SELECT COUNT(*) FROM users WHERE blocked=1')}\n"
        f"المشرفون: {count('SELECT COUNT(*) FROM admins')}\n"
        f"المواد الظاهرة: {count('SELECT COUNT(*) FROM subjects WHERE visible=1')}\n"
        f"الأقسام: {count('SELECT COUNT(*) FROM csections')}\n"
        f"الكتب: {count('SELECT COUNT(*) FROM files WHERE kind=?', ('book',))}\n"
        f"الملازم: {count('SELECT COUNT(*) FROM files WHERE kind=?', ('note',))}\n"
        f"الملخصات: {count('SELECT COUNT(*) FROM files WHERE kind=?', ('summary',))}\n"
        f"الأسئلة الوزارية: {count('SELECT COUNT(*) FROM files WHERE kind=?', ('question',))}\n"
        f"إجمالي التحميلات الفعلية: {count('SELECT COALESCE(SUM(downloads), 0) FROM files')}\n"
        f"الملفات المخفية: {count('SELECT COUNT(*) FROM files WHERE visible=0')}\n"
        f"القنوات الإجبارية: {len(CHANNELS)}\n"
        f"الاشتراك: {'مفعّل' if setting('sub_on') == '1' else 'معطّل'}"
    )
    await ctx.bot.send_message(chat, text, reply_markup=owner_markup(is_owner))


async def _send_bcast(bot, uid, text):
    for _ in range(2):
        try:
            await bot.send_message(uid, text)
            return True
        except RetryAfter as e:
            await asyncio.sleep(min(e.retry_after, 30))
        except Forbidden:
            x("UPDATE users SET blocked=1 WHERE user_id=?", (uid,))
            USERS_SEEN.discard(uid)
            return False
        except TelegramError:
            return False
    return False


async def run_broadcast(bot, text, report_chat):
    BCAST["running"] = True
    ok = bad = 0
    try:
        uids = [r["user_id"] for r in q("SELECT user_id FROM users WHERE blocked=0")]
        for i in range(0, len(uids), BROADCAST_BATCH):
            res = await asyncio.gather(*(_send_bcast(bot, u, text) for u in uids[i:i + BROADCAST_BATCH]))
            ok += sum(1 for r in res if r)
            bad += sum(1 for r in res if not r)
            await asyncio.sleep(1)
        await bot.send_message(report_chat, f"✅ انتهى الإعلان.\nنجح: {ok}\nفشل: {bad}")
    except Exception:
        log.exception("Broadcast failed")
    finally:
        BCAST["running"] = False


async def run_owner_action(msg, ctx, uid, text):
    chat, is_owner = msg.chat_id, uid == OWNER_ID
    spec = OWNER_ACTIONS[text]
    ctx.user_data.pop("flow", None)
    k = spec[0]
    if k == "panel":
        await open_panel(chat, ctx, is_owner)
    elif k == "home":
        await send_home(chat, ctx, uid)
    elif k == "ids":
        await send_all_ids(chat, ctx, is_owner)
    elif k == "links":
        await send_all_links(chat, ctx, is_owner)
    elif k == "stats":
        await send_stats(chat, ctx, is_owner)
    elif k == "pause":
        set_setting("bot_on", "0" if setting("bot_on") == "1" else "1")
        status = "يعمل" if setting("bot_on") == "1" else "تحت الصيانة"
        await msg.reply_text(f"البوت الآن: {status}", reply_markup=owner_markup(is_owner))
    elif k == "flow":
        await start_flow(chat, ctx, spec[1])



# ============================================================
# محرك التدفقات
# ============================================================

async def flow_prompt(chat, ctx):
    f = ctx.user_data["flow"]
    text, rows = flow_build(f)
    await ctx.bot.send_message(chat, text, reply_markup=kb(list(rows) + [[(CANCEL, "danger")]]))


async def goto(chat, ctx, f, step):
    f["step"] = step
    await flow_prompt(chat, ctx)


def snapshot(f):
    return {k: f[k] for k in NAV_KEYS if k in f}


async def enter(chat, ctx, f, step, **state):
    """ينتقل لشاشة جديدة ويحفظ حالة الشاشة الحالية للرجوع إليها (بدون ما يفقد الأرقام)."""
    f.setdefault("hist", []).append(snapshot(f))
    f.update(state)
    f["step"] = step
    await flow_prompt(chat, ctx)


async def go_back(chat, ctx, f):
    prev = f["hist"].pop() if f.get("hist") else {"step": "root"}
    for k in NAV_KEYS:
        if k not in prev:
            f.pop(k, None)
    f.update(prev)
    await flow_prompt(chat, ctx)


async def start_flow(chat, ctx, typ, **extra):
    ctx.user_data["flow"] = {"type": typ, "step": FLOW_FIRST[typ], "hist": [], **extra}
    await flow_prompt(chat, ctx)


async def fail(msg, ctx, hint):
    await msg.reply_text(hint)
    await flow_prompt(msg.chat_id, ctx)


async def finish(msg, ctx, text, uid):
    ctx.user_data.pop("flow", None)
    await msg.reply_text(text, reply_markup=owner_markup(uid == OWNER_ID))


def flow_build(f):
    t, step = f["type"], f["step"]

    if step == "target":
        f["map"], items = {}, []
        for s in q("SELECT * FROM subjects ORDER BY pos, id"):
            f["map"][subject_label(s)] = ("s", s["id"])
            items.append((subject_label(s), s["color"]))
        for c in q("SELECT * FROM csections ORDER BY pos, id"):
            f["map"][csec_label(c)] = ("c", c["id"])
            items.append((csec_label(c), c["color"]))
        return "اختر المادة أو القسم:", pair(items)

    if step == "cbtn":
        f["map"], items = {}, []
        for b in q("SELECT * FROM cbuttons WHERE ptype='c' AND pid=? ORDER BY pos, id", (f["cid"],)):
            f["map"][b["name"]] = b["id"]
            items.append((b["name"], b["color"]))
        if not items:
            return "لا توجد أزرار داخل هذا القسم. أضف زراً من 🧩 تعديل الأزرار أولاً.", []
        return "اختر الزر داخل القسم:", pair(items)

    if step == "kind":
        return "اختر نوع المحتوى:", [
            [("📘 كتاب", "success"), ("📙 ملزمة", "success")],
            [("🧾 ملخص", "success"), ("📄 أسئلة وزارية", "danger")],
        ]

    if step == "qmode":
        return "أسئلة وزارية: كيف تريد إضافتها؟", [
            [("📄 ملف PDF وزاري", "primary")],
            [("🔘 داخل زر أسئلة", "success")],
        ]

    if step == "qyear":
        return "أرسل سنة الأسئلة (مثل 2024)، أو اضغط تخطي:", [[(SKIP, "primary")]]

    if step == "qround":
        return "اختر الدور، أو اضغط تخطي:", [
            [("الدور الأول", "success"), ("الدور الثاني", "primary"), ("الدور الثالث", "danger")],
            [(SKIP, "primary")],
        ]

    if step == "sumpick":
        f["map"], items = {}, []
        for r in sum_list(f["sid"]):
            f["map"][r["name"]] = r["id"]
            items.append((r["name"], "success"))
        return "اختر الفصل أو الوحدة للملخص:", pair(items)

    if step == "qpick":
        f["map"], items = {}, []
        for b in q("SELECT * FROM cbuttons WHERE ptype='q' AND pid=? ORDER BY pos, id", (f["sid"],)):
            f["map"][b["name"]] = b["id"]
            items.append((b["name"], b["color"]))
        return "اختر قسم الأسئلة:", pair(items)

    if step == "payload":
        if "bid" in f:
            return "أرسل الصور أو الملفات أو النص، أو ID: ثم الـ ID. عند الانتهاء اضغط تم.", [[(DONE, "success")]]
        rows = [[(DONE, "success")]] if f.get("loop") else []
        return "أرسل الملف أو الصورة، أو أرسل الـ ID كنص.", rows

    if step == "title":
        return "أرسل اسم الملف:", []

    if step == "teacher":
        return "أرسل اسم الأستاذ، أو اضغط تخطي:", [[(SKIP, "primary")]]

    if step in ("subj", "qsubj"):
        return "اختر المادة:", pair([(subject_label(s), s["color"])
                                      for s in q("SELECT * FROM subjects ORDER BY pos, id")])

    if step == "qbname":
        return "أرسل اسم الزر، مثل: أسئلة الشهر الأول:", []

    if step == "qbcolor":
        return "اختر لون الزر:", [COLOR_ROW]

    if step == "cname":
        return "أرسل اسم القسم الجديد:", []

    if step == "cemoji":
        return "أرسل إيموجي القسم:", []

    if step == "cmsg":
        return "أرسل الرسالة التي تظهر للطالب إذا كان القسم فارغاً، أو اضغط تخطي:", [[(SKIP, "primary")]]

    if step == "ccolor":
        return "اختر لون القسم والأزرار الجديدة فيه:", [COLOR_ROW]

    if step == "cbtns":
        listed = "\n".join(f"- {n}" for n in f["buttons"]) or "لا يوجد بعد"
        return f"أرسل اسم زر داخل القسم، وعند الانتهاء اضغط تم.\nالأزرار:\n{listed}", [[(DONE, "success")]]

    if step == "sname":
        return "أرسل اسم المادة الجديدة:", []

    if step == "semoji":
        return "أرسل إيموجي المادة، أو اضغط تخطي إذا لا تريد إيموجي:", [[(SKIP, "primary")]]

    if step == "sumnames":
        listed = "\n".join(f"- {n}" for n in f.get("sumnames", [])) or "لا يوجد بعد"
        return (
            "أرسل اسم فصل أو وحدة للملخصات واحداً تلو الآخر.\n"
            "عند الانتهاء اضغط تم، أو تخطَّ إذا لا تريد ملخصات.\n"
            f"المضاف:\n{listed}"
        ), [[(SKIP, "primary"), (DONE, "success")]]

    if step == "sfield":
        return "اختر ما تريد تعديله:", [[("✏️ الاسم", "success"), ("😀 الإيموجي", "success")]]

    if step == "svalue":
        rows = [[(SKIP, "primary")]] if f.get("col") == "emoji" else []
        return "أرسل القيمة الجديدة:", rows

    if step == "sact":
        return "اختر ما تريد فعله بفصول الملخصات:", [
            [("➕ فصل جديد", "success")],
            [("✏️ تعديل اسم فصل", "primary"), ("🗑 حذف فصل", "danger")],
        ]

    if step == "sadd":
        return "أرسل اسم الفصل أو الوحدة الجديد:", []

    if step in ("srpick", "sdpick"):
        f["map"], items = {}, []
        for r in sum_list(f["sid"]):
            f["map"][r["name"]] = r["id"]
            items.append((r["name"], "success" if step == "srpick" else "danger"))
        text = "اختر الفصل لتعديل اسمه:" if step == "srpick" else "اختر الفصل لحذفه:"
        if not items:
            text = "لا توجد فصول لهذه المادة بعد."
        return text, pair(items)

    if step == "srename":
        return "أرسل الاسم الجديد للفصل:", []

    if step == "file":
        f["map"] = {}
        rows = []
        for r in q("SELECT id, title FROM files ORDER BY id"):
            label = f"#{r['id']} {r['title']}"[:60]
            f["map"][label] = r["id"]
            rows.append([(label, "success")])
        return "اختر الملف، أو أرسل رقمه مثل #12:", rows

    if step == "ffield":
        rows = [[("✏️ الاسم", "success"), ("👨‍🏫 الأستاذ", "success")]]
        r = q1("SELECT kind FROM files WHERE id=?", (f.get("rid"),))
        if r and r["kind"] == "question":
            rows.append([("📅 السنة", "primary"), ("🔢 الدور", "primary")])
        return "اختر ما تريد تعديله:", rows

    if step == "fvalue":
        rows = [[(SKIP, "primary")]] if f.get("col") in ("teacher", "section", "month") else []
        if f.get("col") == "month":
            return "أرسل الدور (1 أو 2 أو 3، أو الأول/الثاني/الثالث):", rows
        return "أرسل القيمة الجديدة:", rows

    if step == "confirm":
        if f["do"][0] == "delsumsec":
            return "⚠️ سيتم حذف الفصل وكل ملخصاته. هل تؤكد؟", [[(CONFIRM, "danger")]]
        if f["do"][0] == "delch":
            return "⚠️ سيتم حذف القناة من الاشتراك الإجباري. هل تؤكد؟", [[(CONFIRM, "danger")]]
        return "هل تؤكد هذه العملية؟", [[(CONFIRM, "danger")]]

    if step == "csec":
        f["map"], items = {}, []
        for c in q("SELECT * FROM csections ORDER BY pos, id"):
            f["map"][csec_label(c)] = c["id"]
            items.append((csec_label(c), c["color"]))
        return "اختر القسم:", pair(items)

    if step == "wait":
        return "أرسل أي ملف أو صورة لأستخرج الـ ID:", []

    if step == "ftext":
        return f"الوصف الحالي:\n\n{setting('footer')}\n\nأرسل الوصف الجديد:", [[("🗑 حذف الوصف", "danger")]]

    if step == "btext":
        return "أرسل نص الإعلان:", []

    if step == "amenu":
        return "👥 إدارة المشرفين", [
            [("➕ إضافة مشرف", "success"), ("🗑 حذف مشرف", "danger")],
            [("📋 قائمة المشرفين", "primary")],
        ]

    if step == "aid":
        return "أرسل Telegram ID للمشرف الجديد:", []

    if step == "apick":
        f["map"], items = {}, []
        for a in q("SELECT user_id FROM admins"):
            items.append((f"#{a['user_id']}", "danger"))
        return "اختر المشرف للحذف:", pair(items)

    # ----- الاشتراك الإجباري -----
    if step == "smenu":
        status = "مفعّل" if setting("sub_on") == "1" else "معطّل"
        note = "\n⚠️ ما فيه قنوات، فالاشتراك ما يفرض شي." if not CHANNELS else ""
        return (f"🔒 الاشتراك الإجباري\nالحالة: {status}\nعدد القنوات: {len(CHANNELS)}{note}\nاختر:"), [
            [("➕ إضافة قناة", "success"), ("📋 القنوات والحذف", "primary")],
            [("⚙️ تشغيل/إيقاف الاشتراك", "primary")],
            [(BACK, "danger")],
        ]

    if step == "chref":
        return ("أرسل معرف القناة:\n- عامة: @username\n- خاصة: رقمها مثل -1001234567890\n"
                "البوت لازم يكون أدمن فيها."), [[(BACK, "danger")]]

    if step == "chlink":
        return ("القناة الخاصة ما قدرت أطلع لها رابط دعوة. "
                "أرسل رابط الدعوة (يبدأ بـ https://t.me/):"), [[(BACK, "danger")]]

    if step == "chlist":
        f["map"], items = {}, []
        for c in CHANNELS:
            label = f"🗑 {c['ref']}"[:60]
            f["map"][label] = c["id"]
            items.append((label, "danger"))
        text = "اختر القناة لحذفها:" if items else "لا توجد قنوات مضافة."
        return text, pair(items) + [[(BACK, "danger")]]

    # ----- المحرر: مادة/قسم ← أزرار ← زر داخل زر ... -----
    if step == "root":
        f["map"], items = {}, []
        for s in q("SELECT * FROM subjects ORDER BY pos, id"):
            f["map"][subject_label(s)] = ("s", s["id"])
            items.append((subject_label(s), s["color"]))
        for c in q("SELECT * FROM csections ORDER BY pos, id"):
            f["map"][csec_label(c)] = ("c", c["id"])
            items.append((csec_label(c), c["color"]))
        return "🧩 اختر المادة أو القسم:", pair(items) + [[(BACK, "danger")]]

    if step == "node":
        f["opts"] = {}
        if f["kind"] == "s":
            s = q1("SELECT * FROM subjects WHERE id=?", (f["id"],))
            hidden = hidden_set(s["hidden"])
            title = subject_label(s)
            for key, name in (("book", "📘 الكتب"), ("note", "📙 الملازم"),
                              ("summary", "🧾 الملخصات"), ("questions", "الأسئلة")):
                f["opts"][f"{name}: {'مخفي' if key in hidden else 'ظاهر'}"] = ("tog", key)
            f["opts"]["أزرار الأسئلة"] = ("blist", "q", f["id"])
        else:
            c = q1("SELECT * FROM csections WHERE id=?", (f["id"],))
            title = csec_label(c)
            f["opts"] = {
                "✏️ اسم القسم": ("field", "name"),
                "😀 إيموجي القسم": ("field", "emoji"),
                "📝 رسالة القسم": ("field", "message"),
                "👁 إظهار/إخفاء القسم": ("tvis",),
                "➕ زر جديد داخل القسم": ("newbtn", "c", f["id"]),
                "🗂 الأزرار الداخلية": ("blist", "c", f["id"]),
                "🗑 حذف القسم": ("delcs",),
            }
        rows = pair([(k, style_for(k)) for k in f["opts"]]) + [[(BACK, "danger")]]
        return f"⚙️ {title}\nاختر:", rows

    if step == "blist":
        f["map"], items = {}, []
        for b in q("SELECT * FROM cbuttons WHERE ptype=? AND pid=? ORDER BY pos, id", (f["kind"], f["id"])):
            label = b["name"] if b["visible"] else f"🙈 {b['name']}"
            f["map"][label] = b["id"]
            items.append((label, b["color"]))
        f["opts"] = {"➕ زر جديد هنا": ("newbtn", f["kind"], f["id"])}
        rows = pair(items) + [[("➕ زر جديد هنا", "success")], [(BACK, "danger")]]
        return ("🗂 الأزرار:" if items else "🗂 لا توجد أزرار بعد."), rows

    if step == "bnode":
        b = q1("SELECT * FROM cbuttons WHERE id=?", (f["bid"],))
        if not b:
            return "الزر غير موجود.", [[(BACK, "danger")]]
        f["opts"] = {
            "✏️ اسم الزر": ("bname",),
            "🎨 لون الزر": ("color",),
            "👁 إظهار/إخفاء الزر": ("tbtn",),
            "📥 إضافة محتوى": ("content",),
            "🧹 حذف المحتوى": ("clear",),
            "➕ زر داخل هذا الزر": ("newbtn", "b", f["bid"]),
            "🗂 الأزرار الداخلية": ("blist", "b", f["bid"]),
            "🗑 حذف الزر": ("delb",),
        }
        rows = pair([(k, style_for(k)) for k in f["opts"]]) + [[(BACK, "danger")]]
        return f"🔘 {b['name']}\nاختر:", rows

    if step == "bnew":
        return "أرسل اسم الزر الجديد:", []

    if step == "bcolor":
        return "اختر لون الزر الجديد:", [COLOR_ROW]

    if step == "bname":
        return "أرسل الاسم الجديد للزر:", []

    if step == "color":
        return "اختر اللون الجديد:", [COLOR_ROW]

    if step == "content":
        return "📥 أرسل المحتوى: نص أو صورة أو ملف، أو ID: ثم الـ ID.\nعند الانتهاء اضغط تم.", [[(DONE, "success")]]

    if step == "input":
        return "أرسل القيمة الجديدة:", []

    return "اختر من الأزرار:", []


def run_do(do):
    k = do[0]
    if k == "delsub":
        for b in q("SELECT id FROM cbuttons WHERE ptype IN ('s','q') AND pid=?", (do[1],)):
            purge_button(b["id"])
        x("DELETE FROM files WHERE subject_id=?", (do[1],))
        x("DELETE FROM sumsec WHERE subject_id=?", (do[1],))
        x("DELETE FROM subjects WHERE id=?", (do[1],))
    elif k == "delcs":
        for b in q("SELECT id FROM cbuttons WHERE ptype='c' AND pid=?", (do[1],)):
            purge_button(b["id"])
        x("DELETE FROM csections WHERE id=?", (do[1],))
    elif k == "delfile":
        x("DELETE FROM files WHERE id=?", (do[1],))
    elif k == "deladmin":
        x("DELETE FROM admins WHERE user_id=?", (do[1],))
        ADMIN_IDS.discard(do[1])
    elif k == "footer":
        set_setting("footer", do[1])
    elif k == "delbtn":
        purge_button(do[1])
    elif k == "clearc":
        x("UPDATE files SET cbutton_id=NULL WHERE cbutton_id=?", (do[1],))
        x("DELETE FROM content WHERE cbutton_id=?", (do[1],))
    elif k == "delsumsec":
        x("DELETE FROM files WHERE kind='summary' AND section=?", (str(do[1]),))
        x("DELETE FROM sumsec WHERE id=?", (do[1],))
    elif k == "delch":
        x("DELETE FROM channels WHERE id=?", (do[1],))
        load_channels()
        SUB_CACHE.clear()


async def h_confirm(msg, ctx, uid, f, text):
    if text != CONFIRM:
        return await fail(msg, ctx, "اضغط ✅ تأكيد أو ❌ إلغاء.")
    run_do(f["do"])
    if f["type"] in ("edit", "subs"):
        await msg.reply_text("✅ تم التنفيذ.")
        return await go_back(msg.chat_id, ctx, f)
    await finish(msg, ctx, "✅ تم التنفيذ.", uid)


async def save_subject_file(msg, ctx, uid, f, teacher):
    if f["kind"] == "summary":
        ok, err = insert_file(f["sid"], "summary", str(f["secid"]), None, f["title"], None, f["fid"], f["ftype"])
    elif f["kind"] == "question":
        ok, err = insert_file(f["sid"], "question", f.get("year"), f.get("round"), f["title"], None,
                              f["fid"], f["ftype"])
    else:
        ok, err = insert_file(f["sid"], f["kind"], None, None, f["title"], teacher, f["fid"], f["ftype"])
    return await finish(msg, ctx, "✅ تمت إضافة الملف." if ok else err, uid)


async def h_addfile(msg, ctx, uid, f, text, media):
    chat, step = msg.chat_id, f["step"]
    if step == "target":
        if text not in f.get("map", {}):
            return await fail(msg, ctx, "اختر من الأزرار.")
        kind, tid = f["map"][text]
        if kind == "s":
            f["sid"] = tid
            return await goto(chat, ctx, f, "kind")
        f["cid"] = tid
        return await goto(chat, ctx, f, "cbtn")

    if step == "cbtn":
        if text not in f.get("map", {}):
            return await fail(msg, ctx, "اختر الزر من الأزرار.")
        bid = f["map"][text]
        if f.get("fid"):
            insert_content(bid, f["ftype"], None, f["fid"])
            return await finish(msg, ctx, "✅ تمت الإضافة.", uid)
        f["bid"] = bid
        return await goto(chat, ctx, f, "payload")

    if step == "kind":
        k = FILE_KINDS.get(text)
        if not k:
            return await fail(msg, ctx, "اختر النوع من الأزرار.")
        f["kind"] = k
        if k == "summary":
            if not sum_list(f["sid"]):
                return await finish(msg, ctx, "لا توجد فصول للملخصات لهذه المادة. أضفها من ➕ إضافة زر للملخصات أولاً.", uid)
            return await goto(chat, ctx, f, "sumpick")
        if k == "question":
            return await goto(chat, ctx, f, "qmode")
        return await goto(chat, ctx, f, "title" if f.get("fid") else "payload")

    if step == "qmode":
        if text == "📄 ملف PDF وزاري":
            return await goto(chat, ctx, f, "title" if f.get("fid") else "payload")
        if text == "🔘 داخل زر أسئلة":
            if not q1("SELECT 1 FROM cbuttons WHERE ptype='q' AND pid=?", (f["sid"],)):
                return await finish(msg, ctx, "لا توجد أزرار للأسئلة لهذه المادة. أضفها من ➕ إضافة زر للأسئلة أولاً.", uid)
            return await goto(chat, ctx, f, "qpick")
        return await fail(msg, ctx, "اختر من الأزرار.")

    if step == "qyear":
        if text == SKIP:
            f["year"] = None
        elif re.fullmatch(r"\d{4}", text or ""):
            f["year"] = text
        else:
            return await fail(msg, ctx, "أرسل السنة بأربعة أرقام مثل 2024، أو اضغط تخطي.")
        return await goto(chat, ctx, f, "qround")

    if step == "qround":
        if text == SKIP:
            f["round"] = None
        else:
            code = parse_round(text)
            if not code:
                return await fail(msg, ctx, "اختر الدور من الأزرار.")
            f["round"] = code
        return await save_subject_file(msg, ctx, uid, f, None)

    if step == "sumpick":
        if text not in f.get("map", {}):
            return await fail(msg, ctx, "اختر الفصل من الأزرار.")
        f["secid"] = f["map"][text]
        return await goto(chat, ctx, f, "title" if f.get("fid") else "payload")

    if step == "qpick":
        if text not in f.get("map", {}):
            return await fail(msg, ctx, "اختر القسم من الأزرار.")
        bid = f["map"][text]
        if f.get("fid"):
            insert_content(bid, f["ftype"], None, f["fid"])
            return await finish(msg, ctx, "✅ تمت الإضافة إلى الأسئلة.", uid)
        f["bid"], f["loop"] = bid, True
        return await goto(chat, ctx, f, "payload")

    if step == "payload":
        if "bid" in f:
            if text == DONE:
                return await finish(msg, ctx, "✅ انتهت الإضافة.", uid)
            res = content_step(f["bid"], text, media)
            if res == "added":
                await msg.reply_text("✅ تمت الإضافة، أرسل التالي أو اضغط تم.")
                return await flow_prompt(chat, ctx)
            return await fail(msg, ctx, "أرسل نصاً أو صورة أو ملفاً، أو ID: ثم الـ ID.")
        fid, ftype = read_file_payload(text, media)
        if not fid:
            return await fail(msg, ctx, "أرسل الملف أو الـ ID.")
        f["fid"], f["ftype"] = fid, ftype
        return await goto(chat, ctx, f, "title")

    if step == "title":
        if not text:
            return await fail(msg, ctx, "أرسل الاسم كنص.")
        f["title"] = text
        if f["kind"] == "note":
            return await goto(chat, ctx, f, "teacher")
        if f["kind"] == "question":
            return await goto(chat, ctx, f, "qyear")
        return await save_subject_file(msg, ctx, uid, f, None)

    if step == "teacher":
        return await save_subject_file(msg, ctx, uid, f, None if text == SKIP else text)


async def h_addqbtn(msg, ctx, uid, f, text, media):
    chat, step = msg.chat_id, f["step"]
    if step == "qsubj":
        s = label_of_subject(text)
        if not s:
            return await fail(msg, ctx, "اختر المادة من الأزرار.")
        f["sid"] = s["id"]
        return await goto(chat, ctx, f, "qbname")
    if step == "qbname":
        if not text:
            return await fail(msg, ctx, "أرسل اسم الزر.")
        f["qname"] = text
        return await goto(chat, ctx, f, "qbcolor")
    if step == "qbcolor":
        if text not in COLORS:
            return await fail(msg, ctx, "اختر اللون من الأزرار.")
        pos = q1("SELECT COALESCE(MAX(pos), 0) + 1 AS p FROM cbuttons WHERE ptype='q' AND pid=?", (f["sid"],))["p"]
        cur = x("INSERT INTO cbuttons(section_id, ptype, pid, name, color, pos) VALUES(NULL, 'q', ?, ?, ?, ?)",
                (f["sid"], f["qname"], COLORS[text], pos))
        f["bid"] = cur.lastrowid
        await msg.reply_text("✅ تم إنشاء الزر. أرسل صوره أو ملفاته أو نصه الآن، وعند الانتهاء اضغط تم.")
        return await goto(chat, ctx, f, "content")
    if step == "content":
        res = content_step(f["bid"], text, media)
        if res == "done":
            return await finish(msg, ctx, "✅ انتهت الإضافة.", uid)
        if res == "added":
            await msg.reply_text("✅ تمت الإضافة، أرسل التالي أو اضغط تم.")
            return await flow_prompt(chat, ctx)
        return await fail(msg, ctx, "أرسل نصاً أو صورة أو ملفاً، أو ID: ثم الـ ID.")


async def h_addsummary(msg, ctx, uid, f, text, media):
    chat, step = msg.chat_id, f["step"]
    if step == "subj":
        s = label_of_subject(text)
        if not s:
            return await fail(msg, ctx, "اختر المادة من الأزرار.")
        f["sid"] = s["id"]
        if not sum_list(s["id"]):
            return await finish(msg, ctx, "لا توجد فصول للملخصات لهذه المادة. أضفها من ➕ إضافة زر للملخصات أولاً.", uid)
        return await goto(chat, ctx, f, "sumpick")
    if step == "sumpick":
        if text not in f.get("map", {}):
            return await fail(msg, ctx, "اختر الفصل من الأزرار.")
        f["secid"], f["loop"] = f["map"][text], True
        return await goto(chat, ctx, f, "payload")
    if step == "payload":
        if text == DONE:
            return await finish(msg, ctx, "✅ انتهت الإضافة.", uid)
        fid, ftype = read_file_payload(text, media)
        if not fid:
            return await fail(msg, ctx, "أرسل الملف أو الـ ID، أو اضغط تم.")
        s = q1("SELECT name FROM subjects WHERE id=?", (f["sid"],))
        title = f"ملخص {s['name']} - {sum_name(str(f['secid']))}"
        ok, err = insert_file(f["sid"], "summary", str(f["secid"]), None, title, None, fid, ftype)
        await msg.reply_text("✅ تمت الإضافة، أرسل التالي أو اضغط تم." if ok else err)
        return await flow_prompt(chat, ctx)


async def h_addsumbtn(msg, ctx, uid, f, text, media):
    chat, step = msg.chat_id, f["step"]
    if step == "subj":
        s = label_of_subject(text)
        if not s:
            return await fail(msg, ctx, "اختر المادة من الأزرار.")
        f["sid"] = s["id"]
        return await goto(chat, ctx, f, "sact")
    if step == "sact":
        if text == "➕ فصل جديد":
            return await goto(chat, ctx, f, "sadd")
        if text == "✏️ تعديل اسم فصل":
            return await goto(chat, ctx, f, "srpick")
        if text == "🗑 حذف فصل":
            return await goto(chat, ctx, f, "sdpick")
        return await fail(msg, ctx, "اختر من الأزرار.")
    if step == "sadd":
        if not text:
            return await fail(msg, ctx, "أرسل اسم الفصل.")
        pos = q1("SELECT COALESCE(MAX(pos), 0) + 1 AS p FROM sumsec WHERE subject_id=?", (f["sid"],))["p"]
        x("INSERT INTO sumsec(subject_id, name, pos) VALUES(?, ?, ?)", (f["sid"], text, pos))
        await msg.reply_text("✅ تمت إضافة الفصل.")
        return await goto(chat, ctx, f, "sact")
    if step == "srpick":
        if text not in f.get("map", {}):
            return await fail(msg, ctx, "اختر الفصل من الأزرار.")
        f["secid"] = f["map"][text]
        return await goto(chat, ctx, f, "srename")
    if step == "srename":
        if not text:
            return await fail(msg, ctx, "أرسل الاسم الجديد.")
        x("UPDATE sumsec SET name=? WHERE id=?", (text, f["secid"]))
        return await finish(msg, ctx, "✅ تم تعديل اسم الفصل.", uid)
    if step == "sdpick":
        if text not in f.get("map", {}):
            return await fail(msg, ctx, "اختر الفصل من الأزرار.")
        f["do"] = ("delsumsec", f["map"][text])
        return await goto(chat, ctx, f, "confirm")


async def h_addsection(msg, ctx, uid, f, text, media):
    chat, step = msg.chat_id, f["step"]
    if step == "cname":
        if not text:
            return await fail(msg, ctx, "أرسل اسم القسم.")
        f["cname"] = text
        return await goto(chat, ctx, f, "cemoji")
    if step == "cemoji":
        if not text:
            return await fail(msg, ctx, "أرسل إيموجي القسم.")
        f["cemoji"] = text
        return await goto(chat, ctx, f, "cmsg")
    if step == "cmsg":
        f["cmsg"] = "" if text == SKIP else text
        return await goto(chat, ctx, f, "ccolor")
    if step == "ccolor":
        if text not in COLORS:
            return await fail(msg, ctx, "اختر اللون من الأزرار.")
        f["ccolor"], f["buttons"] = COLORS[text], []
        return await goto(chat, ctx, f, "cbtns")
    if step == "cbtns":
        if text == DONE:
            try:
                pos = q1("SELECT COALESCE(MAX(pos), 0) + 1 AS p FROM csections")["p"]
                cur = DB.execute(
                    "INSERT INTO csections(name, emoji, color, pos, message) VALUES(?, ?, ?, ?, ?)",
                    (f["cname"], f["cemoji"], f["ccolor"], pos, f["cmsg"]),
                )
                for i, name in enumerate(f["buttons"], 1):
                    DB.execute(
                        "INSERT INTO cbuttons(section_id, ptype, pid, name, color, pos) VALUES(?, 'c', ?, ?, ?, ?)",
                        (cur.lastrowid, cur.lastrowid, name, f["ccolor"], i),
                    )
                DB.commit()
            except sqlite3.IntegrityError:
                DB.rollback()
                return await finish(msg, ctx, "اسم القسم مستخدم من قبل.", uid)
            return await finish(msg, ctx, f"✅ تم إنشاء القسم: {f['cemoji']} {f['cname']}", uid)
        if not text:
            return await fail(msg, ctx, "أرسل اسم الزر.")
        if text in f["buttons"]:
            return await fail(msg, ctx, "هذا الزر موجود مسبقاً.")
        f["buttons"].append(text)
        return await flow_prompt(chat, ctx)


async def h_addsubject(msg, ctx, uid, f, text, media):
    chat, step = msg.chat_id, f["step"]
    if step == "sname":
        if not text:
            return await fail(msg, ctx, "أرسل اسم المادة.")
        f["sname"] = text
        return await goto(chat, ctx, f, "semoji")
    if step == "semoji":
        f["semoji"] = "" if text == SKIP else text
        return await goto(chat, ctx, f, "sumnames")
    if step == "sumnames":
        if text == SKIP:
            names = []
        elif text == DONE:
            names = f.get("sumnames", [])
        else:
            if not text:
                return await fail(msg, ctx, "أرسل اسم الفصل أو اضغط تم أو تخطي.")
            f.setdefault("sumnames", []).append(text)
            return await flow_prompt(chat, ctx)
        try:
            create_subject(f["sname"], f["semoji"], names)
        except sqlite3.IntegrityError:
            return await finish(msg, ctx, "هذه المادة موجودة مسبقاً.", uid)
        return await finish(msg, ctx, "✅ تمت إضافة المادة.", uid)


async def h_editsubject(msg, ctx, uid, f, text, media):
    chat, step = msg.chat_id, f["step"]
    if step == "subj":
        s = label_of_subject(text)
        if not s:
            return await fail(msg, ctx, "اختر المادة من الأزرار.")
        f["sid"] = s["id"]
        return await goto(chat, ctx, f, "sfield")
    if step == "sfield":
        col = {"✏️ الاسم": "name", "😀 الإيموجي": "emoji"}.get(text)
        if not col:
            return await fail(msg, ctx, "اختر من الأزرار.")
        f["col"] = col
        return await goto(chat, ctx, f, "svalue")
    if step == "svalue":
        if f["col"] == "emoji" and text == SKIP:
            value = ""
        elif not text:
            return await fail(msg, ctx, "أرسل القيمة.")
        else:
            value = text
        try:
            x(f"UPDATE subjects SET {f['col']}=? WHERE id=?", (value, f["sid"]))
        except sqlite3.IntegrityError:
            return await finish(msg, ctx, "هذا الاسم مستخدم من مادة أخرى.", uid)
        return await finish(msg, ctx, "✅ تم التعديل.", uid)


async def h_delsubject(msg, ctx, uid, f, text, media):
    s = label_of_subject(text)
    if not s:
        return await fail(msg, ctx, "اختر المادة من الأزرار.")
    f["do"] = ("delsub", s["id"])
    return await goto(msg.chat_id, ctx, f, "confirm")


async def h_delsection(msg, ctx, uid, f, text, media):
    if text not in f.get("map", {}):
        return await fail(msg, ctx, "اختر القسم من الأزرار.")
    f["do"] = ("delcs", f["map"][text])
    return await goto(msg.chat_id, ctx, f, "confirm")


async def h_editfile(msg, ctx, uid, f, text, media):
    chat, step = msg.chat_id, f["step"]
    if step == "file":
        rid = resolve_file(f, text)
        if rid is None:
            return await fail(msg, ctx, "اختر الملف من الأزرار أو أرسل رقمه مثل #12.")
        f["rid"] = rid
        return await goto(chat, ctx, f, "ffield")
    if step == "ffield":
        col = {"✏️ الاسم": "title", "👨‍🏫 الأستاذ": "teacher", "📅 السنة": "section", "🔢 الدور": "month"}.get(text)
        if not col:
            return await fail(msg, ctx, "اختر من الأزرار.")
        f["col"] = col
        return await goto(chat, ctx, f, "fvalue")
    if step == "fvalue":
        if f["col"] in ("teacher", "section", "month") and text == SKIP:
            value = None
        elif not text:
            return await fail(msg, ctx, "أرسل القيمة.")
        elif f["col"] == "month":
            value = parse_round(text)
            if not value:
                return await fail(msg, ctx, "أرسل 1 أو 2 أو 3، أو الأول/الثاني/الثالث.")
        else:
            value = text
        x(f"UPDATE files SET {f['col']}=? WHERE id=?", (value, f["rid"]))
        return await finish(msg, ctx, "✅ تم التعديل.", uid)


async def h_replacefile(msg, ctx, uid, f, text, media):
    chat, step = msg.chat_id, f["step"]
    if step == "file":
        rid = resolve_file(f, text)
        if rid is None:
            return await fail(msg, ctx, "اختر الملف من الأزرار.")
        f["rid"] = rid
        return await goto(chat, ctx, f, "payload")
    if step == "payload":
        fid, ftype = read_file_payload(text, media)
        if not fid:
            return await fail(msg, ctx, "أرسل الملف أو الـ ID.")
        try:
            x("UPDATE files SET file_id=?, ftype=? WHERE id=?", (fid, ftype, f["rid"]))
        except sqlite3.IntegrityError:
            return await finish(msg, ctx, "هذا الملف مستخدم في ملف آخر.", uid)
        return await finish(msg, ctx, "✅ تم استبدال الملف.", uid)


async def h_deletefile(msg, ctx, uid, f, text, media):
    rid = resolve_file(f, text)
    if rid is None:
        return await fail(msg, ctx, "اختر الملف من الأزرار.")
    f["do"] = ("delfile", rid)
    return await goto(msg.chat_id, ctx, f, "confirm")


async def h_togglefile(msg, ctx, uid, f, text, media):
    rid = resolve_file(f, text)
    if rid is None:
        return await fail(msg, ctx, "اختر الملف من الأزرار.")
    x("UPDATE files SET visible = 1 - visible WHERE id=?", (rid,))
    row = q1("SELECT visible FROM files WHERE id=?", (rid,))
    return await finish(msg, ctx, "✅ تم. الحالة الآن: " + ("ظاهر" if row["visible"] else "مخفي"), uid)


async def h_identify(msg, ctx, uid, f, text, media):
    if not media[0]:
        return await fail(msg, ctx, "أرسل ملفاً أو صورة.")
    ctx.user_data["pending"] = media
    markup = InlineKeyboardMarkup([[InlineKeyboardButton(
        "➕ إضافة هذا الملف للبوت", callback_data="idadd", style="success")]])
    await msg.reply_text(
        f"📄 الاسم: {html.escape(media_name(msg))}\n🆔 الـ ID (اضغط عليه للنسخ):\n<code>{media[0]}</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=markup,
    )
    return await flow_prompt(msg.chat_id, ctx)


async def h_genlink(msg, ctx, uid, f, text, media):
    rid = resolve_file(f, text)
    if rid is None:
        row = q1("SELECT id FROM files WHERE file_id=?", (text,))
        rid = row["id"] if row else None
    if rid is None:
        return await fail(msg, ctx, "لم أجد هذا الملف. أرسل الـ ID أو رقم الملف.")
    link = f"https://t.me/{ctx.bot.username}?start=f{rid}"
    return await finish(msg, ctx, f"🔗 رابط الملف:\n{link}", uid)


async def h_footer(msg, ctx, uid, f, text, media):
    if text == "🗑 حذف الوصف":
        f["do"] = ("footer", "")
        return await goto(msg.chat_id, ctx, f, "confirm")
    if not text:
        return await fail(msg, ctx, "أرسل الوصف الجديد كنص.")
    set_setting("footer", text)
    return await finish(msg, ctx, "✅ تم تحديث الوصف.", uid)


async def h_broadcast(msg, ctx, uid, f, text, media):
    if not text:
        return await fail(msg, ctx, "أرسل نص الإعلان.")
    if tg_len(text) > TEXT_LIMIT:
        return await fail(msg, ctx, f"نص الإعلان أطول من الحد ({TEXT_LIMIT} حرف).")
    if BCAST["running"]:
        return await finish(msg, ctx, "يوجد إعلان قيد الإرسال، انتظر حتى ينتهي.", uid)
    spawn(run_broadcast(ctx.bot, text, msg.chat_id))
    return await finish(msg, ctx, "⏳ بدأ الإرسال، وبيوصلك التقرير لما ينتهي.", uid)


async def h_admins(msg, ctx, uid, f, text, media):
    chat, step = msg.chat_id, f["step"]
    if step == "amenu":
        if text == "➕ إضافة مشرف":
            return await goto(chat, ctx, f, "aid")
        if text == "🗑 حذف مشرف":
            return await goto(chat, ctx, f, "apick")
        if text == "📋 قائمة المشرفين":
            listed = "\n".join(f"#{a['user_id']}" for a in q("SELECT user_id FROM admins")) or "لا يوجد مشرفون."
            return await finish(msg, ctx, f"👥 المشرفون:\n{listed}", uid)
        return await fail(msg, ctx, "اختر من الأزرار.")
    if step == "aid":
        if not text.isdigit():
            return await fail(msg, ctx, "أرسل Telegram ID رقمياً.")
        x("INSERT OR IGNORE INTO admins(user_id, added) VALUES(?, ?)", (int(text), now()))
        ADMIN_IDS.add(int(text))
        return await finish(msg, ctx, "✅ تمت إضافة المشرف.", uid)
    if step == "apick":
        m = re.match(r"#(\d+)", text)
        if not m:
            return await fail(msg, ctx, "اختر المشرف من الأزرار.")
        f["do"] = ("deladmin", int(m.group(1)))
        return await goto(chat, ctx, f, "confirm")


async def save_channel(msg, ctx, f, ref, title, link):
    x("INSERT OR IGNORE INTO channels(ref, title, link, added) VALUES(?, ?, ?, ?)", (ref, title, link, now()))
    load_channels()
    SUB_CACHE.clear()
    await msg.reply_text(f"✅ تمت إضافة القناة: {title}")
    return await go_back(msg.chat_id, ctx, f)


async def h_subs(msg, ctx, uid, f, text, media):
    chat, step, bot = msg.chat_id, f["step"], ctx.bot

    if step == "smenu":
        if text == "➕ إضافة قناة":
            return await enter(chat, ctx, f, "chref")
        if text == "📋 القنوات والحذف":
            return await enter(chat, ctx, f, "chlist")
        if text == "⚙️ تشغيل/إيقاف الاشتراك":
            set_setting("sub_on", "0" if setting("sub_on") == "1" else "1")
            SUB_CACHE.clear()
            return await flow_prompt(chat, ctx)
        return await fail(msg, ctx, "اختر من الأزرار.")

    if step == "chref":
        ref = parse_ref(text)
        if not ref:
            return await fail(msg, ctx, "أرسل معرف القناة مثل @channel، أو رقمها مثل -1001234567890.")
        if any(c["ref"] == ref for c in CHANNELS):
            return await fail(msg, ctx, "هذه القناة مضافة مسبقاً.")
        try:
            info = await bot.get_chat(chat_arg(ref))
            me = await bot.get_chat_member(chat_arg(ref), bot.id)
        except TelegramError:
            return await fail(msg, ctx, "ما قدرت أوصل للقناة. تأكد من المعرف، وأن البوت موجود فيها.")
        if me.status not in ("administrator", "creator"):
            return await fail(msg, ctx, "البوت مو أدمن في القناة. ارفعه أدمن ثم أرسل المعرف من جديد.")
        title = info.title or ref
        if info.username:
            ref = "@" + info.username
            if any(c["ref"] == ref for c in CHANNELS):
                return await fail(msg, ctx, "هذه القناة مضافة مسبقاً.")
            return await save_channel(msg, ctx, f, ref, title, f"https://t.me/{info.username}")
        # قناة خاصة: ننشئ رابط دعوة جديد بدون ما نلغي الروابط القديمة
        try:
            invite = await bot.create_chat_invite_link(chat_arg(ref))
            link = invite.invite_link
        except TelegramError:
            link = ""
        if link:
            return await save_channel(msg, ctx, f, ref, title, link)
        f["chref"], f["chtitle"] = ref, title
        return await goto(chat, ctx, f, "chlink")

    if step == "chlink":
        link = (text or "").strip()
        if not (link.startswith("https://t.me/") or link.startswith("https://telegram.me/")):
            return await fail(msg, ctx, "أرسل رابط دعوة صحيح يبدأ بـ https://t.me/")
        return await save_channel(msg, ctx, f, f["chref"], f["chtitle"], link)

    if step == "chlist":
        cid = f.get("map", {}).get(text)
        if cid is None:
            return await fail(msg, ctx, "اختر القناة من الأزرار.")
        f["do"] = ("delch", cid)
        return await enter(chat, ctx, f, "confirm")

    return await fail(msg, ctx, "اختر من الأزرار.")


async def h_edit(msg, ctx, uid, f, text, media):
    chat, step = msg.chat_id, f["step"]
    if text == BACK:
        if f.get("hist"):
            return await go_back(chat, ctx, f)
        return await finish(msg, ctx, "تم الخروج من تعديل الأزرار.", uid)

    if step == "root":
        if text not in f.get("map", {}):
            return await fail(msg, ctx, "اختر من الأزرار.")
        kind, eid = f["map"][text]
        return await enter(chat, ctx, f, "node", kind=kind, id=eid)

    if step == "node":
        act = f.get("opts", {}).get(text)
        if not act:
            return await fail(msg, ctx, "اختر من الأزرار.")
        k = act[0]
        if k == "tog":
            s = q1("SELECT hidden FROM subjects WHERE id=?", (f["id"],))
            hidden = hidden_set(s["hidden"]) ^ {act[1]}
            x("UPDATE subjects SET hidden=? WHERE id=?", (",".join(sorted(hidden)), f["id"]))
            return await flow_prompt(chat, ctx)
        if k == "tvis":
            x("UPDATE csections SET visible = 1 - visible WHERE id=?", (f["id"],))
            return await flow_prompt(chat, ctx)
        if k == "field":
            return await enter(chat, ctx, f, "input", field=act[1])
        if k == "newbtn":
            return await enter(chat, ctx, f, "bnew", ptype=act[1], pid=act[2])
        if k == "blist":
            return await enter(chat, ctx, f, "blist", kind=act[1], id=act[2])
        if k == "delcs":
            f["do"] = ("delcs", f["id"])
            f["step"] = "confirm"
            return await flow_prompt(chat, ctx)
        return await fail(msg, ctx, "اختر من الأزرار.")

    if step == "blist":
        act = f.get("opts", {}).get(text)
        if act and act[0] == "newbtn":
            return await enter(chat, ctx, f, "bnew", ptype=act[1], pid=act[2])
        cbid = f.get("map", {}).get(text)
        if cbid is None:
            return await fail(msg, ctx, "اختر الزر من الأزرار.")
        return await enter(chat, ctx, f, "bnode", bid=cbid)

    if step == "bnode":
        act = f.get("opts", {}).get(text)
        if not act:
            return await fail(msg, ctx, "اختر من الأزرار.")
        k = act[0]
        if k == "bname":
            return await enter(chat, ctx, f, "bname")
        if k == "color":
            return await enter(chat, ctx, f, "color")
        if k == "tbtn":
            x("UPDATE cbuttons SET visible = 1 - visible WHERE id=?", (f["bid"],))
            return await flow_prompt(chat, ctx)
        if k == "content":
            return await enter(chat, ctx, f, "content")
        if k == "clear":
            f["do"] = ("clearc", f["bid"])
            return await enter(chat, ctx, f, "confirm")
        if k == "newbtn":
            return await enter(chat, ctx, f, "bnew", ptype=act[1], pid=act[2])
        if k == "blist":
            return await enter(chat, ctx, f, "blist", kind=act[1], id=act[2])
        if k == "delb":
            f["do"] = ("delbtn", f["bid"])
            f["step"] = "confirm"
            return await flow_prompt(chat, ctx)
        return await fail(msg, ctx, "اختر من الأزرار.")

    if step == "bnew":
        if not text:
            return await fail(msg, ctx, "أرسل اسم الزر.")
        f["bname"] = text
        return await goto(chat, ctx, f, "bcolor")

    if step == "bcolor":
        if text not in COLORS:
            return await fail(msg, ctx, "اختر اللون من الأزرار.")
        pos = q1("SELECT COALESCE(MAX(pos), 0) + 1 AS p FROM cbuttons WHERE ptype=? AND pid=?",
                 (f["ptype"], f["pid"]))["p"]
        sec_id = f["pid"] if f["ptype"] == "c" else None
        x("INSERT INTO cbuttons(section_id, ptype, pid, name, color, pos) VALUES(?, ?, ?, ?, ?, ?)",
          (sec_id, f["ptype"], f["pid"], f["bname"], COLORS[text], pos))
        await msg.reply_text("✅ تمت إضافة الزر.")
        return await go_back(chat, ctx, f)

    if step == "bname":
        if not text:
            return await fail(msg, ctx, "أرسل الاسم.")
        x("UPDATE cbuttons SET name=? WHERE id=?", (text, f["bid"]))
        return await go_back(chat, ctx, f)

    if step == "color":
        if text not in COLORS:
            return await fail(msg, ctx, "اختر اللون من الأزرار.")
        x("UPDATE cbuttons SET color=? WHERE id=?", (COLORS[text], f["bid"]))
        return await go_back(chat, ctx, f)

    if step == "content":
        res = content_step(f["bid"], text, media)
        if res == "done":
            return await go_back(chat, ctx, f)
        if res == "added":
            await msg.reply_text("✅ تمت الإضافة.")
            return await flow_prompt(chat, ctx)
        return await fail(msg, ctx, "أرسل نصاً أو صورة أو ملفاً، أو ID: ثم الـ ID.")

    if step == "input":
        if not text:
            return await fail(msg, ctx, "أرسل القيمة.")
        col = f.get("field")
        if col not in ("name", "emoji", "message"):
            return await fail(msg, ctx, "اختر من الأزرار.")
        try:
            x(f"UPDATE csections SET {col}=? WHERE id=?", (text, f["id"]))
        except sqlite3.IntegrityError:
            return await fail(msg, ctx, "هذا الاسم مستخدم من قسم آخر.")
        return await go_back(chat, ctx, f)

    return await fail(msg, ctx, "اختر من الأزرار.")


FLOW_HANDLERS = {
    "addfile": h_addfile,
    "addqbtn": h_addqbtn,
    "addsummary": h_addsummary,
    "addsumbtn": h_addsumbtn,
    "addsection": h_addsection,
    "addsubject": h_addsubject,
    "editsubject": h_editsubject,
    "delsubject": h_delsubject,
    "delsection": h_delsection,
    "editfile": h_editfile,
    "replacefile": h_replacefile,
    "deletefile": h_deletefile,
    "togglefile": h_togglefile,
    "identify": h_identify,
    "genlink": h_genlink,
    "footer": h_footer,
    "broadcast": h_broadcast,
    "admins": h_admins,
    "subs": h_subs,
    "edit": h_edit,
}


async def handle_flow(msg, ctx, uid):
    f = ctx.user_data.get("flow")
    if not f:
        return False
    text = (msg.text or "").strip()
    media = media_payload(msg)

    if text == BACK and f["step"] != "confirm":
        if f["type"] in ("subs", "edit"):
            if f.get("hist"):
                await go_back(msg.chat_id, ctx, f)
            else:
                ctx.user_data.pop("flow", None)
                await msg.reply_text("تم الخروج.", reply_markup=owner_markup(uid == OWNER_ID))
            return True
        ctx.user_data.pop("flow", None)
        await msg.reply_text("تم الإلغاء.", reply_markup=owner_markup(uid == OWNER_ID))
        return True

    if f["step"] == "confirm":
        await h_confirm(msg, ctx, uid, f, text)
        return True
    handler = FLOW_HANDLERS.get(f["type"])
    if handler is None:
        ctx.user_data.pop("flow", None)
        return False
    await handler(msg, ctx, uid, f, text, media)
    return True

async def on_inline(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    iq = update.inline_query
    if not iq:
        return
    token = iq.query.strip()
    results = []
    if setting("bot_on") == "1" and re.fullmatch(r"[fc]\d+", token):
        link = f"https://t.me/{ctx.bot.username}?start={token}"
        if token[0] == "f":
            row = q1("SELECT * FROM files WHERE id=? AND visible=1", (int(token[1:]),))
            if row:
                name = row["teacher"] if row["kind"] == "note" and row["teacher"] else row["title"]
                results.append(InlineQueryResultArticle(
                    id=token, title=name[:64], description="اضغط لإرسال رابط الملف",
                    input_message_content=InputTextMessageContent(f"{name}\n{link}"),
                ))
        else:
            cb = q1("SELECT * FROM cbuttons WHERE id=? AND visible=1", (int(token[1:]),))
            if cb:
                results.append(InlineQueryResultArticle(
                    id=token, title=f"📦 {cb['name']}"[:64], description="اضغط لإرسال رابط المحتوى",
                    input_message_content=InputTextMessageContent(f"{cb['name']}\n{link}"),
                ))
    await iq.answer(results, cache_time=0, is_personal=True)


# ============================================================
# أوامر وأحداث البوت
# ============================================================

async def safe_answer(cb, *args, **kwargs):
    try:
        await cb.answer(*args, **kwargs)
    except TelegramError:
        pass


async def gate_block(ctx, uid):
    """يرجع (نص، markup) إذا الطالب ممنوع (صيانة/اشتراك)، وإلا None."""
    if not is_staff(uid) and setting("bot_on") == "0":
        return MAINT_TEXT, None
    state = await member_state(ctx.bot, uid)
    if state != "ok":
        return gate_text(state), state
    return None


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg, user = update.effective_message, update.effective_user
    if not msg or not user:
        return
    uid = user.id
    upsert_user(uid)
    ctx.user_data.pop("flow", None)
    token = ctx.args[0] if ctx.args else ""
    token = token if re.fullmatch(r"[fc]\d+", token) else ""
    if not is_staff(uid) and setting("bot_on") == "0":
        await msg.reply_text(MAINT_TEXT)
        return
    state = await member_state(ctx.bot, uid)
    if state != "ok":
        await msg.reply_text(gate_text(state), reply_markup=gate_markup(token))
        return
    if token:
        await deliver(ctx, msg.chat_id, token, uid)
    await send_home(msg.chat_id, ctx, uid)


async def cmd_top(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg, user = update.effective_message, update.effective_user
    if not msg or not user:
        return
    uid = user.id
    upsert_user(uid)
    block = await gate_block(ctx, uid)
    if block:
        text, state = block
        await msg.reply_text(text, reply_markup=gate_markup() if state else None)
        return
    text, markup = build_top()
    await msg.reply_text(text, reply_markup=markup)


async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user and is_staff(user.id):
        await open_panel(update.effective_chat.id, ctx, user.id == OWNER_ID)


async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user and is_staff(user.id):
        ctx.user_data.pop("flow", None)
        await update.effective_message.reply_text("تم الإلغاء.", reply_markup=owner_markup(user.id == OWNER_ID))


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg, user = update.effective_message, update.effective_user
    if not msg or not user or not msg.text:
        return
    uid = user.id
    upsert_user(uid)
    text = msg.text.strip()
    staff, is_owner = is_staff(uid), uid == OWNER_ID

    if not staff and setting("bot_on") == "0":
        await msg.reply_text(MAINT_TEXT)
        return
    state = await member_state(ctx.bot, uid)
    if state != "ok":
        await msg.reply_text(gate_text(state), reply_markup=gate_markup())
        return

    if staff:
        if text == CANCEL:
            ctx.user_data.pop("flow", None)
            await msg.reply_text("تم الإلغاء.", reply_markup=owner_markup(is_owner))
            return
        if text in OWNER_ACTIONS:
            if text in OWNER_ONLY and not is_owner:
                await msg.reply_text("هذا الزر للمالك فقط.")
                return
            await run_owner_action(msg, ctx, uid, text)
            return
        if await handle_flow(msg, ctx, uid):
            return

    if text in (BACK, CANCEL) or len(text) < 2:
        return
    # أي نص من الطالب = بحث عن ملف بالاسم
    text_out, markup = build_search(text)
    await tg_retry(msg.reply_text, text_out, reply_markup=markup)


async def on_media(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg, user = update.effective_message, update.effective_user
    if msg and user and is_staff(user.id):
        await handle_flow(msg, ctx, user.id)


async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cb = update.callback_query
    if not cb or not cb.data:
        return
    uid = cb.from_user.id
    chat = cb.message.chat_id if cb.message else uid
    upsert_user(uid)
    data = cb.data

    if data.startswith("chk:"):
        token = data[4:]
        token = token if re.fullmatch(r"[fc]\d+", token) else ""
        if not is_staff(uid) and setting("bot_on") == "0":
            await safe_answer(cb, MAINT_TEXT, show_alert=True)
            return
        state = await member_state(ctx.bot, uid)
        if state == "no":
            await safe_answer(cb, "لم تشترك بعد", show_alert=True)
            return
        if state == "err":
            await safe_answer(cb, GATE_ERR_TEXT, show_alert=True)
            return
        await safe_answer(cb, "تم التحقق ✅")
        if token:
            await deliver(ctx, chat, token, uid)
        await show(cb, ctx, *build_home(is_staff(uid)))
        return

    if data == "idadd":
        await safe_answer(cb)
        if not is_staff(uid):
            return
        pending = ctx.user_data.pop("pending", None)
        if not pending:
            await ctx.bot.send_message(chat, "انتهى الطلب، أعد التعرف على الملف.")
            return
        await start_flow(chat, ctx, "addfile", fid=pending[0], ftype=pending[1])
        return

    # ----- أزرار الطالب -----
    if not is_staff(uid) and setting("bot_on") == "0":
        await safe_answer(cb, MAINT_TEXT, show_alert=True)
        return
    state = await member_state(ctx.bot, uid)
    if state != "ok":
        await safe_answer(cb, "اشترك بالقناتين أولاً" if state == "no" else GATE_ERR_TEXT, show_alert=True)
        await show(cb, ctx, gate_text(state), gate_markup())
        return
    # الرد على الضغطة فوراً بالتوازي مع التنفيذ، حتى ما يظهر تعليق على الزر
    await asyncio.gather(safe_answer(cb), do_nav(cb, ctx, data, uid))



async def on_error(update: object, ctx: ContextTypes.DEFAULT_TYPE):
    log.error("Unhandled error", exc_info=ctx.error)
    try:
        if isinstance(update, Update):
            if update.callback_query:
                await safe_answer(update.callback_query, "صار خطأ غير متوقع، حاول مرة ثانية.")
            elif update.effective_message:
                await update.effective_message.reply_text("صار خطأ غير متوقع، حاول مرة ثانية.")
    except TelegramError:
        pass


async def post_init(app):
    try:
        await app.bot.set_my_commands([
            BotCommand("start", "القائمة الرئيسية"),
            BotCommand("top", "الملفات الأكثر تحميلاً"),
        ])
    except TelegramError as e:
        log.warning("set_my_commands failed: %s", e)


# ============================================================
# التشغيل
# ============================================================

def main():
    if not BOT_TOKEN:
        raise RuntimeError("لم يتم ضبط BOT_TOKEN. أضف التوكن في متغيرات البيئة في الاستضافة.")
    init_db()
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)
        .connection_pool_size(256)
        .pool_timeout(10)
        .read_timeout(20)
        .write_timeout(30)
        .connect_timeout(10)
        .get_updates_connection_pool_size(4)
        .post_init(post_init)
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("top", cmd_top))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(InlineQueryHandler(on_inline))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(MessageHandler((filters.Document.ALL | filters.PHOTO) & ~filters.COMMAND, on_media))
    app.add_error_handler(on_error)
    log.info("Bot is running.")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=False)


if __name__ == "__main__":
    main()
