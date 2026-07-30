class TelethonkPanel extends HTMLElement {
  set hass(value) {
    this._hass = value;
    if (!this._loaded) {
      this._loaded = true;
      this._renderShell();
      this._subscribe();
      this._refresh();
    }
  }

  set panel(value) {
    this._panel = value;
  }

  connectedCallback() {
    if (this._loaded) this._refresh();
  }

  disconnectedCallback() {
    if (this._unsubscribe) {
      this._unsubscribe();
      this._unsubscribe = undefined;
    }
  }

  _renderShell() {
    this.innerHTML = `
      <style>
        :host { display: block; min-height: 100vh; background: var(--primary-background-color); color: var(--primary-text-color); }
        .topbar { height: 64px; display: flex; align-items: center; gap: 12px; padding: 0 18px; background: var(--app-header-background-color, var(--primary-color)); color: var(--app-header-text-color, white); box-sizing: border-box; }
        .menu { appearance: none; border: 0; background: transparent; color: inherit; font-size: 25px; cursor: pointer; padding: 8px; }
        .title { font-size: 20px; font-weight: 500; flex: 1; }
        .tabs { display: flex; gap: 4px; padding: 14px max(16px, calc((100% - 1120px) / 2)); border-bottom: 1px solid var(--divider-color); }
        .tab { border: 0; border-radius: 18px; padding: 9px 16px; color: var(--primary-text-color); background: transparent; cursor: pointer; }
        .tab.active { color: var(--text-primary-color, white); background: var(--primary-color); }
        main { max-width: 1120px; margin: 0 auto; padding: 20px 16px 60px; box-sizing: border-box; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(290px, 1fr)); gap: 16px; }
        .card { background: var(--card-background-color); border-radius: var(--ha-card-border-radius, 12px); box-shadow: var(--ha-card-box-shadow); padding: 20px; }
        h2, h3 { margin: 0 0 14px; }
        .row { display: flex; justify-content: space-between; gap: 18px; padding: 7px 0; }
        .muted { color: var(--secondary-text-color); }
        .toggle { position: relative; width: 48px; height: 28px; border-radius: 16px; border: 0; background: var(--switch-unchecked-track-color, #777); cursor: pointer; }
        .toggle::after { content: ""; position: absolute; width: 22px; height: 22px; left: 3px; top: 3px; border-radius: 50%; background: white; transition: transform .15s; }
        .toggle.on { background: var(--switch-checked-color, var(--primary-color)); }
        .toggle.on::after { transform: translateX(20px); }
        table { width: 100%; border-collapse: collapse; }
        th, td { text-align: left; padding: 11px 8px; border-bottom: 1px solid var(--divider-color); vertical-align: top; }
        .status { text-transform: capitalize; white-space: nowrap; }
        .transcript { max-width: 520px; white-space: pre-wrap; }
        .empty, .error { padding: 30px; text-align: center; color: var(--secondary-text-color); }
        @media (max-width: 720px) {
          .topbar { height: 56px; padding: 0 8px; }
          main { padding: 14px 10px 40px; }
          .tabs { padding: 10px; }
          table, thead, tbody, tr, th, td { display: block; }
          thead { display: none; }
          tr { padding: 12px 0; border-bottom: 1px solid var(--divider-color); }
          td { border: 0; padding: 4px 0; }
          td::before { content: attr(data-label) ": "; color: var(--secondary-text-color); }
        }
      </style>
      <div class="topbar">
        <button class="menu" aria-label="Open menu">☰</button>
        <div class="title">Receptionist</div>
        <button class="menu refresh" aria-label="Refresh">↻</button>
      </div>
      <nav class="tabs">
        <button class="tab active" data-tab="overview">Overview</button>
        <button class="tab" data-tab="interactions">Interactions</button>
      </nav>
      <main><div class="empty">Loading receptionist…</div></main>
    `;
    this.querySelector(".menu").addEventListener("click", () =>
      this.dispatchEvent(new CustomEvent("hass-toggle-menu", { bubbles: true, composed: true }))
    );
    this.querySelector(".refresh").addEventListener("click", () => this._refresh());
    this.querySelectorAll(".tab").forEach((button) =>
      button.addEventListener("click", () => {
        this._tab = button.dataset.tab;
        this.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("active", tab === button));
        this._renderContent();
      })
    );
    this._tab = "overview";
  }

  async _subscribe() {
    this._unsubscribe = await this._hass.connection.subscribeEvents(
      () => this._refresh(),
      "telethonk_updated"
    );
  }

  async _refresh() {
    if (!this._hass) return;
    try {
      const [overview, interactions] = await Promise.all([
        this._hass.callWS({ type: "telethonk/overview" }),
        this._hass.callWS({ type: "telethonk/interactions", limit: 200 }),
      ]);
      this._profiles = overview.profiles || [];
      this._interactions = interactions || [];
      this._error = undefined;
    } catch (error) {
      this._error = error?.message || String(error);
    }
    this._renderContent();
  }

  _renderContent() {
    const main = this.querySelector("main");
    if (!main) return;
    if (this._error) {
      main.innerHTML = `<div class="card error">${this._escape(this._error)}</div>`;
      return;
    }
    if (this._tab === "interactions") {
      this._renderInteractions(main);
    } else {
      this._renderOverview(main);
    }
  }

  _renderOverview(main) {
    if (!this._profiles?.length) {
      main.innerHTML = `<div class="card empty">No receptionist profiles are loaded.</div>`;
      return;
    }
    main.innerHTML = `<div class="grid">${this._profiles.map((profile) => `
      <section class="card">
        <h2>${this._escape(profile.title)}</h2>
        <div class="row"><span>Auto-unlock</span><button class="toggle ${profile.auto_unlock ? "on" : ""}" data-entry="${profile.entry_id}" data-enabled="${!profile.auto_unlock}" aria-pressed="${profile.auto_unlock}"></button></div>
        <div class="row"><span class="muted">DID</span><span>${this._escape(profile.did)}</span></div>
        <div class="row"><span class="muted">Buzzer</span><span>${this._escape(profile.buzzer_number)}</span></div>
        <div class="row"><span class="muted">Decision timeout</span><span>${profile.response_timeout}s</span></div>
        <div class="row"><span class="muted">Active calls</span><span>${profile.active_calls}</span></div>
        <div class="row"><span class="muted">Notifications</span><span>${this._escape(profile.notification_recipients.join(", ") || "None")}</span></div>
        <div class="row"><span class="muted">Fallback phones</span><span>${this._escape(profile.fallback_numbers.join(", ") || "None")}</span></div>
      </section>
    `).join("")}</div>`;
    main.querySelectorAll(".toggle").forEach((button) =>
      button.addEventListener("click", async () => {
        button.disabled = true;
        try {
          await this._hass.callWS({
            type: "telethonk/set_auto_unlock",
            entry_id: button.dataset.entry,
            enabled: button.dataset.enabled === "true",
          });
          await this._refresh();
        } finally {
          button.disabled = false;
        }
      })
    );
  }

  _renderInteractions(main) {
    if (!this._interactions?.length) {
      main.innerHTML = `<div class="card empty">No receptionist interactions have been recorded.</div>`;
      return;
    }
    main.innerHTML = `<section class="card"><h2>Interactions</h2><table>
      <thead><tr><th>Time</th><th>Type</th><th>Caller</th><th>Transcript</th><th>Status / action</th></tr></thead>
      <tbody>${this._interactions.map((item) => `
        <tr>
          <td data-label="Time">${this._escape(this._formatDate(item.created_at))}</td>
          <td data-label="Type">${this._escape(item.kind || "")}</td>
          <td data-label="Caller">${this._escape(item.from || "")}</td>
          <td data-label="Transcript" class="transcript">${this._escape(item.transcript || "—")}</td>
          <td data-label="Status" class="status">${this._escape(item.status || "")}${item.action ? `<div class="muted">${this._escape(item.action)}</div>` : ""}${item.detail ? `<div class="muted">${this._escape(item.detail)}</div>` : ""}</td>
        </tr>`).join("")}</tbody>
    </table></section>`;
  }

  _formatDate(value) {
    try { return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)); }
    catch (_) { return value || ""; }
  }

  _escape(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
    })[char]);
  }
}

if (!customElements.get("telethonk-panel")) {
  customElements.define("telethonk-panel", TelethonkPanel);
}

