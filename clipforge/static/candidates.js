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

  function displayCandidates(items, minScore=0) {
    panel.replaceChildren();
    const candidates=minScore>0 ? items.filter(item=>
      Number(item.score||0)>=minScore && Number(item.duration||0)>=14 &&
      Number(item.duration||0)<=70
    ) : items;
    if (!candidates.length) {
      panel.appendChild(make("p", items.length ?
        "Nenhum candidato atingiu o filtro de qualidade por metadados. Aguarde novos clipes." :
        "Nenhum clipe encontrado. Confira a conexão e a categoria da Twitch.", "hint"));
      return;
    }
    panel.appendChild(make("p", "Pré-triagem: "+candidates.length+" de "+items.length+
      " candidatos pontuados. A nota não é uma avaliação do vídeo; somente AutoClip analisa as cenas.", "hint"));
    for (const item of candidates.slice(0, 40)) {
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
      const healthy = Boolean(meta.configured && meta.last_sync && !meta.last_error);
      state.textContent = !meta.configured ? "Twitch não conectada" :
        meta.last_error ? "Twitch · erro na busca" :
        healthy ? (meta.auto_monitoring ? "Twitch conectada · monitorando" : "Twitch conectada · manual") :
        (meta.auto_monitoring ? "Twitch configurada · buscando" : "Twitch configurada · manual");
      state.className = "tag " + (meta.last_error ? "bad" : meta.configured ? "good" : "muted");
      const desktopState = node("desktop-twitch-status");
      if (desktopState) {
        desktopState.textContent = state.textContent;
        desktopState.className = state.className;
      }
      const desktopButton = node("desktop-twitch-connect");
      if (desktopButton) desktopButton.textContent = meta.configured ?
        "Atualizar Twitch" : "Conectar Twitch";
      const gta6 = meta.profile === "gta6_only";
      const gta5 = meta.profile === "gta5_only";
      if(heading) heading.textContent = gta6 ? "Twitch · prioridade GTA VI" : gta5 ? "Twitch · GTA V (modo manual)" : "Twitch · categorias em alta";
      if(mode) mode.textContent = gta6 ? "Categoria GTA VI selecionada. Português tem prioridade no ranking." : gta5 ? "Override GTA V ativo. A configuração permite intervenção manual." : "Até 12 categorias configuráveis; prioridade GTA VI na data de lançamento configurada.";
      const pipe=node("twitch-auto-pipeline");
      if(pipe){
        const p=meta.auto_pipeline||{};
        const reviewed=Number(p.last_candidates_scanned||0);
        const eligible=Number(p.last_quality_passed||0);
        const stats=reviewed ? " · Triagem: "+eligible+"/"+reviewed+
          " candidatos com sinais positivos" : "";
        pipe.textContent = !p.enabled ? "Pipeline automático desativado." :
          !p.editor_grant_present ? "Busca ativa · downloads bloqueados: clique em Autorizar downloads Twitch. Client ID não basta." :
          !p.authorized_broadcasters ? "Downloads autorizados apenas para canais próprios ou criadores registrados com permissão." :
          p.last_error ? "Fila automática: "+p.last_error :
          p.ready ? "Pipeline automático ligado · "+Number(p.downloaded||0)+" mídia(s) obtida(s) · AutoClip edita e envia para revisão." :
          "AutoClip indisponível ou sem modelo de IA. Verifique o status na biblioteca.";
        pipe.textContent += stats;
      }
      if(categories) categories.textContent = (meta.categories?.length ? "Categorias recentes: " + meta.categories.join(" · ") : "Aguardando consulta de categorias.") + " · Streamers: " + (meta.monitored_streamers||0) + " · Ao vivo: " + (meta.live_streams||0);
      last.textContent = "Última busca: " + relativeTime(meta.last_sync) +
        (meta.last_error ? " · Erro: " + meta.last_error : "");
      const streamers=node("twitch-streamers");
      if(streamers){streamers.replaceChildren();for(const item of live.streamers||[]){const row=make("p",(item.name||item.broadcaster_id)+" · "+(item.is_live?"Ao vivo: "+item.title:"Offline na última consulta")+" · "+relativeTime(item.checked_at),"hint");streamers.append(row);}}
      displayCandidates(listing.candidates || [], gta6 ? Number((meta.auto_pipeline||{}).min_score||78) : 0);
    } catch (err) {
      state.textContent = "Monitor indisponível";
      state.className = "tag bad";
      const desktopState = node("desktop-twitch-status");
      if (desktopState) {
        desktopState.textContent = "Twitch: indisponível";
        desktopState.className = "tag bad";
      }
      last.textContent = err.message;
    }
  }

  scan.addEventListener("click", async () => {
    scan.disabled = true;
    scan.textContent = "Consultando API...";
    try {
      const result = await api("/api/twitch/refresh","POST");
      if (typeof toast === "function")
        toast("Twitch: " + result.processed + " registros catalogados. Candidatos elegíveis serão avaliados para AutoClip.");
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
