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
      panel.appendChild(make("p", "Nenhum clipe encontrado. Conecte a Twitch e faça a primeira busca nas categorias em alta.", "hint"));
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
        ((item.language || "").toLowerCase().startsWith("pt") ? "PT-BR · " : "") +
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
      const [meta, listing, live] = await Promise.all([
        api("/api/twitch/status"), api("/api/twitch/candidates"), api("/api/twitch/streamers")
      ]);
      state.textContent = meta.configured ?
        (meta.auto_monitoring ? "Monitoramento ativo" : "Configurado · manual") :
        "OAuth não configurado";
      state.className = "tag " + (meta.configured ? "good" : "muted");
      const gta6 = meta.profile === "gta6_only";
      const gta5 = meta.profile === "gta5_only";
      if(heading) heading.textContent = gta6 ? "Twitch · prioridade GTA VI" : gta5 ? "Twitch · GTA V (modo manual)" : "Twitch · categorias em alta";
      if(mode) mode.textContent = gta6 ? "Categoria GTA VI selecionada. Português tem prioridade no ranking." : gta5 ? "Override GTA V ativo. A configuração permite intervenção manual." : "Até 12 categorias configuráveis; prioridade GTA VI na data de lançamento configurada.";
      if(categories) categories.textContent = (meta.categories?.length ? "Categorias recentes: " + meta.categories.join(" · ") : "Aguardando consulta de categorias.") + " · Streamers: " + (meta.monitored_streamers||0) + " · Ao vivo: " + (meta.live_streams||0);
      last.textContent = "Última busca: " + relativeTime(meta.last_sync) +
        (meta.last_error ? " · Erro: " + meta.last_error : "");
      const streamers=node("twitch-streamers");
      if(streamers){streamers.replaceChildren();for(const item of live.streamers||[]){const row=make("p",(item.name||item.broadcaster_id)+" · "+(item.is_live?"Ao vivo: "+item.title:"Offline na última consulta")+" · "+relativeTime(item.checked_at),"hint");streamers.append(row);}}
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
