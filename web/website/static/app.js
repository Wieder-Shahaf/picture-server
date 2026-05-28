(() => {
  const LS_TOKEN = "ps_token";
  const LS_USER = "ps_user";
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));
  const logEl = $("#log");

  const state = {
    mode: "login",
    token: localStorage.getItem(LS_TOKEN) || null,
    user: localStorage.getItem(LS_USER) || null,
    file: null,
    filter: "all",
  };

  // ---------- log entries (chat-style cards) ----------
  function tone(status) {
    if (status === 0) return "err";
    if (status >= 200 && status < 300) return "ok";
    if (status >= 500) return "err";
    if (status >= 400) return "warn";
    return "info";
  }
  function logEntry(method, path, status, message = "") {
    const t = new Date().toISOString().split("T")[1].slice(0, 8);
    const cls = tone(status);
    const tagCls = cls === "ok" ? "status-ok" : (cls === "err" || cls === "warn") ? "status-err" : "";
    const wrap = document.createElement("div");
    wrap.className = `log-entry ${cls}`;
    wrap.dataset.tone = cls;
    wrap.innerHTML = `
      <div class="row1">
        <span class="who">${method.toUpperCase()} ${path}</span>
        <span class="tag ${tagCls}">${status || "ERR"}</span>
      </div>
      <div class="row2"><span class="meth">→</span> ${escape(message || statusLabel(status))}</div>
      <div class="row3">${t}</div>
    `;
    logEl.prepend(wrap);
    applyFilter();
  }
  function statusLabel(s) {
    return ({
      200: "OK", 201: "Created", 400: "Bad Request", 401: "Unauthorized",
      403: "Forbidden", 404: "Not Found", 405: "Method Not Allowed",
      409: "Conflict", 500: "Internal Server Error", 0: "network error",
    })[s] || `status ${s}`;
  }
  function applyFilter() {
    $$(".log-entry").forEach((e) => {
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
    else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
    let res, data, raw = "";
    try {
      res = await fetch(path, { method, headers, body: payload });
      raw = await res.text();
      try { data = JSON.parse(raw); } catch (_) { data = raw; }
    } catch (e) {
      logEntry(method, path, 0, "network error");
      throw e;
    }
    const msg = (data && data.error && data.error.message) ||
                (data && data.message) ||
                (data && data.token ? "token issued" : "") ||
                (data && data.matches ? `${data.matches.length} matches` : "") ||
                statusLabel(res.status);
    logEntry(method, path, res.status, msg);
    return { res, data };
  }

  // ---------- status polling ----------
  async function refreshStatus() {
    if (!state.token) return;
    const { res, data } = await api("GET", "/status");
    if (res.status === 401) { clearSession(); return; }
    if (res.status === 200 && data?.status) {
      const s = data.status;
      $("#m-uptime").textContent = s.uptime.toFixed(1) + "s";
      $("#m-success").textContent = s.processed.success;
      $("#m-fail").textContent = s.processed.fail;
      const h = $("#m-health"); const d = $("#d-health");
      h.textContent = s.health;
      h.className = "v " + (s.health === "ok" ? "ok" : "err");
      d.className = "dot " + (s.health === "ok" ? "ok" : "err");
      $("#m-api").textContent = "v" + s.api_version;
    }
  }

  // ---------- UI / auth ----------
  function setMode(mode) {
    state.mode = mode;
    $$(".mtab").forEach((b) => b.classList.toggle("is-active", b.dataset.mtab === mode));
    const btn = document.querySelector("#auth-form button[type=submit] [data-text]");
    btn.textContent = mode === "login" ? "LOG IN" : "REGISTER";
  }
  function showSession(user) {
    state.user = user;
    localStorage.setItem(LS_USER, user);
    $("#card-auth").hidden = true;
    $("#card-session").hidden = false;
    $("#who").textContent = user;
    refreshStatus();
  }
  function clearSession() {
    state.token = null;
    state.user = null;
    localStorage.removeItem(LS_TOKEN);
    localStorage.removeItem(LS_USER);
    $("#card-auth").hidden = false;
    $("#card-session").hidden = true;
    $("#preview").hidden = true;
    $("#results").innerHTML = "";
    ["m-uptime", "m-success", "m-fail", "m-health", "m-api"].forEach((id) => {
      const el = document.getElementById(id);
      el.textContent = "—";
      el.className = "v";
    });
    $("#d-health").className = "dot";
  }

  $$(".mtab").forEach((b) => b.addEventListener("click", () => setMode(b.dataset.mtab)));

  $("#auth-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const msg = $("#auth-msg");
    msg.textContent = "…"; msg.className = "hint";
    const fd = new FormData(e.target);
    const body = { username: fd.get("username"), password: fd.get("password") };
    const path = state.mode === "register" ? "/register" : "/login";
    const { res, data } = await api("POST", path, { body, auth: false });
    if (path === "/register" && res.status === 201) {
      msg.textContent = "Account created. Logging you in…"; msg.className = "hint ok";
      const r2 = await api("POST", "/login", { body, auth: false });
      if (r2.res.status === 200) {
        state.token = r2.data.token;
        localStorage.setItem(LS_TOKEN, state.token);
        showSession(body.username);
      } else {
        msg.textContent = (r2.data?.error?.message) || "Login failed.";
        msg.className = "hint error";
      }
      return;
    }
    if (path === "/login" && res.status === 200) {
      state.token = data.token;
      localStorage.setItem(LS_TOKEN, state.token);
      msg.textContent = "Signed in."; msg.className = "hint ok";
      showSession(body.username);
      return;
    }
    msg.textContent = (data?.error?.message) || `Error ${res.status}`;
    msg.className = "hint error";
  });

  $("#btn-logout").addEventListener("click", async () => {
    await api("POST", "/logout");
    clearSession();
  });

  // ---------- upload ----------
  const dz = $("#dropzone");
  const fileInput = $("#file");
  const preview = $("#preview");
  const previewImg = $("#preview-img");

  function loadFile(f) {
    if (!f) return;
    const okType = f.type === "image/png" || f.type === "image/jpeg";
    const okName = /\.(png|jpeg)$/i.test(f.name);
    if (!okType || !okName) {
      renderResults([], `Only .png / .jpeg accepted (got ${f.name})`, true);
      return;
    }
    state.file = f;
    preview.hidden = false;
    const reader = new FileReader();
    reader.onload = (e) => (previewImg.src = e.target.result);
    reader.readAsDataURL(f);
  }
  dz.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", (e) => loadFile(e.target.files[0]));
  ;["dragenter", "dragover"].forEach((ev) =>
    dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("dragging"); })
  );
  ;["dragleave", "drop"].forEach((ev) =>
    dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("dragging"); })
  );
  dz.addEventListener("drop", (e) => loadFile(e.dataTransfer.files[0]));

  $("#btn-classify").addEventListener("click", async () => {
    if (!state.file) return;
    if (!state.token) {
      renderResults([], "Log in first.", true);
      return;
    }
    const btn = $("#btn-classify");
    btn.disabled = true; const orig = btn.textContent; btn.textContent = "CLASSIFYING…";
    const fd = new FormData();
    fd.append("image", state.file, state.file.name);
    const { res, data } = await api("POST", "/classifier", { body: fd, isForm: true });
    btn.disabled = false; btn.textContent = orig;
    if (res.status === 200 && data?.matches) renderResults(data.matches, "");
    else renderResults([], (data?.error?.message) || `Error ${res.status}`, true);
    refreshStatus();
  });

  function renderResults(matches, msg, isErr = false) {
    const out = $("#results");
    if (!matches.length) {
      out.innerHTML = `<p class="hint ${isErr ? "error" : ""}">${escape(msg || "no matches")}</p>`;
      return;
    }
    out.innerHTML = matches
      .map((m) => {
        const pct = (m.score * 100).toFixed(1);
        return `
          <div class="row">
            <span class="name">${escape(m.name)}</span>
            <span class="score">${pct}%</span>
            <span class="bar"><i style="width:${pct}%"></i></span>
          </div>`;
      })
      .join("");
  }
  function escape(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }

  // ---------- log filter / clear ----------
  $("#log-filter").addEventListener("change", (e) => { state.filter = e.target.value; applyFilter(); });
  $("#btn-clear").addEventListener("click", () => (logEl.innerHTML = ""));

  // ---------- tab strip → scroll to section ----------
  $$(".tabs .tab").forEach((b) => {
    b.addEventListener("click", () => {
      $$(".tabs .tab").forEach((x) => x.classList.toggle("is-active", x === b));
      const t = b.dataset.tab;
      if (t === "account") $("#account").scrollIntoView({ behavior: "smooth", block: "start" });
      if (t === "classify") $("#classify").scrollIntoView({ behavior: "smooth", block: "start" });
      if (t === "log") $(".aside").scrollIntoView({ behavior: "smooth", block: "start" });
      if (t === "status") window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });

  // ---------- bootstrap ----------
  if (state.token && state.user) showSession(state.user);
  refreshStatus();
  setInterval(refreshStatus, 5000);
})();
