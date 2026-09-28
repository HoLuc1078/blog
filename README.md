# 樱羽小筑 · Petal Blog

毛玻璃 + 樱花粉的个人博客：Flask + SQLite，无账号系统，Markdown / LaTeX 渲染语义参考洛谷。

## 运行

```bash
pip install -r requirements.txt   # Flask / Markdown / Pillow
python app.py                     # 监听 0.0.0.0:8848（debug 默认关，DEBUG=1 打开）
```

打开 http://127.0.0.1:8848。可选环境变量：`DEBUG=1` 打开调试模式（**默认是关的**；开了才有改代码自动重载与出错页堆栈，只在本地开发时用）；`PORT` 换端口；`THEME_FROM_BG=1` 让主色从 `static/bg.jpg` 提取（`theme.py`）；部署在自有反向代理之后才设 `TRUST_PROXY=1` 并用 `PROXY_HOPS` 声明可信代理跳数（默认不信任 `X-Forwarded-For`，一旦误信，解锁与评论限流都会被绕过）。

## 功能

- **界面**：毛玻璃樱花粉、全站直角面板与虚线分隔，顶栏三档切换「浅色 / 护眼 / 暗黑」（护眼档带强度滑块）；`static/js/petals.js` 提供花瓣粒子 canvas。
- **正文**：`md_math.py` 按洛谷格式手册实现 CommonMark + GFM + 洛谷 directive（折叠框、`:::align`、题记、三线表、代码行号与区间高亮等）和 KaTeX 公式，输出经 HTML 白名单净化；KaTeX 资源走 CDN（带 `integrity` SRI 校验，CDN 被投毒时浏览器直接不执行）。
- **本站扩展语法**（洛谷没有的三条）：
  - `~[标题](地址)` 视频 —— B 站 / YouTube 链接自动转内嵌播放器，`.mp4` 等直链用原生 `<video>`，都不认识就退化成外链卡片。
  - `*[文件名](地址)` 文件 —— 渲染成带扩展名徽标与「下载」按钮的卡片，点击直接下载（同源附件会带上原文件名）。
  - `:::charge[标题]` … `:::` 评论解锁 —— 没在本页评论过的访客**拿不到里面的 HTML**（不是用 CSS 遮住，查看源码也是空的）；站长和在本页评论过的人正常看到内容。评论被删掉后解锁自动失效。
- **图片**：正文图片默认按屏幕缩放（宽不溢出、高不超过一屏 82%），不再是原始像素尺寸，也不带任何透明度；点一下进灯箱，可滚轮缩放、拖动平移、双击切换原图，Esc / 点背景关闭。
- **发文**：浏览器打开 `/admin` 设置站长口令（≥6 位，只存 `site_cfg.owner_pass_hash` 的哈希），解锁后顶栏出现「写文章」。编辑页支持摘要、标签、置顶量、发布时间、内容过滤标记（不安全 / 负能量 / 非学术），以及图标搜索与随机、存草稿。
- **附件上传（仅站长）**：顶栏「上传」进 `/files` —— 拖拽 / 选择 / 直接 Ctrl+V 粘贴都能传，传完立刻给出 Markdown 与直链（一键复制），下面按类型列出以前传过的所有文件（缩略图、原始文件名、大小、时间、删除）。编辑页工具条也能传，**粘贴或拖入图片会自动上传**并插入 Markdown。文件落在仓库外的 `uploads/YYYY/MM/`，只经 `/u/<路径>` 这一个出口对外；图片 / 音视频内联，其余一律 `Content-Disposition: attachment` 强制下载。扩展名走白名单（`.html` / `.svg` / `.js` 一律不收），且图片 / 音视频还要过文件头魔数校验。
- **阅读**：首页一次渲染全部已发布文章，`static/js/index.js` 在前端完成过滤、标签筛选与翻页（零请求）；「不显示不安全内容」**默认勾选**（其他两个默认不勾，选择记在 localStorage）；选中多个标签时按命中标签数排序（命中越多越靠前，相同再比置顶量），每张卡片都显示置顶量；作者栏可编辑联系方式、友链、昵称、头像、站点标题与页脚。
- **草稿**：只有站长可见（游客打开草稿链接是 404），顶栏「草稿箱」可继续编辑 / 发布 / 删除。
- **评论**：不用登录，填名字 + 噪点图形验证码即可；支持多级回复（统一挂在顶层线程下）与连带删除回复；同一浏览器两次评论间隔 15 秒，同 IP 10 分钟最多 20 次提交尝试（验证码答错也计数）；`/captcha.png` 同 IP 10 分钟最多 60 张。

## 图标

- **站内 27 个**（`static/icons-local.svg`）：24 个水果（`icon-caomei` … `icon-shizi`）+ `icon-sakura` / `icon-rainbow` / `icon-clover`，在编辑页图标选择器里排最前。
  其中 19 个取自 [Twemoji](https://github.com/jdecked/twemoji)（**CC-BY 4.0**，© Twitter, Inc. and other contributors）；
  火龙果 / 荔枝 / 榴莲 / 龙眼 / 山竹 / 石榴 / 西梅 / 柿子这 8 个没有对应 emoji，按同一画风自绘。**再分发时请保留这份署名。**
- **其余 380 个** `ic-*` 来自 `static/icons.svg`（iconfont sprite）。
- 这两套都是**按需引用**：编辑器图标选择器直接 `<use href="/static/icons-local.svg#名字">` / `/static/icons.svg#名字`（各只拉一次，之后走缓存）；文章页 / 首页 / 草稿箱只把本页真正用到的那一两个 `<symbol>` 内联进 HTML（`post_icon_sprites()`），既不额外拉整份 sprite，也不会把 27 个水果全塞进每个页面。
- 没选图标、或图标名已失效的文章统一显示 `icon-sakura`（`DEFAULT_ICON`）。
- `templates/icons.html` 里只剩 5 个**界面图标**：`icon-sun` / `icon-eye` / `icon-moon` / `icon-pen` / `icon-close`，它们随每个页面内联，可以直接 `<use href="#名字">`。界面上一律用 SVG，不用 emoji。

## 数据与升级

- 数据是单文件 SQLite（`blog.db`，启动时自动建表，建表语句幂等；新增表只要写进 `SCHEMA` 即可，老库启动时自动补）；`blog.db` 与 `.secret_key` 都不进版本库，会话密钥也可用 `SECRET_KEY` 环境变量覆盖。
- 老库升级跑一次 `python migrate.py`（或 `python migrate.py <库路径>` 指定别的库）：把 `icon-peach` 改成 `icon-taozi`、把失效或为空的图标统一成 `icon-sakura`，并清掉账号系统时代的残留（`users` / `email_codes` / `favorites` 三张表、`site_cfg.author_avatar`，站长口令保留）。脚本幂等、可重复跑，改动前会在同目录留一份 `<库名>.bak-<时间戳>` 备份，跑完可以删。
- 忘记站长口令：删掉 `site_cfg` 里 `owner_pass_hash` 那一行就能重设。

## 目录

```
app.py              Flask 后端（路由 / 站长口令 / 验证码 / 图标 / 净化 / 反代与限流）
AGENTS.md           给维护者/协作者的项目说明（结构、每个文件的职责、改代码的约定与自查清单）
migrate.py          一次性数据迁移（图标名对齐 + 清理账号系统残留；幂等，跑完可删）
theme.py            从 static/bg.jpg 提取主体色（THEME_FROM_BG=1 时启用）
md_math.py          Markdown + LaTeX 保护式渲染 + HTML 白名单净化
requirements.txt    Flask / Markdown / Pillow
templates/          base / index / article / editor / drafts / admin / author_col / author_edit_modal / icons / error
static/
  css/style.css     全站样式
  icons.svg         iconfont 图标 sprite（380 个 ic-*，编辑器选择器直接引用）
  js/petals.js      花瓣粒子 canvas
  js/index.js       首页筛选 / 标签 / 翻页（零请求）
  js/app.js         toast / CSRF / KaTeX / 代码复制 / 验证码刷新 / 作者栏编辑 / 评论回复
  js/editor.js      发布页逻辑（摘要、标签、图标搜索与随机、置顶量、时间、过滤标记、草稿）
  js/uploads.js     上传页 /files：拖拽 / 选择 / 粘贴上传，结果与列表的复制按钮
  bg.jpg  favicon.svg  sakura.svg（空状态）  note.svg（草稿箱空状态）  avatar.png（上传即覆盖）
uploads/            站长上传的附件（YYYY/MM/<随机名>.<ext>，**不进版本库**，经 /u/<路径> 对外；
                    /files 页面列出它们，记录存在 uploads 表里，目录里的文件会自动补录）
```

## 安全

SQL 全参数化；会话签名 + CSRF 令牌；头像与附件上传都校验文件头魔数，上传只认扩展名白名单；站长口令与评论各自限流；评论走严格净化（站外图片改为点击后加载、链接强制 `rel`、类名收紧，且不内嵌第三方播放器）。
`:::charge` 的解锁凭证是 `(文章 id, 评论 id)` 的 HMAC 签名 cookie——cookie 明文存在客户端，不签名就等于谁都能自己编一条「我评论过」；渲染时还会回库确认那条评论确实还在。
CSP 的 `script-src` 用每请求一个 nonce 取代 `'unsafe-inline'`，站外资源（KaTeX）带 SRI 校验；`frame-src` 只放行 B 站与 YouTube 的播放器域名，`media-src` 放行站内外音视频；渲染入口会把用户输入里的私有区占位字符（U+E000~U+E009）剥掉——那是渲染器的内部 token，留着能在属性位置造出 XSS。
