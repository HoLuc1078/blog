/* 上传页 /files：传文件拿 Markdown / 直链；列表里的复制与删除交给公共脚本处理 */
(function () {
  "use strict";
  function $(id) { return document.getElementById(id); }
  var drop = $("uplDrop");
  var input = $("uplInput");
  var pick = $("uplPick");
  var state = $("uplState");
  var results = $("uplResults");
  var grid = $("uplGrid");
  if (!drop || !input) return;

  var idleText = state ? state.innerHTML : "";
  var busy = 0;

  function csrf() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.getAttribute("content") : "";
  }
  function fmtSize(n) {
    n = Number(n) || 0;
    if (n < 1024) return n + " B";
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
    return (n / 1024 / 1024).toFixed(2) + " MB";
  }
  function copyText(text, okMsg) {
    function done() { toast(okMsg || "已复制", "ok"); }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () { legacy(text, done); });
    } else legacy(text, done);
  }
  function legacy(text, done) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); done(); } catch (e) { toast("复制失败", "err"); }
    ta.remove();
  }

  function setBusy(delta) {
    busy += delta;
    if (!state) return;
    if (busy > 0) state.textContent = "正在上传 " + busy + " 个文件…";
    else state.innerHTML = idleText;
  }

  /* 结果卡片：上传完立刻停在这儿，Markdown 与直链都能一键复制 */
  function addResult(f) {
    if (!results) return;
    var row = document.createElement("div");
    row.className = "upl-result";

    var head;
    if (f.is_image) {
      head = document.createElement("img");
      head.className = "upl-result-thumb";
      head.src = f.url;
      head.alt = "";
      head.loading = "lazy";
    } else {
      head = document.createElement("span");
      head.className = "upl-ext upl-ext-" + f.kind;
      head.textContent = String(f.ext || "FILE").toUpperCase();
    }

    var body = document.createElement("div");
    body.className = "upl-result-body";
    var name = document.createElement("div");
    name.className = "upl-result-name";
    name.textContent = f.name + " · " + fmtSize(f.size);
    var md = document.createElement("div");
    md.className = "upl-md upl-md-block";
    md.textContent = f.markdown;
    var acts = document.createElement("div");
    acts.className = "upl-acts";
    acts.appendChild(button("Markdown", function () { copyText(f.markdown, "Markdown 已复制"); }));
    acts.appendChild(button("直链", function () { copyText(f.abs_url, "直链已复制"); }));
    acts.appendChild(link("打开", f.url));
    body.appendChild(name);
    body.appendChild(md);
    body.appendChild(acts);

    row.appendChild(head);
    row.appendChild(body);
    results.insertBefore(row, results.firstChild);
    while (results.children.length > 6) results.removeChild(results.lastChild);
  }

  function button(label, fn) {
    var b = document.createElement("button");
    b.type = "button";
    b.textContent = label;
    b.addEventListener("click", fn);
    return b;
  }
  function link(label, href) {
    var a = document.createElement("a");
    a.textContent = label;
    a.href = href;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    return a;
  }

  /* 新传的也顺手插进下面的列表，不用刷新页面 */
  function addCard(f) {
    if (!grid) return;
    var card = document.createElement("div");
    card.className = "upl-item";
    card.setAttribute("data-id", f.id || "");
    var thumb = link("", f.url);
    thumb.className = "upl-thumb";
    if (f.is_image) {
      var im = document.createElement("img");
      im.src = f.url;
      im.alt = f.name;
      im.loading = "lazy";
      thumb.appendChild(im);
    } else {
      var ex = document.createElement("span");
      ex.className = "upl-ext upl-ext-" + f.kind;
      ex.textContent = String(f.ext || "FILE").toUpperCase();
      thumb.appendChild(ex);
    }
    var info = document.createElement("div");
    info.className = "upl-info";
    var nm = document.createElement("div");
    nm.className = "upl-name";
    nm.title = f.name;
    nm.textContent = f.name;
    var meta = document.createElement("div");
    meta.className = "upl-meta dim";
    meta.textContent = fmtSize(f.size);
    var md = document.createElement("div");
    md.className = "upl-md";
    md.textContent = f.markdown;
    var acts = document.createElement("div");
    acts.className = "upl-acts";
    acts.appendChild(button("Markdown", function () { copyText(f.markdown, "Markdown 已复制"); }));
    acts.appendChild(button("直链", function () { copyText(f.abs_url, "直链已复制"); }));
    acts.appendChild(link("打开", f.url));
    info.appendChild(nm);
    info.appendChild(meta);
    info.appendChild(md);
    info.appendChild(acts);
    card.appendChild(thumb);
    card.appendChild(info);
    grid.insertBefore(card, grid.firstChild);
  }

  function upload(files) {
    if (!files || !files.length) return;
    var fd = new FormData();
    for (var i = 0; i < files.length; i++) {
      fd.append("file", files[i], files[i].name || ("paste-" + Date.now() + ".png"));
    }
    setBusy(1);
    fetch("/api/upload", {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRF-Token": csrf() },
      body: fd
    }).then(function (res) {
      return res.json().catch(function () { return {}; });
    }).then(function (j) {
      setBusy(-1);
      if (!j.ok || !j.files || !j.files.length) {
        toast(j.error || "上传失败", "err");
        return;
      }
      j.files.forEach(function (f) { addResult(f); addCard(f); });
      toast("已上传 " + j.files.length + " 个文件", "ok");
    }).catch(function () {
      setBusy(-1);
      toast("网络错误，上传失败", "err");
    });
  }

  if (pick) pick.addEventListener("click", function () { input.click(); });
  drop.addEventListener("click", function (e) {
    if (e.target === drop || e.target === state || (state && state.contains(e.target))) input.click();
  });
  input.addEventListener("change", function () {
    upload(this.files);
    this.value = "";
  });

  ["dragenter", "dragover"].forEach(function (t) {
    drop.addEventListener(t, function (e) {
      if (!e.dataTransfer) return;
      e.preventDefault();
      drop.classList.add("over");
    });
  });
  drop.addEventListener("dragleave", function () { drop.classList.remove("over"); });
  drop.addEventListener("drop", function (e) {
    drop.classList.remove("over");
    if (!e.dataTransfer || !e.dataTransfer.files.length) return;
    e.preventDefault();
    upload(e.dataTransfer.files);
  });

  document.addEventListener("paste", function (e) {
    var items = (e.clipboardData && e.clipboardData.items) || [];
    var files = [];
    for (var i = 0; i < items.length; i++) {
      if (items[i].kind === "file") {
        var fl = items[i].getAsFile();
        if (fl) files.push(fl);
      }
    }
    if (!files.length) return;
    e.preventDefault();
    upload(files);
  });

  /* 列表里的「Markdown / 直链」按钮（服务端渲染的那些） */
  document.addEventListener("click", function (e) {
    var b = e.target.closest ? e.target.closest("[data-copy]") : null;
    if (!b) return;
    e.preventDefault();
    copyText(b.getAttribute("data-copy"), b.getAttribute("data-copied"));
  });
})();
