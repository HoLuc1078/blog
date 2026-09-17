# 樱羽小筑 · Petal Blog

毛玻璃 + 樱花粉的个人博客：Flask + SQLite，无账号系统，Markdown / LaTeX 渲染语义参考洛谷。

## 运行

```bash
pip install -r requirements.txt   # Flask / Markdown / Pillow
python app.py                     # 监听 0.0.0.0:8848（debug 默认开，DEBUG=0 关掉）
```

打开 http://127.0.0.1:8848。可选环境变量：`DEBUG=0` 关掉调试模式（**默认是开的**：改代码自动重载、出错页带堆栈，线上务必关）；`PORT` 换端口；`THEME_FROM_BG=1` 让主色从 `static/bg.jpg` 提取（`theme.py`）；部署在自有反向代理之后才设 `TRUST_PROXY=1` 并用 `PROXY_HOPS` 声明可信代理跳数（默认不信任 `X-Forwarded-For`，一旦误信，解锁与评论限流都会被绕过）。

## 功能

- **界面**：毛玻璃樱花粉、全站直角面板与虚线分隔，顶栏三档切换「浅色 / 护眼 / 暗黑」（护眼档带强度滑块）；`static/js/petals.js` 提供花瓣粒子 canvas。
- **正文**：`md_math.py` 按洛谷格式手册实现 CommonMark + GFM + 洛谷 directive（折叠框、`:::align`、题记、三线表、代码行号与区间高亮等）和 KaTeX 公式，输出经 HTML 白名单净化；KaTeX 资源走 CDN（带 `integrity` SRI 校验，CDN 被投毒时浏览器直接不执行）。
- **发文**：浏览器打开 `/admin` 设置站长口令（≥6 位，只存 `site_cfg.owner_pass_hash` 的哈希），解锁后顶栏出现「写文章」。编辑页支持摘要、标签、置顶量、发布时间、内容过滤标记（不安全 / 负能量 / 非学术），以及图标搜索与随机、存草稿。
- **阅读**：首页一次渲染全部已发布文章，`static/js/index.js` 在前端完成过滤、标签筛选与翻页（零请求）；作者栏可编辑链接、昵称、头像、站点标题与页脚。
- **草稿**：只有站长可见（游客打开草稿链接是 404），顶栏「草稿箱」可继续编辑 / 发布 / 删除。
- **评论**：不用登录，填名字 + 噪点图形验证码即可；支持多级回复（统一挂在顶层线程下）与连带删除回复；同一浏览器两次评论间隔 15 秒，同 IP 10 分钟最多 20 次提交尝试（验证码答错也计数）；`/captcha.png` 同 IP 10 分钟最多 60 张。

## 图标

- `templates/icons.html` 内联 sprite 里是 **27 个本地自绘图标**：24 个水果（`icon-caomei` … `icon-shizi`）+ `icon-sakura` / `icon-rainbow` / `icon-clover`，在编辑页图标选择器里排最前。
- 其余 **380 个** `ic-*` 来自 `static/icons.svg`（iconfont sprite）：选择器直接 `<use href="/static/icons.svg#ic-x">` 引用，整份只拉一次、之后走缓存；文章页 / 首页 / 草稿箱只把本页用到的 `<symbol>` 内联（`post_icon_sprites()`），不为一个图标去拉整份文件。
- 没选图标、或图标名已失效的文章统一显示 `icon-sakura`（`DEFAULT_ICON`），不再按文章 id 分配。
- `icon-sun` / `icon-eye` / `icon-moon` / `icon-pen` / `icon-close` 只给界面用，不进选择器。

## 数据与升级

- 数据是单文件 SQLite（`blog.db`，启动时自动建表，建表语句幂等）；`blog.db` 与 `.secret_key` 都不进版本库，会话密钥也可用 `SECRET_KEY` 环境变量覆盖。
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
  bg.jpg  favicon.svg  sakura.svg（空状态）  note.svg（草稿箱空状态）  avatar.png（上传即覆盖）
```

## 安全

SQL 全参数化；会话签名 + CSRF 令牌；头像上传校验文件头魔数；站长口令与评论各自限流；评论走严格净化（站外图片改为点击后加载、链接强制 `rel`、类名收紧）。
CSP 的 `script-src` 用每请求一个 nonce 取代 `'unsafe-inline'`，站外资源（KaTeX）带 SRI 校验；渲染入口会把用户输入里的私有区占位字符（U+E000~U+E007）剥掉——那是渲染器的内部 token，留着能在属性位置造出 XSS。
