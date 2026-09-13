/* 发布页（洛谷风格全屏编辑器）：
   编辑/预览 双标签、快捷插入 Markdown 与 LaTeX、本地草稿、发布表单 */
(function () {
  "use strict";
  function $(id) { return document.getElementById(id); }
  var titleEl = $("edTitle");
  var contentEl = $("edContent");
  var summaryEl = $("edSummary");
  var tagsEl = $("edTags");
  var tagInputEl = $("edTagInput");
  var tagListEl = $("edTagList");
  var pinEl = $("edPin");
  var createdEl = $("edCreated");
  var iconEl = $("edIcon");
  var previewEl = $("edPreview");
  var draftEl = $("draftState");
  var countEl = $("edCount");
  var badgeEl = $("edDraftBadge");
  var aid = document.body.getAttribute("data-aid") || "";
  var status = document.body.getAttribute("data-status") || "";
  var DRAFT_KEY = "petal.draft." + (aid || "new");

  function flagValues() {
    return [].slice.call(document.querySelectorAll(".ed-flag:checked"))
      .map(function (c) { return c.value; });
  }

  /* ---------- 标签（= 文章分类，可多个） ---------- */
  var MAX_TAGS = 12, MAX_TAG_LEN = 20;
  var tags = (tagsEl ? (tagsEl.value || "") : "").split(",")
    .map(function (s) { return s.trim(); })
    .filter(function (s) { return s; })
    .slice(0, MAX_TAGS);

  function renderTags() {
    if (tagsEl) tagsEl.value = tags.join(",");
    if (!tagListEl) return;
    tagListEl.textContent = "";
    tags.forEach(function (t) {
      var chip = document.createElement("span");
      chip.className = "tag-edit-item";
      var name = document.createElement("span");
      name.className = "tag-edit-name";
      name.textContent = t;
      var del = document.createElement("button");
      del.type = "button";
      del.className = "tag-edit-del";
      del.title = "移除";
      del.setAttribute("aria-label", "移除标签 " + t);
      del.innerHTML = '<svg class="icon" aria-hidden="true" focusable="false">' +
        '<use href="#icon-close" xlink:href="#icon-close"></use></svg>';
      del.addEventListener("click", function () {
        tags = tags.filter(function (x) { return x !== t; });
        renderTags();
        scheduleDraft();
      });
      chip.appendChild(name);
      chip.appendChild(del);
      tagListEl.appendChild(chip);
    });
  }

  function addTag(raw) {
    var t = String(raw == null ? "" : raw).replace(/\s+/g, " ").trim();
    if (t) {
      if (t.length > MAX_TAG_LEN) t = t.slice(0, MAX_TAG_LEN);
      if (tags.indexOf(t) < 0 && tags.length < MAX_TAGS) tags.push(t);
      renderTags();
      scheduleDraft();
    }
    if (tagInputEl) tagInputEl.value = "";
  }

  function tagValues() { return tags.slice(); }

  if (tagInputEl) {
    tagInputEl.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === "," || e.key === "，") {
        e.preventDefault();
        addTag(tagInputEl.value);
      } else if (e.key === "Backspace" && !tagInputEl.value && tags.length) {
        tags.pop();
        renderTags();
        scheduleDraft();
      }
    });
    tagInputEl.addEventListener("blur", function () { addTag(tagInputEl.value); });
  }
  var tagAddBtn = $("edTagAdd");
  if (tagAddBtn) {
    tagAddBtn.addEventListener("click", function () {
      addTag(tagInputEl ? tagInputEl.value : "");
    });
  }

  /* ---------- 文章图标 ---------- */
  var iconPicks = [].slice.call(document.querySelectorAll("#edIconPicks .icon-pick"));

  function setIcon(name) {
    if (iconEl) iconEl.value = name || "";
    iconPicks.forEach(function (b) {
      b.classList.toggle("on", b.getAttribute("data-icon") === name);
    });
  }
  iconPicks.forEach(function (b) {
    b.addEventListener("click", function () {
      setIcon(b.getAttribute("data-icon"));
      scheduleDraft();
    });
  });

  /* ---------- Ctrl+B / Ctrl+I：给选中的文字套上标记 ---------- */
  function applyInsert(pre, suf) {
    var v = contentEl.value, s = contentEl.selectionStart, e = contentEl.selectionEnd;
    var sel = v.slice(s, e);
    contentEl.value = v.slice(0, s) + pre + sel + suf + v.slice(e);
    var cursor = s + pre.length + sel.length;
    contentEl.focus();
    contentEl.setSelectionRange(cursor, cursor);
    onInput();
  }

  /* ---------- 快捷键（Ctrl+B / Ctrl+I 插入标记） ---------- */
  document.addEventListener("keydown", function (e) {
    if (e.ctrlKey || e.metaKey) {
      var k = (e.key || "").toLowerCase();
      if (k === "s") { e.preventDefault(); saveDraft(true); }
      else if (k === "enter") { e.preventDefault(); submitForm(); }
      else if (k === "b") { e.preventDefault(); applyInsert("**", "**"); }
      else if (k === "i") { e.preventDefault(); applyInsert("*", "*"); }
    }
  });

  /* ---------- 统计 / 输入联动 ---------- */
  var saveTimer = null;
  function onInput() {
    var v = contentEl.value;
    countEl.textContent = v.length + " 字 · " + (v.split("\n").length) + " 行";
    clearTimeout(saveTimer);
    saveTimer = setTimeout(function () { saveDraft(false); }, 900);
    markStale();
  }
  titleEl.addEventListener("input", function () {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(function () { saveDraft(false); }, 900);
  });
  summaryEl.addEventListener("input", function () {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(function () { saveDraft(false); }, 900);
  });
  if (tagInputEl) tagInputEl.addEventListener("input", scheduleDraft);
  if (pinEl) pinEl.addEventListener("input", scheduleDraft);
  if (createdEl) createdEl.addEventListener("input", scheduleDraft);
  [].slice.call(document.querySelectorAll(".ed-flag")).forEach(function (c) {
    c.addEventListener("change", scheduleDraft);
  });
  function scheduleDraft() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(function () { saveDraft(false); }, 900);
  }
  contentEl.addEventListener("input", onInput);
  contentEl.addEventListener("keyup", onInput);

  /* ---------- 本地草稿 ---------- */
  function saveDraft(notify) {
    try {
      var data = {
        t: titleEl.value, c: contentEl.value, s: summaryEl.value,
        tags: tagValues(),
        pin: pinEl ? pinEl.value : "0",
        created: createdEl ? createdEl.value : "",
        flags: flagValues(),
        icon: iconEl ? iconEl.value : "",
        ts: Date.now()
      };
      localStorage.setItem(DRAFT_KEY, JSON.stringify(data));
      var hm = new Date().toTimeString().slice(0, 5);
      if (draftEl) draftEl.textContent = "草稿 " + hm;
      if (notify) toast("草稿已保存", "ok");
    } catch (e) { /* localStorage 不可用则忽略 */ }
  }
  function restoreDraft() {
    var raw;
    try { raw = localStorage.getItem(DRAFT_KEY); } catch (e) { return; }
    if (!raw) return;
    var d;
    try { d = JSON.parse(raw); } catch (e) { return; }
    if (!d || typeof d.c !== "string") return;
    if (aid && !contentEl.value && d.ts) return; // 编辑旧文章不自动覆盖
    if (!contentEl.value && d.c) {
      titleEl.value = d.t || "";
      contentEl.value = d.c;
      summaryEl.value = d.s || "";
      if (Array.isArray(d.tags)) {
        tags = d.tags.filter(function (s) { return typeof s === "string" && s; })
          .slice(0, MAX_TAGS);
      } else if (typeof d.cat === "string" && d.cat) {   // 兼容旧本地草稿
        tags = [d.cat];
      }
      renderTags();
      if (pinEl) pinEl.value = d.pin || "0";
      if (createdEl && d.created) createdEl.value = d.created;
      if (Array.isArray(d.flags)) {
        [].slice.call(document.querySelectorAll(".ed-flag")).forEach(function (c) {
          c.checked = d.flags.indexOf(c.value) >= 0;
        });
      }
      if (d.icon) setIcon(d.icon);
      toast("已恢复草稿 " + new Date(d.ts).toLocaleString(), "ok");
      onInput();
    }
  }

  /* ---------- 预览（服务端渲染，与最终一致；KaTeX 前端渲染） ---------- */
  var stale = true;
  function markStale() { stale = true; }
  function renderPreview() {
    var v = contentEl.value;
    previewEl.innerHTML = '<p class="dim small">渲染中…</p>';
    postJSON("/api/preview", { md: v }).then(function (j) {
      if (j.ok) {
        previewEl.innerHTML = j.html;
        window.renderMath(previewEl);
        window.attachCodeCopy(previewEl);
        stale = false;
      } else if (j.error) {
        previewEl.innerHTML = '<p class="dim small">预览失败：' + j.error + "</p>";
      }
    }).catch(function () {
      previewEl.innerHTML = '<p class="dim small">网络异常，请稍后再试</p>';
    });
  }

  var tabs = document.querySelectorAll(".tab-btn");
  function setTab(name) {
    tabs.forEach(function (t) {
      var on = t.getAttribute("data-tab") === name;
      t.classList.toggle("active", on);
    });
    var editOn = name === "edit";
    contentEl.hidden = !editOn;
    previewEl.hidden = editOn;
    if (!editOn && stale) renderPreview();
    if (!editOn) contentEl.blur();
    if (editOn) contentEl.focus();
  }
  tabs.forEach(function (t) {
    t.addEventListener("click", function () { setTab(t.getAttribute("data-tab")); });
  });

  /* ---------- 发布 / 存草稿（都是 fetch，成功才清本地草稿） ---------- */
  var submitting = false;

  function payload(st) {
    return {
      title: titleEl.value.trim(),
      content: contentEl.value,
      summary: summaryEl.value.trim(),
      tags: tagValues(),
      pin: pinEl ? pinEl.value : 0,
      created: createdEl ? createdEl.value : "",
      flags: flagValues(),
      icon: iconEl ? iconEl.value : "",
      status: st
    };
  }

  function clearLocalDraft() {
    try {
      localStorage.removeItem(DRAFT_KEY);
      localStorage.removeItem("petal.draft.new");
      if (aid) localStorage.removeItem("petal.draft." + aid);
    } catch (e) { /* ignore */ }
  }

  function send(st) {
    if (submitting) return;
    var body = payload(st);
    if (!body.title) { toast("请填写标题", "err"); titleEl.focus(); return; }
    if (st !== "draft" && !body.content.trim()) {
      toast("正文不能为空", "err"); contentEl.focus(); return;
    }
    if (st === "draft" && status === "published" && aid) {
      if (!window.confirm("存为草稿后访客就看不到这篇文章了，确定吗？")) return;
    }
    submitting = true;
    setPublishText(st === "draft" ? "保存中…" : "发布中…");
    var url = aid ? "/a/" + aid + "/edit" : "/write";
    postJSON(url, body)
      .then(function (j) {
        submitting = false;
        setPublishText("");
        if (j.need_owner) {
          location.href = "/admin?next=" + encodeURIComponent(url);
          return;
        }
        if (j.ok && (j.id || aid)) {
          var id = j.id || aid;
          clearLocalDraft();
          if (st === "draft") {
            status = "draft";
            if (badgeEl) badgeEl.hidden = false;
            if (!aid) {                                  // 新草稿：留在编辑页，地址换成这篇文章
              aid = String(id);
              DRAFT_KEY = "petal.draft." + aid;
              try { history.replaceState(null, "", "/a/" + aid + "/edit"); } catch (e) { /* ignore */ }
            }
            toast("已存草稿", "ok");
          } else {
            window.location.href = "/a/" + id;
          }
        } else {
          toast(j.error || "保存失败，请重试", "err");
        }
      })
      .catch(function () {
        submitting = false;
        setPublishText("");
        toast("网络异常，保存失败", "err");
      });
  }

  function submitForm() { send("published"); }

  function setPublishText(txt) {
    var p2 = $("edPublish2");
    if (p2) p2.textContent = txt || "发布 / 更新";
  }
  var p2 = $("edPublish2");
  if (p2) p2.addEventListener("click", submitForm);
  var save2 = $("edSave2");
  if (save2) save2.addEventListener("click", function () { send("draft"); });

  /* ---------- 启动 ---------- */
  renderTags();
  setIcon(iconEl ? iconEl.value : "");
  restoreDraft();
  onInput();
  setTab("edit");
})();
