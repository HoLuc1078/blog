/* 首页列表：过滤（不显示不安全/负能量/非学术）、按标签筛选、翻页、每页篇数
   —— 全部在前端做，勾选/翻页都不发任何请求；选择记在 localStorage 里，换页回来还在。
   每页篇数是可手输的数字框（1–MAX_PER，没有"全部"这一档）：越界自动夹紧，清空后失焦还原。
   卡片上的标签链接（/?tag=xxx）与服务端都只是把「初始选中标签」带进来，筛选照旧在前端完成 */
(function () {
  "use strict";
  var list = document.getElementById("postList");
  if (!list) return;
  var meta = document.getElementById("listMeta");
  var pager = document.getElementById("pager");
  var perInput = document.getElementById("perPage");
  var emptyEl = document.getElementById("listEmpty");
  var resetBtn = document.getElementById("filterReset");
  var bar = document.getElementById("filterBar");
  var curTag = bar ? (bar.getAttribute("data-cur-tag") || "") : "";
  var boxes = [].slice.call(document.querySelectorAll("#filterBar input[data-hide]"));
  var chips = [].slice.call(document.querySelectorAll(".tag-chip[data-tag]"));
  var KEY = "petal.home.filter";
  var MIN_PER = 1, MAX_PER = 200, DEFAULT_PER = 12;   // 与 templates/index.html 的 min / max / value 对应

  var cards = [].slice.call(list.querySelectorAll(".post-card")).map(function (el) {
    var rawFlags = el.getAttribute("data-flags") || "";
    var rawTags = el.getAttribute("data-tags") || "";
    return {
      el: el,
      flags: rawFlags ? rawFlags.split(",") : [],
      tags: rawTags ? rawTags.split(",") : []
    };
  });

  var state = { hides: [], tags: [], per: DEFAULT_PER, page: 1 };
  try {
    var saved = JSON.parse(localStorage.getItem(KEY) || "null");
    if (saved && typeof saved === "object") {
      if (Array.isArray(saved.hides)) state.hides = saved.hides;
      if (Array.isArray(saved.tags)) state.tags = saved.tags;
      // 旧版本存过 0（那时表示"全部"）：现在没有这一档，直接回落到默认值
      if (typeof saved.per === "number" && isFinite(saved.per) && saved.per >= MIN_PER) {
        state.per = clampPer(saved.per);
      }
    }
  } catch (e) { /* ignore */ }
  if (curTag) state.tags = [curTag];      // URL 上的标签优先于本地记录

  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) { /* ignore */ }
  }

  /* 每页篇数：夹到 [MIN_PER, MAX_PER]，非法值退回默认 */
  function clampPer(n) {
    n = Math.floor(Number(n));
    if (!isFinite(n)) return DEFAULT_PER;
    return Math.max(MIN_PER, Math.min(MAX_PER, n));
  }

  /* 把 state.per 写回输入框（正在输入时不打断，失焦时再对齐） */
  function syncPerInput() {
    if (!perInput || document.activeElement === perInput) return;
    var v = String(state.per);
    if (perInput.value !== v) perInput.value = v;
  }

  function matches(card) {
    for (var i = 0; i < state.hides.length; i++) {
      if (card.flags.indexOf(state.hides[i]) >= 0) return false;    // 勾了"不显示…"
    }
    if (state.tags.length) {                                        // 选了标签：命中任意一个即可
      var hit = false;
      for (var j = 0; j < state.tags.length; j++) {
        if (card.tags.indexOf(state.tags[j]) >= 0) { hit = true; break; }
      }
      if (!hit) return false;
    }
    return true;
  }

  function pageCount(n) {
    return Math.max(1, Math.ceil(n / state.per));
  }

  function syncChips() {
    chips.forEach(function (chip) {
      var tag = chip.getAttribute("data-tag");
      var on = !tag ? state.tags.length === 0 : state.tags.indexOf(tag) >= 0;
      chip.classList.toggle("on", on);
    });
  }

  function render() {
    syncChips();
    var shown = [];
    cards.forEach(function (c) {
      var ok = matches(c);
      if (ok) shown.push(c);
      c.el.hidden = true;
    });
    var pages = pageCount(shown.length);
    if (state.page > pages) state.page = pages;
    if (state.page < 1) state.page = 1;
    var start = (state.page - 1) * state.per;
    var end = start + state.per;
    shown.slice(start, end).forEach(function (c) { c.el.hidden = false; });

    if (emptyEl) emptyEl.hidden = shown.length > 0;
    if (meta) {
      meta.textContent = "共 " + cards.length + " 篇" +
        (shown.length !== cards.length ? " · 显示 " + shown.length + " 篇" : "") +
        (pages > 1 ? " · 第 " + state.page + " / " + pages + " 页" : "");
    }
    if (resetBtn) resetBtn.hidden = !(state.hides.length || state.tags.length);
    renderPager(pages);
    syncPerInput();
  }

  function renderPager(pages) {
    if (!pager) return;
    pager.innerHTML = "";
    if (pages > 1) {
      pager.appendChild(pageBtn("‹ 上一页", state.page - 1, state.page <= 1, "btn small"));
      var nums = pageNums(state.page, pages);
      nums.forEach(function (n) {
        if (n === 0) {
          var sp = document.createElement("span");
          sp.className = "pager-gap";
          sp.textContent = "…";
          pager.appendChild(sp);
          return;
        }
        pager.appendChild(pageBtn(String(n), n, false,
          "btn small pager-num" + (n === state.page ? " on" : "")));
      });
      pager.appendChild(pageBtn("下一页 ›", state.page + 1, state.page >= pages, "btn small"));
    }
  }

  function pageNums(cur, pages) {
    var out = [];
    if (pages <= 7) {
      for (var i = 1; i <= pages; i++) out.push(i);
      return out;
    }
    out.push(1);
    var from = Math.max(2, cur - 1), to = Math.min(pages - 1, cur + 1);
    if (from > 2) out.push(0);
    for (var j = from; j <= to; j++) out.push(j);
    if (to < pages - 1) out.push(0);
    out.push(pages);
    return out;
  }

  function pageBtn(text, page, disabled, cls) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = cls || "btn small";
    b.textContent = text;
    if (disabled) b.disabled = true;
    else b.addEventListener("click", function () {
      state.page = page;
      render();
      var board = document.querySelector(".latest-board");
      if (board) window.scrollTo({ top: board.offsetTop - 70, behavior: "smooth" });
    });
    return b;
  }

  /* ---------- 交互 ---------- */
  if (boxes.length) {
    boxes.forEach(function (b) {
      b.checked = state.hides.indexOf(b.getAttribute("data-hide")) >= 0;
      b.addEventListener("change", function () {
        state.hides = boxes.filter(function (x) { return x.checked; })
          .map(function (x) { return x.getAttribute("data-hide"); });
        state.page = 1;
        save();
        render();
      });
    });
  }
  chips.forEach(function (chip) {
    var tag = chip.getAttribute("data-tag");
    chip.addEventListener("click", function () {
      if (!tag) {                                   // "全部" = 清空标签选择
        state.tags = [];
      } else {
        var i = state.tags.indexOf(tag);
        if (i >= 0) state.tags.splice(i, 1);
        else state.tags.push(tag);
      }
      state.page = 1;
      save();
      render();
    });
  });
  if (perInput) {
    function onPerInput() {
      var raw = String(perInput.value || "").trim();
      if (!raw) return;                        // 清空时先不动，失焦后再还原上一个有效值
      var n = parseInt(raw, 10);
      if (!isFinite(n) || n < MIN_PER) return;
      state.per = clampPer(n);                 // 超过 MAX_PER 会被夹紧，失焦时写回输入框
      state.page = 1;
      save();
      render();
    }
    perInput.addEventListener("input", onPerInput);
    perInput.addEventListener("change", onPerInput);
    perInput.addEventListener("blur", function () { perInput.value = String(state.per); });
  }
  if (resetBtn) {
    resetBtn.addEventListener("click", function () {
      state.hides = [];
      state.tags = [];
      state.page = 1;
      boxes.forEach(function (b) { b.checked = false; });
      save();
      render();
    });
  }

  /* 标签上的篇数（按全部文章统计，不受"不显示"影响） */
  chips.forEach(function (chip) {
    var tag = chip.getAttribute("data-tag");
    var n = chip.querySelector(".tag-n");
    if (!n || !tag) return;
    var c = cards.filter(function (x) { return x.tags.indexOf(tag) >= 0; }).length;
    n.textContent = c ? " " + c : "";
  });

  render();
})();
