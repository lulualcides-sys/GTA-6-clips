/* Twitch discovery dashboard: PUBLIC METADATA ONLY; no downloads or social posts. */
"use strict";
(function () {
  const node = id => document.getElementById(id);
  const panel = node("twitch-results");
  const state = node("twitch-state");
  const scan = node("twitch-refresh");
  const last = node("twitch-last");
  if (!panel || !state || !scan) return;

  function make(tag, text, className) {
    const n = document.createElement(tag);
    n.textContent = text;
    if (className) n.className = className;
    return n;
  }

  function relativeTime(value) {
    if (!value) return "Sem atualização";
    const when = new Date(value);
    if (isNaN(when.getTime())) return "Não disponível";
    return when.toLocaleString("pt-BR");
  }

  function isTwitchUrl(raw) {
    try {
      const url = new URL(raw);
      return url.protocol === "https:" &&
        ["clips.twitch.tv","www.twitch.tv","twitch.tv"].includes(url.hostname);
    } catch (_) { return false; }
  }

  function displayCandidates(items) {
    panel.replaceChildren();
    if (!items.length) {
      panel.appendChild(make("p","Nenhum clipe encontrado. Configure o OAuth da Twitch e verifique a categoria GTA VI.","hint"));
      return;
    }
    for (const item of items.slice(0, 40)) {
      const card = make("article","","candidate");
      const left = make("div","","candidate-main");
      const tag = make("span",item.consent_flag === "declared_permission" ?
        "Permissão declarada" : "Direitos não verificados",
        "candidate-flag " + (item.consent_flag === "declared_permission" ? "yes" : "no"));
      const title = make("strong",item.title || "Clipe sem título");
      const meta = make("small",
        (item.creator_name || "Canal desconhecido") + " · " +
        Number(item.view_count || 0).toLocaleString("pt-BR") + " visualizações · " +
        Math.round(Number(item.duration || 0)) + "s");
      left.append(tag,title,meta);
      card.appendChild(left);
      const side = make("div","","candidate-side");
      side.appendChild(make("span",String(item.score ?? 0) + "/100","score"));
      if (isTwitchUrl(item.url)) {
        const a = make("a","Ver na Twitch ↗","candidate-open");
        a.href = item.url;
        a.rel = "noopener noreferrer";
        a.target = "_blank";
        side.appendChild(a);
      }
      card.appendChild(side);
      panel.appendChild(card);
    }
  }

  async function load() {
    try {
      const [meta, listing] = await Promise.all([
        api("/api/twitch/status"), api("/api/twitch/candidates")
      ]);
      state.textContent = meta.configured ?
        (meta.auto_monitoring ? "Monitoramento ativo" : "Configurado · manual") :
        "OAuth não configurado";
      state.className = "tag " + (meta.configured ? "good" : "muted");
      last.textContent = "Última busca: " + relativeTime(meta.last_sync) +
        (meta.last_error ? " · Erro: " + meta.last_error : "");
      displayCandidates(listing.candidates || []);
    } catch (err) {
      state.textContent = "Monitor indisponível";
      state.className = "tag bad";
      last.textContent = err.message;
    }
  }

  scan.addEventListener("click", async () => {
    scan.disabled = true;
    scan.textContent = "Consultando API...";
    try {
      const result = await api("/api/twitch/refresh","POST");
      if (typeof toast === "function")
        toast("Twitch: " + result.processed + " clipe(s) catalogados. Nenhum vídeo foi baixado.");
    } catch (err) {
      if (typeof toast === "function") toast("Twitch: " + err.message);
    } finally {
      scan.disabled = false;
      scan.textContent = "↻ Buscar clipes";
      await load();
    }
  });
  setInterval(load, 15000);
  load();
})();
