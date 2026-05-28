(() => {
  const LS_TOKEN = "ps_token";
  const LS_USER = "ps_user";
  const $ = (s) => document.querySelector(s);
  const log = $("#log");

  const state = {
    mode: "login",
    token: localStorage.getItem(LS_TOKEN) || null,
    user: localStorage.getItem(LS_USER) || null,
    file: null,
  };

  // ---------- HTTP log helpers ----------
  function logLine(method, path, status, extra = "") {
    const t = new Date().toISOString().split("T")[1].slice(0, 8);
    const cls = status >= 200 && status < 300 ? "ok" : "err";
    const line = document.createElement("span");
    line.innerHTML =
      `<span class="dim">${t}</span> ` +
      `<span class="meth">${method.toUpperCase()}</span> ${path} ` +
      `<span class="${cls}">${status}</span>` +
      (extra ? ` <span class="dim">${extra}</span>` : "") +
      "\n";
    log.appendChild(line);
    log.scrollTop = log.scrollHeight;
  }

  async function api(method, path, { body, isForm = false, auth = true } = {}) {
    const headers = {};
    if (auth && state.token) headers["Authorization"] = `Bearer ${state.token}`;
    let payload;
    if (isForm) {
      payload = body; // FormData
    } else if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(body);
    }
    let res, data, raw = "";
    try {
      res = await fetch(path, { method, headers, body: payload });
      raw = await res.text();
      try { data = JSON.parse(raw); } catch (_) { data = raw; }
    } catch (e) {
      logLine(method, path, 0, "network error");
      throw e;
    }
    const tag = (data && data.error && data.error.message) ? `· ${data.error.message}` : "";
    logLine(method, path, res.status, tag);
    return { res, data };
  }

  // ---------- status polling ----------
  async function refreshStatus() {
    if (!state.token) return;
    const { res, data } = await api("GET", "/status");
    if (res.status === 401) {
      // token expired or invalidated
      clearSession();
      return;
    }
    if (res.status === 200 && data?.status) {
      const s = data.status;
      $("#m-uptime").textContent = s.uptime.toFixed(1) + "s";
      $("#m-success").textContent = s.processed.success;
      $("#m-fail").textContent = s.processed.fail;
      const h = $("#m-health");
      h.textContent = s.health;
      h.className = s.health === "ok" ? "ok" : "err";
      $("#m-api").textContent = "v" + s.api_version;
    }
  }

  // ---------- UI / auth ----------
  function setMode(mode) {
    state.mode = mode;
    document.querySelectorAll(".tab").forEach((b) =>
      b.classList.toggle("is-active", b.dataset.tab === mode)
    );
    const btn = document.querySelector("#auth-form button[type=submit] [data-text]");
    btn.textContent = mode === "login" ? "Log in" : "Register";
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
    ["m-uptime", "m-success", "m-fail", "m-health", "m-api"].forEach(id => {
      const el = document.getElementById(id);
      el.textContent = "—";
      el.className = "";
    });
  }

  document.querySelectorAll(".tab").forEach((b) =>
    b.addEventListener("click", () => setMode(b.dataset.tab))
  );

  $("#auth-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const msg = $("#auth-msg");
    msg.textContent = "…";
    msg.className = "hint";
    const fd = new FormData(e.target);
    const body = { username: fd.get("username"), password: fd.get("password") };
    const path = state.mode === "register" ? "/register" : "/login";
    const { res, data } = await api("POST", path, { body, auth: false });
    if (path === "/register" && res.status === 201) {
      msg.textContent = "Account created. Logging you in…";
      msg.className = "hint ok";
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
      msg.textContent = "Signed in.";
      msg.className = "hint ok";
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
      flashResult([], `Only .png / .jpeg accepted (got ${f.name})`, true);
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
    const btn = $("#btn-classify");
    btn.disabled = true;
    btn.querySelector ? null : null;
    btn.textContent = "Classifying…";
    const fd = new FormData();
    fd.append("image", state.file, state.file.name);
    const { res, data } = await api("POST", "/classifier", { body: fd, isForm: true });
    btn.disabled = false;
    btn.textContent = "Classify";
    if (res.status === 200 && data?.matches) {
      flashResult(data.matches, "");
    } else {
      flashResult([], (data?.error?.message) || `Error ${res.status}`, true);
    }
    refreshStatus();
  });

  function flashResult(matches, msg, isErr = false) {
    const out = $("#results");
    if (!matches.length) {
      out.innerHTML = `<p class="hint ${isErr ? "error" : ""}">${msg || "no matches"}</p>`;
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

  $("#btn-clear").addEventListener("click", () => (log.innerHTML = ""));

  // ---------- bootstrap ----------
  if (state.token && state.user) {
    showSession(state.user);
  }
  setInterval(refreshStatus, 5000);
})();
