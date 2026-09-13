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

  /* ---------- 头像加载兜底：图挂了就隐藏（已无默认头像图） ---------- */
  function bindAvatarFallback() {
    document.addEventListener("error", function (e) {
      var t = e.target;
      if (t && t.tagName === "IMG" && t.classList && t.classList.contains("author-avatar")) {
        t.hidden = true;
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
        '<use href="#icon-close" xlink:href="#icon-close"></use></svg></button>';
      $("#aeLinks").appendChild(row);
    }
    $("#aeAddLink").addEventListener("click", function () { addRow("", ""); });
    $("#aeLinks").addEventListener("click", function (e) {
      if (e.target.classList && e.target.classList.contains("ae-link-del")) {
        e.target.closest(".ae-link-row").remove();
      }
    });

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
      var links = [];
      $all("#aeLinks .ae-link-row").forEach(function (row) {
        var label = row.querySelector(".ae-link-label").value.trim();
        var url = row.querySelector(".ae-link-url").value.trim();
        if (!label && !url) return;
        links.push({ label: label, url: url });
      });
      var body = {
        author_nickname: $("#aeNickname").value.trim(),
        author_bio: $("#aeBio").value,
        site_title: $("#aeSiteTitle").value.trim(),
        site_subtitle: $("#aeSiteSubtitle").value.trim(),
        footer_text: $("#aeFooterText").value.trim(),
        links: links
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

  /* ---------- 启动 ---------- */
  function init() {
    bindConfirms();
    bindAvatarFallback();
    bindTheme();
    bindCare();
    bindCaptcha();
    bindExternalImages();
    bindAuthorEditor();
    bindCommentReply();
    attachCodeCopy(document.body);
    renderMath(document.body);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else init();
})();
