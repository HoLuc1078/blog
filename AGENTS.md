# AGENTS.md —— 樱羽小筑 · Petal Blog

给在这个仓库里干活的人（和 AI）看的说明：项目是什么、每个文件干什么、改代码要守哪些约定。
**每次动代码前先扫一眼「关键约定」和「改动检查清单」两节。**

---

## 1. 项目是什么

一个**个人博客**：Flask + SQLite 单体应用，无账号系统，毛玻璃 + 樱花粉主题。

- **后端**：Flask 3（`app.py` 一个文件装下所有路由），单文件 SQLite 数据库 `blog.db`。
- **前端**：原生 HTML/CSS/JS（**不用任何前端框架、没有构建步骤**），Jinja2 模板 + 少量 vanilla JS。
- **Markdown / LaTeX**：渲染语义对齐「洛谷 Markdown 格式手册」，实现在 `md_math.py`。
- **权限模型**：没有注册登录。站长在 `/admin` 自己设一个口令，解锁后写文章 / 编辑作者栏 / 管评论；
  游客只填「名字 + 图形验证码」就能评论。
- **入口**：`http://0.0.0.0:8848`（端口可用 `PORT` 改），调试模式**默认关**（`DEBUG=1` 才开）。

## 2. 快速开始

```bash
pip install -r requirements.txt    # Flask / Markdown / Pillow
python app.py                      # 监听 0.0.0.0:8848，debug 默认关（本地开发设 DEBUG=1 才有自动重载）
```

打开 <http://127.0.0.1:8848>，先访问 <http://127.0.0.1:8848/admin> 设置站长口令（≥6 位），
之后顶栏才会出现「写文章」「草稿箱」。

要开调试（本地开发用；线上**别开**，出错页会把堆栈直接给访客看）：

```bash
DEBUG=1 python app.py                        # Linux / macOS
${env:DEBUG="1"}; python app.py               # PowerShell
set DEBUG=1 && python app.py                 # cmd
```

### 环境变量一览

| 变量 | 默认 | 作用 |
| --- | --- | --- |
| `DEBUG` | **关** | 调试开关：自动重载 + 出错页显示堆栈。不设、或设成 `0` / `false` / `no` / `off`（大小写不敏感）都算关；**要开就设 `DEBUG=1`**。见 `app.py` 顶部的 `DEBUG` 常量 |
| `PORT` | `8848` | 监听端口 |
| `SECRET_KEY` | 无 | 会话签名密钥。不设则读仓库根目录的 `.secret_key`，文件不存在就自动生成一个 |
| `THEME_FROM_BG` | 关 | 设 `1` 时由 `theme.py` 从 `static/bg.jpg` 提取主体色，覆盖手写配色 |
| `TRUST_PROXY` | 关 | 设 `1` 才信任 `X-Forwarded-For` / `X-Forwarded-Proto`（**只有部署在自有反代之后才能开**，否则所有限流形同虚设） |
| `PROXY_HOPS` | `1` | 可信代理跳数，配合 `TRUST_PROXY` 使用 |

## 3. 目录结构与每个文件的职责

```
app.py               Flask 后端：全部路由 + 配置 + 图标 + 验证码 + 限流 + 安全头。
                     它是全站唯一的路由入口，改动前先读文末的模块结构注释。
md_math.py           Markdown + LaTeX 渲染管线：洛谷语法（折叠框 / 三线表 / 代码行号 /
                     题记 / cute-table / anti-ai 水印…）+ 本站扩展语法（~[]() 视频、
                     *[]() 文件卡片、:::charge 评论解锁）+ KaTeX 公式 + HTML 白名单净化。
                     渲染顺序、私有代理字符表、以及「新语法必须另占一段代理字符」的
                     原因都写在文件头 docstring 里 —— 动这块前**务必先读**。
theme.py             从 static/bg.jpg 逐像素 HSV 取主色相族，生成一整套 CSS 变量
                     （THEME_FROM_BG=1 时启用；app.py 按文件 mtime 缓存结果）。
migrate.py           一次性数据迁移脚本（幂等、可重复跑、跑完可删）：老图标名对齐
                     （icon-peach → icon-taozi、失效图标 → icon-sakura）+ 清理账号系统
                     时代的残留表/配置。跑前自动留 <库名>.bak-<时间戳>。用法见文件头。
requirements.txt     依赖清单：Flask==3.0.0 / Markdown==3.10 / Pillow>=10.0。
README.md            面向使用者的说明（运行方式、功能、图标、数据与升级、安全）。
AGENTS.md            本文件：面向维护者的结构说明与约定。
blog.db              本地 SQLite 数据库（**不进版本库**，启动时自动建表）。
.secret_key          自动生成的会话密钥（**不进版本库**）。
On_server/           服务器上那份数据库及其备份（**不进版本库**），供本地对照排查。

templates/           Jinja2 模板（服务端渲染；除 editor.html 外都 extends base.html）
  base.html          全站骨架：<head>、主题预设脚本、图标 sprite、花瓣 canvas、顶栏
                     （主题三档切换 + 草稿箱 / 写文章）、toast 容器、公共脚本引入。
  icons.html         内联 sprite：**只剩 5 个界面图标**（icon-sun / eye / moon / pen / close），
                     每个页面都 include，所以这些图标可以直接 <use href="#名字">。
                     文章标题用的那 27 个已经搬到 static/icons-local.svg（见下）。
  index.html         首页：过滤条（不安全 / 负能量 / 非学术 + 标签 chips）、文章卡片列表、
                     空状态、底部翻页 + 「每页 N 篇」数字输入框（**可手输，1–200，没有"全部"**）。
  article.html       文章页：标题 / 图标 / 元信息 / 正文（md 渲染）/ 评论区（多级回复、
                     验证码、站长删除按钮）/ 站长编辑入口。
  editor.html        发文 / 改文页（洛谷风格全屏编辑器，独立页面不继承 base）：
                     左右双栏 + 右侧文章设置（摘要、标签、置顶量、发布时间、过滤标记、
                     图标搜索、存草稿）。逻辑在 static/js/editor.js。
  drafts.html        草稿箱：仅站长可见，列出草稿并可继续编辑 / 发布 / 删除。
  admin.html         管理入口 /admin：设口令 / 输口令解锁 / 改口令 / 锁定。
  author_col.html    首页右侧作者栏（3:1 分栏的 1）：头像、昵称、简介、联系方式、友链、数据统计。
  author_edit_modal.html  站长专用的「编辑作者栏 / 站点」弹窗（base.html 里按 is_owner 引入）。
  error.html         404 / 400 / 403 / 413 / 500 的统一样式错误页。

static/
  css/style.css      全站样式：CSS 变量、三档主题（浅色 / 护眼 / 暗黑）、毛玻璃面板、
                     直角与虚线分隔、首页卡片、编辑器、评论区、弹窗、翻页等。
  js/petals.js       花瓣粒子 canvas（1300 片自下而上飘动，鼠标附近被吸附绕转；
                     尊重 prefers-reduced-motion）。
  js/app.js          全站公共脚本：toast、带 CSRF 头的 fetch 封装、KaTeX 客户端渲染、
                     代码块复制、删除确认、作者栏编辑弹窗、验证码刷新、评论回复框。
  js/index.js        首页列表：过滤 / 标签筛选 / 翻页 / 每页篇数（**全部在前端做，零请求**）；
                     选择存 localStorage；多选标签时按命中标签数降序、再按置顶量降序重排。
  js/editor.js       编辑器逻辑：编辑-预览切换、快捷插入 Markdown 与 LaTeX、摘要、标签编辑、
                     图标搜索与随机、置顶量、发布时间、过滤标记、本地草稿、提交前校验。
  icons.svg          iconfont sprite：380 个 ic-* 图标（约 800KB）。编辑器图标选择器直接
                     <use href="/static/icons.svg#ic-x">；文章页只内联用到的那几个 <symbol>。
  icons-local.svg   站内那 27 个图标（24 水果 + 樱花 / 彩虹 / 四叶草，约 33KB）。
                     19 个取自 Twemoji（CC-BY 4.0，README 里有署名，别删）；
                     火龙果/荔枝/榴莲/龙眼/山竹/石榴/西梅/柿子 8 个没有对应 emoji，同画风自绘。
                     viewBox 统一 0 0 36 36，只含 <symbol>，不放 <script> / 事件属性。
  bg.jpg             背景图（同时是 THEME_FROM_BG 取色来源）。
  avatar.png         博主头像：**固定就这一个文件**，上传即覆盖，不存路径。
  favicon.svg        站点图标 + 顶栏 logo（favicon-dark.svg 是暗色主题的蓝色版）。
  sakura.svg         空状态插画（首页无文章 / 筛选无结果；sakura-dark.svg 暗色蓝色版）。
  note.svg           草稿箱空状态插画（note-dark.svg 暗色蓝色版）。
                     三张 -dark 版由 CSS 的 .theme-light-only / .theme-dark-only 按 data-theme 切换。

uploads/             站长上传的附件（YYYY/MM/<16 位随机名>.<ext>，**不进版本库**）。
                     **刻意放在 static/ 之外**：静态目录会被 Flask 按扩展名猜 MIME 直接内联，
                     放外面才能统一走 /u/<路径> 这个受控出口（普通附件强制下载）。
```

## 4. 数据模型（`app.py` 里的 `SCHEMA`，启动时幂等建表）

- **articles**：`id` / `title` / `summary` / `content_md` / `tags`（CSV，最多 12 个、每个 ≤20 字）/
  `pin`（置顶量 -999–999，可为负数，越小越靠后）/ `status`（`published` | `draft`）/ `flags`（CSV：unsafe, negative, nonacademic）/
  `icon`（图标名，空 = 用默认 `icon-sakura`）/ `views` / `created_at` / `updated_at`。
- **comments**：`id` / `article_id` / `parent_id`（0 = 顶层）/ `author_name` / `ip` / `content` / `created_at`。
  展示时由 `_thread_comments()` 拍平成「顶层 + 其下所有回复」两级。
- **无新表**：`:::charge` 的解锁状态不落库，走签名 cookie `petal_unlock`（见第 5 节第 13 条）。
- **site_cfg**：键值表。站点标题 / 副标题 / 页脚 / 昵称 / 简介 / 联系方式 JSON（`author_contacts`）/ 友链 JSON（`author_links`）/
  `contacts_split`（旧 author_links 拆到联系方式的一次性标记）/ `owner_pass_hash`（站长口令哈希）。
  忘记口令：删掉 `owner_pass_hash` 这一行即可重设。

## 5. 关键约定（改代码前先看）

1. **时间统一存 UTC**，格式 `YYYY-MM-DD HH:MM:SS`；展示时用 `fmt_dt()` 转东八区，
   反向用 `parse_created()` / 模板全局 `input_dt()`。别在别处自己拼时间字符串。
2. **首页筛选 / 标签 / 翻页 / 每页篇数全在前端**（`static/js/index.js`）：服务端 `index()`
   一次把全部已发布文章给模板，之后不发任何请求。要加筛选维度就得同时改
   `index.html`（卡片上的 `data-*` 属性）和 `index.js`（`matches()` 等）。
   多选标签时：命中标签数多的文章排前面，命中数相同再比置顶量；卡片上的置顶量
   （`data-pin`，可为 0 / 负数）每篇都显示。
   「每页 N 篇」是数字输入框，范围 1–200，**没有"全部"这一档**；越界由 `clampPer()` 夹紧。
3. **草稿对游客彻底隐身**：`status='draft'` 的文章游客打开链接直接 404，且不进任何列表 / 统计。
4. **图标分三处，取值统一走函数，别手写 `<use href>`**：
   - `static/icons-local.svg`：站内 27 个（`LOCAL_ICONS`，选择器里排最前）→ `/static/icons-local.svg#名字`
   - `static/icons.svg`：380 个 iconfont `ic-*` → `/static/icons.svg#名字`
   - `templates/icons.html`：只剩 5 个界面图标，随页面内联 → `#名字`
   一律用 `post_icon()` 取名字、`post_icon_ref()` 取引用地址、`post_icon_sprites()` 内联本页用到的
   （前两处**不**随每个页面下发；27 个水果要是又内联回去，每个页面白白多背 33KB）。
5. **正文与评论渲染分开**：正文 `{{ text | md | safe }}`，评论用 `| md_comment`（严格净化：
   禁站外图片、强制 `rel`、收紧 class）。渲染结果都经过 `md_math.sanitize()` 白名单，别绕过。
6. **权限只有一个开关**：`session["owner"]`（`owner_unlocked()`）。写操作 / 接口入口一律
   先调 `_required_owner()`：页面未解锁跳 `/admin`，接口返回 403 JSON。
7. **所有 POST 都要 CSRF 令牌**：`_csrf_protect` 是全局 before_request，表单放隐藏域
   `_csrf`，fetch 放 `X-CSRF-Token` 头（`csrf_token()` 在模板里可取）。新加表单别忘了。
8. **验证码答案只存服务端**：会话里只放不透明 token（`captcha_issue()`），答案在 `_CAPTCHA` 字典里，
   一次性、5 分钟过期。**别把答案写进 session** —— Flask 的会话是签名不加密的 Cookie。
9. **限流**：`rate_ok()` 进程内滑动窗口。评论同浏览器 15 秒冷却、同 IP 10 分钟 20 次
   **提交尝试**（`rate_ok("cmt", …)` 必须排在 `captcha_ok()` **前面**：验证码是「答对才通过」，
   把限流放它后面，答错的请求一条都不计数，等于没限流）；`/captcha.png` 同 IP 10 分钟 60 张
   （未认证 + PIL 逐像素画图，超了返回 429，且不覆盖会话里已领到的那张）；
   解锁口令同 IP 10 分钟 8 次。真实 IP 由 `ip_of()` 决定，默认**不信任** `X-Forwarded-For`。
10. **CSP 收紧**（`app.py` 的 `CSP` 常量）：外链只放行 `cdn.jsdelivr.net`，`connect-src 'self'`。
    `script-src` **没有 `'unsafe-inline'`**：页首那段「先写主题再加载 CSS」的内联脚本靠
    **每请求一个 nonce** 放行（`_csp_nonce()`；模板里写 `nonce="{{ csp_nonce() }}"`）——
    **新加内联 `<script>` 忘了写 nonce 会被浏览器静默拦掉**。站外资源一律带 `integrity`
    （SRI）+ `crossorigin="anonymous"`，见 `base.html` / `editor.html` 的 KaTeX。
    `style-src` 仍保留 `'unsafe-inline'`（模板里大量 `style="…"` 属性 + `theme_css()` 的
    `<style>` 块，nonce 管不到属性）。新增外部资源必须同步改 CSP，否则会被浏览器拦掉。
11. **没有构建步骤**：改 JS/CSS 就是改文件，浏览器强刷即生效（静态文件走 Flask 默认缓存策略）。
    Python 侧默认**不会**自动重载（`DEBUG` 默认关），本机开发要么设 `DEBUG=1`，要么改完手动重启。
12. **入库的边界**：`blog.db`、`.secret_key`、`On_server/`、`uploads/`、`*.bak-*`、`__pycache__/` 都被
    `.gitignore` 忽略，**不要 add -f**。数据库结构变更要同时更新 `SCHEMA`（幂等）和 `migrate.py`。
13. **`:::charge` 的解锁凭证必须签名**（`_charge_sig()` / `_grant_charge()` / `charge_unlocked()`）：
    在本页评论成功后往 cookie `petal_unlock` 里塞一条 `文章id:评论id:HMAC(secret_key)`，
    最多 20 条、一年有效。cookie 是明文存在客户端的，**不签名就等于谁都能自己编一条「我评论过」**；
    渲染时还会回库确认那条评论确实还在（删掉评论 = 解锁失效）。站长永远算解锁。
14. **上传只走 `/u/<路径>` 这一个出口，目录在 `uploads/`（不在 `static/` 里）**：静态目录会被 Flask
    按扩展名猜 MIME 直接内联，一个 `.txt` 也可能被当页面渲染。现在只有图片 / 音频 / 视频内联，
    其余统一 `Content-Disposition: attachment`。`UPLOAD_KINDS` 是**扩展名白名单**
    （`.html` / `.svg` / `.js` / `.xml` 一律不收），会内联的几类还要过 `_magic_type()` 文件头校验。
    要加新类型就改 `UPLOAD_KINDS`，别放开白名单。
15. **`md_math._TokenStore` 的每个「类」都要占一段独立的私有代理字符**：`\uE000/\uE001` 数学、
    `\uE002/\uE003` 行内代码、`\uE004/\uE005` 容器、`\uE006/\uE007` cute-table、
    `\uE008/\uE009` 视频 / 文件卡片。**加新语法时一定要挑一段没人用的**——`md_render` 里
    `_split_containers`（容器）和 `protect`（行内）是**两个各自从 0 开始计数的 `_TokenStore`**，
    共用同一段字符时第 0 个容器会和第一个行内块生成完全相同的 token，回填时后者被顶掉
    （实测过一次：带视频的文章里 `:::charge` 整块消失）。

## 6. 常见改动落在哪里

| 想做的事 | 改哪里 |
| --- | --- |
| 加 / 改接口、路由、权限、限流 | `app.py`（路由集中在「页面」「文章发布 / 编辑 / 删除」「评论」「管理入口」等分区） |
| 改 Markdown / LaTeX 语法或净化白名单 | `md_math.py`（并同步 README 的语法清单） |
| 改首页卡片、过滤条、翻页区 | `templates/index.html` + `static/js/index.js` + `static/css/style.css` |
| 改编辑器界面与交互 | `templates/editor.html` + `static/js/editor.js` |
| 改配色 / 主题档位 | `static/css/style.css` 的 CSS 变量；想让主色跟着背景图走则开 `THEME_FROM_BG=1` |
| 加图标 | 站内那 27 个加进 `static/icons-local.svg` + `app.py` 的 `LOCAL_ICONS`；iconfont 的丢进 `static/icons.svg`；纯界面图标放 `templates/icons.html`（三处都自动识别，按 mtime 缓存） |
| 改站点文案 / 昵称 / 链接的默认值 | `app.py` 的 `load_cfg()` 与 `templates/author_col.html` |
| 加 / 改扩展语法（视频、文件卡片、`:::charge` 之类） | `md_math.py`：行内指令加在 `_substitute_media` 那一套里，容器加在 `_render_container`；**新占一段私有代理字符**（第 5 节第 15 条），并同步 README 的语法清单 |
| 改图片缩放 / 灯箱 | `static/css/style.css` 的 `.md-body img` 与 `.img-zoom*` + `static/js/app.js` 的 `bindImageZoom()` |
| 改上传的类型 / 大小限制 | `app.py` 的 `UPLOAD_KINDS` / `MAX_UPLOAD*` / `_magic_type()`；前端在 `static/js/editor.js` |
| 改 `:::charge` 的解锁规则 | `app.py` 的 `charge_unlocked()` / `_grant_charge()` + `md_math.md_render(ctx=…)` 的 `ctx` |

## 7. 改动检查清单

项目**没有自动化测试**，改完请自己起服务手测：

- [ ] `python app.py` 起得来，控制台端口与 `debug=on/off` 打印符合预期。
- [ ] `DEBUG=1 python app.py` 才开调试（出错页显示堆栈）；默认启动不带调试。
- [ ] 首页：文章列表、过滤三连（**「不显示不安全」默认勾选**）、标签 chips、翻页、**每页篇数手输**（输 1 / 6 / 200 / 999 / 清空 / 非数字）都正常。
- [ ] 未解锁时访问 `/write`、`/drafts`，游客访问草稿链接 → 行为分别是跳 `/admin`、404。
- [ ] 发文 / 改文 / 存草稿 / 发布草稿 / 删除；评论 + 回复 + 删除 + 验证码。
- [ ] 扩展语法：`~[标题](B站/YouTube/mp4 直链)` 三种都出得来，`*[文件名](地址)` 点得动。
- [ ] `:::charge`：游客页面里**搜不到里面的正文**（查看源码也没有）；评论成功后同浏览器立刻可见；把那条评论删掉又变回锁着。
- [ ] 上传：图片 / 视频 / 文档各传一个；**在编辑区直接粘贴截图**会自动上传并插入 Markdown；`.html` / `.svg` / 改名的假图片都被拒。
- [ ] 正文图片不透明、按屏幕缩放，点一下能进灯箱（滚轮 / 拖动 / Esc）。
- [ ] 手机宽度下布局不炸（顶栏、3:1 分栏、编辑器、文件卡片、视频）。
- [ ] 改动后确认 `git status` 里没有 `blog.db` / `.secret_key` / `__pycache__` / `uploads/` / `*.bak-*`。

## 8. 收尾

所有目标做完并经过用户验证玩后，推送到Github
