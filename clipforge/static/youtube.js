/* Radar YouTube BR: metadados públicos pela Data API oficial; download só de canais autorizados. */
"use strict";
(function () {
  const node = id => document.getElementById(id);
  const state = node("youtube-state"), pipeline = node("youtube-pipeline");
  const channels = node("youtube-channels"), videos = node("youtube-videos");
  const refreshButton = node("youtube-refresh"), runButton = node("youtube-run"), ptOnly = node("youtube-pt");
  const authModal = node("youtube-auth-modal"), authForm = node("youtube-auth-form"), evidence = node("youtube-auth-evidence");
  if (!state || !channels || !videos) return;
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
      if (url.protocol === "https:" && ["www.youtube.com", "youtube.com"].includes(url.hostname)) {
        const a = make("a", label);
        a.href = url.href; a.target = "_blank"; a.rel = "noopener noreferrer";
        return a;
      }
    } catch (_) { /* link inválido */ }
    return make("span", label);
  }
  const fmt = n => n === null || n === undefined ? "oculto" : Number(n).toLocaleString("pt-BR");
  const minutes = s => Math.round(Number(s || 0) / 60) + " min";

  async function authorize(row, remove) {
    try {
      const body = remove ? { action: "remove", channel_id: row.channel_id }
        : { channel_id: row.channel_id, creator: row.name, rights_status: "permission_granted", evidence: evidence.value };
      await api("/api/youtube/sources", "POST", false, body);
      if (remove) toast("Autorização removida: " + row.name);
      else {
        const st = await api("/api/youtube/status");
        toast(row.name + " autorizado. " + (st.enabled ? "O app vai baixar e editar os vídeos novos dele."
          : "Para baixar, ligue o download em Conectar YouTube."));
      }
    } catch (e) { toast("Autorização: " + e.message); }
    await load();
  }

  function describePipeline(st) {
    if (!st.api_key_present) return "Pipeline YouTube: conecte a chave da API para começar.";
    if (!st.enabled) return "Pipeline YouTube: download desligado. Só o radar funciona (ligue em Conectar YouTube).";
    const parts = [st.authorized_channels + " canal(is) autorizado(s)", "até " + st.batch + " vídeo(s) por rodada",
      st.js_runtime ? "Deno ok" : "sem Deno (YouTube pode falhar)",
      st.cookies_browser ? "cookies: " + st.cookies_browser : "sem cookies (YouTube pode pedir login)",
      st.downloaded + " baixado(s)"];
    let text = "Pipeline YouTube: " + (st.ready ? "pronto · " : "aguardando · ") + parts.join(" · ");
    if (st.running) text += " · baixando agora";
    if (st.last_error) text += " · último aviso: " + st.last_error;
    return text;
  }

  async function load() {
    try {
      const [data, st] = await Promise.all([
        api("/api/youtube/radar?pt=" + (ptOnly && ptOnly.checked ? "1" : "0")),
        api("/api/youtube/status")]);
      pipeline.textContent = describePipeline(st);
      if (runButton) runButton.disabled = !st.ready || st.running;
      const when = data.updated_at ? new Date(data.updated_at).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) : "nunca";
      state.textContent = (data.error ? data.error + " · " : "") + data.channels.length + " YouTuber(s) com " +
        (data.min_subscribers ? "≥ " + fmt(data.min_subscribers) + " inscritos" : "qualquer porte") + " · " +
        data.videos.length + " vídeo(s) · " + data.authorized_count + " autorizado(s) · " +
        (data.gta6_mode ? "foco GTA VI" : "jogos em alta no Brasil") + " · atualizado " + when;
      channels.replaceChildren();
      if (!data.channels.length) channels.appendChild(make("li", data.configured ? "Nenhum YouTuber grande em alta agora." : "Conecte o YouTube para ver os canais.", "hint"));
      data.channels.forEach(row => {
        const li = make("li");
        li.appendChild(safeLink(row.url, row.name || row.channel_id));
        li.appendChild(make("span", fmt(row.subscribers) + " inscritos · " + row.trending_videos + " vídeo(s) em alta · " +
          fmt(row.total_views) + " views", "meta"));
        const policy = row.policy || {};
        const where = policy.where === "canal" ? "Descrição do canal" : "Descrição de vídeo";
        if (!row.authorized && policy.status === "allowed")
          li.appendChild(make("span", where + " libera cortes: “" + policy.snippet + "”", "meta ok"));
        else if (!row.authorized && policy.status === "restricted")
          li.appendChild(make("span", where + " restringe cortes: “" + policy.snippet + "”", "meta bad"));
        else if (!row.authorized)
          li.appendChild(make("span", "Não fala de cortes; peça permissão antes.", "meta"));
        if (row.authorized) {
          li.appendChild(make("span", "✓ Autorizado ", "ok"));
          const undo = make("button", "Remover", "btn secondary"); undo.type = "button";
          undo.addEventListener("click", () => authorize(row, true));
          li.appendChild(undo);
        } else if (policy.status !== "restricted") {
          const allowed = policy.status === "allowed";
          const ok = make("button", allowed ? "Confirmar (descrição libera)" : "Ele autorizou", allowed ? "btn primary" : "btn secondary");
          ok.type = "button";
          ok.addEventListener("click", () => {
            pending = row;
            evidence.value = allowed ? (where + " no YouTube (lida em " + new Date(data.updated_at || Date.now()).toLocaleDateString("pt-BR") + "): " + policy.snippet).slice(0, 500) : "";
            node("youtube-auth-title").textContent = "Autorizar " + (row.name || row.channel_id);
            authModal.showModal();
          });
          li.appendChild(ok);
        }
        channels.appendChild(li);
      });
      videos.replaceChildren();
      if (!data.videos.length) videos.appendChild(make("li", "Nenhum vídeo em alta catalogado ainda.", "hint"));
      data.videos.forEach(v => {
        const li = make("li");
        li.appendChild(safeLink(v.url, v.title || "Vídeo"));
        li.appendChild(make("span", v.channel_title + " · " + fmt(v.views) + " views · " + fmt(v.views_per_hour) + "/h · " +
          minutes(v.duration) + " · nota " + v.score + (v.authorized ? (v.autoclip_ok ? " · ✓ autorizado" : " · autorizado, fora do filtro (live/duração/jogo)") : " · aguardando permissão"), "meta"));
        videos.appendChild(li);
      });
    } catch (e) { state.textContent = "Radar YouTube: " + e.message; }
  }

  authForm.addEventListener("submit", () => { if (pending) authorize(pending, false); pending = null; });
  node("youtube-auth-cancel").addEventListener("click", () => { pending = null; authModal.close(); });
  refreshButton.addEventListener("click", async () => {
    refreshButton.disabled = true;
    try { await api("/api/youtube/radar/refresh", "POST"); } catch (e) { toast("YouTube: " + e.message); }
    finally { refreshButton.disabled = false; }
    await load();
  });
  if (runButton) runButton.addEventListener("click", async () => {
    runButton.disabled = true;
    try { await api("/api/youtube/run", "POST"); toast("Baixando os melhores vídeos novos dos canais autorizados. O AutoClip edita em seguida."); }
    catch (e) { toast("YouTube: " + e.message); }
    await load();
  });
  if (ptOnly) ptOnly.addEventListener("change", load);

  // Conectar YouTube: somente no app Windows (a chave nunca passa pela API HTTP).
  function mountDesktop() {
    const bridge = window.pywebview && window.pywebview.api;
    const button = node("youtube-connect"), modal = node("youtube-settings-modal"), form = node("youtube-settings-form");
    if (!bridge || !button || !modal || !button.hidden || typeof bridge.save_youtube_settings !== "function") return;
    button.hidden = false;
    button.addEventListener("click", async () => {
      try {
        const st = await api("/api/youtube/status");
        node("youtube-public-download").checked = !!st.enabled;
        node("youtube-cookies").value = st.cookies_browser || "";
      } catch (_) { /* mantém valores do formulário */ }
      modal.showModal();
    });
    node("youtube-settings-cancel").addEventListener("click", () => { node("youtube-api-key").value = ""; modal.close(); });
    form.addEventListener("submit", async event => {
      event.preventDefault();
      const save = node("youtube-settings-save");
      if (save.disabled) return;
      save.disabled = true;
      try {
        const r = await bridge.save_youtube_settings(node("youtube-api-key").value.trim(),
          node("youtube-public-download").checked, node("youtube-cookies").value);
        if (!r || !r.ok) { toast((r && r.error) || "Não foi possível salvar o YouTube."); return; }
        node("youtube-api-key").value = "";
        modal.close();
        toast(r.public_download ? "YouTube conectado. Download dos canais autorizados ligado." : "YouTube conectado (só radar; download desligado).");
        await api("/api/youtube/radar/refresh", "POST").catch(() => null);
      } catch (e) { toast("YouTube: " + e.message); }
      finally { save.disabled = false; await load(); }
    });
  }
  window.addEventListener("pywebviewready", mountDesktop);
  mountDesktop();
  window.addEventListener("gta:auth-updated", load);
  window.addEventListener("gta:view", e => { if (e.detail === "youtube") load(); });
  setInterval(() => { if (document.body.dataset.view === "youtube") load(); }, 60000);
  load();
})();
