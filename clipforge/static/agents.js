/* GTA VI Mission Control: real SQLite activity, never mocked "working" agents. */
"use strict";
(function () {
  const get = id => document.getElementById(id);
  const graph = get("agent-nodes");
  const feed = get("mission-feed");
  const state = get("mission-connection");
  const selected = get("mission-focus");
  const stamp = get("mission-updated");
  const summary = get("mission-summary");
  if (!graph || !feed || !state || !selected) return;

  const stateText = {
    idle: "EM ESPERA", waiting: "AGUARDANDO", blocked: "INDISPONÍVEL",
    queued: "NA FILA", running: "EXECUTANDO", complete: "CONCLUÍDO", failed: "ATENÇÃO"
  };
  const iconText = {
    radar: "⌁", ingestao: "↓", direitos: "✓", curadoria: "⌘",
    edicao: "◈", legendas: "≡", motion: "✦", revisao: "⊙", publicacao: "↑"
  };
  let last = null;
  let agentFilter = null;
  let feedFilter = "all";
  let inFlight = false;
  let selectedClip = null;

  function e(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
  }
  function timeLabel(value) {
    if (!value) return "Sem execução";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "Sem horário" :
      date.toLocaleString("pt-BR",{day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"});
  }
  function currentClipId() {
    return (typeof activeId !== "undefined" && activeId) ? activeId : null;
  }
  function showConnection(type, label) {
    state.className = "mission-live " + type;
    state.replaceChildren(e("span","live-dot"),e("span","",label));
  }
  function decorateSummary(data) {
    const counts = data.counts || {};
    get("agent-count").textContent = data.stages.filter(s=>s.state==="running").length;
    get("agent-tasks").textContent = Number(counts.in_progress || 0);
    get("agent-pending").textContent = Number(counts.review || 0);
    get("agent-error").textContent = Number(counts.failed || 0);
    const details = [];
    details.push(data.auto_scan ? "Scanner automático ativado" : "Scanner manual");
    details.push(data.auto_render ? "Render automático ativado" : "Render manual");
    details.push(data.transcription_available ? "Whisper instalado" : "Whisper não instalado");
    details.push("Publicação desativada");
    summary.textContent = details.join(" · ");
    get("mission-demo").hidden = !data.demo_enabled;

    const current = (typeof clips !== "undefined" && data.selected_clip) ?
      clips.find(c=>c.id===data.selected_clip) : null;
    selected.textContent = current ? current.filename : "Visão global da produção";
  }
  function drawNodes(stages) {
    graph.replaceChildren();
    stages.forEach((agent,index)=>{
      const card = e("button","agent-unit");
      card.type = "button";
      card.dataset.agent = agent.id;
      card.dataset.state = agent.state;
      card.setAttribute("aria-label",
        agent.name + ": " + (stateText[agent.state] || "Sem estado") +
        ". " + (agent.message || "Nenhuma execução"));
      card.setAttribute("aria-pressed",String(agentFilter===agent.id));
      if (agentFilter===agent.id) card.classList.add("chosen");

      const head=e("div","agent-unit-head");
      const emblem=e("span","agent-emblem",iconText[agent.id] || "•");
      emblem.setAttribute("aria-hidden","true");
      head.append(emblem,e("span","agent-order",String(index+1).padStart(2,"0")));
      const title=e("strong","agent-name",agent.name);
      const subtitle=e("span","agent-subtitle",agent.description);
      const bottom=e("div","agent-foot");
      const indicator=e("span","agent-indicator");
      indicator.setAttribute("aria-hidden","true");
      bottom.append(indicator,e("span","agent-state",stateText[agent.state]||"EM ESPERA"));
      const note=e("p","agent-note",agent.message || "Sem atividade registrada");
      card.append(head,title,subtitle,bottom,note);
      card.addEventListener("click",()=>{
        agentFilter=agentFilter===agent.id?null:agent.id;
        drawNodes(last.stages);
        drawFeed(last.activity);
        get("agent-filter-label").textContent = agentFilter ?
          ("Exibindo: "+agent.name+" · tocar novamente para limpar") :
          "Todas as atividades";
      });
      graph.appendChild(card);
    });
  }
  function drawFeed(items) {
    feed.replaceChildren();
    const filtered = items.filter(item=>
      (!agentFilter || item.agent===agentFilter) &&
      (feedFilter==="all" || (feedFilter==="running"
        ? ["running","queued"].includes(item.state)
        : item.state==="failed"))
    );
    get("mission-activity-count").textContent = filtered.length;
    if (!filtered.length) {
      const empty=e("div","mission-empty");
      empty.append(e("span","empty-orb","◎"),
        e("strong","", "Nenhuma atividade registrada"),
        e("p","", last?.selected_clip ?
          "As ações reais deste clipe aparecerão aqui conforme forem executadas." :
          "O histórico aparece quando tarefas do pipeline são executadas. Não há simulação de agentes."));
      feed.appendChild(empty);
      return;
    }
    for (const item of filtered.slice(0,50)) {
      const wrapper=e("article","activity-entry");
      wrapper.dataset.state=item.state;
      const dot=e("span","activity-rail");
      dot.setAttribute("aria-hidden","true");
      const content=e("div","activity-copy");
      const header=e("div","activity-heading");
      const meta=last.stages.find(s=>s.id===item.agent);
      header.append(
        e("strong","",meta?.name||item.agent.toUpperCase()),
        e("time","activity-time",timeLabel(item.at))
      );
      content.append(
        header,
        e("p","",item.message),
        e("span","activity-state",stateText[item.state]||"EVENTO")
      );
      wrapper.append(dot,content);
      feed.appendChild(wrapper);
    }
  }
  async function loadSnapshot() {
    if (inFlight) return;
    inFlight=true;
    const clipId=currentClipId();
    if (clipId!==selectedClip) {
      agentFilter=null;
      get("agent-filter-label").textContent="Todas as atividades";
    }
    try {
      const url="/api/agents"+(clipId?"?clip_id="+encodeURIComponent(clipId):"");
      const data=await api(url);
      // Ignore stale response after a different clip was selected.
      if (clipId!==currentClipId()) return;
      last=data;
      selectedClip=clipId;
      drawNodes(data.stages||[]);
      drawFeed(data.activity||[]);
      decorateSummary(data);
      stamp.textContent="Atualizado: "+new Date().toLocaleTimeString("pt-BR");
      showConnection("connected","DADOS REAIS · ONLINE");
    } catch(err) {
      showConnection("offline","SEM CONEXÃO");
      stamp.textContent="Não foi possível obter a atividade: "+err.message;
    } finally {
      inFlight=false;
    }
  }
  get("mission-refresh").addEventListener("click",loadSnapshot);
  get("mission-demo").addEventListener("click", async ()=>{
    const button=get("mission-demo");
    button.disabled=true;
    try {
      const result=await api("/api/demo","POST");
      if(typeof toast==="function")
        toast("Teste real iniciado com vídeo sintético próprio. Acompanhe a atividade e selecione o clipe quando aparecer.");
      await loadSnapshot();
    } catch(err) {
      if(typeof toast==="function") toast("Teste: "+err.message);
    } finally {button.disabled=false;}
  });
  document.querySelectorAll("[data-activity-filter]").forEach(btn=>{
    btn.addEventListener("click",()=>{
      feedFilter=btn.dataset.activityFilter;
      document.querySelectorAll("[data-activity-filter]").forEach(other=>
        other.classList.toggle("active",other===btn));
      if(last) drawFeed(last.activity||[]);
    });
  });
  window.addEventListener("gta:clip-selected",loadSnapshot);
  window.GTAAgents={refresh:loadSnapshot};
  window.setInterval(loadSnapshot,6000);
  loadSnapshot();
})();
