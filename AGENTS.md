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
- **入口**：`http://0.0.0.0:8848`（端口可用 `PORT` 改），调试模式**默认开**。

## 2. 快速开始

```bash
pip install -r requirements.txt    # Flask / Markdown / Pillow
python app.py                      # 监听 0.0.0.0:8848，debug 默认开（改代码自动重载）
```

打开 <http://127.0.0.1:8848>，先访问 <http://127.0.0.1:8848/admin> 设置站长口令（≥6 位），
之后顶栏才会出现「写文章」「草稿箱」。

关掉调试（线上部署务必关）：

```bash
DEBUG=0 python app.py                        # Linux / macOS
${env:DEBUG="0"}; python app.py               # PowerShell
set DEBUG=0 && python app.py                 # cmd
```

### 环境变量一览

| 变量 | 默认 | 作用 |
| --- | --- | --- |
| `DEBUG` | **开** | 调试开关：自动重载 + 出错页显示堆栈。认 `0` / `false` / `no` / `off`（大小写不敏感）为「关」；不设或设成别的值都算开。见 `app.py` 顶部的 `DEBUG` 常量 |
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
                     题记 / cute-table / anti-ai 水印…）+ KaTeX 公式 + HTML 白名单净化。
                     渲染顺序与私有代理字符约定写在文件头 docstring 里。
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
  icons.html         内联 sprite：27 个本地自绘图标（24 水果 + 樱花/彩虹/四叶草），
                     每个页面都 include，所以这些图标可以直接 <use href="#名字">。
  index.html         首页：过滤条（不安全 / 负能量 / 非学术 + 标签 chips）、文章卡片列表、
                     空状态、底部翻页 + 「每页 N 篇」数字输入框（**可手输，1–200，没有"全部"**）。
  article.html       文章页：标题 / 图标 / 元信息 / 正文（md 渲染）/ 评论区（多级回复、
                     验证码、站长删除按钮）/ 站长编辑入口。
  editor.html        发文 / 改文页（洛谷风格全屏编辑器，独立页面不继承 base）：
                     左右双栏 + 右侧文章设置（摘要、标签、置顶量、发布时间、过滤标记、
                     图标搜索、存草稿）。逻辑在 static/js/editor.js。
  drafts.html        草稿箱：仅站长可见，列出草稿并可继续编辑 / 发布 / 删除。
  admin.html         管理入口 /admin：设口令 / 输口令解锁 / 改口令 / 锁定。
  author_col.html    首页右侧作者栏（3:1 分栏的 1）：头像、昵称、简介、链接、数据统计。
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
                     选择存 localStorage。
  js/editor.js       编辑器逻辑：编辑-预览切换、快捷插入 Markdown 与 LaTeX、摘要、标签编辑、
                     图标搜索与随机、置顶量、发布时间、过滤标记、本地草稿、提交前校验。
  icons.svg          iconfont sprite：380 个 ic-* 图标（约 800KB）。编辑器图标选择器直接
                     <use href="/static/icons.svg#ic-x">；文章页只内联用到的那几个 <symbol>。
  bg.jpg             背景图（同时是 THEME_FROM_BG 取色来源）。
  avatar.png         博主头像：**固定就这一个文件**，上传即覆盖，不存路径。
  favicon.svg        站点图标 + 顶栏 logo。
  sakura.svg         空状态插画（首页无文章 / 筛选无结果）。
  note.svg           草稿箱空状态插画。
```

## 4. 数据模型（`app.py` 里的 `SCHEMA`，启动时幂等建表）

- **articles**：`id` / `title` / `summary` / `content_md` / `tags`（CSV，最多 12 个、每个 ≤20 字）/
  `pin`（置顶量 0–999）/ `status`（`published` | `draft`）/ `flags`（CSV：unsafe, negative, nonacademic）/
  `icon`（图标名，空 = 用默认 `icon-sakura`）/ `views` / `created_at` / `updated_at`。
- **comments**：`id` / `article_id` / `parent_id`（0 = 顶层）/ `author_name` / `ip` / `content` / `created_at`。
  展示时由 `_thread_comments()` 拍平成「顶层 + 其下所有回复」两级。
- **site_cfg**：键值表。站点标题 / 副标题 / 页脚 / 昵称 / 简介 / 链接 JSON / `owner_pass_hash`（站长口令哈希）。
  忘记口令：删掉 `owner_pass_hash` 这一行即可重设。

## 5. 关键约定（改代码前先看）

1. **时间统一存 UTC**，格式 `YYYY-MM-DD HH:MM:SS`；展示时用 `fmt_dt()` 转东八区，
   反向用 `parse_created()` / 模板全局 `input_dt()`。别在别处自己拼时间字符串。
2. **首页筛选 / 标签 / 翻页 / 每页篇数全在前端**（`static/js/index.js`）：服务端 `index()`
   一次把全部已发布文章给模板，之后不发任何请求。要加筛选维度就得同时改
   `index.html`（卡片上的 `data-*` 属性）和 `index.js`（`matches()` 等）。
   「每页 N 篇」是数字输入框，范围 1–200，**没有"全部"这一档**；越界由 `clampPer()` 夹紧。
3. **草稿对游客彻底隐身**：`status='draft'` 的文章游客打开链接直接 404，且不进任何列表 / 统计。
4. **图标分两套**：本地自绘的 27 个（`LOCAL_ICONS`，定义在 `templates/icons.html`，用 `#名字` 引用）
   与 `static/icons.svg` 里的 380 个 ic-*（用 `/static/icons.svg#名字` 引用）。
   取值统一走 `post_icon()` / `post_icon_ref()`，需要内联时用 `post_icon_sprites()`，**别手写 <use href>**。
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
    Python 侧因为 `DEBUG` 默认开，改完自动重载。
12. **入库的边界**：`blog.db`、`.secret_key`、`On_server/`、`*.bak-*`、`__pycache__/` 都被
    `.gitignore` 忽略，**不要 add -f**。数据库结构变更要同时更新 `SCHEMA`（幂等）和 `migrate.py`。

## 6. 常见改动落在哪里

| 想做的事 | 改哪里 |
| --- | --- |
| 加 / 改接口、路由、权限、限流 | `app.py`（路由集中在「页面」「文章发布 / 编辑 / 删除」「评论」「管理入口」等分区） |
| 改 Markdown / LaTeX 语法或净化白名单 | `md_math.py`（并同步 README 的语法清单） |
| 改首页卡片、过滤条、翻页区 | `templates/index.html` + `static/js/index.js` + `static/css/style.css` |
| 改编辑器界面与交互 | `templates/editor.html` + `static/js/editor.js` |
| 改配色 / 主题档位 | `static/css/style.css` 的 CSS 变量；想让主色跟着背景图走则开 `THEME_FROM_BG=1` |
| 加图标 | 本地自绘的加进 `templates/icons.html` + `app.py` 的 `LOCAL_ICONS`；iconfont 的丢进 `static/icons.svg`（自动识别） |
| 改站点文案 / 昵称 / 链接的默认值 | `app.py` 的 `load_cfg()` 与 `templates/author_col.html` |

## 7. 改动检查清单

项目**没有自动化测试**，改完请自己起服务手测：

- [ ] `python app.py` 起得来，控制台端口与 `debug=on/off` 打印符合预期。
- [ ] `DEBUG=0 python app.py` 确实关掉了调试（出错页不再显示堆栈）。
- [ ] 首页：文章列表、过滤三连、标签 chips、翻页、**每页篇数手输**（输 1 / 6 / 200 / 999 / 清空 / 非数字）都正常。
- [ ] 未解锁时访问 `/write`、`/drafts`，游客访问草稿链接 → 行为分别是跳 `/admin`、404。
- [ ] 发文 / 改文 / 存草稿 / 发布草稿 / 删除；评论 + 回复 + 删除 + 验证码。
- [ ] 手机宽度下布局不炸（顶栏、3:1 分栏、编辑器）。
- [ ] 改动后确认 `git status` 里没有 `blog.db` / `.secret_key` / `__pycache__` / `*.bak-*`。

## 8. 收尾

所有目标做完并经过用户验证玩后，推送到Github
