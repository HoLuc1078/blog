# 樱羽小筑 · Petal Blog

毛玻璃 + 樱花粉的个人博客。Markdown / LaTeX 渲染语义参考洛谷，发布页参考洛谷文章编辑器布局。

## 运行

```bash
pip install -r requirements.txt   # Flask / Markdown / Pillow
python app.py                     # 监听 0.0.0.0:8848
```

打开 http://127.0.0.1:8848

> 端口可用环境变量覆盖：`PORT=9000 python app.py`
> 背景图重新生成：`python gen_bg.py`（写 `static/bg.jpg`）

## 使用方式（无账号系统）

- **浏览**：任何人可看文章、标签、评论。
- **评论**：不用登录，填「名字 + 噪点图形验证码」即可（验证码点图片可换一张，
  5 分钟有效、一次一用；同一浏览器两次评论间隔 15 秒，同 IP 10 分钟最多 20 条）。
- **站长发文**：浏览器直接打开 **`/admin`**（页面上不放入口）设置**站长口令**（首次设置，≥6 位）。
  解锁后顶栏出现「写文章」，作者栏出现「编辑作者栏」；解锁状态保存在本机浏览器（30 天），
  随时可在 `/admin` 锁定。口令只存在本机 `blog.db` 的 `site_cfg.owner_pass_hash`（哈希），
  忘记时清掉该行即可重设。

## 需求对照

| 需求 | 实现 |
| --- | --- |
| 毛玻璃 UI（仿 yingaobichibang） | `static/css/style.css`：浅色玻璃面板 + 淡粉渐变标题，可爱风（淡粉 + 白） |
| 主体色 | 默认手写可爱配色：`--accent:#f0a6c0` / `--accent-deep:#cf7a9b`（降饱和的淡粉，不刺眼）+ 白色面板；实心色块 `--solid-side:#fbe7f0` 等。想让主色跟着 `static/bg.jpg` 自动提取（`theme.py`），启动时设 `THEME_FROM_BG=1` 即可 |
| main-col 透明度 | `.main-col { opacity: .75 }`（主栏整体 75% 不透明） |
| topbar 最左侧站点图标 | `.brand` 内 `<img class="site-logo" src="/static/favicon.svg">`（用原来的粉色图标，未做任何改动/滤镜）；顶栏为**纯色**白底（`--topbar-bg:#ffffff`，不做毛玻璃） |
| 发布时间可自己填 | 编辑页「发布时间」（`datetime-local`，按北京时间填）→ 存库转 UTC；留空＝当前时间，非法值报错；列表按 `pin DESC, created_at DESC` 排序 |
| 发布页深色玻璃、少圆角 | `.ed-main` / `.side-card` / `.editor-top`：深色玻璃 `rgba(78,56,72,.52) → rgba(56,40,53,.63)` + `blur(24px) saturate(150%)`，内部文字/控件/预览区整套改成浅色（`--ed-ink` / `--ed-field` / `--ed-line`）；编辑页所有面板与控件 `border-radius: 0` |
| 文案精简 | 全站去掉「（如：…）」「越大越靠前」「留空则…」等说明性文字，只保留标签、按钮与必要的错误提示 |
| 站长标识 | 已去掉作者栏昵称旁的「博」标签（`.owner-tag`） |
| 主页面 : 作者页 = 3:1 | `.main-col{flex:3}` / `.author-col{flex:1}`（作者栏另有 286px 固定宽度上限，屏幕窄时降到 248px） |
| 作者栏纯色实心、无圆角、固定高度不随页面滚动 | `.author-card`：纯色 `--solid-side`、无毛玻璃、无圆角、无阴影；`position: sticky; top: var(--topbar-h); height: calc(100vh - var(--topbar-h) - 16px)` —— 固定高度吸顶，只有内部 `.author-links`（Links / 分类 / 最近文章三个列表）各自 `overflow-y: auto` 独立滚动 |
| main-split 尽量占满页面 | `.layout` 最大宽 1720、左右 10px 留白、底部无空隙 |
| 花瓣粒子（美化版） | `static/js/petals.js`：**纯 JS 文件**（由 `<script src>` 加载，整页 HTML 不能贴进来，否则浏览器按 JS 解析会直接语法错误、粒子整层不执行）。`COUNT`：桌面 1300 / 窄屏 700；z 景深（近大远小）、残影拖尾（`destination-out` 淡出，保留页面背景、暗色下不留白底）、鼠标力场吸附。改密度只改 `COUNT`。绘制全是「纯色路径填充」一条管线——小花瓣 `arc` 圆点、大花瓣（约 1/8）带旋转的压扁 `ellipse`；颜色按块分组，`fillStyle` 每帧只改一百多次；画布半分辨率渲染后由 CSS 拉伸铺满视口。鼠标附近为力场式吸附（边界平滑归零 + 近处轻推成环 + 切向分量绕转），不会在影响半径上来回抖 |
| 文章点得开 | 整张卡片（含标题、摘要、留白）都是进入文章的点击区（`static/css/style.css` 的 `.post-title::after`） |
| 标题与正文用虚线分割 | 列表卡 `.post-head` 与文章页 `.art-title` / `.art-meta` 均为 `1px dashed` |
| 列表摘要更小更淡 | `.post-excerpt` 12.5px、62% 透明，与标题拉开层次 |
| 最新文章不同样式 + 纯色填充 + 与每篇宽度不同 | `.latest-board` 纯色板 + 实心标题条占满主栏；每篇 `.post-card` 纯色且窄 14px，左侧留白仅 4px |
| 标题前的 svg 图标（409 个，可搜索、可随机） | `templates/icons.html` 内联 sprite 放了站内自绘的 5 个（`#icon-lizi`、`#icon-peach`、`#icon-sakura`、`#icon-rainbow`、`#icon-clover`，老文章存的就是这些名字）；其余 **404 个**是 yc-lain 博客那套 iconfont（`static/icons.svg`，由 `gen_icons.py` 生成，id 统一加 `ic-` 前缀避免撞名）。编辑页「图标」里可**搜索名字**、可**点「随机」**抓一个（`#edIconRandom`），网格自带滚动区。渲染方式分两路：编辑器选择器直接 `<use href="/static/icons.svg#ic-x">`（整个 sprite 只下一次、之后走缓存）；文章页/首页/草稿箱只把**本页用到的那几个 `<symbol>` 内联**进页面（`post_icon_sprites()`），所以正文页不会为了一个图标去拉 881KB。没选过图标的老文章仍按 id 在自绘的 5 个里稳定分配（`post_icon()` 兜底） |
| 减少圆角 | 大面板一律直角（0），按钮 3px、输入 2px |
| 评论改成名字 + 图形验证码（无头像） | `/captcha.png`（Pillow 生成：噪点 + 干扰线 + 字符随机旋转）、`/a/<id>/comment` 校验；失败带 `?cerr=` 回评论区给出具体提示；评论不显示头像 |
| 取消登录/注册 | 删掉了注册、登录、邮箱验证码、个人主页、账号管理；发文改为 `/admin` 站长口令 |
| 头像只留一张、上传即覆盖 | `static/avatar.png` 固定文件：上传时方形裁剪 + 缩放到 256 后直接覆盖，不写数据库、不保留旧文件（老上传目录里的头像会自动搬过来）；没有头像时作者栏用昵称首字占位（已删除默认头像图） |
| 作者栏竖排链接、站长可编辑 | 作者栏 Links 竖排；「编辑作者栏」可增删改链接（GitHub/Bilibili/邮箱…，可省 `https://`，自动补全）；也可改昵称/简介/头像/站点标题/页脚 |
| 护眼滤镜 / 暗黑模式 | 顶栏三档切换「浅色 / 护眼 / 暗黑」：护眼是整屏暖色叠层（压蓝光、不改布局，**普通混合**，不用 `mix-blend-mode` —— 原因见下面「浏览器合成」一节），且只在护眼档挂载（其它主题 `display: none`）；切到护眼时顶栏出现强度滑块（10%~85%，存 `localStorage` 的 `petal.care`）。暗黑参考 cnblogs `/yc-lain` 的暗黑色系、整套 CSS 变量互换（bg `#171e23`、面板 `#1b2329`、正文 `#c6d0d7`，玻璃面板走 `--glass-hi/--glass-lo`）。选择存 `localStorage`，`<head>` 内联脚本首屏即生效、无白闪；文章页与发布页一样跟随 |
| 文章标签（= 文章分类，可多个） | 编辑页「标签（可多个）」：输入回车/逗号即添加，带已有标签提示，一篇可打多个（`articles.tags` 存 CSV，最多 12 个 × 20 字）；首页卡片、文章页、草稿箱显示标签并可点进筛选；作者栏「标签 · Tags」列表（含篇数） |
| 置顶量 | 编辑页「置顶量」0~999，越大越靠前（`ORDER BY pin DESC, created_at DESC`），列表与文章页显示置顶标记 |
| 三个内容过滤标记 | 编辑页侧栏「内容过滤标记」三个选框：**不安全 / 负能量 / 非学术**（可多选，`articles.flags` 存 CSV），首页卡片与文章页以彩色小标签显示；它们只是内容提示，不是文章分类 |
| 首页过滤 + 按标签筛选 | 「过滤」三个复选框（不显示不安全/负能量/非学术内容）+「标签」按钮（= 文章分类，多选，命中任一即显示，带篇数）+「重置」；选择记在 `localStorage`，刷新后仍在；`/?tag=xxx` 会把它设为初始选中标签 |
| 过滤/标签/翻页不发请求 | 首页一次性把已发布文章全渲染出来，`static/js/index.js` 在前端完成过滤、按标签筛选、翻页与每页篇数（`fetch`/`XHR` 零调用，实测 0 次） |
| 翻页在最下面 + 每页篇数 | `.list-foot` 在列表底部：上一页 / 页码 / 下一页 + 「每页 6 / 12 / 24 / 48 / 全部 篇」 |
| 存草稿 | 编辑页顶部与侧栏各一个「存草稿」按钮（`status=draft`）；草稿允许先只写标题；草稿状态在编辑页显示紫色「草稿」小标 |
| 草稿只有站长看得到 | 首页/分类/作者栏统计/最近文章一律只算 `status='published'`；游客直接开草稿链接也是 404 |
| 草稿箱 | 顶栏右侧**粉色文本超链接**「草稿箱」（仅站长可见，不是按钮），带未发布篇数角标；`/drafts` 里可继续编辑 / 发布 / 删除 |
| 评论可以回复、回复的回复 | `comments.parent_id`；回复统一挂在顶层线程下，回复回复会标「回复 @某人」；右上角「回复」把主表单切到回复模式（共用同一张验证码，不额外发请求）；删除评论会连带删除其下所有回复 |
| 端口 8848 | 见上 |

## 内容能力

### Markdown：按洛谷格式手册实现（`md_math.py`）

洛谷的语法集合 = CommonMark + GFM + 洛谷自己的 directive 扩展。本站照此实现：

| 语法 | 渲染结果 |
| --- | --- |
| `*斜体*` `**粗体**` `***粗斜体***` | `<em>` / `<strong>` |
| `~~删除线~~` | `<del>`（GFM，内部仍可写 **粗体** 等） |
| `- [ ]` / `- [x]` | 只读复选框（GFM 任务列表） |
| `文字[^1]` + `[^1]: 注` | GFM 脚注，文末自动汇总 |
| `\| a \| b \|` GFM 表格 | `<table>`，`:-:` 等对齐分隔行照常生效 |
| 表格单元格 `^` / `<` | `^` 向上合并（rowspan）、`<` 向左合并（colspan）；N 格合并要 N−1 个标记格，且格子内容必须只有该标记 |
| `:::info[标题]{open}` | 折叠框（洛谷只有 `info`/`success`/`warning`/`error` 四种），无标题时默认「提示/成功/警告/错误」，`{open}` 默认展开，可嵌套 |
| `:::align{center\|right\|left}` | 段落与标题居中 / 居右 / 居左（代码块、表格、列表不受影响，和洛谷一致） |
| `:::epigraph[——署名]` | 题记：靠右的引用块，署名单独一行、右对齐、上方带分隔线 |
| `::anti-ai[隐藏文字]` | 洛谷的反 AI 水印：不可见，但复制正文时会一起被带走 |
| `::cute-table{tuack\|three}[表 1]` | 包装下面的表格：三线表 / Tuack 风格 + 表标题 |
| ```` ```cpp line-numbers ```` | 代码块行号（纯 CSS 计数器，无 JS） |
| ```` ```cpp lines=5-6,11 ```` | 指定行高亮；可与 `line-numbers` 同用 |
| 裸链接 `https://…` | 自动变成链接（GFM），代码块 / 行内代码 / `[x](url)` 里不动 |
| `$..$`、`$$..$$`、`\(..\)`、`\[..\]` | KaTeX 公式（`\(..\)`、`\[..\]` 是本站额外支持，洛谷只有 `$`） |

洛谷本身**不支持**、因此本站也按字面文本输出的：`^上标^`、`~下标~`、`==高亮==`、
`->居中<-`、`[TOC]`、定义列表、缩写、原始 HTML（公式里请用 `$x^2$`、`$\text{H}_2\text{O}$`）。

实现要点：容器 / 对齐 / 题记等先摘成私有代理字符（`_split_containers`），
行内代码 → 公式 → 删除线 → 自动链接依次保护（`protect`），再交给 python-markdown
（`fenced_code` / `tables` / `footnotes` / `attr_list` / `sane_lists` / `def_list`），
然后由 `_LuoguTreeprocessor`（任务列表、表格合并、colgroup、cute-table）与
`_LuoguPostprocessor`（代码行号 / 区间高亮）加工，最后白名单净化（`sanitize`）。

### 安全

- 内容经 HTML 白名单净化（XSS）：类名走白名单（评论里无法用 `.btn` 之类伪造站内控件）、
  只放行脚注锚点 `id`、任务列表复选框强制 `disabled`；
- SQL 参数化、会话签名、CSRF 令牌、上传图片做文件头魔数校验、口令尝试限流；
- 评论（访客可写）走严格模式：站外图片默认不加载、链接强制 `rel`。

## 目录

```
app.py              Flask 后端（路由 / 站长口令 / 验证码 / 内容 API / 数据库迁移）
theme.py            从 static/bg.jpg 提取主体色，生成 CSS 变量
md_math.py          Markdown + LaTeX 保护式渲染 + HTML 白名单净化
gen_bg.py           生成 static/bg.jpg
gen_icons.py        从 iconfont 项目导出 static/icons.svg（404 个图标 sprite）
requirements.txt
templates/          base / index / article / editor / drafts / admin / author_col / icons / modal / error
static/
  css/style.css     全站样式（主体色由 theme.py 注入覆盖）
  icons.svg         图标 sprite（由 gen_icons.py 生成；编辑器选择器直接引用它）
  js/petals.js      花瓣粒子（纯 JS，禁止放 HTML；颜色跟随主体色）
  js/index.js       首页前端筛选 / 标签 / 翻页 / 每页篇数（零请求）
  js/app.js         toast / CSRF / KaTeX / 代码复制 / 验证码刷新 / 作者栏编辑 / 评论回复
  js/editor.js      发布页逻辑（摘要、标签、图标搜索/随机、置顶量、发布时间、内容过滤标记、存草稿、发布）
  bg.jpg  favicon.svg  sakura.svg（空状态樱花）  note.svg（草稿箱空状态）  avatar.png（运行时生成）
blog.db             运行时自动生成（SQLite，老库自动迁移补列）
```

### 图标怎么再生成

`static/icons.svg` 不是手写的，换/加图标集时跑：

```bash
python gen_icons.py                                  # 默认取 yc-lain 用的那份 iconfont
python gen_icons.py <js-url 或本地 js 路径> [输出.svg]  # 换地址 / 换输出
```

脚本把 iconfont 的 js 里那份 `<symbol>` sprite 抠出来，id 统一加 `ic-` 前缀
（避免和站内自绘的 `icon-lizi` 撞名），路径坐标取整压缩（881KB ← 原始 1.8MB），
写成 `static/icons.svg`。写完重启一下 Flask 即可（`app.py` 按文件 mtime 自动重载，
不用改代码）。

## 浏览器合成：护眼档与「玻璃」面板

Chromium 在 `mix-blend-mode` 与 `backdrop-filter` 同处一个混合组时合成会出错（混合的
源图可能取到过滤前的上一层，见 crbug 503307127、40855567、496284084；Firefox 正常），
表现为**鼠标划过触发重绘时，某些色块被重复混合而显得更深**。据此本站做了两处调整：

- `.bg` 去掉了 `background-attachment: fixed`（该元素本来就是 `position: fixed; inset: 0`，
  居中/`cover` 结果完全一样），因为 fixed 背景走的是 Blink 里「不跟随常规 effect 层级」的
  绘制路径（crbug 40255683），而 `backdrop-filter` 的回读建立在常规绘制节点上，两者叠加会
  取到跟着可见矩形走的模糊区域（w3c/fxtf-drafts#238）。
- `.theme-tint`（护眼暖色层）不再用 `mix-blend-mode: multiply`：改成普通混合的暖色盖层，
  恒为 `normal`、不设 `opacity`、不做 `opacity` 过渡（crbug 40490696 的成因正是「为 opacity
  动画建层 + backdrop-filter」），并且**只在护眼档出现**（其余主题 `display: none`，不再
  无条件挂一个非 normal 混合层）。
  观感差异：普通混合没法像 multiply 那样「黑的更黑」，所以护眼档在深色玻璃面板（发布页）上
  会比以前略亮一些、更柔；想调浓淡只改 `.theme-tint` 里的 `--care-tint`（默认 `.30`），
  或直接拖顶栏的护眼强度滑块。

如果仍然看到色块：按顺序试（DevTools → Rendering → Paint flashing 看哪些矩形在重绘）
①切到暗黑档（暗黑档的 `.bg` 本来就没有 fixed）；②`.theme-tint{display:none}`；
③给 `.side-card` / `.ed-main` / `.editor-top` 逐个去掉 `backdrop-filter`（面板越多、
每个面板都是一次独立的背景回读，越容易踩到这类 bug）；④换 100% / 110% 缩放对比
（crbug 443985458）。不要用 `will-change: transform` / `translateZ(0)` / `isolation` 去「修」：
前者会把 `background-attachment: fixed` 悄悄降级成 `scroll`，而且这些都会新建渲染表面，
在 Chromium 里「凡是新建渲染表面的元素都会成为 backdrop root」，反而更容易出问题。

## 迁移说明

- 老库（带账号系统）升级时：`comments` 会自动加上 `author_name` 并用原用户名回填，
  旧评论一条不丢；`users` 表原样保留（不再使用），`email_codes`、`favorites` 已删除，
  `site_cfg.author_avatar` 已清理。
- 新增列都会自动补上：`articles.status`（默认 `published`）、`articles.flags`（默认空）、
  `articles.icon`（默认空，空 = 按 id 自动分配图标）、
  `articles.tags`（默认空，老库的单个 `articles.category` 会自动搬进 `tags`，内容不丢；
  旧 `category` 列保留但不再读写）、`comments.parent_id`（默认 0，即顶层评论），老数据不受影响。
- 老的头像（`static/uploads/xxx.png`）会自动转换搬成 `static/avatar.png`，不会丢。
- 站长口令存在 `site_cfg.owner_pass_hash`，忘记时 `DELETE FROM site_cfg WHERE key='owner_pass_hash'` 即可重设。
