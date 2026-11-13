/* Twitch discovery dashboard: PUBLIC METADATA ONLY; no downloads or social posts. */
"use strict";
(function () {
  const node = id => document.getElementById(id);
  const panel = node("twitch-results");
  const state = node("twitch-state");
  const scan = node("twitch-refresh");
  const last = node("twitch-last");
  const mode = node("twitch-mode");
  const categories = node("twitch-categories");
  const heading = node("twitch-heading");
  let focused = false;
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
      panel.appendChild(make("p", focused ? "Nenhum clipe GTA VI encontrado. Verifique o OAuth e a categoria exata na Twitch." : "Nenhum clipe encontrado. Configure as credenciais da Twitch e faça a primeira busca.", "hint"));
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
        (item.game_name || "Categoria não identificada") + " · " +
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
      focused = meta.profile === "gta6_only";
      if(heading) heading.textContent = focused ?
        "GTA VI · monitoramento exclusivo" : "Twitch · melhores clipes de várias categorias";
      if(mode) mode.textContent = focused ?
        "Foco automático: somente Grand Theft Auto VI (a partir do lançamento)" :
        "Modo atual: categorias populares da Twitch até 19/11/2026; depois, somente GTA VI";
      if(categories) categories.textContent = focused ?
        "Categoria monitorada: Grand Theft Auto VI" :
        (meta.categories?.length ?
         "Categorias da última busca: " + meta.categories.join(" · ") :
         "A primeira busca descobrirá até 12 categorias populares, incluindo jogos e IRL.");
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
  window.addEventListener("gta:auth-updated",load);
  setInterval(load, 15000);
  load();
})();
