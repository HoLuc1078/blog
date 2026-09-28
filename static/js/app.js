/* Petal Blog 公共脚本：toast / CSRF fetch / KaTeX 渲染 / 代码复制 /
   确认删除 / 作者栏编辑弹窗 / 图形验证码刷新 */
(function () {
  "use strict";

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  /* ---------- toast ---------- */
  function toast(msg, type) {
    var box = $("#toast-box");
    if (!box) return;
    var el = document.createElement("div");
    el.className = "toast" + (type === "ok" ? " ok" : type === "err" ? " err" : "");
    el.textContent = msg;
    box.appendChild(el);
    setTimeout(function () {
      el.classList.add("out");
      setTimeout(function () { el.remove(); }, 320);
    }, 3000);
  }
  window.toast = toast;

  function csrfToken() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.getAttribute("content") : "";
  }

  function postJSON(url, data) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken() },
      body: JSON.stringify(data || {})
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (j) {
        j._status = res.status;
        return j;
      });
    });
  }
  window.postJSON = postJSON;

  /* ---------- KaTeX 渲染（把服务端输出的 .math 区域变成公式） ---------- */
  function renderMath(root) {
    if (!window.katex) return;
    $all(".math-inline, .math-block", root).forEach(function (el) {
      if (el.dataset.katexDone) return;
      var tex = el.textContent;
      try {
        window.katex.render(tex, el, {
          displayMode: el.classList.contains("math-block"),
          throwOnError: false,
          strict: "ignore"
        });
        el.dataset.katexDone = "1";
      } catch (e) {
        el.classList.add("math-err");
      }
    });
  }
  window.renderMath = renderMath;

  /* ---------- 长代码块右上角复制 ---------- */
  function attachCodeCopy(root) {
    $all("pre", root).forEach(function (pre) {
      if (pre.dataset.copyReady) return;
      var code = pre.querySelector(":scope > code");
      if (!code) return;
      pre.dataset.copyReady = "1";
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "md-code-copy";
      btn.textContent = "复制";
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        var text = code.innerText;
        function done() { toast("已复制", "ok"); }
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(done, function () { legacyCopy(text, done); });
        } else legacyCopy(text, done);
      });
      pre.appendChild(btn);
    });
  }
  function legacyCopy(text, done) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); done(); } catch (e) { toast("复制失败", "err"); }
    ta.remove();
  }
  window.attachCodeCopy = attachCodeCopy;

  /* ---------- 确认提交 ---------- */
  function bindConfirms() {
    document.addEventListener("submit", function (e) {
      var f = e.target;
      if (f.matches && f.matches("form[data-confirm]")) {
        var msg = f.getAttribute("data-confirm") || "确定执行此操作？";
        if (!window.confirm(msg)) e.preventDefault();
      }
    }, true);
  }

  /* ---------- 图形验证码：点击换一张 ---------- */
  function bindCaptcha() {
    var img = $("#captchaImg");
    if (!img) return;
    img.addEventListener("click", function () {
      img.src = "/captcha.png?t=" + Date.now();
    });
  }

  /* ---------- 评论里的站外图片：默认不发起任何请求，点击后才加载 ---------- */
  function bindExternalImages() {
    document.addEventListener("click", function (e) {
      var btn = e.target.closest ? e.target.closest(".ext-img-load") : null;
      if (!btn || btn.disabled) return;
      e.preventDefault();
      var url = btn.getAttribute("data-src");
      if (!url) return;
      var img = document.createElement("img");
      img.className = "ext-img-loaded";
      img.alt = btn.getAttribute("data-alt") || "外部图片";
      img.referrerPolicy = "no-referrer";       // 不把本文地址带给第三方
      img.addEventListener("error", function () { toast("图片加载失败", "err"); });
      // 先放进 DOM 再设 src：游离的 <img> 配合 loading=lazy 可能永远不触发加载
      btn.replaceWith(img);
      img.src = url;                            // 只有点了这里才会发起第三方请求
    });
  }

  /* ---------- 作者栏编辑弹窗（站长解锁后可见） ---------- */
  function bindAuthorEditor() {
    var modal = $("#authorEditModal");
    if (!modal) return;
    var openBtn = $("#editAuthorBtn");
    if (!openBtn) return;

    function open() { modal.hidden = false; document.body.style.overflow = "hidden"; }
    function close() { modal.hidden = true; document.body.style.overflow = ""; }
    openBtn.addEventListener("click", open);
    $("#aeCancel").addEventListener("click", close);
    modal.addEventListener("click", function (e) {
      if (e.target === modal) close();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !modal.hidden) close();
    });

    function esc(s) {
      return String(s || "").replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
    }
    /* 友链与联系方式的编辑列表结构一样，共用一套增删逻辑 */
    function bindList(listSel, addSel) {
      var listEl = $(listSel);
      var addEl = $(addSel);
      if (!listEl || !addEl) return;
      function addRow(label, url) {
        var row = document.createElement("div");
        row.className = "ae-link-row";
        row.innerHTML =
          '<input type="text" class="ae-link-label" maxlength="30" placeholder="名称" value="' +
          esc(label) + '">' +
          '<input type="text" class="ae-link-url" maxlength="2000" ' +
          'placeholder="网址" value="' + esc(url) + '">' +
          '<button type="button" class="ae-link-del" title="移除" aria-label="移除">' +
          '<svg class="icon" aria-hidden="true" focusable="false">' +
          '<use href="#icon-close"></use></svg></button>';
        listEl.appendChild(row);
      }
      addEl.addEventListener("click", function () { addRow("", ""); });
      listEl.addEventListener("click", function (e) {
        if (e.target.classList && e.target.classList.contains("ae-link-del")) {
          e.target.closest(".ae-link-row").remove();
        }
      });
    }
    bindList("#aeLinks", "#aeAddLink");
    bindList("#aeContacts", "#aeAddContact");

    $("#aeAvatarFile").addEventListener("change", function () {
      var file = this.files && this.files[0];
      if (!file) return;
      var fd = new FormData();
      fd.append("file", file);
      fetch("/api/avatar", {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRF-Token": csrfToken() },
        body: fd
      }).then(function (res) { return res.json(); }).then(function (j) {
        if (j.ok && j.avatar) {
          var img = $("#aeAvatarPreview");
          img.hidden = false;
          img.src = j.avatar;                    // 固定文件 + ?v= 时间戳，直接覆盖生效
          toast("头像已更新", "ok");
        } else toast(j.error || "上传失败", "err");
      }).catch(function () { toast("网络错误", "err"); });
      this.value = "";
    });

    $("#aeSave").addEventListener("click", function () {
      var btn = this;
      function collect(sel) {
        var out = [];
        $all(sel + " .ae-link-row").forEach(function (row) {
          var label = row.querySelector(".ae-link-label").value.trim();
          var url = row.querySelector(".ae-link-url").value.trim();
          if (!label && !url) return;
          out.push({ label: label, url: url });
        });
        return out;
      }
      var body = {
        author_nickname: $("#aeNickname").value.trim(),
        author_bio: $("#aeBio").value,
        site_title: $("#aeSiteTitle").value.trim(),
        site_subtitle: $("#aeSiteSubtitle").value.trim(),
        footer_text: $("#aeFooterText").value.trim(),
        links: collect("#aeLinks"),
        contacts: collect("#aeContacts")
      };
      btn.disabled = true;
      postJSON("/api/site", body).then(function (j) {
        if (j.ok) {
          toast(j.warn || "已保存", j.warn ? "err" : "ok");
          setTimeout(function () { location.reload(); }, j.warn ? 1500 : 450);
        } else {
          toast(j.error || "保存失败", "err");
          btn.disabled = false;
        }
      }).catch(function () { toast("网络错误", "err"); btn.disabled = false; });
    });
  }

  /* ---------- 评论回复：点「回复」把目标塞进主表单（验证码只有一张，共用最省事） ---------- */
  function bindCommentReply() {
    var form = $("#cmtForm");
    if (!form) return;
    var parent = $("#cmtParent");
    var box = $("#cmtReplyTo");
    var nameEl = $("#cmtReplyName");
    var submit = $("#cmtSubmit");
    var cancel = $("#cmtReplyCancel");
    if (!parent || !box) return;
    var ta = form.querySelector('textarea[name="content"]');

    function setTarget(cid, name, scroll) {
      parent.value = cid ? String(cid) : "0";
      if (cid) {
        if (nameEl) nameEl.textContent = name || "";
        box.hidden = false;
        if (submit) submit.textContent = "发表回复";
        if (scroll) {
          box.scrollIntoView({ behavior: "smooth", block: "center" });
          setTimeout(function () { if (ta) ta.focus(); }, 260);
        }
      } else {
        box.hidden = true;
        if (submit) submit.textContent = "发表评论";
      }
    }

    document.addEventListener("click", function (e) {
      var btn = e.target.closest ? e.target.closest(".cmt-reply") : null;
      if (!btn) return;
      e.preventDefault();
      setTarget(btn.getAttribute("data-cid"), btn.getAttribute("data-name"), true);
    });
    if (cancel) cancel.addEventListener("click", function () { setTarget(0); });

    /* 提交失败回到页面时（服务端带回了 cp），把回复目标恢复出来 */
    var cur = parent.value;
    if (cur && cur !== "0") {
      var b = document.querySelector('.cmt-reply[data-cid="' + cur + '"]');
      setTarget(cur, b ? b.getAttribute("data-name") : "", false);
    }
  }

  /* ---------- 主题：浅色 / 护眼 / 暗黑 ---------- */
  function bindTheme() {
    var btns = $all(".theme-btn[data-theme-set]");
    if (!btns.length) return;
    function apply(t) {
      document.documentElement.setAttribute("data-theme", t);
      btns.forEach(function (b) {
        b.classList.toggle("on", b.getAttribute("data-theme-set") === t);
      });
      try { localStorage.setItem("petal.theme", t); } catch (e) { /* ignore */ }
    }
    var cur = document.documentElement.getAttribute("data-theme");
    if (cur !== "care" && cur !== "dark") cur = "light";
    btns.forEach(function (b) {
      b.classList.toggle("on", b.getAttribute("data-theme-set") === cur);
      b.addEventListener("click", function () { apply(b.getAttribute("data-theme-set")); });
    });
  }

  /* ---------- 护眼强度 ---------- */
  function careSaved() {
    var v = 0;
    try { v = parseInt(localStorage.getItem("petal.care") || "", 10); } catch (e) { v = 0; }
    return v >= 10 && v <= 85 ? v : 52;
  }

  function applyCare(v) {
    document.documentElement.style.setProperty("--care-strength", (v / 100).toFixed(2));
    var el = $("#careRange");
    if (el && String(el.value) !== String(v)) el.value = String(v);
  }

  function bindCare() {
    applyCare(careSaved());
    var el = $("#careRange");
    if (!el) return;
    el.addEventListener("input", function () {
      var v = parseInt(el.value, 10);
      if (!(v >= 10 && v <= 85)) v = 52;
      applyCare(v);
      try { localStorage.setItem("petal.care", v); } catch (e) { /* ignore */ }
    });
  }

  /* ---------- 图片灯箱：点正文里的图片放大看原图 ---------- */
  function bindImageZoom() {
    var box = null, pic = null, bar = null, pct = null;
    var scale = 1, tx = 0, ty = 0, drag = null, lastFocus = null;

    function paint() {
      pic.style.transform = "translate(" + tx + "px, " + ty + "px) scale(" + scale + ")";
      if (pct) pct.textContent = Math.round(scale * 100) + "%";
    }
    /* 以鼠标位置（没给就按图片中心）为锚点缩放，视觉上更跟手 */
    function setScale(next, cx, cy) {
      next = Math.min(8, Math.max(0.15, next));
      if (next === scale) return;
      var r = pic.getBoundingClientRect();
      var ax = cx == null ? r.left + r.width / 2 : cx;
      var ay = cy == null ? r.top + r.height / 2 : cy;
      var ox = (ax - (r.left + r.width / 2)) / scale;
      var oy = (ay - (r.top + r.height / 2)) / scale;
      tx -= ox * (next - scale);
      ty -= oy * (next - scale);
      scale = next;
      paint();
    }
    function reset() { scale = 1; tx = 0; ty = 0; paint(); }

    function build() {
      box = document.createElement("div");
      box.className = "img-zoom";
      box.hidden = true;
      pic = document.createElement("img");
      pic.className = "img-zoom-pic";
      pic.alt = "";
      pic.draggable = false;
      bar = document.createElement("div");
      bar.className = "img-zoom-bar";
      bar.innerHTML =
        '<button type="button" data-zoom="out" title="缩小">−</button>' +
        '<span class="zoom-pct">100%</span>' +
        '<button type="button" data-zoom="in" title="放大">+</button>' +
        '<button type="button" data-zoom="one" title="原始大小">1:1</button>' +
        '<button type="button" data-zoom="close" title="关闭">关闭</button>';
      pct = bar.querySelector(".zoom-pct");
      var tip = document.createElement("div");
      tip.className = "img-zoom-tip";
      tip.textContent = "滚轮缩放 · 拖动平移 · 双击切换原图 · Esc 关闭";
      box.appendChild(pic);
      box.appendChild(bar);
      box.appendChild(tip);
      document.body.appendChild(box);

      bar.addEventListener("click", function (e) {
        var b = e.target.closest ? e.target.closest("button[data-zoom]") : null;
        if (!b) return;
        e.stopPropagation();
        var act = b.getAttribute("data-zoom");
        if (act === "in") setScale(scale * 1.4);
        else if (act === "out") setScale(scale / 1.4);
        else if (act === "one") reset();
        else close();
      });
      box.addEventListener("click", function (e) {
        if (e.target === box) close();          // 点背景关闭；点图本身不关
      });
      box.addEventListener("wheel", function (e) {
        e.preventDefault();
        setScale(scale * (e.deltaY < 0 ? 1.15 : 1 / 1.15), e.clientX, e.clientY);
      }, { passive: false });
      box.addEventListener("dblclick", function (e) {
        e.preventDefault();
        if (scale > 1.01) reset();
        else setScale(2, e.clientX, e.clientY);
      });
      pic.addEventListener("pointerdown", function (e) {
        if (scale <= 1.01) return;
        e.preventDefault();
        drag = { x: e.clientX, y: e.clientY, tx: tx, ty: ty };
        box.classList.add("grabbing");
        try { pic.setPointerCapture(e.pointerId); } catch (err) { /* ignore */ }
      });
      pic.addEventListener("pointermove", function (e) {
        if (!drag) return;
        tx = drag.tx + (e.clientX - drag.x);
        ty = drag.ty + (e.clientY - drag.y);
        paint();
      });
      function endDrag() { drag = null; box.classList.remove("grabbing"); }
      pic.addEventListener("pointerup", endDrag);
      pic.addEventListener("pointercancel", endDrag);
      pic.addEventListener("error", function () { toast("图片加载失败", "err"); });
    }

    function open(src, alt, from) {
      if (!box) build();
      lastFocus = from || null;
      pic.src = src;
      pic.alt = alt || "";
      reset();
      box.hidden = false;
      document.body.classList.add("zoom-open");
      document.body.style.overflow = "hidden";
    }
    function close() {
      if (!box || box.hidden) return;
      box.hidden = true;
      pic.removeAttribute("src");
      drag = null;
      document.body.classList.remove("zoom-open");
      document.body.style.overflow = "";
      if (lastFocus && lastFocus.focus) { try { lastFocus.focus(); } catch (e) { /* ignore */ } }
    }

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && box && !box.hidden) close();
    });
    document.addEventListener("click", function (e) {
      var img = e.target.closest ? e.target.closest(".md-body img") : null;
      if (!img || img.classList.contains("img-zoom-pic")) return;
      if (img.closest("a")) return;                 // 图片本身是链接：让人正常跳转
      if (!img.currentSrc && !img.src) return;
      e.preventDefault();
      open(img.currentSrc || img.src, img.getAttribute("alt") || "", img);
    });
  }

  /* ---------- 启动 ---------- */
  function init() {
    bindConfirms();
    bindTheme();
    bindCare();
    bindCaptcha();
    bindExternalImages();
    bindAuthorEditor();
    bindCommentReply();
    bindImageZoom();
    attachCodeCopy(document.body);
    renderMath(document.body);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else init();
})();
