# -*- coding: utf-8 -*-
r"""
Markdown + LaTeX 渲染管线（洛谷格式手册的完整实现）
==================================================
本模块按「洛谷 Markdown 格式手册 / 编辑器帮助手册」逐条实现洛谷站内的
Markdown 语法，外加本站原有的 LaTeX 支持。

洛谷语法清单（✅ = 支持，❌ = 洛谷本身也没有，故不实现）
------------------------------------------------------
✅ 强调：`*斜体*` `**粗体**` `***粗斜体***`
✅ 删除线：`~~删除线~~`                        → <del>
✅ 任务列表：`- [ ]` / `- [x]`                 → 只读复选框
✅ 脚注：`文字[^1]` + `[^1]: 内容`
✅ 表格：GFM 表格 + 单元格合并（`^` 向上合并 / `<` 向左合并）+ <colgroup>
✅ 代码块：```cpp line-numbers```（行号）、```cpp lines=5-6,11```（区间高亮）
✅ 容器 / 折叠框：`:::info[标题]{open}`，类型仅 info / success / warning / error
   → <details class="md-block md-block-info"><summary>…</summary>…</details>
   （无标题时用中文默认名：提示 / 成功 / 警告 / 错误；`{open}` 默认展开；可嵌套）
✅ 居中 / 居右 / 居左：`:::align{center}` / `{right}` / `{left}`（只影响段落与标题）
✅ 题记：`:::epigraph[——署名]`（署名移到末尾并右对齐）
✅ 反 AI 水印：`::anti-ai[隐藏文字]`（不可见，但复制时会带走）
✅ 表格样式：`::cute-table{tuack|three}[表 1]`
✅ 引用、列表、标题、分隔线、行内代码、自动链接、段内换行（行末两空格或 `\`）
✅ 数学：`$..$`、`$$..$$`，以及本站额外支持的 `\\(..\\)`、`\\[..\\]`
❌ 上标 `^x^` / 下标 `~x~` / 高亮 `==x==` / `->居中<-` / `[TOC]` / 定义列表 /
   缩写 / 原始 HTML —— 洛谷一律按纯文本输出（公式请用 `$x^2$`、`$\\text{H}_2\\text{O}$`）

渲染顺序
--------
1. `_split_containers()`  先摘出块级容器 / 叶子指令（可递归：容器内仍是完整 Markdown）
2. `protect()`            摘出行内代码 → 数学 → 删除线 → 自动链接（代码与公式内部的
                          `$`、`~~`、URL 一律原样保留）
3. `python-markdown`      渲染普通 Markdown（fenced_code / tables / footnotes / attr_list…）
4. `_LuoguTreeprocessor`  任务列表、表格合并、colgroup、cute-table 包裹
5. `_LuoguPostprocessor`  代码块行号 / 区间高亮（拆行成 <span class="md-line">）
6. `sanitize()`           白名单净化（XSS 防护），类名走白名单，只放行任务列表复选框
7. `_restore()`           回填公式 / 行内代码 / 删除线 / 容器 HTML

私有代理字符
------------
\\uE000{i}\\uE001   行内 / 行间公式
\\uE002{i}\\uE003   行内代码
\\uE004{i}\\uE005   预渲染容器 HTML（净化后回填，内容已在递归时净化过）
\\uE006{i}\\uE007   cute-table 指令（交给 treeprocessor 包裹后面的表格）
"""

import re
import threading
from html.parser import HTMLParser
from xml.etree import ElementTree as ET

import markdown as _pymd
from markdown.extensions import Extension
from markdown.postprocessors import Postprocessor
from markdown.treeprocessors import Treeprocessor

M_INLINE_BEGIN = "\uE000"
M_END = "\uE001"
C_BEGIN = "\uE002"
C_END = "\uE003"
H_BEGIN = "\uE004"
H_END = "\uE005"
K_BEGIN = "\uE006"
K_END = "\uE007"

# ----------------------------------------------------------------------
# 行级语法
# ----------------------------------------------------------------------
_FENCE_INFO = re.compile(r"^([ \t]{0,3})(`{3,}|~{3,})[ \t]*(.*?)[ \t]*$")
_FENCE_OPEN = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})[ \t]*(.*)$")
_FENCE_CLOSE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})[ \t]*$")
_FENCE_LINE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")
_INLINE_CODE = re.compile(r"(?<!`)(`{1,3})(?!`)([^\n]*?)(?<!`)\1(?!`)")

# :::type[标题]{属性}   容器（至少三个冒号）
_CONTAINER_HEAD = re.compile(r"^[ \t]{0,3}(:{3,})[ \t]*([A-Za-z][\w\-]*)[ \t]*(.*)$")
_CONTAINER_CLOSE = re.compile(r"^[ \t]{0,3}:{3,}[ \t]*$")
# ::type[标题]{属性}     叶子指令（恰好两个冒号，且必须独立成行）
_LEAF_HEAD = re.compile(r"^[ \t]{0,3}::[ \t]*([A-Za-z][\w\-]*)(.*)$")

# 容器类型：只有这四个是洛谷认的，标题缺省时用中文默认名
CONTAINER_TYPES = {
    "info": "提示",
    "success": "成功",
    "warning": "警告",
    "error": "错误",
}
_ALIGN_DIRS = ("center", "right", "left")
_CUTE_STYLES = ("tuack", "three")

_LINES_SPEC = re.compile(r"^[0-9][0-9,\-\s]*$")
_ATTR_OK = re.compile(r"^[A-Za-z_][\w\-]*$")


def _backslash_run(text, pos):
    """统计 text[pos] 之前连续反斜杠个数：奇数则该字符被转义。"""
    n = 0
    k = pos - 1
    while k >= 0 and text[k] == "\\":
        n += 1
        k -= 1
    return n


def _parse_tail(tail):
    """解析指令名后面的 `[标题]` 与 `{属性}`（顺序不限）。

    返回 (label, attrs, 其余文字)。洛谷只把 `[标题]` 当标题，
    `:::info 标题` 这种写法会把「标题」当成正文首行 —— 这里保持同样行为。
    """
    label = None
    attrs = None
    extra = []
    rest = (tail or "").strip()
    while rest:
        if rest.startswith("["):
            end = rest.find("]")
            if end < 0:
                extra.append(rest)
                break
            if label is None:
                label = rest[1:end]
            rest = rest[end + 1:].strip()
        elif rest.startswith("{"):
            end = rest.find("}")
            if end < 0:
                extra.append(rest)
                break
            if attrs is None:
                attrs = rest[:end + 1]
            rest = rest[end + 1:].strip()
        else:
            extra.append(rest)
            break
    return label, attrs, " ".join(extra).strip()


def _match_container(line):
    m = _CONTAINER_HEAD.match(line)
    if not m:
        return None
    name = m.group(2)
    label, attrs, extra = _parse_tail(m.group(3))
    return name, label, attrs, extra


def _match_leaf(line):
    m = _LEAF_HEAD.match(line)
    if not m:
        return None
    name = m.group(1)
    label, attrs, extra = _parse_tail(m.group(2))
    return name, label, attrs, extra


def _attr_flags(raw):
    """把 `{open}` / `{tuack=3}` 这样的属性串解析成 (位置参数集合, 原始词表)。"""
    if not raw:
        return set(), []
    body = raw.strip()
    if body.startswith("{") and body.endswith("}"):
        body = body[1:-1]
    toks = [t.strip() for t in re.split(r"[\s,]+", body) if t.strip()]
    return {t.split("=", 1)[0].lower() for t in toks}, toks


def _inline_md(text, strict=False):
    """把一行文字当「行内 Markdown」渲染，并去掉最外层 <p>（标题、容器标题用）。"""
    if not text:
        return ""
    html = md_render(text, strict=strict)
    m = re.match(r"^<p>(.*)</p>\s*$", html, re.S)
    return m.group(1) if m else html


# ----------------------------------------------------------------------
# 容器 / 叶子指令
# ----------------------------------------------------------------------
class _TokenStore:
    def __init__(self):
        self.seq = [0]
        self.map = {}          # token -> (kind, raw)
        self.cute = {}         # 序号 -> (样式, 表标题)：cute-table 用

    def new(self, kind, raw):
        i = self.seq[0]
        self.seq[0] += 1
        if kind.startswith("m-"):
            token = f"{M_INLINE_BEGIN}{i}{M_END}"
        elif kind == "code":
            token = f"{C_BEGIN}{i}{C_END}"
        elif kind == "cute":
            token = f"{K_BEGIN}{i}{K_END}"
            self.cute[i] = raw
        else:
            token = f"{H_BEGIN}{i}{H_END}"
        self.map[token] = (kind, raw)
        return token


def _esc_text(v):
    return (v or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _block_span(lines, start):
    """start 指向容器开头那一行：返回 (结束行下标, 内部行列表)。

    以「冒号数量 >= 开头」的纯冒号行作为结束；内部再出现容器开头则深度 +1，
    因此 `:::warning` 里嵌 `:::success` 也能正确配对（洛谷建议外层冒号更多）。
    """
    n = len(lines)
    depth = 0
    inner = []
    j = start + 1
    f_in = False
    fc = ""
    fl = 0
    while j < n:
        line = lines[j]
        if not f_in:
            mf = _FENCE_LINE.match(line)
            if mf:
                f_in = True
                fc = mf.group(1)[0]
                fl = len(mf.group(1))
                inner.append(line)
                j += 1
                continue
            if _match_container(line):
                depth += 1
                inner.append(line)
                j += 1
                continue
            if _CONTAINER_CLOSE.match(line):
                if depth == 0:
                    return j, inner
                depth -= 1
                inner.append(line)
                j += 1
                continue
            inner.append(line)
            j += 1
        else:
            inner.append(line)
            if _FENCE_LINE.match(line):
                seg = line.lstrip(" \t")
                if seg and seg[0] == fc and seg.rstrip(" \t").count(fc) >= fl:
                    f_in = False
            j += 1
    return n, inner      # 未闭合：容错到结尾


def _details_html(name, title, inner_html, opened):
    """洛谷的容器就是 <details>/<summary>：标题点了能折叠。"""
    safe = re.sub(r"[^A-Za-z0-9_-]", "", name) or "box"
    open_attr = " open" if opened else ""
    return (
        f'<details class="md-block md-block-{safe}"{open_attr}>'
        f'<summary class="md-block-head">'
        f'<span class="md-block-tag">{title}</span>'
        '<span class="md-block-caret">▾</span>'
        "</summary>"
        f'<div class="md-block-body">{inner_html}</div>'
        "</details>"
    )


def _plain_box_html(name, title, inner_html):
    """洛谷没有的容器名：仍然给一个朴素盒子（比原样吐出来友好）。"""
    safe = re.sub(r"[^A-Za-z0-9_-]", "", name) or "box"
    return (
        f'<div class="md-block md-block-{safe}">'
        f'<div class="md-block-head"><span class="md-block-tag">{title}</span>'
        '<span class="md-block-caret">▾</span></div>'
        f'<div class="md-block-body">{inner_html}</div>'
        "</div>"
    )


def _render_container(name, label, attrs_raw, inner_lines, strict):
    """渲染一个 :::type 容器，返回要回填的 HTML。"""
    flags, toks = _attr_flags(attrs_raw)
    lname = name.lower()
    inner_md = "\n".join(inner_lines)

    # ---- 居中 / 居右 / 居左：不产生包裹元素，只给段落与标题加对齐类 ----
    if lname == "align":
        direction = ""
        bare = [t.lower() for t in toks]
        for d in _ALIGN_DIRS:
            if d in bare or f"align={d}" in bare:
                direction = d
                break
        if not direction:
            direction = "center"      # 洛谷只认属性键；给个合理兜底
        body = md_render(inner_md, strict=strict)
        return f'<div class="md-align md-align-{direction}">{body}</div>'

    # ---- 题记：署名挪到最后一行并右对齐 ----
    if lname == "epigraph":
        body = md_render(inner_md, strict=strict)
        src = _inline_md(label, strict=strict) if label else ""
        tail = f'<p class="md-epigraph-src">{src}</p>' if src else ""
        cls = "epigraph has-source" if src else "epigraph"
        return f'<div class="{cls}">{body}{tail}</div>'

    # ---- info / success / warning / error：洛谷认的四个类型 ----
    if lname in CONTAINER_TYPES:
        title = _inline_md(label, strict=strict) if label else CONTAINER_TYPES[lname]
        return _details_html(lname, title, md_render(inner_md, strict=strict),
                             "open" in flags)

    # ---- 其它名字：朴素盒子，标题取 [..] 或用类型名 ----
    title = _inline_md(label, strict=strict) if label else _esc_text(name.upper())
    return _plain_box_html(lname, title, md_render(inner_md, strict=strict))


def _split_containers(content, store, strict=False):
    """把 :::容器 / ::叶子指令 摘成 HTML 代理，返回剩余可交给 protect 的文本。"""
    lines = content.split("\n")
    res = []
    buf = []
    i = 0
    n = len(lines)
    in_fence = False
    fence_char = ""
    fence_len = 0

    def flush():
        if buf:
            res.extend(buf)
            buf.clear()

    while i < n:
        line = lines[i]
        if in_fence:
            buf.append(line)
            if _FENCE_LINE.match(line):
                seg = line.lstrip(" \t")
                if seg and seg[0] == fence_char and \
                        seg.rstrip(" \t").count(fence_char) >= fence_len:
                    in_fence = False
            i += 1
            continue

        mf = _FENCE_LINE.match(line)
        if mf:
            in_fence = True
            fence_char = mf.group(1)[0]
            fence_len = len(mf.group(1))
            buf.append(line)
            i += 1
            continue

        mo = _match_container(line)
        if mo:
            flush()
            name, label, attrs, extra = mo
            end, inner = _block_span(lines, i)
            if extra:                 # `:::info 标题`：多余文字当正文首行
                inner.insert(0, extra)
            html = _render_container(name, label, attrs, inner, strict)
            token = store.new("html", html)
            res.append("")
            res.append(token)
            res.append("")
            i = end + 1
            continue

        ml = _match_leaf(line)
        if ml:
            name, label, attrs, extra = ml
            lname = name.lower()
            if lname == "anti-ai":
                # 洛谷：隐藏文字。人看不见，但复制 Markdown 时会被带走。
                flush()
                text = " ".join(x for x in (label, extra) if x)
                token = store.new("html",
                                  '<p class="invisible">%s</p>' % _esc_text(text))
                res.extend(["", token, ""])
                i += 1
                continue
            if lname == "cute-table":
                flags, _toks = _attr_flags(attrs)
                style = "tuack"
                for s in _CUTE_STYLES:
                    if s in flags:
                        style = s
                        break
                flush()
                token = store.new("cute", (style, label or ""))
                res.extend(["", token, ""])
                i += 1
                continue
            # 其它叶子指令（洛谷未定义）：当普通段落原样留着
        buf.append(line)
        i += 1
    flush()
    return "\n".join(res)


# ----------------------------------------------------------------------
# 行内保护：代码 / 数学 / 删除线 / 自动链接
# ----------------------------------------------------------------------
def _find_close(text, start, close, allow_newlines):
    """从 start 处找 close 串，可跨行时以空行（段落边界）为上限；返回下标或 -1。"""
    idx = start
    while True:
        pos = text.find(close, idx)
        if pos < 0:
            return -1
        if not allow_newlines:
            nl = text.find("\n", start, pos)
            if nl >= 0:
                return -1
            return pos
        seg = text[start:pos]
        if "\n\n" in seg or re.search(r"\n[ \t]+\n", seg):
            return -1
        if _backslash_run(text, pos) % 2 == 1:
            idx = pos + len(close)
            continue
        return pos


def _substitute_math(text, store):
    """在无围栏、无行内代码的文本上摘除公式。返回替换后的文本。"""
    out = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        escaped = _backslash_run(text, i) % 2 == 1
        if escaped:
            out.append(ch)
            i += 1
            continue
        if ch == "$" and i + 1 < n and text[i + 1] == "$":
            j = _find_close(text, i + 2, "$$", allow_newlines=True)
            if j >= 0:
                out.append(store.new("m-block", text[i + 2:j]))
                i = j + 2
                continue
            i += 1
            continue
        if ch == "\\" and i + 1 < n and text[i + 1] in "([":
            close = r"\]" if text[i + 1] == "[" else r"\)"
            kind = "m-block" if text[i + 1] == "[" else "m-inline"
            allow = text[i + 1] == "["
            j = _find_close(text, i + 2, close, allow_newlines=allow)
            if j >= 0:
                out.append(store.new(kind, text[i + 2:j]))
                i = j + 2
                continue
            out.append(ch)
            i += 1
            continue
        if ch == "\\" and i + 1 < n and text[i + 1] == "$":
            out.append("$")
            i += 2
            continue
        if ch == "$":
            # 行内公式 $...$：仅同行闭合；紧跟空白/数字时视为价格文本
            nxt = text[i + 1] if i + 1 < n else ""
            if not nxt or nxt.isspace() or nxt.isdigit():
                out.append(ch)
                i += 1
                continue
            j = text.find("$", i + 1)
            if j < 0:
                out.append(ch)
                i += 1
                continue
            nl = text.find("\n", i, j)
            if 0 <= nl < j:
                out.append(ch)
                i += 1
                continue
            inner = text[i + 1:j]
            if not inner or inner[0].isspace() or inner[-1].isspace() or inner[-1] == "\\":
                out.append(ch)
                i += 1
                continue
            out.append(store.new("m-inline", inner))
            i = j + 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


# GFM 删除线：~~文字~~ → <del>文字</del>（内部仍是 Markdown，交给后面的解析器）
_STRIKE = re.compile(r"(?<!~)~~(?=[^\s~])(.+?)(?<=[^\s~])~~(?!~)", re.S)
# GFM 自动链接：裸 URL。前面的字符不允许是链接/属性边界，避免破坏 [x](url) 与 <a href="">
_AUTOLINK = re.compile(
    r"(?<![\w/\"'=(<\[`>])(https?://[^\s<>\"'`）】」]+)")
_AUTOLINK_TAIL = re.compile(r"[.,;:!?、。，；：！？]+$")


def _apply_inline_extras(text):
    """删除线 + 裸链接自动识别（此时代码与公式已换成私有代理字符）。"""
    text = _STRIKE.sub(lambda m: "<del>" + m.group(1) + "</del>", text)

    def _link(m):
        url = m.group(1)
        tail = ""
        t = _AUTOLINK_TAIL.search(url)
        if t:
            url, tail = url[:t.start()], url[t.start():]
        # 括号要配平，否则把多余的后括号还给正文
        while url.endswith(")") and url.count("(") < url.count(")"):
            url, tail = url[:-1], ")" + tail
        if not url:
            return m.group(0)
        return f'<a href="{url}">{url}</a>{tail}'

    return _AUTOLINK.sub(_link, text)


def protect(content):
    """输入整篇 Markdown，返回 (受保护文本, token 表)。"""
    store = _TokenStore()
    pieces = []
    buf = []
    fence_char = ""
    fence_len = 0
    in_fence = False

    def flush():
        nonlocal buf
        if buf:
            pieces.append(("proc", "\n".join(buf)))
            buf = []

    for line in content.split("\n"):
        if not in_fence:
            m = _FENCE_OPEN.match(line)
            if m:
                flush()
                fence_char = m.group(1)[0]
                fence_len = len(m.group(1))
                pieces.append(("raw", _normalize_fence(line)))
                in_fence = True
                continue
            buf.append(line)
        else:
            cm = _FENCE_CLOSE.match(line)
            if cm and cm.group(1)[0] == fence_char and len(cm.group(1)) >= fence_len:
                pieces.append(("raw", line))
                in_fence = False
            else:
                pieces.append(("raw", line))
    flush()

    final_parts = []
    for kind, text in pieces:
        if kind == "raw":
            final_parts.append(text)
            continue
        # 1) 行内代码先摘除（其内部的 $ / ~~ / URL 都不算语法）
        code_parts = []
        pos = 0
        for m in _INLINE_CODE.finditer(text):
            code_parts.append(text[pos:m.start()])
            code_parts.append(store.new("code", m.group(2)))
            pos = m.end()
        code_parts.append(text[pos:])
        segment = "".join(code_parts)
        # 2) 数学
        segment = _substitute_math(segment, store)
        # 3) 删除线 / 自动链接
        segment = _apply_inline_extras(segment)
        final_parts.append(segment)
    return "\n".join(final_parts), store


def _normalize_fence(line):
    """把 ```cpp line-numbers lines=5-6,11 改写成 python-markdown 认的属性写法。

    python-markdown 的 fenced_code 只接受「单一语言」或 `{...}` 属性两种信息串，
    多一个空格分词（line-numbers / lines=5-6,11）整段围栏就会失效、代码被当成正文。
    行号与高亮区间随后由 _LuoguPostprocessor 消费（data-line 需要 attr_list 扩展）。
    """
    m = _FENCE_INFO.match(line)
    if not m:
        return line
    indent, fence, info = m.groups()
    if not info or info.startswith("{"):
        return line
    lang = ""
    classes = []
    dataline = ""
    for tok in info.split():
        if tok in ("line-numbers", "linenums", "showLineNumbers", "showLineNumber"):
            if "line-numbers" not in classes:
                classes.append("line-numbers")
        elif tok.startswith("lines="):
            spec = tok[6:].strip()
            if spec and _LINES_SPEC.match(spec):
                dataline = spec
        elif ":" in tok and not lang:               # ```cpp:line-numbers
            head, extra = tok.split(":", 1)
            if head:
                lang = head
            if extra in ("line-numbers", "linenums") and "line-numbers" not in classes:
                classes.append("line-numbers")
        elif not lang:
            lang = tok
        else:
            t = tok.lstrip(".")
            if _ATTR_OK.match(t) and t not in classes:
                classes.append(t)
    parts = ["." + re.sub(r"[^0-9A-Za-z#.+_-]", "", lang)] if lang else [".plain"]
    for c in classes:
        parts.append("." + c)
    attr = f' data-line="{dataline}"' if dataline else ""
    return f"{indent}{fence}{{{' '.join(parts)}{attr}}}"


# ----------------------------------------------------------------------
# 树处理：任务列表 / 表格合并 / cute-table
# ----------------------------------------------------------------------
_TASK_ITEM = re.compile(r"^\[([ xX])\][ \t]+")
_CUTE_MARK = re.compile("^\\s*" + re.escape(K_BEGIN) + r"(\d+)" + re.escape(K_END) + "\\s*$")


def _cell_marker(cell):
    """单元格内容恰好是 `^` / `<` 时返回标记，否则 None（与洛谷判定一致）。"""
    if len(cell):
        return None
    txt = (cell.text or "").strip()
    if txt == "^":
        return "^"
    if txt == "<":
        return "<"
    return None


def _reorder(el, items):
    for c in list(el):
        el.remove(c)
    for c in items:
        el.append(c)


def _task_lists(root):
    """GFM 任务列表：- [x] / - [ ] → 只读复选框。"""
    for ul in root.iter("ul"):
        items = [li for li in list(ul) if li.tag == "li"]
        hit = 0
        for li in items:
            txt = li.text or ""
            m = _TASK_ITEM.match(txt)
            if not m:
                continue
            box = ET.Element("input", {"type": "checkbox", "disabled": "disabled"})
            if m.group(1).lower() == "x":
                box.set("checked", "checked")
            # 复选框要排在文字前面：文字挂到它尾巴上
            box.tail = txt[m.end():]
            li.text = None
            li.insert(0, box)
            cls = (li.get("class") or "").split()
            if "task-list-item" not in cls:
                cls.append("task-list-item")
            li.set("class", " ".join(cls))
            hit += 1
        if hit:
            cls = (ul.get("class") or "").split()
            if "contains-task-list" not in cls:
                cls.append("contains-task-list")
            ul.set("class", " ".join(cls))


def _merge_tables(root):
    """表格单元格合并：`^` 向上合并（rowspan），`<` 向左合并（colspan）+ <colgroup>。"""
    for table in root.iter("table"):
        rows = [tr for tr in table.iter("tr")]
        if not rows:
            continue
        grid = []             # grid[r][c] = 该格元素
        occupy_until = {}     # 列 -> 被 rowspan 占到第几行
        for r, tr in enumerate(rows):
            occupied = {c for c, last in occupy_until.items() if last >= r}
            col = 0
            keep = []
            rowmap = {}
            for cell in list(tr):
                while col in occupied:
                    col += 1
                marker = _cell_marker(cell)
                if marker == "^":
                    src = grid[r - 1].get(col) if r > 0 else None
                    if src is not None:
                        src.set("rowspan",
                                str(int(src.get("rowspan", "1") or 1) + 1))
                        occupy_until[col] = r
                        rowmap[col] = src
                        col += 1
                        continue
                    # 孤儿标记（上面没有可合并的格）：原样留成字面量
                elif marker == "<":
                    if keep:
                        prev = keep[-1]
                        prev.set("colspan",
                                 str(int(prev.get("colspan", "1") or 1) + 1))
                        col += 1
                        continue
                keep.append(cell)
                rowmap[col] = cell
                occupy_until[col] = r
                col += 1
            if keep != list(tr):
                _reorder(tr, keep)
            grid.append(rowmap)

        # 补一个 <colgroup>（洛谷每个表格都会插）
        ncols = 0
        for rowmap in grid:
            span = 0
            for cell in rowmap.values():
                if cell.get("rowspan"):
                    continue
                span += int(cell.get("colspan", "1") or 1)
            ncols = max(ncols, span)
        if ncols and table.find("colgroup") is None:
            cg = ET.Element("colgroup")
            for _ in range(ncols):
                ET.SubElement(cg, "col")
            # caption 必须排在最前面，colgroup 紧随其后
            first = list(table)[0].tag if len(table) else ""
            table.insert(1 if first == "caption" else 0, cg)


def _cute_tables(root, cute_map):
    """::cute-table{tuack} 会把它下面那张表格包进样式容器里。"""
    if not cute_map:
        return
    for parent in list(root.iter()):
        kids = list(parent)
        for idx, el in enumerate(kids):
            if el.tag != "p":
                continue
            m = _CUTE_MARK.match(el.text or "")
            if not m:
                continue
            key = int(m.group(1))
            if key not in cute_map:
                continue
            table = None
            for j in range(idx + 1, len(kids)):
                cand = kids[j]
                if cand.tag == "table":
                    table = cand
                    break
                if cand.tag == "p" and not (cand.text or "").strip():
                    continue
                break
            if table is None:
                continue
            style, caption = cute_map[key]
            div = ET.Element("div", {"class": f"cute-table cute-table-{style}"})
            if caption:
                # caption 必须是 table 的子元素（放在 div 里会被 HTML 解析器丢掉）
                cap = ET.Element("caption")
                cap.text = caption
                table.insert(0, cap)
            div.append(table)
            parent.remove(el)
            parent.remove(table)
            parent.insert(min(idx, len(parent)), div)


class _LuoguTreeprocessor(Treeprocessor):
    def __init__(self, md=None, cute_map=None):
        super().__init__(md)
        # 注意：不能写成 `cute_map or {}` —— 空 dict 是 falsy，
        # 那样 treeprocessor 会拿到另一个新字典，永远看不到后面填进去的表。
        self.cute_map = cute_map if cute_map is not None else {}

    def run(self, root):
        _task_lists(root)
        _cute_tables(root, self.cute_map)
        _merge_tables(root)
        # 空属性（checked / disabled 等）在 XHTML 输出里也要是合法的
        return root


# ----------------------------------------------------------------------
# 后处理：代码块行号与区间高亮
# ----------------------------------------------------------------------
_CODE_BLOCK = re.compile(
    r"<pre(?P<pre>[^>]*)>[ \t]*<code(?P<code>[^>]*)>(?P<body>.*?)</code>[ \t]*</pre>",
    re.S)
_ATTR_DATA_LINE = re.compile(r'\s*data-line="([^"]*)"')


def _split_lines(spec, total):
    """把 `5-6,11` 解析成行号集合。"""
    out = set()
    for part in (spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part[1:]:
            a, _, b = part.partition("-")
            try:
                a, b = int(a), int(b)
            except ValueError:
                continue
            if a > b:
                a, b = b, a
            for i in range(a, b + 1):
                if 1 <= i <= total:
                    out.add(i)
        else:
            try:
                i = int(part)
            except ValueError:
                continue
            if 1 <= i <= total:
                out.add(i)
    return out


def _code_postprocess(html):
    def fix(m):
        pre_attr = m.group("pre")
        code_attr = m.group("code")
        body = m.group("body")
        dm = _ATTR_DATA_LINE.search(code_attr)
        spec = dm.group(1) if dm else ""
        numbered = "line-numbers" in pre_attr
        if not numbered and not spec:
            return m.group(0)
        code_attr = _ATTR_DATA_LINE.sub("", code_attr)
        lines = body.split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        hl = _split_lines(spec, len(lines))
        chunks = []
        for i, ln in enumerate(lines, 1):
            cls = "md-line md-hl" if i in hl else "md-line"
            chunks.append(f'<span class="{cls}">{ln}</span>')
        new_pre = pre_attr
        if numbered and "line-numbers" not in new_pre:
            new_pre = (new_pre + ' class="line-numbers"') if "class=" not in new_pre \
                else re.sub(r'class="([^"]*)"', r'class="\1 line-numbers"', new_pre, count=1)
        return (f"<pre{new_pre}><code{code_attr}>{''.join(chunks)}</code></pre>")

    return _CODE_BLOCK.sub(fix, html)


class _LuoguPostprocessor(Postprocessor):
    def run(self, text):
        return _code_postprocess(text)


class _LuoguExtension(Extension):
    """洛谷扩展：任务列表 / 表格合并 / colgroup / cute-table / 代码块行号。

    `cute_map` 每次渲染前刷新，treeprocessor 持有的是同一个 dict，
    因此不需要重复注册（python-markdown 的注册表不适合同名覆盖）。
    """

    def __init__(self):
        super().__init__()
        self.cute_map = {}

    def extendMarkdown(self, md):
        md.treeprocessors.register(
            _LuoguTreeprocessor(md, self.cute_map), "luogu_tree", 5)
        # 20 < RawHtmlPostprocessor 的 30，因此跑在「占位符还原」之后
        md.postprocessors.register(_LuoguPostprocessor(md), "luogu_code", 20)


# ----------------------------------------------------------------------
# 净化（白名单）
# ----------------------------------------------------------------------
_SAFE_TAGS = {
    "p", "br", "strong", "b", "em", "i", "del", "s", "u", "code", "pre",
    "blockquote", "ul", "ol", "li", "hr", "h1", "h2", "h3", "h4", "h5", "h6",
    "a", "img", "table", "thead", "tbody", "tfoot", "tr", "th", "td",
    "sup", "sub", "span", "div", "kbd", "mark", "details", "summary",
    "section", "colgroup", "col", "caption", "input", "dl", "dt", "dd",
}

# 类名白名单：只放行渲染器自己产出的类，避免评论者用 .btn / .tag-chip 伪造站内控件
_CLASS_ALLOW = re.compile(
    r"^(?:md-[\w-]+|math|math-inline|math-block|katex|katex-display|"
    r"language-[\w#+.+-]+|line-numbers|contains-task-list|task-list-item|"
    r"footnote|footnotes|footnote-ref|footnote-backref|"
    r"epigraph|has-source|cute-table|cute-table-tuack|cute-table-three|"
    r"invisible)$")
_FOOTNOTE_ID = re.compile(r"^(?:user-content-)?fn(?:ref)?[-:][\w.-]+$")

_URL_PROTO = re.compile(r"^(https?:|mailto:|#|/|\.\.?/)", re.I)
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")
_FORCED_REL = "nofollow noopener noreferrer"


def _local_src_ok(v):
    """严格模式的 img src：只放行站内相对路径（防追踪信标）。"""
    if not v or len(v) > 2000:
        return False
    if v.startswith("//") or _SCHEME_RE.match(v):
        return False
    return v.startswith(("/", "./", "../"))


_VOID_TAGS = {"br", "hr", "img", "input", "wbr", "source", "col"}
_BLOCK_DROP = {"script", "style", "noscript", "template", "iframe", "object", "embed"}
_SKIP_TAGS = {"form", "select", "textarea", "button", "svg", "math", "video",
              "audio", "canvas", "link", "meta", "base"}


def _clean_class(value):
    out = []
    for c in re.split(r"\s+", value or ""):
        c = c[:64]
        if c and _CLASS_ALLOW.match(c) and c not in out:
            out.append(c)
    return " ".join(out)


class _Sanitizer(HTMLParser):
    """白名单净化：丢弃危险标签，仅保留安全标签与受控属性。

    strict=True 用于**访客可写**的内容（评论）：站外图片改为「点击后加载」
    （默认不发请求，防追踪信标）、禁止复用站内 UI 类名（防界面伪装）、
    并由服务端强制 rel。
    """

    def __init__(self, strict=False):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.drop_stack = []
        self.strict = strict

    def _dropping(self):
        return any(self.drop_stack)

    def _attrs(self, tag, attrs):
        allowed = []
        for k, v in attrs:
            kl = (k or "").lower()
            v = v if v is not None else ""
            if kl == "class" and v:
                cls = _clean_class(v)
                if cls:
                    allowed.append((kl, cls))
            elif kl == "href" and tag == "a":
                if _URL_PROTO.match(v) and len(v) <= 2000:
                    allowed.append((kl, v))
            elif kl == "src" and tag == "img":
                ok = _local_src_ok(v) if self.strict else (
                    bool(_URL_PROTO.match(v)) and len(v) <= 2000)
                if ok:
                    allowed.append((kl, v))
            elif kl == "id" and _FOOTNOTE_ID.match(v):
                # 只放行脚注锚点 id，避免评论者用 id 撞掉站内元素
                allowed.append((kl, v))
            elif kl == "open" and tag == "details":
                allowed.append((kl, ""))
            elif kl in ("alt", "title", "target", "rel") and tag in ("a", "img") and v:
                if kl == "rel" and self.strict:
                    continue
                if kl == "target" and self.strict and v != "_blank":
                    continue
                if len(v) <= 500:
                    allowed.append((kl, v))
            elif kl in ("align", "rowspan", "colspan") and tag in ("th", "td", "table"):
                if re.fullmatch(r"[a-zA-Z0-9]{1,8}", v):
                    allowed.append((kl, v))
        if self.strict and tag == "a":
            allowed.append(("rel", _FORCED_REL))
        return allowed

    def _strict_img_placeholder(self, attrs):
        """严格模式下的站外图片：返回「点击后加载」占位 HTML。"""
        src = alt = ""
        for k, v in attrs:
            kl = (k or "").lower()
            v = v or ""
            if kl == "src" and v:
                src = v
            elif kl == "alt" and v:
                alt = v[:200]
        if not src or len(src) > 2000 or src.startswith("#"):
            return None
        if _local_src_ok(src):
            return None
        if not _URL_PROTO.match(src):
            return None
        host = _SCHEME_RE.sub("", src)
        if host.startswith("//"):
            host = host[2:]
        host = host.split("/")[0].split("?")[0].split("#")[0][:80] or "外部站点"
        host_e = self._esc_text(host)
        data_alt = f' data-alt="{self._esc_attr(alt)}"' if alt else ""
        return (
            '<span class="ext-img">'
            f'<span class="ext-img-tip">外部图片 · {host_e} · 点击前不会加载</span>'
            f'<button type="button" class="ext-img-load" data-src="{self._esc_attr(src)}"{data_alt}'
            f'>点击加载图片（会向 {host_e} 发起请求，对方能看到你的 IP 和来源页）</button>'
            "</span>"
        )

    def _emit(self, tag, attrs):
        if self.strict and tag == "img":
            placeholder = self._strict_img_placeholder(attrs)
            if placeholder is not None:
                self.out.append(placeholder)
                return
        allowed = self._attrs(tag, attrs)
        attrs_s = "".join(f' {k}="{self._esc_attr(v)}"' for k, v in allowed)
        self.out.append(f"<{tag}{attrs_s}>")

    def _task_checkbox(self, attrs):
        """任务列表的只读复选框：只认 type=checkbox 且 disabled 的 input。"""
        d = {(k or "").lower(): (v or "") for k, v in attrs}
        if d.get("type", "").lower() != "checkbox" or "disabled" not in d:
            return
        checked = " checked" if "checked" in d else ""
        self.out.append(f'<input type="checkbox" disabled{checked}>')

    def handle_starttag(self, tag, attrs):
        if tag in _BLOCK_DROP:
            self.drop_stack.append(True)
            return
        if self._dropping() or tag in _SKIP_TAGS:
            return
        if tag == "input":
            self._task_checkbox(attrs)
            return
        if tag not in _SAFE_TAGS:
            return                      # 未知标签：保留内容、去掉外壳
        self._emit(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        if tag in _BLOCK_DROP or self._dropping() or tag in _SKIP_TAGS:
            return
        if tag == "input":
            self._task_checkbox(attrs)
            return
        if tag not in _SAFE_TAGS:
            return
        self._emit(tag, attrs)

    def handle_endtag(self, tag):
        if tag in _BLOCK_DROP:
            if self.drop_stack:
                self.drop_stack.pop()
            return
        if tag in _SKIP_TAGS or self._dropping():
            return
        if tag in _SAFE_TAGS and tag not in _VOID_TAGS:
            self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if not self._dropping():
            self.out.append(self._esc_text(data))

    def handle_entityref(self, name):
        if not self._dropping():
            self.out.append(f"&{name};")

    def handle_charref(self, name):
        if not self._dropping():
            self.out.append(f"&#{name};")

    @staticmethod
    def _esc_attr(v):
        return v.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")

    @staticmethod
    def _esc_text(v):
        return v.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def sanitize(html_text, strict=False):
    p = _Sanitizer(strict=strict)
    try:
        p.feed(html_text)
        p.close()
    except Exception:
        return ""
    return "".join(p.out)


def _restore(html_text, store):
    for token, (kind, raw) in store.map.items():
        if kind == "code":
            repl = "<code>" + _esc_text(raw) + "</code>"
        elif kind == "m-inline":
            repl = '<span class="math math-inline">' + _esc_text(raw) + "</span>"
        elif kind == "m-block":
            repl = '<span class="math math-block">' + _esc_text(raw) + "</span>"
        elif kind == "cute":
            repl = ""          # 后面没有表格可包：指令本身不显示
        else:
            repl = raw
        html_text = html_text.replace(token, repl)
    return html_text


# ----------------------------------------------------------------------
# 对外接口
# ----------------------------------------------------------------------
_TLS = threading.local()


def _engine():
    """每线程一套 Markdown 实例 + 洛谷扩展（python-markdown 的实例带可变状态）。"""
    md = getattr(_TLS, "md", None)
    ext = getattr(_TLS, "ext", None)
    if md is None:
        ext = _LuoguExtension()
        md = _pymd.Markdown(
            extensions=["fenced_code", "tables", "sane_lists", "def_list",
                        "footnotes", "attr_list", ext],
            output_format="html",
        )
        _TLS.md = md
        _TLS.ext = ext
    return md, ext


def md_render(content, strict=False):
    """整篇 Markdown + LaTeX -> 安全 HTML（数学留 span 由前端 KaTeX 渲染）。

    strict=True 用于评论等访客可写内容：禁站外图片、强制 rel、收紧类名。
    """
    if not content:
        return ""
    text = content.replace("\r\n", "\n").replace("\r", "\n")

    hstore = _TokenStore()
    md_text = _split_containers(text, hstore, strict=strict)
    protected, store = protect(md_text)
    engine, ext = _engine()
    # 实例是复用的，必须手动 reset：否则上一个文档的脚注 / 引用定义会漏到下一篇
    engine.reset()
    ext.cute_map.clear()
    ext.cute_map.update(hstore.cute)      # 供 treeprocessor 包裹后面的表格
    html_text = engine.convert(protected)
    # 容器代理若被单独包进 <p>，把该 <p> 去掉（容器是块级元素）
    for token in hstore.map:
        if hstore.map[token][0] == "html":
            html_text = html_text.replace(f"<p>{token}</p>", token)
    safe = sanitize(html_text, strict=strict)
    out = _restore(safe, store)
    return _restore(out, hstore)


def plain_excerpt(content, limit=150):
    """从 Markdown 源提取纯文本摘要。"""
    if not content:
        return ""
    text = content.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"^[ \t]*:{2,4}[^\n]*\n?", "", text, flags=re.M)
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"~~~.*?~~~", " ", text, flags=re.S)
    text = re.sub(r"`{1,3}[^`\n]*`{1,3}", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"^\s*>\s?", "", text, flags=re.M)
    text = re.sub(r"^\s*([-*+]|\d+[.)])\s+(\[[ xX]\]\s*)?", "", text, flags=re.M)
    text = re.sub(r"\[\^[^\]]*\]", " ", text)
    text = re.sub(r"^\s*\[\^[^\]]*\]:.*$", "", text, flags=re.M)
    text = re.sub(r"\$\$", " ", text)
    text = re.sub(r"\$", " ", text)
    text = text.replace(r"\(", " ").replace(r"\)", " ")
    text = text.replace(r"\[", " ").replace(r"\]", " ")
    text = re.sub(r"^[-=]{2,}\s*$", "", text, flags=re.M)
    text = re.sub(r"[*_~=]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    return cut.rsplit(" ", 1)[0] if " " in cut else cut
