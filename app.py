# -*- coding: utf-8 -*-
"""
Petal Blog · 樱羽小筑
====================
Flask + SQLite 个人博客：
  - 毛玻璃 + 樱花粉主题（风格继承参考项目 yingaobichibang）
  - 首页/文章页 3:1 主从分栏：左主内容，右作者栏（纯色实心、无圆角、吸顶固定高度）
  - 粉色花瓣粒子（canvas，19998 片自下而上，鼠标附近被吸附绕转）
  - 无需注册登录：评论填「名字 + 噪点图形验证码」即可；评论可回复评论/回复的回复
  - 站长口令：在 /admin 自设口令，输入后本机解锁，可写文章 / 编辑作者栏 / 管理评论
  - Markdown + LaTeX（$、$$、\\(..\\)、\\[..\\] 及 Markdown 内嵌公式）见 md_math.py
  - 文章标签（= 文章分类，可多个）+ 置顶量 + 内容过滤标记（不安全 / 负能量 / 非学术）
  - 首页的「不显示…」过滤、按标签筛选、翻页与每页篇数全部在前端完成（不发请求）
  - 草稿：编辑页可存草稿（status=draft），游客完全看不到，只在顶栏的「草稿箱」里管理
  - 发布页参考洛谷文章编辑器：全屏 + 右侧 sidebar-container 文章设置
  - 监听 0.0.0.0:8848；调试模式**默认开**（改代码自动重载），用 DEBUG=0 关掉
"""

import hmac
import io
import json
import os
import random
import re
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, unquote

from flask import (Flask, abort, g, jsonify, make_response, redirect,
                   render_template, request, send_from_directory, session, url_for)
from markupsafe import Markup
from werkzeug.routing import IntegerConverter
from werkzeug.security import check_password_hash, generate_password_hash

import md_math
import theme

# ----------------------------------------------------------------------
# 基础配置
# ----------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "blog.db")
SECRET_FILE = os.path.join(BASE_DIR, ".secret_key")
BG_PATH = os.path.join(BASE_DIR, "static", "bg.jpg")
AVATAR_PATH = os.path.join(BASE_DIR, "static", "avatar.png")     # 头像固定这一个文件，上传即覆盖
AVATAR_URL = "/static/avatar.png"
AVATAR_SIZE = 256

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8848"))

# 调试开关：**默认开**（改代码自动重载、出错页显示完整堆栈）。要关掉就设环境变量
# DEBUG=0 / false / no / off（大小写不敏感，两侧空格无所谓）；不设这个变量，
# 或者设成别的值，都算开。线上部署务必 DEBUG=0。
DEBUG = (os.environ.get("DEBUG") or "0").strip().lower() not in ("0", "false", "no", "off")

# 反向代理：默认**不信任** X-Forwarded-For。该头可被任何人伪造，一旦采信，
# 解锁限流 / 评论限流全部失效（可无限爆破站长口令）。只有部署在自有反代
# 之后才设 TRUST_PROXY=1，并用 PROXY_HOPS 声明可信代理的跳数。
TRUST_PROXY = os.environ.get("TRUST_PROXY", "") == "1"
try:
    PROXY_HOPS = max(1, int(os.environ.get("PROXY_HOPS") or 1))
except ValueError:
    PROXY_HOPS = 1


BJ_TZ = timezone(timedelta(hours=8))

# 内容限制
MAX_TITLE = 120
MAX_CONTENT = 300_000
MAX_COMMENT = 5000
MAX_NAME = 20
MAX_BIO = 2000
MAX_LINKS = 20
PIN_MIN = -999
PIN_MAX = 999
MIN_OWNER_PASS = 6
MAX_OWNER_PASS = 72

# 图形验证码
CAPTCHA_TTL = 5 * 60
CAPTCHA_LEN = 4
CAPTCHA_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # 去掉易混的 0/O/1/I/L
COMMENT_COOLDOWN = 15          # 同一浏览器两次评论间隔（秒）
COMMENT_RATE = (20, 600)       # 同一 IP：10 分钟最多 20 次提交尝试（验证码答错也计数）
UNLOCK_RATE = (8, 600)         # 同一 IP：10 分钟最多 8 次口令尝试
CAPTCHA_RATE = (60, 600)       # 同一 IP：10 分钟最多领 60 张验证码图（PIL 逐像素画图不便宜）

MAX_UPLOAD = 8 * 1024 * 1024              # 单个图片 / 普通附件
MAX_UPLOAD_MEDIA = 64 * 1024 * 1024       # 单个视频 / 音频
MAX_UPLOAD_FILES = 8                      # 一次最多几个文件
UPLOAD_ROOT = os.path.join(BASE_DIR, "uploads")   # **刻意放在 static/ 之外**：
                                          # 静态目录里的文件会被 Flask 按扩展名猜 MIME 直接内联，
                                          # 放到外面才能统一走 /u/<路径> 这个受控出口

# 文章标签（编辑页三个选框；首页可勾选"不显示…"并可按标签筛选，全部在前端完成）
FLAGS = [
    ("unsafe", "不安全"),
    ("negative", "负能量"),
    ("nonacademic", "非学术"),
]
FLAG_KEYS = [k for k, _ in FLAGS]
FLAG_LABEL = dict(FLAGS)

# 文章状态：published 正常可见；draft 草稿（游客完全不可见，只能在 /drafts 草稿箱里看到）
ST_PUBLISHED = "published"
ST_DRAFT = "draft"

# 文章标题前的 svg 图标（洛谷式的 <svg class="icon"><use href="#…"></use></svg>）
#   · static/icons-local.svg：站内这 27 个（24 个水果 + 樱花 / 彩虹 / 四叶草），
#     在图标选择器里排最前。换高清重绘后体积上去了，就从 templates/icons.html 里
#     挪了出来 —— 那 21KB 原来是要随**每个页面**下发的；现在只有真正用到的
#     那一两个 <symbol> 会被内联进文章页 / 首页（见 post_icon_sprites）。
#   · static/icons.svg：yc-lain 博客那套 iconfont（380 个 ic- 前缀）。
#   · templates/icons.html 里只剩 icon-sun / eye / moon / pen / close 这 5 个界面图标，
#     它们随每个页面内联，所以能直接 <use href="#icon-sun">。
FRUIT_ICONS = [
    "icon-caomei", "icon-boluo", "icon-huolongguo", "icon-chengzi", "icon-hamigua",
    "icon-lizhi", "icon-mangguo", "icon-liulian", "icon-lizi", "icon-lanmei",
    "icon-longyan", "icon-shanzhu", "icon-pingguo", "icon-mihoutao", "icon-niuyouguo",
    "icon-xigua", "icon-putao", "icon-xiangjiao", "icon-ningmeng", "icon-yingtao",
    "icon-taozi", "icon-shiliu", "icon-ximei", "icon-shizi",
]
LOCAL_ICONS = FRUIT_ICONS + ["icon-sakura", "icon-rainbow", "icon-clover"]
DEFAULT_ICON = "icon-sakura"        # 没选图标的文章统一显示它
ICON_SPRITE = os.path.join(BASE_DIR, "static", "icons.svg")
LOCAL_ICON_SPRITE = os.path.join(BASE_DIR, "static", "icons-local.svg")
ICON_URL = "/static/icons.svg"
LOCAL_ICON_URL = "/static/icons-local.svg"
_ICON_CACHE = {}          # 文件路径 -> (mtime, {名字: <symbol> 片段})
_SYMBOL_RE = re.compile(r'<symbol\b[^>]*\bid="([^"]+)"[^>]*>.*?</symbol>', re.S)

# ----------------------------------------------------------------------
# 数据库
# ----------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    summary     TEXT NOT NULL DEFAULT '',
    content_md  TEXT NOT NULL DEFAULT '',
    tags        TEXT NOT NULL DEFAULT '',
    pin         INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'published',
    flags       TEXT NOT NULL DEFAULT '',
    icon        TEXT NOT NULL DEFAULT '',
    views       INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS comments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id  INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    parent_id   INTEGER NOT NULL DEFAULT 0,
    author_name TEXT NOT NULL DEFAULT '',
    ip          TEXT NOT NULL DEFAULT '',
    content     TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_articles_created ON articles(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_comments_article ON comments(article_id);
CREATE TABLE IF NOT EXISTS uploads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    rel         TEXT NOT NULL UNIQUE,            -- 相对 uploads/ 的路径：2026/09/<16位随机名>.<ext>
    name        TEXT NOT NULL DEFAULT '',       -- 上传时的原始文件名
    ext         TEXT NOT NULL DEFAULT '',
    kind        TEXT NOT NULL DEFAULT 'file',   -- image / video / audio / file
    size        INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_uploads_created ON uploads(created_at DESC);
CREATE TABLE IF NOT EXISTS site_cfg (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);
"""


def _db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def get_db():
    return _db()


app = Flask(__name__)


class _BoundedIntConverter(IntegerConverter):
    """限制 URL 里整数的位数。

    默认的 int 转换器接受任意长度的数字，/a/<40 位数字> 会让 sqlite3 抛
    OverflowError（未捕获异常）。这里把 id 限制在 9 位以内。
    """

    def __init__(self, map, *args, **kwargs):
        super().__init__(map, *args, **kwargs)
        self.regex = r"\d{1,9}"


app.url_map.converters["int"] = _BoundedIntConverter

# 会话密钥
if os.environ.get("SECRET_KEY"):
    app.secret_key = os.environ["SECRET_KEY"]
else:
    if os.path.exists(SECRET_FILE):
        with open(SECRET_FILE, "r", encoding="utf-8") as f:
            app.secret_key = f.read().strip()
    else:
        app.secret_key = secrets.token_hex(32)
        with open(SECRET_FILE, "w", encoding="utf-8") as f:
            f.write(app.secret_key)

app.config.update(
    SESSION_COOKIE_NAME="petal_session",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    MAX_CONTENT_LENGTH=80 * 1024 * 1024,      # 一次可带多个附件（单文件上限见 MAX_UPLOAD*）
)


@app.teardown_appcontext
def _close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """建表（幂等）。老库的历史结构升级见 migrate.py。"""
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


# ----------------------------------------------------------------------
# 小工具
# ----------------------------------------------------------------------
def now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def fmt_dt(utc_text: str, with_time=True):
    """sqlite datetime('now')（UTC）转东八区展示。"""
    try:
        dt = datetime.strptime(utc_text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return utc_text or ""
    dt = dt.astimezone(BJ_TZ)
    return dt.strftime("%Y-%m-%d %H:%M") if with_time else dt.strftime("%Y-%m-%d")


def parse_created(value):
    """界面上填的「北京时间」-> 库里存的 UTC 字符串；空返回 None，非法返回 False。"""
    v = (value or "").strip().replace("T", " ")
    if not v:
        return None
    if len(v) == 10:
        v += " 00:00"
    if len(v) == 16:
        v += ":00"
    try:
        dt = datetime.strptime(v, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return False
    if not (1970 <= dt.year <= 2100):
        return False
    return dt.replace(tzinfo=BJ_TZ).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


@app.template_global()
def input_dt(utc_text=None):
    """库里的 UTC 时间 -> <input type="datetime-local"> 需要的北京时间；空则给当前时间。"""
    dt = None
    if utc_text:
        try:
            dt = datetime.strptime(utc_text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            dt = None
    if dt is None:
        dt = datetime.now(timezone.utc)
    return dt.astimezone(BJ_TZ).strftime("%Y-%m-%dT%H:%M")


def cfg_get(key, default=""):
    row = _db().execute("SELECT value FROM site_cfg WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def cfg_set(key, value):
    _db().execute(
        "INSERT INTO site_cfg(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )
    _db().commit()


def _ensure_contacts_split():
    """一次性迁移：老库里 author_links 放的是个人链接（Github / 洛谷 等），
    现在拆成独立的「联系方式」，author_links 从此只放友链。
    用 contacts_split 标记保证只跑一次；不覆盖已有的 author_contacts。"""
    if cfg_get("contacts_split", "") == "1":
        return
    if cfg_get("author_contacts", None) is None:
        # 只有真的把旧内容搬过去时才清空 author_links，避免误伤已单独存在的友链
        cfg_set("author_contacts", cfg_get("author_links", "[]") or "[]")
        cfg_set("author_links", "[]")
    cfg_set("contacts_split", "1")


def load_cfg():
    """站点配置快照（含解析好的联系方式与友链）。"""
    _ensure_contacts_split()
    cfg = {
        "site_title": cfg_get("site_title", "樱羽小筑"),
        "site_subtitle": cfg_get("site_subtitle", "花见之时 · 记录代码与生活"),
        "author_nickname": cfg_get("author_nickname", "博主"),
        "author_avatar": avatar_url(),
        "author_bio": cfg_get("author_bio", ""),
        "footer_text": cfg_get("footer_text", ""),
    }
    cfg["author_links"] = _parse_links(cfg_get("author_links", "[]"))
    cfg["author_contacts"] = _parse_links(cfg_get("author_contacts", "[]"))
    return cfg


# ---- 链接归一化（少了协议头也能用） ----
def norm_url(url):
    u = (url or "").strip().replace(" ", "")
    if not u:
        return ""
    if u.startswith("//") or re.match(r"^(https?|mailto|tel):", u, re.I):
        return u
    if u.startswith("/") or u.startswith("#"):
        return u
    if re.match(r"^[\w.\-]+@[\w.\-]+\.[A-Za-z]{2,}$", u):      # 邮箱 -> mailto
        return "mailto:" + u
    if re.match(r"^[\w.\-]+\.[A-Za-z]{2,}([/?#].*)?$", u):      # 域名 -> https
        return "https://" + u
    return ""


def clean_links(links, limit=MAX_LINKS):
    """[{label,url}] -> (可用列表, 被忽略条数)"""
    clean, skipped = [], 0
    if not isinstance(links, list):
        return clean, skipped
    for l in links[:limit]:
        if not isinstance(l, dict):
            continue
        label = (l.get("label") or "").strip()[:30]
        url = norm_url(l.get("url"))
        if not label and not url:
            continue
        if not label or not url:
            skipped += 1
            continue
        clean.append({"label": label, "url": url})
    return clean, skipped


def _parse_links(raw):
    try:
        data = json.loads(raw or "[]")
    except Exception:
        return []
    return clean_links(data)[0]


def _read_sprite(path):
    """读一个 sprite 文件里的全部 <symbol>：{名字: 片段}（按 mtime 自动重载）。"""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {}
    cached = _ICON_CACHE.get(path)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return cached[1] if cached else {}
    found = {}
    for m in _SYMBOL_RE.finditer(text):
        found.setdefault(m.group(1), m.group(0))
    _ICON_CACHE[path] = (mtime, found)
    return found


def _local_sprite():
    return _read_sprite(LOCAL_ICON_SPRITE)


def _icon_sprite():
    """两套外部图标合并后的表（同名时本地那份优先）。"""
    merged = dict(_read_sprite(ICON_SPRITE))
    merged.update(_local_sprite())
    return merged


def post_icons():
    """图标选择器里的全部图标：站内那 27 个排前面，后面是 iconfont 那整套。"""
    sprite = _icon_sprite()
    return LOCAL_ICONS + [n for n in sprite if n not in LOCAL_ICONS]


def clean_icon(value):
    """只接受存在的图标名，其余（含空）→ 空串，表示用默认图标。"""
    v = (value or "").strip() if isinstance(value, str) else ""
    if not v:
        return ""
    return v if (v in LOCAL_ICONS or v in _icon_sprite()) else ""


def post_icon(post):
    """文章标题前的 svg 图标：用文章自己选的；没选（或名字已失效）就用默认图标。

    传文章 dict / sqlite3.Row，也兼容直接传 id，以及 None（取默认图标）。
    """
    icon = ""
    if isinstance(post, dict):
        icon = post.get("icon") or ""
    elif isinstance(post, sqlite3.Row):
        icon = (post["icon"] if "icon" in post.keys() else "") or ""
    if icon in LOCAL_ICONS or icon in _icon_sprite():
        return icon
    return DEFAULT_ICON


def post_icon_ref(name):
    """<use> 该指向哪里。

    站内 27 个 → static/icons-local.svg；iconfont → static/icons.svg；
    剩下（icon-sun 等界面图标）在本页内联的 sprite 里，直接 #名字。
    """
    if name in _local_sprite():
        return LOCAL_ICON_URL + "#" + name
    if name in _read_sprite(ICON_SPRITE):
        return ICON_URL + "#" + name
    return "#" + name


def post_icon_sprites(posts):
    """把这一页用到的外部图标内联成 <symbol>（同名只出现一次）。

    这样文章页 / 首页为了标题图标既不必额外拉整份 sprite（icons-local 33KB +
    iconfont 800KB），也不会把 27 个水果全塞进每个页面 —— 用到哪个内联哪个。
    界面图标（icon-sun 等）本来就在 templates/icons.html 里，不在这两套里，会跳过。
    """
    sprite = _icon_sprite()
    need, seen = [], set()
    for p in posts or []:
        name = post_icon(p)
        if name in seen or name not in sprite:
            continue
        seen.add(name)
        need.append(sprite[name])
    if not need:
        return Markup("")
    return Markup('<svg class="icon-sprite" aria-hidden="true" focusable="false" '
                  'xmlns="http://www.w3.org/2000/svg">%s</svg>' % "".join(need))


app.jinja_env.globals["post_icon"] = post_icon
app.jinja_env.globals["post_icons"] = post_icons
app.jinja_env.globals["post_icon_ref"] = post_icon_ref
app.jinja_env.globals["post_icon_sprites"] = post_icon_sprites


# ---- 文章标签（不安全 / 负能量 / 非学术）----
def clean_flags(value):
    """接受 ['unsafe', …] 或 'unsafe,negative' -> 规范化后的 CSV（顺序固定）。"""
    if isinstance(value, str):
        items = re.split(r"[,\s]+", value)
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = []
    got = {str(x).strip().lower() for x in items}
    return ",".join(k for k in FLAG_KEYS if k in got)


def flag_list(csv_text):
    """CSV -> [{'key':…, 'label':…}]，供模板展示。"""
    got = {x for x in (csv_text or "").split(",") if x}
    return [{"key": k, "label": FLAG_LABEL[k]} for k in FLAG_KEYS if k in got]


app.jinja_env.globals["flag_list"] = flag_list
app.jinja_env.globals["FLAGS"] = FLAGS


# ---- 文章标签（= 文章分类，可多个；首页按标签筛选在前端完成）----
MAX_TAGS = 12
MAX_TAG_LEN = 20


def clean_tags(value):
    """接受 ['a', 'b'] 或 'a,b' / 'a，b' -> 规范化后的 CSV（去空白、去重、限量）。"""
    if isinstance(value, str):
        items = re.split(r"[,，\n]+", value)
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = []
    out = []
    for x in items:
        t = re.sub(r"\s+", " ", str(x)).strip()
        if not t or len(t) > MAX_TAG_LEN or t in out:
            continue
        out.append(t)
        if len(out) >= MAX_TAGS:
            break
    return ",".join(out)


def tag_list(csv_text):
    """CSV -> ['a', 'b']，供模板展示 / 前端筛选用。"""
    return [x for x in (csv_text or "").split(",") if x]


def all_tags(limit=50):
    """所有已发布文章用过的标签 + 篇数（按篇数降序、名字升序）。"""
    counts = {}
    rows = _db().execute(
        "SELECT tags FROM articles WHERE status=? AND TRIM(tags)<>''",
        (ST_PUBLISHED,)).fetchall()
    for r in rows:
        for t in tag_list(r["tags"]):
            counts[t] = counts.get(t, 0) + 1
    return [{"name": t, "n": n} for t, n in
            sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]]


def fmt_size(n):
    """字节数 -> 人看的字符串。"""
    try:
        n = float(n or 0)
    except (TypeError, ValueError):
        return "0 B"
    if n < 1024:
        return "%d B" % n
    for unit in ("KB", "MB", "GB"):
        n /= 1024.0
        if n < 1024 or unit == "GB":
            return "%.1f %s" % (n, unit)
    return "%.1f GB" % n


app.jinja_env.globals["fmt_size"] = fmt_size
app.jinja_env.globals["tag_list"] = tag_list
app.jinja_env.globals["MAX_TAGS"] = MAX_TAGS
app.jinja_env.globals["MAX_TAG_LEN"] = MAX_TAG_LEN


def is_draft(row):
    return row["status"] == ST_DRAFT


# ---- 主体色 ----
# 默认用 style.css 里手写的「淡粉 + 白」可爱配色；
# 想让主色跟着 static/bg.jpg 自动提取，设环境变量 THEME_FROM_BG=1 再启动。
THEME_FROM_BG = os.environ.get("THEME_FROM_BG", "") == "1"
_THEME_CACHE = {"key": None, "css": ""}


def theme_css():
    if not THEME_FROM_BG:
        return Markup("")
    try:
        key = int(os.path.getmtime(BG_PATH))
    except OSError:
        key = None
    if _THEME_CACHE["key"] != key or not _THEME_CACHE["css"]:
        try:
            css = theme.build_css(BG_PATH)
        except Exception:
            css = ""
        _THEME_CACHE.update(key=key, css=css)
    return Markup(_THEME_CACHE["css"])


# ---- 头像：只用一个固定文件，上传即覆盖，不存任何路径 ----
def avatar_url():
    try:
        st = os.stat(AVATAR_PATH)
    except OSError:
        return ""
    return f"{AVATAR_URL}?v={int(st.st_mtime)}"


def save_avatar(file_storage):
    """裁剪成方形并缩放后覆盖写 static/avatar.png，返回新头像 URL。"""
    data = file_storage.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        return None, "图片不能超过 8MB"
    if not (data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n"
            or data[:6] in (b"GIF87a", b"GIF89a")
            or (len(data) >= 12 and data[0:4] == b"RIFF" and data[8:12] == b"WEBP")):
        return None, "图片格式不支持"
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        _write_avatar(img)
    except Exception:
        return None, "图片解析失败"
    return avatar_url(), None


def _write_avatar(img):
    """方形裁剪 + 缩放到 256，覆盖写 static/avatar.png（永远只有这一张）。"""
    from PIL import Image, ImageOps

    img = ImageOps.exif_transpose(img).convert("RGBA")
    w, h = img.size
    side = min(w, h)
    img = img.crop(((w - side) // 2, (h - side) // 2, (w + side) // 2, (h + side) // 2))
    img = img.resize((AVATAR_SIZE, AVATAR_SIZE), Image.LANCZOS)
    img.save(AVATAR_PATH, "PNG", optimize=True)
    return AVATAR_PATH


def ip_of(req=None):
    """真实客户端 IP。

    默认**不信任** X-Forwarded-For：该头任何人都能伪造，一旦采信就等于把
    所有限流（站长口令爆破、评论刷屏）全部作废。只有部署在自有反向代理之后、
    并显式设置 TRUST_PROXY=1 时才启用，且只取代理链末端的 PROXY_HOPS 跳
    （即由可信代理写入的那一跳），客户端自行前置的伪造值不会被采信。
    """
    r = req or request
    if TRUST_PROXY:
        hops = [p.strip() for p in (r.headers.get("X-Forwarded-For") or "").split(",")
                if p.strip()]
        if len(hops) >= PROXY_HOPS:
            return hops[-PROXY_HOPS]
    return r.remote_addr or ""


def safe_next(value):
    """校验跳转目标，阻断开放重定向。

    只接受站内绝对路径；此外必须显式拒绝反斜杠——浏览器会把 /\\evil.com
    规范化成 //evil.com（协议相对 URL），从而跳到外站。
    """
    v = (value or "").strip()
    if not v.startswith("/") or v.startswith("//"):
        return "/"
    if "\\" in v or any(c in v for c in "\r\n\t"):
        return "/"
    return v


_RATE = {}
_RATE_LOCK = threading.Lock()
_RATE_SWEEP = [0.0]
_RATE_MAX_KEYS = 50_000      # 键里含客户端 IP，必须设上限，否则可被撑爆内存
_RATE_MAX_WINDOW = 600


def rate_ok(bucket, key, limit, window):
    """滑动窗口限流（进程内）。"""
    now = time.time()
    with _RATE_LOCK:
        if now - _RATE_SWEEP[0] > 60 or len(_RATE) > _RATE_MAX_KEYS:
            _RATE_SWEEP[0] = now
            for k in [k for k, arr in _RATE.items()
                      if not arr or now - arr[-1] > _RATE_MAX_WINDOW]:
                _RATE.pop(k, None)
        arr = [t for t in _RATE.get((bucket, key), []) if now - t < window]
        if len(arr) >= limit:
            _RATE[(bucket, key)] = arr
            return False
        arr.append(now)
        _RATE[(bucket, key)] = arr
        return True


# ----------------------------------------------------------------------
# 站长口令（无账号系统：一个口令即可解锁发文/管理）
# ----------------------------------------------------------------------
def owner_unlocked():
    return bool(session.get("owner"))


def has_owner_pass():
    return bool(cfg_get("owner_pass_hash", ""))


def set_owner_pass(pw):
    cfg_set("owner_pass_hash", generate_password_hash(pw))
    session.permanent = True
    session["owner"] = True


def check_owner_pass(pw):
    h = cfg_get("owner_pass_hash", "")
    return bool(h) and check_password_hash(h, pw or "")


@app.context_processor
def inject_globals():
    db = _db()
    stats = {
        "articles": db.execute(
            "SELECT COUNT(*) c FROM articles WHERE status=?",
            (ST_PUBLISHED,)).fetchone()["c"],
        "comments": db.execute(
            "SELECT COUNT(*) c FROM comments WHERE article_id IN "
            "(SELECT id FROM articles WHERE status=?)", (ST_PUBLISHED,)).fetchone()["c"],
        "views": db.execute(
            "SELECT COALESCE(SUM(views),0) v FROM articles WHERE status=?",
            (ST_PUBLISHED,)).fetchone()["v"],
    }
    recent = [dict(r) for r in db.execute(
        "SELECT id, title FROM articles WHERE status=? "
        "ORDER BY pin DESC, created_at DESC, id DESC LIMIT 6", (ST_PUBLISHED,)
    ).fetchall()]
    unlocked = owner_unlocked()
    return {
        "is_owner": unlocked,
        "owner_set": has_owner_pass(),
        "site": load_cfg(),
        "stats": stats,
        "recent_posts": recent,
        "all_tags": all_tags(),
        "csrf_token": _csrf_token,
        "theme_css": theme_css,
    }


def _csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


@app.template_filter("md")
def _md_filter(s):
    """模板里用 {{ text | md | safe }} 渲染 Markdown（注意必须加 safe）。"""
    return md_math.md_render(s or "")


@app.template_filter("md_comment")
def _md_comment_filter(s):
    """评论专用：访客可写，按严格模式净化（禁站外图片、强制 rel、收紧 class）。"""
    return md_math.md_render(s or "", strict=True)


@app.before_request
def _csrf_protect():
    if request.method != "POST":
        return
    token = request.form.get("_csrf") or request.headers.get("X-CSRF-Token") or ""
    want = session.get("_csrf", "")
    if not (want and hmac.compare_digest(token, want)):
        if request.is_json or request.path.startswith("/api/"):
            return jsonify(error="安全校验失败，请刷新页面"), 400
        abort(400, description="安全校验失败，请刷新页面")


def _wants_json():
    return (request.is_json or request.path.startswith("/api/")
            or request.headers.get("X-Requested-With") == "XMLHttpRequest")


def owner_gate():
    """未解锁时：页面跳站长入口，接口/写操作返回 403。"""
    if owner_unlocked():
        return None
    if _wants_json():
        return jsonify(error="需要站长口令", need_owner=True), 403
    nxt = request.path if request.method == "GET" else "/"
    return redirect(url_for("admin_entry", next=nxt))


def _required_owner():
    gate = owner_gate()
    if gate:
        return gate
    return None


# ----------------------------------------------------------------------
# 图形验证码（噪点 + 扭曲字符）
# ----------------------------------------------------------------------
_FONT_CACHE = {}


def _captcha_font(size):
    key = ("font", size)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    from PIL import ImageFont
    font = None
    for path in (r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\arial.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            font = ImageFont.truetype(path, size)
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()
    _FONT_CACHE[key] = font
    return font


def captcha_code():
    return "".join(random.choice(CAPTCHA_ALPHABET) for _ in range(CAPTCHA_LEN))


# 验证码答案必须留在服务端。Flask 的会话是「签名但**不加密**」的 Cookie，
# 把答案写进 session 等于把答案随响应一起发给客户端（base64 一解就出来），
# 机器人可以直接读自己的 Cookie 拿到答案，验证码形同虚设。
_CAPTCHA = {}                 # token -> (code, ts)
_CAPTCHA_LOCK = threading.Lock()
_CAPTCHA_MAX = 20_000


def captcha_issue(code):
    """存下答案，返回一个不透明 token（放进会话不会泄露答案）。"""
    now = time.time()
    token = secrets.token_urlsafe(18)
    with _CAPTCHA_LOCK:
        stale = [k for k, (_, ts) in _CAPTCHA.items() if now - ts > CAPTCHA_TTL]
        for k in stale:
            _CAPTCHA.pop(k, None)
        if len(_CAPTCHA) >= _CAPTCHA_MAX:      # 兜底：挤掉最旧的一批
            for k in sorted(_CAPTCHA, key=lambda k: _CAPTCHA[k][1])[:_CAPTCHA_MAX // 4]:
                _CAPTCHA.pop(k, None)
        _CAPTCHA[token] = (code, now)
    return token


def captcha_png(text, w=136, h=46):
    """生成带噪点的验证码图片（bytes）。"""
    from PIL import Image, ImageDraw, ImageFilter

    bg = (random.randint(246, 253), random.randint(242, 250), random.randint(246, 253))
    img = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(img)

    # 背景噪点
    for _ in range(w * h // 22):
        x, y = random.randint(0, w - 1), random.randint(0, h - 1)
        v = random.randint(150, 225)
        d.point((x, y), fill=(v, random.randint(120, 200), random.randint(150, 220)))

    # 干扰线 / 干扰弧
    for _ in range(random.randint(4, 6)):
        d.line(
            [(random.randint(0, w), random.randint(0, h)),
             (random.randint(0, w), random.randint(0, h))],
            fill=(random.randint(120, 210), random.randint(120, 200), random.randint(140, 215)),
            width=1,
        )
    for _ in range(3):
        x, y = random.randint(0, w), random.randint(0, h)
        d.arc([x - 26, y - 16, x + 26, y + 16], random.randint(0, 180),
              random.randint(180, 360), fill=(random.randint(150, 220),) * 3, width=1)

    # 单个字符：随机颜色、位移、旋转
    font = _captcha_font(random.choice((25, 27, 29)))
    step = (w - 18) / CAPTCHA_LEN
    for i, ch in enumerate(text):
        color = (random.randint(30, 110), random.randint(30, 110), random.randint(60, 150))
        layer = Image.new("RGBA", (34, 40), (0, 0, 0, 0))
        ImageDraw.Draw(layer).text((6, 4), ch, font=font, fill=color + (255,))
        layer = layer.rotate(random.uniform(-28, 28), expand=True, resample=Image.BICUBIC)
        px = int(6 + i * step + random.uniform(-2, 2))
        py = int((h - layer.height) / 2 + random.uniform(-3, 3))
        img.paste(layer, (px, py), layer)

    # 前景噪点
    d = ImageDraw.Draw(img)
    for _ in range(90):
        x, y = random.randint(0, w - 1), random.randint(0, h - 1)
        d.point((x, y), fill=(random.randint(60, 160),) * 3)

    img = img.filter(ImageFilter.SMOOTH)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


@app.route("/captcha.png")
def captcha_image():
    # 这是唯一一个谁都调得动、又要跑 PIL 逐像素画图的接口，必须限流，而且放在最前面
    # ——被限流时连图都不画。注意不覆盖会话里已有的 token：之前领到的那张仍然可用。
    if not rate_ok("captcha", ip_of(), *CAPTCHA_RATE):
        resp = make_response("验证码请求过于频繁，请稍后再试", 429)
        resp.headers["Content-Type"] = "text/plain; charset=utf-8"
        resp.headers["Retry-After"] = "60"
        return resp
    code = captcha_code()
    session["captcha"] = captcha_issue(code)
    resp = make_response(captcha_png(code))
    resp.headers["Content-Type"] = "image/png"
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


def captcha_ok(value):
    """比对验证码：会话里只有 token，真正的答案从未离开服务端。"""
    token = session.pop("captcha", None)
    if not isinstance(token, str) or not token:
        return False
    with _CAPTCHA_LOCK:
        rec = _CAPTCHA.pop(token, None)      # 一次性：取走即失效
    if not rec:
        return False
    code, ts = rec
    if time.time() - ts > CAPTCHA_TTL:
        return False
    return hmac.compare_digest((value or "").strip().upper(), code)


# ----------------------------------------------------------------------
# :::charge 评论解锁（本站扩展）
# ----------------------------------------------------------------------
# 在本页评论过的人，cookie 里记一条 (文章 id, 评论 id, 签名)，之后就看得到 :::charge 里的正文。
# cookie 是明文存在客户端的，**必须签名** —— 不然谁都能自己编一条「我评论过」的凭证，
# 把付费 / 隐藏内容白嫖走。签名密钥用 app.secret_key（和会话同源，但不共享其内容）。
CHARGE_COOKIE = "petal_unlock"
CHARGE_MAX = 20                  # 最多同时记 20 篇文章，再多挤掉最旧的
CHARGE_AGE = 400 * 24 * 3600     # 一年


def _charge_sig(aid, cid):
    key = app.secret_key
    if isinstance(key, str):
        key = key.encode("utf-8")
    return hmac.new(key, ("charge:%s:%s" % (aid, cid)).encode("utf-8"),
                    "sha256").hexdigest()[:16]


def _charge_entries():
    """解锁 cookie -> [(文章 id, 评论 id), …]；签名对不上的整条丢掉。"""
    raw = request.cookies.get(CHARGE_COOKIE) or ""
    out = []
    for part in raw.split(",")[-CHARGE_MAX:]:
        bits = part.split(":")
        if len(bits) != 3 or not bits[0].isdigit() or not bits[1].isdigit():
            continue
        if hmac.compare_digest(bits[2], _charge_sig(bits[0], bits[1])):
            out.append((int(bits[0]), int(bits[1])))
    return out


def charge_unlocked(aid):
    """这位访客能不能看本篇 :::charge 的内容。

    站长永远算解锁；游客必须在本页评论过，**而且那条评论还在**（被删了就不算数）。
    """
    if owner_unlocked():
        return True
    db = _db()
    for art_id, cid in _charge_entries():
        if art_id != aid:
            continue
        if db.execute("SELECT 1 FROM comments WHERE id=? AND article_id=?",
                      (cid, aid)).fetchone():
            return True
    return False


def charge_ctx(aid):
    """传给 md_math.md_render 的渲染上下文。"""
    return {"charge": charge_unlocked(aid)}


def _grant_charge(resp, aid, cid):
    """评论成功后：把「这篇文章已解锁」写进 cookie（每篇只留最新一条）。"""
    entries = [(a, c) for a, c in _charge_entries() if a != aid]
    entries.append((aid, cid))
    resp.set_cookie(
        CHARGE_COOKIE,
        ",".join("%d:%d:%s" % (a, c, _charge_sig(a, c)) for a, c in entries[-CHARGE_MAX:]),
        max_age=CHARGE_AGE, samesite="Lax", httponly=True,
        secure=request_is_https(),
    )
    return resp


# ----------------------------------------------------------------------
# 页面
# ----------------------------------------------------------------------
@app.route("/")
def index():
    """首页：一次把「已发布」的文章全给前端，筛选 / 标签 / 翻页 / 每页篇数都在前端做（不再发请求）。

    草稿（status='draft'）对游客完全不可见，站长也只能在 /drafts 草稿箱里看到。
    """
    cur_tag = (request.args.get("tag") or "").strip()[:MAX_TAG_LEN]
    db = get_db()
    rows = db.execute(
        "SELECT a.*, (SELECT COUNT(*) FROM comments c WHERE c.article_id=a.id) cmt "
        "FROM articles a WHERE a.status=? "
        "ORDER BY a.pin DESC, a.created_at DESC, a.id DESC",
        (ST_PUBLISHED,),
    ).fetchall()
    posts = [{
        "id": r["id"],
        "title": r["title"],
        "summary": r["summary"] or md_math.plain_excerpt(r["content_md"], 150),
        "created": fmt_dt(r["created_at"]),
        "views": r["views"],
        "tags": tag_list(r["tags"]),
        "pin": r["pin"],
        "cmt": r["cmt"],
        "flags": flag_list(r["flags"]),
        "icon": r["icon"],
        "flag_keys": [x for x in (r["flags"] or "").split(",") if x],
    } for r in rows]
    draft_n = db.execute("SELECT COUNT(*) c FROM articles WHERE status=?",
                         (ST_DRAFT,)).fetchone()["c"] if owner_unlocked() else 0
    return render_template("index.html", posts=posts, total=len(posts),
                           cur_tag=cur_tag, draft_n=draft_n)


@app.route("/a/<int:aid>")
def article(aid):
    db = get_db()
    row = db.execute("SELECT * FROM articles WHERE id=?", (aid,)).fetchone()
    if not row:
        abort(404)
    draft = is_draft(row)
    if draft and not owner_unlocked():
        abort(404)                       # 草稿：游客连链接都打不开
    post = dict(row)
    post["created"] = fmt_dt(row["created_at"])
    post["updated"] = fmt_dt(row["updated_at"])
    post["tags"] = tag_list(row["tags"])
    post["flags"] = flag_list(row["flags"])
    post["draft"] = draft
    if not draft:                        # 草稿不计阅读量
        db.execute("UPDATE articles SET views=views+1 WHERE id=?", (aid,))
        db.commit()
        post["views"] = row["views"] + 1
    body_html = md_math.md_render(row["content_md"], ctx=charge_ctx(aid))
    crows = db.execute(
        "SELECT id, parent_id, author_name, content, created_at FROM comments "
        "WHERE article_id=? ORDER BY created_at ASC, id ASC", (aid,)
    ).fetchall()
    comments = _thread_comments(crows)
    cerr = request.args.get("cerr", "")
    try:
        cmt_parent = int(request.args.get("cp", 0) or 0)
    except (TypeError, ValueError):
        cmt_parent = 0
    return render_template(
        "article.html", post=post, body_html=body_html, comments=comments,
        can_edit=owner_unlocked(), cerr=cerr, cmt_parent=cmt_parent,
        cmt_total=sum(1 + len(c["replies"]) for c in comments),
        cmt_name=unquote(request.cookies.get("petal_name", "")),
    )


def _thread_comments(rows):
    """把评论整理成「顶层 + 其下回复」两级：回复的回复也挂在同一条线程里，标出回复对象。"""
    nodes = {}
    threads = []
    for r in rows:
        node = {
            "id": r["id"], "name": r["author_name"] or "访客",
            "content": r["content"], "created": fmt_dt(r["created_at"]),
            "replies": [], "reply_to": "",
        }
        nodes[r["id"]] = node
        parent = nodes.get(r["parent_id"])
        if parent is None:               # 顶层（或被删掉的父评论留下的孤儿）
            threads.append(node)
        else:
            node["reply_to"] = parent["name"]
            root = parent.get("root") or parent
            node["root"] = root
            root["replies"].append(node)
    return threads


# ----------------------------------------------------------------------
# 文章发布 / 编辑 / 删除（站长口令解锁后可用）
# ----------------------------------------------------------------------
def _article_payload():
    src = (request.get_json(silent=True) or {}) if request.is_json else request.form
    raw_created = (src.get("created") or "").strip()
    parsed = parse_created(raw_created)
    status = (src.get("status") or "").strip().lower()
    return {
        "title": (src.get("title") or "").strip(),
        "content": src.get("content") or "",
        "summary": (src.get("summary") or "").strip(),
        "tags": clean_tags(src.get("tags")),
        "pin": _to_pin(src.get("pin")),
        "status": ST_DRAFT if status == ST_DRAFT else ST_PUBLISHED,
        "flags": clean_flags(src.get("flags")),
        "icon": clean_icon(src.get("icon")),
        "created_input": raw_created,
        "created_utc": parsed if isinstance(parsed, str) else None,
        "created_bad": parsed is False,
        "as_json": request.is_json,
    }


def _to_pin(value):
    try:
        n = int(str(value or "0").strip() or 0)
    except (TypeError, ValueError):
        return 0
    return max(PIN_MIN, min(PIN_MAX, n))   # 置顶量可正可负：负数把文章压到后面


def _validate_article(title, content, status=ST_PUBLISHED):
    if not title or len(title) > MAX_TITLE:
        return "标题不能为空" if not title else "标题过长"
    if len(content) > MAX_CONTENT:
        return "正文过长"
    if status != ST_DRAFT and not content.strip():
        return "正文不能为空"          # 草稿允许只写个标题先存着
    return None


def _created_error(data):
    if data.get("created_bad"):
        return "发布时间格式不正确"
    return None


@app.route("/write", methods=["GET", "POST"])
def write_article():
    gate = _required_owner()
    if gate:
        return gate
    if request.method == "POST":
        data = _article_payload()
        err = (_validate_article(data["title"], data["content"], data["status"])
               or _created_error(data))
        if err:
            if data["as_json"]:
                return jsonify(error=err), 400
            draft = {"title": data["title"], "content_md": data["content"],
                     "summary": data["summary"], "tags": data["tags"],
                     "pin": data["pin"], "flags": data["flags"],
                     "icon": data["icon"], "status": data["status"],
                     "created_at": data["created_utc"] or ""}
            return render_template("editor.html", error=err, post=draft)
        db = get_db()
        cur = db.execute(
            "INSERT INTO articles(title, summary, content_md, tags, pin, "
            "status, flags, icon, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (data["title"], data["summary"][:300], data["content"],
             data["tags"], data["pin"], data["status"], data["flags"], data["icon"],
             data["created_utc"] or now_str(), now_str()),
        )
        db.commit()
        if data["as_json"]:
            return jsonify(ok=True, id=cur.lastrowid, status=data["status"])
        if data["status"] == ST_DRAFT:
            return redirect(url_for("drafts"))
        return redirect(url_for("article", aid=cur.lastrowid))
    return render_template("editor.html", post=None)


@app.route("/a/<int:aid>/edit", methods=["GET", "POST"])
def edit_article(aid):
    gate = _required_owner()
    if gate:
        return gate
    db = get_db()
    row = db.execute("SELECT * FROM articles WHERE id=?", (aid,)).fetchone()
    if not row:
        abort(404)
    if request.method == "POST":
        data = _article_payload()
        err = (_validate_article(data["title"], data["content"], data["status"])
               or _created_error(data))
        if err:
            if data["as_json"]:
                return jsonify(error=err), 400
            draft = dict(row)
            draft.update(title=data["title"], content_md=data["content"],
                         summary=data["summary"], tags=data["tags"],
                         pin=data["pin"], flags=data["flags"], icon=data["icon"],
                         status=data["status"],
                         created_at=data["created_utc"] or row["created_at"])
            return render_template("editor.html", error=err, post=draft)
        db.execute(
            "UPDATE articles SET title=?, summary=?, content_md=?, tags=?, pin=?, "
            "status=?, flags=?, icon=?, created_at=?, updated_at=? WHERE id=?",
            (data["title"], data["summary"][:300], data["content"], data["tags"],
             data["pin"], data["status"], data["flags"], data["icon"],
             data["created_utc"] or row["created_at"], now_str(), aid),
        )
        db.commit()
        if data["as_json"]:
            return jsonify(ok=True, id=aid, status=data["status"])
        if data["status"] == ST_DRAFT:
            return redirect(url_for("drafts"))
        return redirect(url_for("article", aid=aid))
    return render_template("editor.html", post=dict(row))


@app.route("/a/<int:aid>/publish", methods=["POST"])
def publish_article(aid):
    """草稿箱里一键发布。"""
    gate = _required_owner()
    if gate:
        return gate
    db = get_db()
    if not db.execute("SELECT id FROM articles WHERE id=?", (aid,)).fetchone():
        abort(404)
    db.execute("UPDATE articles SET status=?, updated_at=? WHERE id=?",
               (ST_PUBLISHED, now_str(), aid))
    db.commit()
    return redirect(url_for("article", aid=aid))


@app.route("/drafts")
def drafts():
    """草稿箱：只有站长能进（顶栏那个粉色文本链接）。"""
    if not owner_unlocked():
        return redirect(url_for("admin_entry", next="/drafts"))
    rows = get_db().execute(
        "SELECT * FROM articles WHERE status=? ORDER BY updated_at DESC, id DESC",
        (ST_DRAFT,)).fetchall()
    return render_template("drafts.html", drafts=[{
        "id": r["id"], "title": r["title"], "tags": tag_list(r["tags"]),
        "created": fmt_dt(r["created_at"]), "updated": fmt_dt(r["updated_at"]),
        "flags": flag_list(r["flags"]), "icon": r["icon"],
    } for r in rows])


@app.route("/a/<int:aid>/delete", methods=["POST"])
def delete_article(aid):
    gate = _required_owner()
    if gate:
        return gate
    db = get_db()
    if not db.execute("SELECT id FROM articles WHERE id=?", (aid,)).fetchone():
        abort(404)
    db.execute("DELETE FROM comments WHERE article_id=?", (aid,))
    db.execute("DELETE FROM articles WHERE id=?", (aid,))
    db.commit()
    return redirect(url_for("index"))


# ----------------------------------------------------------------------
# 评论：填名字 + 图形验证码，无需登录
# ----------------------------------------------------------------------
@app.route("/a/<int:aid>/comment", methods=["POST"])
def add_comment(aid):
    db = get_db()
    row = db.execute("SELECT id, status FROM articles WHERE id=?", (aid,)).fetchone()
    if not row:
        abort(404)
    if (row["status"] or ST_PUBLISHED) == ST_DRAFT and not owner_unlocked():
        abort(404)          # 草稿连链接都打不开，自然也不该被挂评论
    name = (request.form.get("name") or "").strip()
    content = (request.form.get("content") or "").strip()
    captcha = request.form.get("captcha") or ""
    try:
        parent_id = int(request.form.get("parent_id") or 0)
    except (TypeError, ValueError):
        parent_id = 0
    if parent_id:                       # 只允许回复本文章里存在的评论
        ok = db.execute("SELECT id FROM comments WHERE id=? AND article_id=?",
                        (parent_id, aid)).fetchone()
        if not ok:
            parent_id = 0
    def back(err):
        url = url_for("article", aid=aid, cerr=err)
        if parent_id:
            url += "&cp=%d" % parent_id
        return redirect(url + "#comments")

    err = ""
    if not name or len(name) > MAX_NAME or re.search(r"[<>\r\n\t]", name):
        err = "name"
    elif not content or len(content) > MAX_COMMENT:
        err = "content"
    # 限流必须排在验证码前面。captcha_ok() 是「答对才通过」，把它放前面等于
    # 完全不限制尝试次数：答错的请求一条都不计数，刷验证码 / 爆破都是免费通道。
    elif not rate_ok("cmt", ip_of(), *COMMENT_RATE):
        err = "rate"
    elif not captcha_ok(captcha):
        err = "captcha"
    else:
        last = session.get("last_cmt", 0)
        if time.time() - float(last) < COMMENT_COOLDOWN:
            err = "slow"
    if err:
        return back(err)
    cur = db.execute(
        "INSERT INTO comments(article_id, parent_id, author_name, ip, content) "
        "VALUES(?,?,?,?,?)",
        (aid, parent_id, name, ip_of(), content),
    )
    db.commit()
    session["last_cmt"] = time.time()
    resp = redirect(url_for("article", aid=aid) + "#comments")
    resp.set_cookie("petal_name", quote(name), max_age=30 * 24 * 3600,
                    samesite="Lax", httponly=False)
    # 评论成功 = 本页 :::charge 解锁（把 (文章, 评论) 签名后记进 cookie）
    return _grant_charge(resp, aid, cur.lastrowid)


@app.route("/a/<int:aid>/comment/<int:cid>/delete", methods=["POST"])
def delete_comment(aid, cid):
    gate = _required_owner()
    if gate:
        return gate
    db = get_db()
    if db.execute("SELECT id FROM comments WHERE id=? AND article_id=?",
                  (cid, aid)).fetchone():
        # 连带删掉它下面的所有回复（回复的回复也一起）
        db.execute("""
        WITH RECURSIVE sub(id) AS (
            SELECT ? UNION ALL
            SELECT c.id FROM comments c JOIN sub ON c.parent_id = sub.id
        )
        DELETE FROM comments WHERE id IN (SELECT id FROM sub)
        """, (cid,))
        db.commit()
    return redirect(url_for("article", aid=aid) + "#comments")


# ----------------------------------------------------------------------
# 管理入口 /admin（不在页面上露出口子，直接访问这个地址）：设置 / 输入 / 更换口令
# ----------------------------------------------------------------------
@app.route("/admin", methods=["GET", "POST"])
def admin_entry():
    nxt = safe_next(request.args.get("next") or request.form.get("next") or "/")
    error = None

    if request.method == "POST":
        action = (request.form.get("action") or "").strip()
        ip = ip_of()
        if action == "lock":
            session.pop("owner", None)
            return redirect(url_for("admin_entry", next=nxt))
        if action == "setup":
            if has_owner_pass() and not owner_unlocked():
                error = "口令已设置"
            else:
                p1 = request.form.get("pass") or ""
                p2 = request.form.get("pass2") or ""
                if len(p1) < MIN_OWNER_PASS:
                    error = f"口令至少 {MIN_OWNER_PASS} 位"
                elif len(p1) > MAX_OWNER_PASS:
                    error = f"口令最多 {MAX_OWNER_PASS} 位"
                elif p1 != p2:
                    error = "两次输入的口令不一致"
                else:
                    set_owner_pass(p1)
                    return redirect(nxt)
        elif action == "unlock":
            if not rate_ok("unlock", ip, *UNLOCK_RATE):
                error = "尝试次数过多"
            elif check_owner_pass(request.form.get("pass")):
                session.permanent = True
                session["owner"] = True
                return redirect(nxt)
            else:
                error = "口令不正确"
        elif action == "change":
            p_new = request.form.get("pass") or ""
            p_new2 = request.form.get("pass2") or ""
            cur = request.form.get("current") or ""
            if not owner_unlocked() and not check_owner_pass(cur):
                error = "当前口令不正确"
            elif len(p_new) < MIN_OWNER_PASS:
                error = f"新口令至少 {MIN_OWNER_PASS} 位"
            elif len(p_new) > MAX_OWNER_PASS:
                error = f"新口令最多 {MAX_OWNER_PASS} 位"
            elif p_new != p_new2:
                error = "两次输入的新口令不一致"
            else:
                set_owner_pass(p_new)
                return redirect(nxt)
        else:
            error = "未知操作"

    return render_template("admin.html", error=error, next_url=nxt,
                           unlocked=owner_unlocked(), has_pass=has_owner_pass())


# ----------------------------------------------------------------------
# 博主资料 / 站点设置（站长）
# ----------------------------------------------------------------------
@app.route("/api/site", methods=["POST"])
def api_site():
    gate = _required_owner()
    if gate:
        return gate
    payload = request.get_json(silent=True) or {}
    upd = []

    def put(key, value, limit=None):
        v = (value or "").strip()
        if limit and len(v) > limit:
            return False
        cfg_set(key, v)
        upd.append(key)
        return True

    if "site_title" in payload:
        if not payload.get("site_title", "").strip() or len(str(payload.get("site_title", ""))) > 40:
            return jsonify(error="站点标题为空或过长"), 400
        put("site_title", payload.get("site_title"))
    if "site_subtitle" in payload:
        put("site_subtitle", payload.get("site_subtitle"), 80)
    if "author_nickname" in payload:
        if not payload.get("author_nickname", "").strip():
            return jsonify(error="昵称不能为空"), 400
        put("author_nickname", payload.get("author_nickname"), 30)
    if "author_bio" in payload:
        put("author_bio", payload.get("author_bio"), MAX_BIO)
    if "footer_text" in payload:
        put("footer_text", payload.get("footer_text"), 200)
    warns = []
    if "links" in payload:
        links = payload.get("links")
        if not isinstance(links, list) or len(links) > MAX_LINKS:
            return jsonify(error=f"友链最多 {MAX_LINKS} 条"), 400
        clean, skipped = clean_links(links)
        cfg_set("author_links", json.dumps(clean, ensure_ascii=False))
        upd.append("links")
        if skipped:
            warns.append(f"{skipped} 条友链已忽略")
    if "contacts" in payload:
        contacts = payload.get("contacts")
        if not isinstance(contacts, list) or len(contacts) > MAX_LINKS:
            return jsonify(error=f"联系方式最多 {MAX_LINKS} 条"), 400
        clean, skipped = clean_links(contacts)
        cfg_set("author_contacts", json.dumps(clean, ensure_ascii=False))
        upd.append("contacts")
        if skipped:
            warns.append(f"{skipped} 条联系方式已忽略")
    if not upd:
        return jsonify(error="没有可更新的字段"), 400
    if warns:
        return jsonify(ok=True, updated=upd, warn="；".join(warns))
    return jsonify(ok=True, updated=upd)


@app.route("/api/avatar", methods=["POST"])
def api_avatar():
    gate = _required_owner()
    if gate:
        return gate
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify(error="未选择文件"), 400
    url, err = save_avatar(f)
    if err:
        return jsonify(error=err), 400
    return jsonify(ok=True, avatar=url)


@app.route("/api/preview", methods=["POST"])
def api_preview():
    gate = _required_owner()
    if gate:
        return gate
    payload = request.get_json(silent=True) or {}
    md = payload.get("md") or ""
    if len(md) > MAX_CONTENT:
        return jsonify(error="正文过长"), 400
    # 预览只有站长进得来：:::charge 一律按解锁渲染，写的时候就看得见自己藏了什么
    return jsonify(ok=True, html=md_math.md_render(md, ctx={"charge": True}))


# ----------------------------------------------------------------------
# 附件上传（仅站长）
# ----------------------------------------------------------------------
# 扩展名 -> (类别, MIME)。**只认白名单**：.html / .svg / .js / .xml 这类能被浏览器
# 当同源页面或脚本跑起来的一律不收，否则等于给自己开一个存储型 XSS 的上传口。
UPLOAD_KINDS = {
    "png": ("image", "image/png"),
    "jpg": ("image", "image/jpeg"), "jpeg": ("image", "image/jpeg"),
    "gif": ("image", "image/gif"), "webp": ("image", "image/webp"),
    "bmp": ("image", "image/bmp"), "avif": ("image", "image/avif"),
    "mp4": ("video", "video/mp4"), "m4v": ("video", "video/x-m4v"),
    "mov": ("video", "video/quicktime"), "webm": ("video", "video/webm"),
    "ogv": ("video", "video/ogg"),
    "mp3": ("audio", "audio/mpeg"), "m4a": ("audio", "audio/mp4"),
    "ogg": ("audio", "audio/ogg"), "wav": ("audio", "audio/wav"),
    "pdf": ("file", "application/pdf"),
    "zip": ("file", "application/zip"), "7z": ("file", "application/x-7z-compressed"),
    "rar": ("file", "application/vnd.rar"), "tar": ("file", "application/x-tar"),
    "gz": ("file", "application/gzip"),
    "doc": ("file", "application/octet-stream"),
    "docx": ("file", "application/octet-stream"),
    "xls": ("file", "application/octet-stream"),
    "xlsx": ("file", "application/octet-stream"),
    "ppt": ("file", "application/octet-stream"),
    "pptx": ("file", "application/octet-stream"),
    "txt": ("file", "text/plain"),
    "md": ("file", "text/plain"),
    "csv": ("file", "text/csv"),
    "json": ("file", "application/json"),
    "log": ("file", "text/plain"),
    "py": ("file", "text/plain"),
    "c": ("file", "text/plain"),
    "h": ("file", "text/plain"),
    "cpp": ("file", "text/plain"),
    "hpp": ("file", "text/plain"),
    "java": ("file", "text/plain"),
    "pas": ("file", "text/plain"),
    "tex": ("file", "text/plain"),
}
# 存盘名固定是 <16 位十六进制>.<扩展名>，路径形态死板到不可能穿越
_UPLOAD_REL_RE = re.compile(r"^\d{4}/\d{2}/[0-9a-f]{16}\.[a-z0-9]{1,5}$")
# 扩展名别名：同一个真实类型可能有多个后缀
_MAGIC_ALIAS = {"jpeg": "jpg", "m4v": "mp4", "mov": "mp4", "ogv": "ogg",
                "m4a": "mp4", "docx": "zip", "xlsx": "zip", "pptx": "zip",
                "7z": "7z", "tar": "tar"}


def _magic_type(head):
    """按文件头认出真实类型；认不出来返回空串。

    扩展名是上传方说了算的，不能只信它 —— 尤其是图片 / 视频 / 音频这几类会**内联**回给
    浏览器的，必须确认内容真的是那个东西。
    """
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if head[:3] == b"\xff\xd8\xff":
        return "jpg"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if head[:2] == b"BM":
        return "bmp"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav"
    if len(head) >= 12 and head[4:8] == b"ftyp":
        return "avif" if head[8:12] in (b"avif", b"avis") else "mp4"
    if head[:4] == b"\x1aE\xdf\xa3":
        return "webm"
    if head[:4] == b"OggS":
        return "ogg"
    if head[:3] == b"ID3" or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "mp3"
    if head[:4] == b"%PDF":
        return "pdf"
    if head[:4] == b"PK\x03\x04":
        return "zip"
    if head[:6] == b"7z\xbc\xaf\x27\x1c":
        return "7z"
    if head[:4] == b"Rar!":
        return "rar"
    if head[:2] == b"\x1f\x8b":
        return "gz"
    return ""


def _upload_ext(filename):
    """取一个合法的小写扩展名；没有 / 不合法返回空串。"""
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    if "." not in name:
        return ""
    ext = name.rsplit(".", 1)[-1].strip().lower()
    return ext if re.fullmatch(r"[a-z0-9]{1,5}", ext) else ""


def _upload_basename(filename, keep_ext):
    """展示名：去掉路径分隔符与控制字符，限量 120 字。"""
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[\r\n\t]+", " ", name).strip()[:120]
    if not keep_ext and "." in name:
        name = name.rsplit(".", 1)[0]
    return name or "文件"


def api_upload():
    """/api/upload —— 仅站长。一次可传多个，逐个落盘并给出 Markdown / 直链。"""
    gate = _required_owner()
    if gate:
        return gate
    files = [f for f in request.files.getlist("file") if f and f.filename]
    if not files:
        return jsonify(error="没有收到文件"), 400
    if len(files) > MAX_UPLOAD_FILES:
        return jsonify(error="一次最多上传 %d 个文件" % MAX_UPLOAD_FILES), 400
    rel_dir = datetime.now(BJ_TZ).strftime("%Y/%m")
    target_dir = os.path.join(UPLOAD_ROOT, *rel_dir.split("/"))
    out = []
    for f in files:
        ext = _upload_ext(f.filename)
        kind, mime = UPLOAD_KINDS.get(ext, ("", ""))
        if not kind:
            return jsonify(error="「%s」的类型不支持上传" % _upload_basename(f.filename, True)), 400
        limit = MAX_UPLOAD_MEDIA if kind in ("video", "audio") else MAX_UPLOAD
        data = f.read(limit + 1)
        if len(data) > limit:
            return jsonify(error="「%s」超过 %dMB" % (_upload_basename(f.filename, True),
                                                     limit // 1024 // 1024)), 400
        if not data:
            return jsonify(error="「%s」是空文件" % _upload_basename(f.filename, True)), 400
        if kind != "file":        # 会内联回浏览器的几类：内容必须和扩展名对得上
            real = _magic_type(data[:64])
            if not real or _MAGIC_ALIAS.get(ext, ext) != real:
                return jsonify(error="「%s」的内容与扩展名不符" %
                                      _upload_basename(f.filename, True)), 400
        try:
            os.makedirs(target_dir, exist_ok=True)
        except OSError:
            return jsonify(error="服务器无法创建上传目录"), 500
        fname = secrets.token_hex(8) + "." + ext
        with open(os.path.join(target_dir, fname), "wb") as fh:
            fh.write(data)
        rel = "%s/%s" % (rel_dir, fname)
        name = _upload_basename(f.filename, True)
        uid = 0
        try:                       # 落盘成功即可用；入库失败不该让整次上传失败
            cur = get_db().execute(
                "INSERT INTO uploads(rel, name, ext, kind, size, created_at) "
                "VALUES(?,?,?,?,?,?)", (rel, name, ext, kind, len(data), now_str()))
            get_db().commit()
            uid = cur.lastrowid
        except sqlite3.Error:
            uid = 0
        out.append(_upload_entry(rel, name, ext, kind, len(data), uid))
    return jsonify(ok=True, files=out)


def _upload_markdown(kind, label, url):
    """按类型给出对应的嵌入写法（和 md_math 认的三条指令一致）。"""
    if kind == "image":
        return "![%s](%s)" % (label, url)
    if kind in ("video", "audio"):
        return "~[%s](%s)" % (label, url)
    return "*[%s](%s)" % (label, url)


def _upload_entry(rel, name, ext, kind, size, uid=0, created=None):
    """给前端 / 模板用的一条上传记录。"""
    url = "/u/" + rel
    label = name.rsplit(".", 1)[0] if (kind != "file" and "." in name) else name
    try:
        base = request.url_root.rstrip("/")
    except RuntimeError:                     # 不在请求里（理论上不会）
        base = ""
    return {
        "id": uid, "rel": rel, "url": url, "abs_url": base + url,
        "name": name, "label": label, "ext": ext, "kind": kind, "size": size,
        "markdown": _upload_markdown(kind, label, url),
        "created": fmt_dt(created) if created else "",
        "is_image": kind == "image",
    }


app.add_url_rule("/api/upload", "api_upload", api_upload, methods=["POST"])


@app.route("/u/<path:rel>")
def upload_file(rel):
    """附件的唯一出口：路径形态写死，普通附件一律 attachment 强制下载。

    上传目录刻意不在 static/ 下 —— Flask 的静态路由会按扩展名猜 MIME 直接内联，
    那样一个 .txt 也可能被当成页面渲染。这里只有图片 / 音频 / 视频内联，其余全下载。
    """
    if not _UPLOAD_REL_RE.match(rel or ""):
        abort(404)
    ext = rel.rsplit(".", 1)[-1].lower()
    kind, mime = UPLOAD_KINDS.get(ext, ("file", "application/octet-stream"))
    try:
        resp = send_from_directory(UPLOAD_ROOT, rel, mimetype=mime, conditional=True)
    except Exception:
        abort(404)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Content-Disposition"] = "inline" if kind != "file" else "attachment"
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp


# ----------------------------------------------------------------------
# 上传页 /files（仅站长）：传文件拿 Markdown / 直链，也能翻以前传过的
# ----------------------------------------------------------------------
UPLOAD_PAGE_SIZE = 60
UPLOAD_KIND_LABEL = [("image", "图片"), ("video", "视频"), ("audio", "音频"), ("file", "文件")]


def _sync_uploads():
    """让 uploads/ 目录与 uploads 表对上。

    老版本上传的文件没有入库记录，这里按目录补进去；反过来，表里有、磁盘上已经没有的
    行也删掉（手工清理过目录之后列表才不会是幽灵条目）。
    """
    db = get_db()
    known = {r["rel"] for r in db.execute("SELECT rel FROM uploads")}
    added = 0
    for dirpath, _dirs, filenames in os.walk(UPLOAD_ROOT):
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, UPLOAD_ROOT).replace(os.sep, "/")
            if rel in known or not _UPLOAD_REL_RE.match(rel):
                continue
            ext = rel.rsplit(".", 1)[-1].lower()
            kind = UPLOAD_KINDS.get(ext, ("file", ""))[0]
            try:
                st = os.stat(full)
            except OSError:
                continue
            db.execute(
                "INSERT OR IGNORE INTO uploads(rel, name, ext, kind, size, created_at) "
                "VALUES(?,?,?,?,?,?)",
                (rel, fn, ext, kind, st.st_size,
                 datetime.fromtimestamp(st.st_mtime, timezone.utc)
                 .strftime("%Y-%m-%d %H:%M:%S")))
            added += 1
    removed = 0
    for r in list(db.execute("SELECT id, rel FROM uploads")):
        p = os.path.join(UPLOAD_ROOT, *r["rel"].split("/"))
        if not os.path.isfile(p):
            db.execute("DELETE FROM uploads WHERE id=?", (r["id"],))
            removed += 1
    if added or removed:
        db.commit()


@app.route("/files")
def uploads_page():
    """上传页：传完直接给 Markdown 与直链，下面列的是以前传过的东西。"""
    if not owner_unlocked():
        return redirect(url_for("admin_entry", next="/files"))
    _sync_uploads()
    db = get_db()
    kind = (request.args.get("kind") or "").strip()
    if kind not in dict(UPLOAD_KIND_LABEL):
        kind = ""
    where, args = (" WHERE kind=?", [kind]) if kind else ("", [])
    total = db.execute("SELECT COUNT(*) c FROM uploads" + where, args).fetchone()["c"]
    total_all = db.execute("SELECT COUNT(*) c FROM uploads").fetchone()["c"]
    used = db.execute("SELECT COALESCE(SUM(size),0) s FROM uploads").fetchone()["s"]
    try:
        page = max(1, int(request.args.get("page") or 1))
    except (TypeError, ValueError):
        page = 1
    pages = max(1, (total + UPLOAD_PAGE_SIZE - 1) // UPLOAD_PAGE_SIZE)
    page = min(page, pages)
    rows = db.execute(
        "SELECT * FROM uploads" + where +
        " ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
        args + [UPLOAD_PAGE_SIZE, (page - 1) * UPLOAD_PAGE_SIZE]).fetchall()
    items = [_upload_entry(r["rel"], r["name"], r["ext"], r["kind"], r["size"],
                           r["id"], r["created_at"]) for r in rows]
    counts = {r["kind"]: r["n"] for r in
              db.execute("SELECT kind, COUNT(*) n FROM uploads GROUP BY kind")}
    return render_template("uploads.html", items=items, cur_kind=kind, page=page,
                           pages=pages, total=total, total_all=total_all, used=used,
                           counts=counts, kinds=UPLOAD_KIND_LABEL)


@app.route("/files/<int:uid>/delete", methods=["POST"])
def delete_upload(uid):
    gate = _required_owner()
    if gate:
        return gate
    db = get_db()
    row = db.execute("SELECT rel FROM uploads WHERE id=?", (uid,)).fetchone()
    if row:
        db.execute("DELETE FROM uploads WHERE id=?", (uid,))
        db.commit()
        path = os.path.join(UPLOAD_ROOT, *row["rel"].split("/"))
        # 再保险一次：只删 uploads/ 目录里的东西
        if os.path.abspath(path).startswith(os.path.abspath(UPLOAD_ROOT) + os.sep):
            try:
                os.remove(path)
            except OSError:
                pass
    return redirect(safe_next(request.form.get("next") or "/files"))


# ----------------------------------------------------------------------
# 静态 / 错误
# ----------------------------------------------------------------------
@app.route("/favicon.ico")
def favicon():
    return send_from_directory(os.path.join(BASE_DIR, "static"), "favicon.svg",
                               mimetype="image/svg+xml")


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, msg="你访问的页面不存在"), 404


@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", code=403,
                           msg="站长口令未解锁"), 403


@app.errorhandler(400)
def bad_request(e):
    desc = getattr(e, "description", None)
    if isinstance(desc, str):
        return render_template("error.html", code=400, msg=desc), 400
    return render_template("error.html", code=400, msg="请求无效"), 400


@app.errorhandler(413)
def too_large(e):
    return render_template("error.html", code=413, msg="上传内容过大"), 413


@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", code=500, msg="服务器错误"), 500


# ----------------------------------------------------------------------
# 安全响应头
# ----------------------------------------------------------------------
def _csp_nonce():
    """每个请求一个 nonce，让 script-src 不必再挂 'unsafe-inline'。

    页首那段「先把主题写进 <html>、再加载 CSS」的内联脚本必须留在 HTML 里（外链会闪
    主题），所以用 nonce 单独放行它。同一个请求内 nonce 只生成一次（存在 g 上），
    after_request 写头时取到的就是模板里用的那一个。
    """
    nonce = getattr(g, "csp_nonce", None)
    if not nonce:
        nonce = secrets.token_urlsafe(16)
        g.csp_nonce = nonce
    return nonce


app.jinja_env.globals["csp_nonce"] = _csp_nonce

CSP = (
    "default-src 'self'; "
    "script-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https: http:; "   # 正文里的站外图片要能直接显示；
                                             # 评论走严格净化，站外图是点击后才加载
    "media-src 'self' https: http: blob:; "   # ~[标题](视频直链) 的 <video>
    "frame-src https://player.bilibili.com https://www.youtube.com "
    "https://www.youtube-nocookie.com; "      # ~[标题](B站/YouTube) 的内嵌播放器
    "font-src 'self' data: https://cdn.jsdelivr.net; "
    "connect-src 'self'; "
    "object-src 'none'; base-uri 'none'; form-action 'self'; "
    "frame-ancestors 'none'"
)


def request_is_https():
    if request.is_secure:
        return True
    if TRUST_PROXY:
        proto = (request.headers.get("X-Forwarded-Proto") or "").split(",")[0]
        return proto.strip().lower() == "https"
    return False


@app.before_request
def _cookie_secure_policy():
    """只有真的走 HTTPS 才给会话 Cookie 打 Secure。

    否则本机 http://127.0.0.1 登录会直接失效（浏览器不会回传 Secure Cookie）。
    """
    app.config["SESSION_COOKIE_SECURE"] = request_is_https()


@app.after_request
def _security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")          # 防点击劫持
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("Content-Security-Policy",
                           CSP.format(nonce=_csp_nonce()))
    if request_is_https():
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    return resp


# ----------------------------------------------------------------------
if __name__ == "__main__":
    init_db()
    print(f"Petal Blog: http://{HOST}:{PORT}  (debug={'on' if DEBUG else 'off'})",
          flush=True)
    with app.app_context():
        if not has_owner_pass():
            print(f"[提示] 还没设置站长口令：打开 http://127.0.0.1:{PORT}/admin 设置后即可写文章",
                  flush=True)
    app.run(host=HOST, port=PORT, debug=DEBUG, threaded=True)
