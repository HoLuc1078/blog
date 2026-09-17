# -*- coding: utf-8 -*-
"""一次性数据迁移（幂等，可重复跑，跑完可以删）。

用法：
    python migrate.py                    # 迁移仓库根目录的 blog.db
    python migrate.py On_server/blog.db  # 指定别的库（例如服务器上那份）

做两件事：
  1. 图标名对齐当前图标集：icon-peach → icon-taozi；其余指向已不存在图标的名字
     （含空值）→ 默认图标 icon-sakura。
  2. 清掉账号系统时代的残留对象：users / email_codes / favorites 三张表、
     site_cfg 里的 author_avatar 配置项（口令 owner_pass_hash 一律保留）。

改动前会自动在同目录留一份 blog.db.bak-<时间戳>（已被 .gitignore 忽略）。
"""

import os
import shutil
import sqlite3
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import app as blog          # noqa: E402  —— 图标清单只从 app.py 取一份，避免两处维护

# 老图标名 → 现图标名
RENAMES = {"icon-peach": "icon-taozi"}
# 账号系统时代的残留对象
LEGACY_TABLES = ("users", "email_codes", "favorites")
LEGACY_CFG_KEYS = ("author_avatar",)


def valid_icons():
    return set(blog.LOCAL_ICONS) | set(blog._icon_sprite())


def migrate(path):
    if not os.path.exists(path):
        print("找不到数据库：%s" % path)
        return 1
    valid = valid_icons()
    default = blog.DEFAULT_ICON

    backup = "%s.bak-%s" % (path, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(path, backup)
    print("备份：%s" % backup)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    changed = 0

    # ---- 1. 图标名 ----
    for old, new in RENAMES.items():
        if new not in valid:
            print("跳过 %s → %s：目标图标不存在" % (old, new))
            continue
        cur = conn.execute("UPDATE articles SET icon=? WHERE icon=?", (new, old))
        if cur.rowcount:
            print("图标改名：%s → %s（%d 篇）" % (old, new, cur.rowcount))
            changed += cur.rowcount

    rows = conn.execute("SELECT id, icon FROM articles").fetchall()
    bad = [r for r in rows if (r["icon"] or "").strip() not in valid]
    for r in bad:
        conn.execute("UPDATE articles SET icon=? WHERE id=?", (default, r["id"]))
        print("图标兜底：文章 #%d %r → %s"
              % (r["id"], r["icon"], default))
    changed += len(bad)

    # ---- 2. 账号系统残留 ----
    fk_users = any("users" in (row["table"] or "")
                   for row in conn.execute("PRAGMA foreign_key_list(articles)"))
    for t in LEGACY_TABLES:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone()
        if not exists:
            continue
        if t == "users" and fk_users:
            print("跳过 DROP TABLE users：articles 还有指向它的外键，先处理表结构")
            continue
        conn.execute("DROP TABLE %s" % t)
        print("删除旧表：%s" % t)
        changed += 1

    for k in LEGACY_CFG_KEYS:
        cur = conn.execute("DELETE FROM site_cfg WHERE key=?", (k,))
        if cur.rowcount:
            print("删除旧配置：site_cfg.%s" % k)
            changed += 1

    conn.commit()
    conn.close()
    print("完成：%s（改动 %d 处）" % (path, changed))
    if not changed:
        print("（本来就没东西要改，删掉刚生成的备份也行）")
    return 0


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE_DIR, "blog.db")
    raise SystemExit(migrate(target))
