"use strict";
(function(){
  const byId=id=>document.getElementById(id);
  function label(k){return {"sem_graca":"Sem graça","corte_ruim":"Corte ruim",
    "repetido":"Repetido","titulo_fraco":"Título fraco","sem_contexto":"Sem contexto",
    "audio_ruim":"Áudio ruim","enquadramento":"Enquadramento ruim","outro":"Outro"}[k]||k;}
  async function decide(decision){
    if(!activeId)return;
    const item=clips.find(c=>c.id===activeId);
    if(!item||item.status!=="ready"&&(decision!=="reject"||item.status!=="approved"))return;
    const button=byId(decision==="approve"?"approve":"reject");
    button.disabled=true;
    try{
      const reason=decision==="reject"?byId("editorial-reason").value:null;
      const res=await api("/api/clips/"+activeId+"/review","POST",false,
        {decision,reason,note:byId("editorial-note").value||""});
      toast((decision==="approve"?"Aprovado":"Rejeitado")+": feedback registrado para seleção futura. Nenhuma postagem automática.");
      await refresh(false);
      await loadLearning();
    }catch(e){toast("Revisão: "+e.message);}
    finally{button.disabled=false;}
  }
  async function loadEvidence(){
    const id=activeId;
    const div=byId("editorial-evidence");
    if(!id){div.textContent="Selecione um clipe para consultar a análise.";return;}
    try{
      const data=await api("/api/clips/"+id+"/editorial");
      if(activeId!==id)return;
      const report=data.analysis||null;
      const sem=report?.semantic||null;
      const tech=report?.technical||null;
      const lines=[
        "Controle editorial: "+(data.analysis_status==="not_started"?"ainda não executado":
           data.analysis_status==="partial"?"parcial":data.analysis_status==="complete"?"avaliado":data.analysis_status),
      ];
      if(tech){
        lines.push("Áudio e imagem: "+tech.status);
        if(tech.warnings?.length)lines.push("Alertas: "+tech.warnings.join("; "));
        else lines.push("Sem alertas técnicos automáticos.");
      }
      if(sem?.status==="visual_partial"){
        lines.push("Cenas analisadas: "+sem.frames_analyzed+" quadros com "+sem.model);
        lines.push("Hipótese: "+sem.category+" — "+(sem.event||"sem descrição"));
        lines.push("Confiança relatada pelo modelo: "+Math.round((sem.confidence||0)*100)+"%");
        lines.push("Não confirma falas, áudio ou humor.");
      }else{
        lines.push("Sem análise semântica verificável"+(sem?.reason?" ("+sem.reason+")":"")+".");
      }
      if(data.feedback)lines.push("Última decisão: "+data.feedback.decision+(data.feedback.reason?" · "+label(data.feedback.reason):""));
      div.textContent=lines.join("\n");
    }catch(e){if(activeId===id)div.textContent="Análise: "+e.message;}
  }
  async function loadLearning(){
    try{
      const m=await api("/api/editorial/summary");
      const txt=(m.reviewed||0)+" revisões · "+(m.approval_rate===null?"sem taxa":m.approval_rate+"% aprovados");
      const reasons=Object.entries(m.reasons||{}).map(([key,count])=>label(key)+": "+count).join(" · ");
      byId("editorial-learning-summary").textContent=txt+". "+(reasons||"Sem rejeições registradas.")+
        " "+(m.model_status==="insufficient_data"?"Poucos dados: ainda não há ajuste de seleção.":
          "Ajustes moderados por criador com pelo menos cinco avaliações.");
    }catch(e){byId("editorial-learning-summary").textContent="Feedback: "+e.message;}
  }
  async function loadMetrics(){
    try{
      const r=await api("/api/metrics");
      const summary=byId("editorial-metrics-summary");
      summary.textContent=r.measured_publications?
        r.measured_publications+" publicação(ões) com métricas oficiais · "+r.totals.views+" visualizações · "+
        (r.totals.likes??"não disponível")+" curtidas · "+(r.totals.comments??"não disponível")+
        " comentários · "+(r.totals.shares??"não disponível")+" compartilhamentos.":
        "Nenhuma publicação possui métricas verificadas. Retenção indisponível sem API com escopo adequado.";
      const div=byId("editorial-metrics-table");div.replaceChildren();
      if(r.retention) {
        const p=document.createElement("p");p.className="hint";
        p.textContent="Retenção YouTube disponível em "+r.retention.measured_videos+
          " vídeo(s); detalhes por publicação abaixo.";
        div.appendChild(p);
      }
      (r.items||[]).slice(0,12).forEach(item=>{
        const p=document.createElement("p");p.className="hint";
        p.textContent=item.platform+" · "+item.remote_id+" · "+
          (item.metrics?
            (item.metrics.views??"—")+" views | "+(item.metrics.likes??"—")+" likes | "+
            (item.metrics.shares??"—")+" compartilhamentos | "+
            (item.metrics.average_view_percentage===undefined?"Retenção não disponível":
              "Retenção média "+item.metrics.average_view_percentage+"% / duração média "+
              item.metrics.average_view_duration_sec+" s")+" | origem "+item.source:
            "Sem dados: "+(item.error||"não consultado"))+
          " · visibilidade "+(item.visibility||"não confirmada");
        div.appendChild(p);
      });
    }catch(e){byId("editorial-metrics-summary").textContent="Métricas: "+e.message;}
  }
  byId("editorial-metrics-refresh").addEventListener("click",async()=>{
    const button=byId("editorial-metrics-refresh");
    button.disabled=true;
    try{const res=await api("/api/metrics/refresh","POST");
      toast("Consulta oficial: "+res.updated+" atualizadas, "+res.errors+" falhas.");
      await loadMetrics();
    }catch(e){toast("Métricas: "+e.message);}
    finally{button.disabled=false;}
  });
  const pair=byId("desktop-mobile-pair");
  pair.addEventListener("click",async()=>{
    pair.disabled=true;
    try{
      const result=await api("/api/mobile/pair","POST");
      byId("mobile-pair-info").textContent="Código temporário: "+result.code+
        " ("+result.expires_in+"s). No Windows com Tailscale instalada, execute: tailscale serve --bg "+
        result.port+" . No Android conectado à mesma tailnet, abra o endereço HTTPS informado pela Tailscale seguido de /review. Não use Funnel. Somente revisão.";
      toast("Código de pareamento criado no seu PC. Não compartilhe com terceiros.");
    }catch(e){toast("Pareamento móvel: "+e.message);}
    finally{pair.disabled=false;}
  });
  window.NexusEditorial={approve:()=>decide("approve"),reject:()=>decide("reject")};
  window.addEventListener("gta:clip-selected",loadEvidence);
  window.addEventListener("gta:clips-updated",()=>{
    if(activeId)loadEvidence();
  });
  loadLearning();loadMetrics();loadEvidence();
  setInterval(()=>{loadLearning();loadMetrics();},60000);
})();
