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
  - 监听 0.0.0.0:8848
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
MIN_OWNER_PASS = 6
MAX_OWNER_PASS = 72

# 图形验证码
CAPTCHA_TTL = 5 * 60
CAPTCHA_LEN = 4
CAPTCHA_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # 去掉易混的 0/O/1/I/L
COMMENT_COOLDOWN = 15          # 同一浏览器两次评论间隔（秒）
COMMENT_RATE = (20, 600)       # 同一 IP：10 分钟最多 20 条
UNLOCK_RATE = (8, 600)         # 同一 IP：10 分钟最多 8 次口令尝试

MAX_UPLOAD = 8 * 1024 * 1024

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
#   · LOCAL_ICONS：站内自绘、定义在 templates/icons.html、随每个页面内联的一组
#     （24 个水果 + 樱花 / 彩虹 / 四叶草），在图标选择器里排最前；
#   · 其余 380 个来自 static/icons.svg —— yc-lain 博客那套 iconfont（ic- 前缀），
#     编辑器选择器直接 <use href="/static/icons.svg#ic-x"> 引用，
#     文章页只把用到的那一两个 <symbol> 内联进页面（见 post_icon_sprites）。
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
_ICON_CACHE = {"mtime": None, "map": {}, "names": ()}
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
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,
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


def load_cfg():
    """站点配置快照（含解析好的链接列表）。"""
    cfg = {
        "site_title": cfg_get("site_title", "樱羽小筑"),
        "site_subtitle": cfg_get("site_subtitle", "花见之时 · 记录代码与生活"),
        "author_nickname": cfg_get("author_nickname", "博主"),
        "author_avatar": avatar_url(),
        "author_bio": cfg_get("author_bio", ""),
        "footer_text": cfg_get("footer_text", ""),
    }
    cfg["author_links"] = _parse_links(cfg_get("author_links", "[]"))
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


def _icon_sprite():
    """static/icons.svg 里的全部 <symbol>：{名字: 片段}（按 mtime 自动重载）。"""
    try:
        mtime = os.path.getmtime(ICON_SPRITE)
    except OSError:
        return _ICON_CACHE["map"]
    if _ICON_CACHE["mtime"] != mtime:
        try:
            with open(ICON_SPRITE, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            return _ICON_CACHE["map"]
        found = {}
        for m in _SYMBOL_RE.finditer(text):
            found.setdefault(m.group(1), m.group(0))
        _ICON_CACHE.update(mtime=mtime, map=found, names=tuple(found))
    return _ICON_CACHE["map"]


def post_icons():
    """图标选择器里的全部图标：本地自绘的 27 个排前面，后面是 iconfont 那整套。"""
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
    """<use> 该指向哪里：本地自绘的在本页内联 sprite 里，iconfont 的在 static/icons.svg 里。"""
    if name in LOCAL_ICONS or name not in _icon_sprite():
        return "#" + name
    return "/static/icons.svg#" + name


def post_icon_sprites(posts):
    """把这一页用到的 iconfont 图标内联成 <symbol>（同名只出现一次）。

    本地自绘的 27 个已经在 templates/icons.html 里了，这里跳过（否则 id 会重复）；
    这样文章页为了图标不需要额外拉 700KB 的 sprite。
    """
    sprite = _icon_sprite()
    need, seen = [], set()
    for p in posts or []:
        name = post_icon(p)
        if name in seen or name in LOCAL_ICONS or name not in sprite:
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
    body_html = md_math.md_render(row["content_md"])
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
    return max(0, min(999, n))


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
    elif not captcha_ok(captcha):
        err = "captcha"
    elif not rate_ok("cmt", ip_of(), *COMMENT_RATE):
        err = "rate"
    else:
        last = session.get("last_cmt", 0)
        if time.time() - float(last) < COMMENT_COOLDOWN:
            err = "slow"
    if err:
        return back(err)
    db.execute(
        "INSERT INTO comments(article_id, parent_id, author_name, ip, content) "
        "VALUES(?,?,?,?,?)",
        (aid, parent_id, name, ip_of(), content),
    )
    db.commit()
    session["last_cmt"] = time.time()
    resp = redirect(url_for("article", aid=aid) + "#comments")
    resp.set_cookie("petal_name", quote(name), max_age=30 * 24 * 3600,
                    samesite="Lax", httponly=False)
    return resp


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
    if "links" in payload:
        links = payload.get("links")
        if not isinstance(links, list) or len(links) > MAX_LINKS:
            return jsonify(error=f"链接最多 {MAX_LINKS} 条"), 400
        clean, skipped = clean_links(links)
        cfg_set("author_links", json.dumps(clean, ensure_ascii=False))
        upd.append("links")
        if skipped:
            return jsonify(ok=True, updated=upd,
                           warn=f"{skipped} 条链接已忽略")
    if not upd:
        return jsonify(error="没有可更新的字段"), 400
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
    return jsonify(ok=True, html=md_math.md_render(md))


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
CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https: http:; "   # 站外图片要等用户点击后才会加载，
                                             # 这里必须放行，否则点了也出不来
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
    resp.headers.setdefault("Content-Security-Policy", CSP)
    if request_is_https():
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    return resp


# ----------------------------------------------------------------------
if __name__ == "__main__":
    init_db()
    print(f"Petal Blog: http://{HOST}:{PORT}", flush=True)
    with app.app_context():
        if not has_owner_pass():
            print(f"[提示] 还没设置站长口令：打开 http://127.0.0.1:{PORT}/admin 设置后即可写文章",
                  flush=True)
    app.run(host=HOST, port=PORT, debug=True, threaded=True)
