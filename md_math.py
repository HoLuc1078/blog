# -*- coding: utf-8 -*-
"""
Markdown + LaTeX 渲染管线
=========================
设计（对应需求：支持 Markdown、LaTeX，以及 Markdown 内嵌 LaTeX：$..$、$$..$$、\\(..\\)、\\[..\\]）：

1. protect()    渲染前先把“公式区域”和“行内代码”摘出来换成私有区代理字符。
   - 代码围栏 (``` / ~~~) 与行内代码 `..` 内部的 $ 一律不当作数学，原样保留；
   - 因此公式可以安全地“嵌套”在粗体 / 斜体 / 列表 / 标题 / 引用等 Markdown 结构里，
     不会受 Markdown 语法干扰，反过来 Markdown 语法也不会被公式内容破坏。
2. markdown     (python-markdown) 只渲染普通 Markdown。
3. sanitize()   白名单式净化，去除一切危险标签/属性（XSS 防护）。
4. 回填公式区域为 <span class="math math-inline"> / <span class="math math-block">，
   再由前端 KaTeX 渲染（katex.render，读取 textContent 即原始 LaTeX）。
5. 洛谷风格容器（:::info … ::: / :::warning[自定义标题] 等）：先在渲染前整体摘出、
   递归渲染内部（内部仍是完整 Markdown，可含公式/代码/嵌套容器），
   在净化之后回填为 <div class="md-block …">，支持任意类型名与嵌套。

私有代理：
  \uE000{i}\uE001  行内 / 行间公式
  \uE002{i}\uE003  行内代码
  \uE004{i}\uE005  预渲染容器 HTML（净化后回填）
"""

from html.parser import HTMLParser

import re

import markdown as _pymd

M_INLINE_BEGIN = "\uE000"
M_END = "\uE001"
C_BEGIN = "\uE002"
C_END = "\uE003"
H_BEGIN = "\uE004"
H_END = "\uE005"

_FENCE_OPEN = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})[ \t]*(.*)$")
_FENCE_CLOSE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})[ \t]*$")
_INLINE_CODE = re.compile(r"(?<!`)(`{1,3})(?!`)([^\n]*?)(?<!`)\1(?!`)")

_CONTAINER_OPEN = re.compile(
    r"^[ \t]{0,3}:::[ \t]*([A-Za-z][\w\-]*)"
    r"(?:[ \t]*(\[[^\]]*\]))?"
    r"(?:[ \t]+([^\n]*?))?[ \t]*$")
_CONTAINER_CLOSE = re.compile(r"^[ \t]{0,3}:::[ \t]*$")
_FENCE_LINE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")

def _backslash_run(text, pos):
    """统计 text[pos] 之前连续反斜杠个数：奇数则该字符被转义。"""
    n = 0
    k = pos - 1
    while k >= 0 and text[k] == "\\":
        n += 1
        k -= 1
    return n

_SAFE_TAGS = {
    "p", "br", "strong", "b", "em", "i", "del", "s", "u", "code", "pre",
    "blockquote", "ul", "ol", "li", "hr", "h1", "h2", "h3", "h4", "h5", "h6",
    "a", "img", "table", "thead", "tbody", "tfoot", "tr", "th", "td",
    "sup", "sub", "span", "div", "kbd", "mark", "details", "summary",
}

_URL_PROTO = re.compile(r"^(https?:|mailto:|#|/|\.\.?/)", re.I)

# 严格模式（评论等访客可写内容）用到的额外规则
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")
_STRICT_CLASS_TAGS = {"code", "pre"}
_FORCED_REL = "nofollow noopener noreferrer"


def _local_src_ok(v):
    """严格模式的 img src：只放行站内相对路径。

    放行 //host/x.png 或 https://host/x.png 会让任何访客在评论里埋一张
    图片，从而拿到每个读者的 IP / Referer（追踪信标）。
    """
    if not v or len(v) > 2000:
        return False
    if v.startswith("//") or _SCHEME_RE.match(v):
        return False
    return v.startswith(("/", "./", "../"))


_VOID_TAGS = {"br", "hr", "img", "input", "wbr", "source"}
# 需要整体吞掉直到闭合标签的元素（内容不保留）
_BLOCK_DROP = {"script", "style", "noscript", "template", "iframe", "object", "embed"}
# 只去掉标签本身、其内部纯文本可保留的元素
_SKIP_TAGS = {"form", "input", "select", "textarea", "button", "svg", "math", "video",
              "audio", "canvas", "link", "meta", "base"}


def _find_close(text, start, close, allow_newlines):
    """从 start 处找 close 串，可跨行时以空行（段落边界）为上限；返回下标或 -1。"""
    idx = start
    while True:
        pos = text.find(close, idx)
        if pos < 0:
            return -1
        if not allow_newlines:
            # 不允许跨行：中间出现换行即放弃
            nl = text.find("\n", start, pos)
            if nl >= 0:
                return -1
            return pos
        # 允许跨行：检查 close 前是否越过空行（\n\n 或 \n \n）
        seg = text[start:pos]
        if "\n\n" in seg or re.search(r"\n[ \t]+\n", seg):
            return -1
        if _backslash_run(text, pos) % 2 == 1:
            idx = pos + len(close)  # 转义过的结束符，继续向后找
            continue
        return pos


class _TokenStore:
    def __init__(self):
        self.seq = [0]
        self.map = {}  # token -> (kind, raw)

    def new(self, kind, raw):
        i = self.seq[0]
        self.seq[0] += 1
        if kind.startswith("m-"):
            token = f"{M_INLINE_BEGIN}{i}{M_END}"
        elif kind == "code":
            token = f"{C_BEGIN}{i}{C_END}"
        else:
            token = f"{H_BEGIN}{i}{H_END}"
        self.map[token] = (kind, raw)
        return token


def _container_html(name, label, inner_html):
    """把递归渲染好的容器内容包成 md-block（洛谷风格：标题 + 可折叠主体）。"""
    safe_name = re.sub(r"[^A-Za-z0-9_-]", "", name) or "box"
    title = (label or name.upper()).replace("&", "&amp;").replace("<", "&lt;")
    return (
        f'<div class="md-block md-block-{safe_name}">'
        f'<div class="md-block-head"><span class="md-block-tag">{title}</span>'
        '<span class="md-block-caret">▾</span></div>'
        f'<div class="md-block-body">{inner_html}</div>'
        "</div>"
    )


def _split_containers(content, store, strict=False):
    """把 :::type … ::: 容器摘成 HTML 代理，返回剩余可交给 protect 的文本。"""
    lines = content.split("\n")
    res = []
    text_buf = []
    i = 0
    n = len(lines)
    in_fence = False
    fence_char = ""
    fence_len = 0

    def flush():
        if text_buf:
            res.extend(text_buf)
            text_buf.clear()

    def block_range(start):
        """start 指向 ':::name' 行：返回 (结束行下标, 内部行列表)。"""
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
                if _CONTAINER_OPEN.match(line):
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
                    # 围栏结束检测：同为该符号且长度足够
                    seg = line.lstrip(" \t")
                    if seg[0] == fc and seg.rstrip(" \t").count(fc) >= fl:
                        f_in = False
                j += 1
        return n, inner  # 未闭合：容错到结尾

    while i < n:
        line = lines[i]
        if not in_fence:
            mf = _FENCE_LINE.match(line)
            if mf:
                in_fence = True
                fence_char = mf.group(1)[0]
                fence_len = len(mf.group(1))
                text_buf.append(line)
                i += 1
                continue
            mo = _CONTAINER_OPEN.match(line)
            if mo:
                flush()
                end, inner = block_range(i)
                name = mo.group(1)
                label = None
                if mo.group(2):  # :::name[标题]
                    label = mo.group(2)[1:-1].strip()
                elif mo.group(3):
                    label = mo.group(3).strip()
                inner_html = md_render("\n".join(inner), strict=strict)
                token = store.new("html", _container_html(name, label, inner_html))
                # 前后补空行，避免容器与相邻文本合并进同一 <p>
                res.append("")
                res.append(token)
                res.append("")
                i = end + 1
                continue
            text_buf.append(line)
            i += 1
        else:
            text_buf.append(line)
            if _FENCE_LINE.match(line):
                seg = line.lstrip(" \t")
                if seg[0] == fence_char and seg.rstrip(" \t").count(fence_char) >= fence_len:
                    in_fence = False
            i += 1
    flush()
    return "\n".join(res)


_FENCE_INFO = re.compile(r"^([ \t]{0,3})(`{3,}|~{3,})[ \t]*(.*?)[ \t]*$")
_ATTR_OK = re.compile(r"^[A-Za-z_][\w\-]*$")


def _normalize_fence(line):
    """把 ```cpp line-numbers（洛谷风格：语言 + 参数）改写成 python-markdown 认的 ```{.cpp .line-numbers}。

    python-markdown 的 fenced_code 只接受「单一语言」或「{...} 属性」两种写法，
    信息串里多一个空格分词（line-numbers / title=xx / showLineNumbers）就会整段围栏失效，
    代码会被当成普通段落渲染（#include 变成一级标题）。
    """
    m = _FENCE_INFO.match(line)
    if not m:
        return line
    indent, fence, info = m.groups()
    if not info or info.startswith("{"):
        return line
    toks = info.split()
    if len(toks) == 1 and ":" not in toks[0]:
        return line
    head, *rest = toks
    if ":" in head:                       # ```cpp:line-numbers
        head, extra = head.split(":", 1)
        rest = ([extra] if extra else []) + rest
    classes = [head] if re.fullmatch(r"[\w#.+-]*", head) and head else []
    for t in rest:
        t = t.lstrip(".")
        if _ATTR_OK.match(t):
            classes.append(t)
    if not classes:
        return line
    return f"{indent}{fence}{{{' '.join('.' + c for c in classes)}}}"


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
            # 行间公式 $$
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
            allow = text[i + 1] == "["  # \[..\] 允许跨行；\(..\) 限单行
            j = _find_close(text, i + 2, close, allow_newlines=allow)
            if j >= 0:
                out.append(store.new(kind, text[i + 2:j]))
                i = j + 2
                continue
            out.append(ch)
            i += 1
            continue
        if ch == "\\" and i + 1 < n and text[i + 1] == "$":
            # 转义美元符 \$
            out.append("$")
            i += 2
            continue
        if ch == "$":
            # 行内公式 $...$：仅同行闭合。
            # 宽松启发：紧跟空白/数字时视为“价格/普通文本”不摘除（如“$5 和 $6”），
            # 其余情况（如 $x^2$、$\vec{a}$、中文后的 $a$）正常摘除。
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
                # 行内公式里出现了换行：不摘（原样显示）
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


def protect(content):
    """输入整篇 Markdown，返回 (受保护文本, token 表)。"""
    store = _TokenStore()
    pieces = []  # (kind, text)：kind raw=围栏原文 / proc=需替换段
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
    if in_fence:  # 未闭合围栏：按原文对待，Markdown 会原样显示
        pass

    final_parts = []
    for kind, text in pieces:
        if kind == "raw":
            final_parts.append(text)
            continue
        # 1) 行内代码先摘除（其内部 $ 不算数学）
        code_parts = []
        pos = 0
        for m in _INLINE_CODE.finditer(text):
            code_parts.append(text[pos:m.start()])
            code_parts.append(store.new("code", m.group(2)))
            pos = m.end()
        code_parts.append(text[pos:])
        segment = "".join(code_parts)
        # 2) 数学摘除
        segment = _substitute_math(segment, store)
        final_parts.append(segment)
    return "\n".join(final_parts), store


class _Sanitizer(HTMLParser):
    """白名单净化：丢弃危险标签，仅保留安全标签与受控属性。

    strict=True 用于**访客可写**的内容（评论）：站外图片改为「点击后加载」
    （默认不发请求，防追踪信标）、禁止复用站内 UI 类名（防界面伪装）、
    并由服务端强制 rel。
    """

    def __init__(self, strict=False):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.drop_stack = []  # 是否处于被丢弃标签内
        self.strict = strict

    def _dropping(self):
        return any(self.drop_stack)

    def _attrs(self, tag, attrs):
        """按白名单筛选属性，返回 [(小写属性名, 值)]。"""
        allowed = []
        for k, v in attrs:
            kl = k.lower()
            if kl == "class" and v:
                if self.strict and tag not in _STRICT_CLASS_TAGS:
                    # 严格模式只允许 <code>/<pre> 带 class（代码语言），
                    # 否则评论者可用 .btn / .btn-primary 之类伪造站内按钮
                    continue
                cls = re.sub(r"[^0-9A-Za-z_\- ]+", "", v)[:200]
                if cls.strip():
                    allowed.append((kl, cls))
            elif kl == "href" and tag == "a":
                if _URL_PROTO.match(v or "") and len(v) <= 2000:
                    allowed.append((kl, v))
            elif kl == "src" and tag == "img":
                if self.strict:
                    ok = _local_src_ok(v)
                else:
                    ok = bool(_URL_PROTO.match(v or "")) and len(v or "") <= 2000
                if ok:
                    allowed.append((kl, v))
            elif kl in ("alt", "title", "target", "rel") and tag in ("a", "img") and v:
                if kl == "rel" and self.strict:
                    continue                       # 严格模式：rel 由下面统一补
                if kl == "target" and self.strict and v != "_blank":
                    continue
                if len(v) <= 500:
                    allowed.append((kl, v))
            elif kl in ("align", "rowspan", "colspan") and tag in ("th", "td", "table"):
                if re.fullmatch(r"[a-zA-Z0-9]{1,8}", v or ""):
                    allowed.append((kl, v))
        if self.strict and tag == "a":
            # 显式 rel="opener" 会推翻浏览器对 target=_blank 的隐式 noopener
            # 保护（反向标签劫持），所以作者写的 rel 一律丢弃，统一强制。
            allowed.append(("rel", _FORCED_REL))
        return allowed

    def _strict_img_placeholder(self, attrs):
        """严格模式下的站外图片：返回「点击后加载」占位 HTML。

        返回 None 表示照常处理（站内图片直接显示；非法 src 照旧丢弃）。
        这样评论里仍然可以贴图，但默认不会向第三方发起任何请求，
        读者必须看到提示并主动点击才会加载。
        """
        src = alt = ""
        for k, v in attrs:
            kl = k.lower()
            if kl == "src" and v:
                src = v
            elif kl == "alt" and v:
                alt = v[:200]
        if not src or len(src) > 2000 or src.startswith("#"):
            return None
        if _local_src_ok(src):
            return None                      # 站内图片：无第三方风险，直接显示
        if not _URL_PROTO.match(src):
            return None                      # 协议不在白名单：交给默认逻辑丢掉
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

    def handle_starttag(self, tag, attrs):
        if tag in _BLOCK_DROP:
            self.drop_stack.append(True)
            return
        if tag in _SKIP_TAGS or self._dropping():
            return
        if tag not in _SAFE_TAGS:
            # 未知标签：保留内容、去掉外壳
            return
        self._emit(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        if tag in _BLOCK_DROP or tag in _SKIP_TAGS or self._dropping():
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
        if self._dropping():
            return
        self.out.append(self._esc_text(data))

    def handle_entityref(self, name):
        # convert_charrefs=True 时通常不会走到这里
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
            repl = "<code>" + raw.replace("&", "&amp;").replace("<", "&lt;") \
                .replace(">", "&gt;") + "</code>"
        elif kind == "m-inline":
            repl = '<span class="math math-inline">' + raw.replace("&", "&amp;") \
                .replace("<", "&lt;").replace(">", "&gt;") + "</span>"
        elif kind == "m-block":
            repl = '<span class="math math-block">' + raw.replace("&", "&amp;") \
                .replace("<", "&lt;").replace(">", "&gt;") + "</span>"
        else:
            repl = raw
        html_text = html_text.replace(token, repl)
    return html_text


_MD = None


def md_render(content, strict=False):
    """整篇 Markdown + LaTeX -> 安全 HTML（数学留 span 由前端 KaTeX 渲染）。

    strict=True 用于评论等访客可写内容：禁站外图片、强制 rel、收紧 class。
    """
    global _MD
    if _MD is None:
        _MD = _pymd.Markdown(
            extensions=["fenced_code", "tables", "sane_lists", "def_list"],
            output_format="html",
        )
    if not content:
        return ""
    text = content.replace("\r\n", "\n").replace("\r", "\n")
    hstore = _TokenStore()
    md_text = _split_containers(text, hstore, strict=strict)
    protected, store = protect(md_text)
    html_text = _MD.convert(protected)
    # 容器代理若被单独包进 <p>，把该 <p> 去掉（容器是块级元素）
    for token in hstore.map:
        html_text = html_text.replace(f"<p>{token}</p>", token)
    safe = sanitize(html_text, strict=strict)
    out = _restore(safe, store)
    return _restore(out, hstore)


def plain_excerpt(content, limit=150):
    """从 Markdown 源提取纯文本摘要。"""
    if not content:
        return ""
    text = content.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"^[ \t]*:::[^\n]*\n?", "", text, flags=re.M)
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"~~~.*?~~~", " ", text, flags=re.S)
    text = re.sub(r"`{1,3}[^`\n]*`{1,3}", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"^\s*>\s?", "", text, flags=re.M)
    text = re.sub(r"^\s*([-*+]|\d+[.)])\s+", "", text, flags=re.M)
    text = re.sub(r"\$\$", " ", text)
    text = re.sub(r"\$", " ", text)
    text = text.replace(r"\(", " ").replace(r"\)", " ")
    text = text.replace(r"\[", " ").replace(r"\]", " ")
    text = re.sub(r"^[-=]{2,}\s*$", "", text, flags=re.M)
    text = re.sub(r"[*_~]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    return cut.rsplit(" ", 1)[0] if " " in cut else cut
