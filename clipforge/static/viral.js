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
      toast(remove ? "Autorização removida: " + row.name : row.name + " autorizado. O app vai baixar e editar os clipes dele automaticamente.");
    } catch (e) { toast("Autorização: " + e.message); }
    await load();
  }

  async function load() {
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
        if (row.authorized) {
          li.appendChild(make("span", "✓ Autorizado ", "ok"));
          const undo = make("button", "Remover", "btn secondary"); undo.type = "button";
          undo.addEventListener("click", () => authorize(row, true));
          li.appendChild(undo);
        } else {
          const ok = make("button", "Ele autorizou", "btn secondary"); ok.type = "button";
          ok.addEventListener("click", () => {
            pending = row; evidence.value = "";
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
          Math.round(c.duration) + "s · nota " + c.score + (c.authorized ? " · ✓ será editado" : " · aguardando permissão"), "meta"));
        clips.appendChild(li);
      });
    } catch (e) { state.textContent = "Radar viral: " + e.message; }
  }

  form.addEventListener("submit", () => { if (pending) authorize(pending, false); pending = null; });
  node("viral-auth-cancel").addEventListener("click", () => { pending = null; modal.close(); });
  refreshButton.addEventListener("click", load);
  if (ptOnly) ptOnly.addEventListener("change", load);
  window.addEventListener("gta:auth-updated", load);
  setInterval(load, 60000);
  load();
})();
