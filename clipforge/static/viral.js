/* Radar viral BR: métricas públicas da Twitch; nenhuma mídia é baixada aqui. */
"use strict";
(function () {
  const node = id => document.getElementById(id);
  const state = node("viral-state"), streamers = node("viral-streamers"), clips = node("viral-clips");
  const refreshButton = node("viral-refresh"), ptOnly = node("viral-pt");
  const modal = node("viral-auth-modal"), form = node("viral-auth-form"), evidence = node("viral-auth-evidence");
  if (!state || !streamers || !clips) return;
  let pending = null;

  function make(tag, text, className) {
    const n = document.createElement(tag);
    if (text !== undefined) n.textContent = text;
    if (className) n.className = className;
    return n;
  }
  function safeLink(raw, label) {
    try {
      const url = new URL(raw);
      if (url.protocol === "https:" && ["clips.twitch.tv", "www.twitch.tv", "twitch.tv"].includes(url.hostname)) {
        const a = make("a", label);
        a.href = url.href; a.target = "_blank"; a.rel = "noopener noreferrer";
        return a;
      }
    } catch (_) { /* link inválido */ }
    return make("span", label);
  }
  const fmt = n => Number(n || 0).toLocaleString("pt-BR");

  async function authorize(row, remove) {
    try {
      const body = remove ? { action: "remove", broadcaster_id: row.broadcaster_id }
        : { broadcaster_id: row.broadcaster_id, creator: row.name, rights_status: "permission_granted", evidence: evidence.value };
      await api("/api/twitch/sources", "POST", false, body);
      if (remove) toast("Autorização removida: " + row.name);
      else {
        // A Twitch só entrega o arquivo oficial ao dono/editor do canal.
        const mode = await downloadMode();
        toast(row.name + " autorizado. " + (mode.public ? "O app vai baixar e editar os clipes dele automaticamente."
          : mode.editor ? "Downloads saem só se você for editor do canal dele na Twitch (ou ative o download público)."
          : "Para baixar: peça para ele te adicionar como editor na Twitch ou ative o download público."));
      }
    } catch (e) { toast("Autorização: " + e.message); }
    await load();
  }

  async function downloadMode() {
    try {
      const auto = (await api("/api/twitch/status")).auto_pipeline || {};
      return { public: !!auto.public_download, editor: !!auto.editor_grant_present };
    } catch (_) { return { public: false, editor: false }; }
  }
  const modeLine = node("viral-download-mode"), publicToggle = node("viral-public-toggle");
  async function showDownloadMode() {
    if (!modeLine) return;
    const mode = await downloadMode();
    modeLine.textContent = mode.public ? "Download: clipes públicos dos autorizados (yt-dlp, não oficial)" +
        (mode.editor ? " + API oficial quando você é editor." : ".")
      : mode.editor ? "Download: só API oficial. Funciona apenas nos canais em que você é editor."
      : "Download desligado para outros canais: a Twitch só libera o arquivo ao dono/editor do canal.";
    const bridge = window.pywebview && window.pywebview.api;
    if (publicToggle) {
      publicToggle.hidden = !(bridge && typeof bridge.set_twitch_public_download === "function");
      publicToggle.textContent = mode.public ? "Desativar download público" : "Ativar download público (não oficial, risco seu)";
      publicToggle.dataset.on = mode.public ? "1" : "0";
    }
  }
  if (publicToggle) publicToggle.addEventListener("click", async () => {
    const bridge = window.pywebview && window.pywebview.api;
    if (!bridge) return;
    publicToggle.disabled = true;
    try {
      const turnOn = publicToggle.dataset.on !== "1";
      const r = await bridge.set_twitch_public_download(turnOn);
      if (!r || !r.ok) toast((r && r.error) || "Não foi possível salvar.");
      else toast(turnOn ? "Download público ligado: só de streamers autorizados. Pode violar os Termos da Twitch."
        : "Download público desligado.");
    } catch (e) { toast("Twitch: " + e.message); }
    finally { publicToggle.disabled = false; await showDownloadMode(); }
  });
  window.addEventListener("pywebviewready", showDownloadMode);

  async function load() {
    showDownloadMode();
    try {
      const data = await api("/api/twitch/viral?pt=" + (ptOnly && !ptOnly.checked ? "0" : "1"));
      state.textContent = (data.scanned ? data.scanned + " clipes analisados · " : "Nenhum clipe catalogado ainda (busque na Twitch). · ") +
        data.clips.length + " com potencial viral · " + data.authorized_count + " streamer(s) autorizado(s) · foco: " + data.focus_game;
      streamers.replaceChildren();
      if (!data.streamers.length) streamers.appendChild(make("li", "Sem streamers ainda.", "hint"));
      data.streamers.forEach(row => {
        const li = make("li");
        li.appendChild(safeLink(row.twitch_url, row.name || row.broadcaster_id));
        li.appendChild(make("span", row.viral_clips + " clipe(s) virais · " + row.clips + " clipes · " + fmt(row.total_views) + " views", "meta"));
        const policy = row.policy || {};
        if (!row.authorized && policy.status === "allowed")
          li.appendChild(make("span", "Bio libera cortes: \u201c" + policy.snippet + "\u201d", "meta ok"));
        else if (!row.authorized && policy.status === "restricted")
          li.appendChild(make("span", "Bio tem restrição a cortes: \u201c" + policy.snippet + "\u201d", "meta bad"));
        else if (!row.authorized && policy.status === "unknown")
          li.appendChild(make("span", "Bio não fala de cortes; peça permissão.", "meta"));
        if (row.authorized) {
          li.appendChild(make("span", "✓ Autorizado ", "ok"));
          const undo = make("button", "Remover", "btn secondary"); undo.type = "button";
          undo.addEventListener("click", () => authorize(row, true));
          li.appendChild(undo);
        } else {
          const allowed = policy.status === "allowed";
          const ok = make("button", allowed ? "Confirmar (bio libera)" : "Ele autorizou", allowed ? "btn primary" : "btn secondary"); ok.type = "button";
          ok.addEventListener("click", () => {
            pending = row;
            evidence.value = allowed ? ("Bio pública da Twitch (lida em " + new Date(policy.checked_at).toLocaleDateString("pt-BR") + "): " + policy.snippet).slice(0, 500) : "";
            node("viral-auth-title").textContent = "Autorizar " + (row.name || row.broadcaster_id);
            modal.showModal();
          });
          li.appendChild(ok);
        }
        streamers.appendChild(li);
      });
      clips.replaceChildren();
      if (!data.clips.length) clips.appendChild(make("li", "Nenhum clipe passou no filtro viral ainda.", "hint"));
      data.clips.forEach(c => {
        const li = make("li");
        li.appendChild(safeLink(c.url, c.title || "Clipe"));
        li.appendChild(make("span", (c.creator_name || "") + " · " + fmt(c.view_count) + " views · " +
          Math.round(c.duration) + "s · nota " + c.score + (c.authorized ? " · ✓ autorizado" : " · aguardando permissão"), "meta"));
        clips.appendChild(li);
      });
    } catch (e) { state.textContent = "Radar viral: " + e.message; }
  }

  form.addEventListener("submit", () => { if (pending) authorize(pending, false); pending = null; });
  node("viral-auth-cancel").addEventListener("click", () => { pending = null; modal.close(); });
  refreshButton.addEventListener("click", load);
  const policyButton = node("viral-policies");
  if (policyButton) policyButton.addEventListener("click", async () => {
    policyButton.disabled = true;
    try {
      const r = await api("/api/twitch/policies", "POST");
      toast(r.checked + " bio(s) lidas · " + r.allowed + " liberam cortes. Confira e confirme cada uma.");
    } catch (e) { toast("Bios: " + e.message); }
    finally { policyButton.disabled = false; }
    await load();
  });
  if (ptOnly) ptOnly.addEventListener("change", load);
  window.addEventListener("gta:auth-updated", load);
  setInterval(load, 60000);
  load();
})();
