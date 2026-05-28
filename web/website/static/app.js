(() => {
  const LS_TOKEN = "ps_token";
  const LS_USER  = "ps_user";
  const $  = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => Array.from(root.querySelectorAll(s));

  const html       = document.documentElement;
  const logEl      = $("#log");
  const logEmpty   = $("#log-empty");
  const resultsEl  = $("#results");
  const resultsEmpty = $("#results-empty");
  const cardUpload = $("#card-upload");
  const cardAuth   = $("#card-auth");
  const stagedEl   = $("#staged");
  const btnClearLog= $("#btn-clear");

  const state = {
    mode:   "login",           // "login" | "register"
    token:  localStorage.getItem(LS_TOKEN) || null,
    user:   localStorage.getItem(LS_USER)  || null,
    file:   null,
    filter: "all",
  };

  /* ─────────── HTTP log helpers ─────────── */
  function tone(status) {
    if (status === 0) return "err";
    if (status >= 200 && status < 300) return "ok";
    if (status >= 500) return "err";
    if (status >= 400) return "warn";
    return "info";
  }
  function statusLabel(s) {
    return ({
      200: "OK", 201: "Created", 400: "Bad Request", 401: "Unauthorized",
      403: "Forbidden", 404: "Not Found", 405: "Method Not Allowed",
      409: "Conflict", 500: "Internal Server Error", 0: "network error",
    })[s] || `status ${s}`;
  }
  function logEntry(method, path, status, message = "") {
    if (logEmpty) logEmpty.classList.add("hidden");
    btnClearLog.hidden = false;
    const t = new Date().toISOString().split("T")[1].slice(0, 8);
    const cls = tone(status);
    const tagCls =
      cls === "ok"   ? "status-ok"   :
      cls === "warn" ? "status-warn" :
      cls === "err"  ? "status-err"  : "";
    const wrap = document.createElement("div");
    wrap.className = `log-entry ${cls}`;
    wrap.dataset.tone = cls;
    wrap.innerHTML = `
      <div class="row1">
        <span class="who">${method.toUpperCase()} ${escape(path)}</span>
        <span class="tag ${tagCls}">${status || "ERR"}</span>
      </div>
      <div class="row2">→ ${escape(message || statusLabel(status))}</div>
      <div class="row3">${t}</div>
    `;
    logEl.prepend(wrap);
    applyFilter();
  }
  function applyFilter() {
    $$(".log-entry", logEl).forEach((e) => {
      const t = e.dataset.tone;
      let show = true;
      if (state.filter === "ok")  show = t === "ok";
      if (state.filter === "err") show = (t === "err" || t === "warn");
      e.style.display = show ? "" : "none";
    });
  }

  async function api(method, path, { body, isForm = false, auth = true } = {}) {
    const headers = {};
    if (auth && state.token) headers["Authorization"] = `Bearer ${state.token}`;
    let payload;
    if (isForm) payload = body;
    else if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(body);
    }
    let res, data, raw = "";
    try {
      res = await fetch(path, { method, headers, body: payload });
      raw = await res.text();
      try { data = JSON.parse(raw); } catch (_) { data = raw; }
    } catch (e) {
      logEntry(method, path, 0, "network error");
      throw e;
    }
    const msg =
      (data && data.error && data.error.message) ||
      (data && data.message) ||
      (data && data.token   ? "token issued" : "") ||
      (data && data.matches ? `${data.matches.length} matches` : "") ||
      statusLabel(res.status);
    logEntry(method, path, res.status, msg);
    return { res, data };
  }

  /* ─────────── ticker / status ─────────── */
  async function refreshStatus() {
    if (!state.token) return;
    const { res, data } = await api("GET", "/status");
    if (res.status === 401) { clearSession(); return; }
    if (res.status === 200 && data?.status) {
      const s = data.status;
      $("#m-uptime").textContent  = s.uptime.toFixed(1) + "s";
      $("#m-success").textContent = s.processed.success;
      $("#m-fail").textContent    = s.processed.fail;
      const h = $("#m-health"); const d = $("#d-health");
      h.textContent = s.health;
      h.className = "v " + (s.health === "ok" ? "ok" : "err");
      d.className = "dot " + (s.health === "ok" ? "ok" : "err");
      $("#m-api").textContent = "v" + s.api_version;
    }
  }

  /* ─────────── auth state ─────────── */
  function setAuthState(authed) {
    html.dataset.auth = authed ? "in" : "out";
    cardUpload.dataset.locked = authed ? "false" : "true";
    const dzt = $("[data-dz-title]");
    const dzs = $("[data-dz-sub]");
    if (authed) {
      dzt.textContent = "Drop or click to upload an image";
      dzs.textContent = "png · jpg · jpeg · webp · gif · bmp · others are transcoded to jpeg";
    } else {
      dzt.textContent = "Sign in to enable upload";
      dzs.textContent = "the /classifier endpoint requires Bearer auth";
    }
  }
  function setMode(mode) {
    state.mode = mode;
    const btnText = $("#auth-form .submit-auth [data-text]");
    const linkText = $("[data-mode-text]");
    if (mode === "login") {
      btnText.textContent = "Sign in";
      linkText.textContent = "No account? Create one →";
    } else {
      btnText.textContent = "Create account";
      linkText.textContent = "Have an account? Sign in →";
    }
  }
  function showSession(user) {
    state.user = user;
    localStorage.setItem(LS_USER, user);
    $("#who").textContent = user;
    setAuthState(true);
    refreshStatus();
  }
  function clearSession() {
    state.token = null;
    state.user = null;
    localStorage.removeItem(LS_TOKEN);
    localStorage.removeItem(LS_USER);
    setAuthState(false);
    setMode("login");
    ["m-uptime", "m-success", "m-fail", "m-api"].forEach((id) => {
      $("#" + id).textContent = id === "m-api" ? "v1" : "—";
    });
    $("#m-health").textContent = "—";
    $("#m-health").className = "v";
    $("#d-health").className = "dot";
    clearStagedFile();
    resultsEl.innerHTML = "";
    resultsEl.appendChild(resultsEmpty);
    resultsEmpty.classList.remove("hidden");
  }

  $("#mode-toggle").addEventListener("click", () => {
    setMode(state.mode === "login" ? "register" : "login");
  });

  /* ─────────── auth form ─────────── */
  $("#auth-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const msg = $("#auth-msg");
    msg.textContent = ""; msg.className = "hint";
    const btn = $("#auth-form .submit-auth");
    btn.disabled = true;
    btn.classList.add("is-loading");
    const fd = new FormData(e.target);
    const body = { username: fd.get("username"), password: fd.get("password") };
    const path = state.mode === "register" ? "/register" : "/login";
    try {
      const { res, data } = await api("POST", path, { body, auth: false });
      if (path === "/register" && res.status === 201) {
        msg.textContent = "account created · signing in…";
        msg.className = "hint ok";
        const r2 = await api("POST", "/login", { body, auth: false });
        if (r2.res.status === 200) {
          state.token = r2.data.token;
          localStorage.setItem(LS_TOKEN, state.token);
          msg.textContent = "signed in";
          showSession(body.username);
          smoothScrollTo(cardUpload);
        } else {
          msg.textContent = (r2.data?.error?.message) || "Login failed.";
          msg.className = "hint error";
        }
        return;
      }
      if (path === "/login" && res.status === 200) {
        state.token = data.token;
        localStorage.setItem(LS_TOKEN, state.token);
        msg.textContent = "signed in";
        msg.className = "hint ok";
        showSession(body.username);
        smoothScrollTo(cardUpload);
        return;
      }
      msg.textContent = (data?.error?.message) || `error ${res.status}`;
      msg.className = "hint error";
    } finally {
      btn.disabled = false;
      btn.classList.remove("is-loading");
    }
  });

  $("#btn-logout").addEventListener("click", async () => {
    await api("POST", "/logout");
    clearSession();
  });

  /* ─────────── upload / classify ─────────── */
  const dz         = $("#dropzone");
  const fileInput  = $("#file");
  const previewImg = $("#preview-img");
  const previewName= $("#preview-name");
  const previewSize= $("#preview-size");

  function fmtBytes(n) {
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / 1024 / 1024).toFixed(2)} MB`;
  }

  function readDataURL(file) {
    return new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => resolve(r.result);
      r.onerror = () => reject(new Error("read failed"));
      r.readAsDataURL(file);
    });
  }
  function loadImageEl(src) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error("decode failed"));
      img.src = src;
    });
  }
  /**
   * Normalize the file to something the server accepts (interface.md mandates
   * .png or .jpeg). .jpg gets renamed; anything else gets canvas-transcoded
   * to JPEG.  Returns the normalized File (may be the original).
   */
  async function normalizeForServer(file) {
    const lowName = (file.name || "image").toLowerCase();
    if (file.type === "image/png"  && lowName.endsWith(".png"))  return { file, note: null };
    if (file.type === "image/jpeg" && lowName.endsWith(".jpeg")) return { file, note: null };
    if (file.type === "image/jpeg" && lowName.endsWith(".jpg")) {
      const renamed = new File([file], lowName.replace(/\.jpg$/i, ".jpeg"), { type: "image/jpeg" });
      return { file: renamed, note: "renamed .jpg → .jpeg" };
    }
    // Everything else: transcode to JPEG via canvas
    const dataUrl = await readDataURL(file);
    const img = await loadImageEl(dataUrl);
    const canvas = document.createElement("canvas");
    canvas.width  = img.naturalWidth || img.width;
    canvas.height = img.naturalHeight || img.height;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#fff";              // flatten alpha to white
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0);
    const blob = await new Promise((resolve, reject) => {
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("toBlob failed"))), "image/jpeg", 0.92);
    });
    const base = (file.name || "image").replace(/\.[^.]+$/, "") || "image";
    const out = new File([blob], `${base}.jpeg`, { type: "image/jpeg" });
    const origFmt = (file.type || lowName.split(".").pop() || "unknown").replace("image/", "");
    return { file: out, note: `transcoded ${origFmt} → jpeg` };
  }

  async function loadFile(f) {
    if (!f) return;
    if (!f.type || !f.type.startsWith("image/")) {
      renderResults([], `not an image (got "${f.name || f.type}")`, true);
      return;
    }
    let normalized;
    try {
      normalized = await normalizeForServer(f);
    } catch (e) {
      renderResults([], `couldn't decode ${f.name}: ${e.message}`, true);
      return;
    }
    state.file = normalized.file;
    stagedEl.hidden = false;
    cardUpload.classList.add("has-staged");
    previewName.textContent = normalized.file.name;
    const noteSuffix = normalized.note ? ` · ${normalized.note}` : "";
    previewSize.textContent = fmtBytes(normalized.file.size) + noteSuffix;
    const reader = new FileReader();
    reader.onload = (e) => (previewImg.src = e.target.result);
    reader.readAsDataURL(normalized.file);
  }
  function clearStagedFile() {
    state.file = null;
    stagedEl.hidden = true;
    cardUpload.classList.remove("has-staged");
    previewImg.removeAttribute("src");
    previewName.textContent = "";
    previewSize.textContent = "";
    fileInput.value = "";
  }
  // <label> wrapping <input type="file"> opens the file dialog natively on click.
  // We only need a keyboard handler so the focusable label responds to Enter/Space.
  dz.addEventListener("keydown", (e) => {
    if ((e.key === "Enter" || e.key === " ") && state.token) {
      e.preventDefault(); fileInput.click();
    }
  });
  fileInput.addEventListener("change", (e) => loadFile(e.target.files[0]));
  ;["dragenter", "dragover"].forEach((ev) =>
    dz.addEventListener(ev, (e) => { e.preventDefault(); if (state.token) dz.classList.add("dragging"); })
  );
  ;["dragleave", "drop"].forEach((ev) =>
    dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("dragging"); })
  );
  dz.addEventListener("drop", (e) => { if (state.token) loadFile(e.dataTransfer.files[0]); });

  $("#btn-remove-file").addEventListener("click", clearStagedFile);

  $("#btn-classify").addEventListener("click", async () => {
    if (!state.file || !state.token) return;
    const btn = $("#btn-classify");
    btn.disabled = true;
    btn.classList.add("is-loading");
    try {
      const fd = new FormData();
      fd.append("image", state.file, state.file.name);
      const { res, data } = await api("POST", "/classifier", { body: fd, isForm: true });
      if (res.status === 200 && data?.matches) {
        renderResults(data.matches, "");
      } else {
        renderResults([], (data?.error?.message) || `error ${res.status}`, true);
      }
    } finally {
      btn.disabled = false;
      btn.classList.remove("is-loading");
      refreshStatus();
    }
  });

  function renderResults(matches, msg, isErr = false) {
    resultsEl.innerHTML = "";
    if (!matches.length) {
      const p = document.createElement("p");
      p.className = isErr ? "row-error" : "empty-line";
      p.textContent = msg || "no matches";
      resultsEl.appendChild(p);
      return;
    }
    matches.forEach((m) => {
      const pct = (m.score * 100).toFixed(1);
      const row = document.createElement("div");
      row.className = "row";
      row.innerHTML = `
        <span class="name" title="${escape(m.name)}">${escape(m.name)}</span>
        <span class="score">${pct}%</span>
        <span class="bar"><i style="width:${pct}%"></i></span>
      `;
      resultsEl.appendChild(row);
    });
  }
  function escape(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }

  /* ─────────── log controls ─────────── */
  $("#log-filter").addEventListener("change", (e) => {
    state.filter = e.target.value; applyFilter();
  });
  btnClearLog.addEventListener("click", () => {
    logEl.innerHTML = "";
    logEl.appendChild(logEmpty);
    logEmpty.classList.remove("hidden");
    btnClearLog.hidden = true;
  });

  /* ─────────── helpers ─────────── */
  function smoothScrollTo(el) {
    if (!el) return;
    const y = el.getBoundingClientRect().top + window.scrollY - 64;
    window.scrollTo({ top: y, behavior: "smooth" });
  }

  /* ─────────── bootstrap ─────────── */
  setAuthState(false);
  setMode("login");
  if (state.token && state.user) showSession(state.user);
  refreshStatus();
  setInterval(refreshStatus, 5000);
})();
