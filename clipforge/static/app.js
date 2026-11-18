"use strict";
const byId = id => document.getElementById(id);
const LABELS = {detected:"Detectado",queued:"Na fila",rendering:"Renderizando",ready:"Pronto para revisar",approved:"Aprovado",rejected:"Rejeitado",failed:"Falhou"};
// The native desktop shell receives its randomly generated loopback API token
// in the URL fragment. Fragments are never sent in HTTP requests.
if (location.hash.startsWith("#desktop-token=")) {
  const provided = decodeURIComponent(location.hash.slice("#desktop-token=".length));
  if (provided.length >= 24) {
    sessionStorage.setItem("gta_clips_token", provided);
  }
  history.replaceState(null, "", location.pathname + location.search);
}
let clips=[], captionStates={}, whisperAvailable=false, activeId=null, filter="all", previewKey="", previewUrl="", token=sessionStorage.getItem("gta_clips_token")||"", toastTimeout;
function toast(message){const b=byId("message");b.textContent=message;b.hidden=false;clearTimeout(toastTimeout);toastTimeout=setTimeout(()=>b.hidden=true,5500);}
async function api(path,method="GET",asBlob=false,body=null){const headers={};if(body!==null)headers["Content-Type"]="application/json";if(token)headers.Authorization="Bearer "+token;const r=await fetch(path,{method,headers,cache:"no-store",body:body===null?undefined:JSON.stringify(body)});if(r.status===401){if(!byId("login-modal").open)byId("login-modal").showModal();throw new Error("Informe o token do painel.");}if(!r.ok){let msg="HTTP "+r.status;try{msg=(await r.json()).error||msg;}catch(_){}throw new Error(msg);}return asBlob?r.blob():r.json();}
function el(type,cls,label){const n=document.createElement(type);if(cls)n.className=cls;if(label!==undefined)n.textContent=label;return n;}
function status(node,state){node.textContent=LABELS[state]||state;node.className="tag "+(["approved","ready"].includes(state)?"good":["failed","rejected"].includes(state)?"bad":"muted");}
function stats(){byId("stat-total").textContent=clips.length;byId("stat-progress").textContent=clips.filter(c=>["queued","rendering"].includes(c.status)).length;byId("stat-ready").textContent=clips.filter(c=>c.status==="ready").length;byId("stat-approved").textContent=clips.filter(c=>c.status==="approved").length;}
function renderList(){const list=byId("clip-list");list.replaceChildren();const shown=clips.filter(c=>filter==="all"||c.status===filter);if(!shown.length){list.appendChild(el("p","placeholder","Nenhum clipe nesta categoria."));return;}shown.forEach(c=>{const btn=el("button","clip"+(c.id===activeId?" selected":""));btn.type="button";btn.appendChild(el("span","clip-name",c.filename));const row=el("span","clip-row");row.appendChild(el("small","",c.creator));row.appendChild(el("span","status "+c.status,LABELS[c.status]||c.status));btn.appendChild(row);btn.addEventListener("click",()=>{activeId=c.id;renderList();renderDetail();window.dispatchEvent(new Event("gta:clip-selected"));});list.appendChild(btn);});}
function field(label,value){const w=el("div");w.appendChild(el("small","",label));w.appendChild(el("strong","",value===null||value===undefined||value===""?"—":String(value)));return w;}
function clearPreview(){byId("player").pause();byId("player").hidden=true;byId("player").removeAttribute("src");byId("player-placeholder").hidden=false;if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl="";previewKey="";}
async function showPreview(c){const key=c.id+":"+c.output_path;if(previewKey===key)return;clearPreview();previewKey=key;try{const b=await api("/api/clips/"+c.id+"/video","GET",true);if(activeId!==c.id)return;previewUrl=URL.createObjectURL(b);byId("player").src=previewUrl;byId("player").hidden=false;byId("player-placeholder").hidden=true;}catch(e){previewKey="";toast("Prévia: "+e.message);}}
function renderDetail(){const c=clips.find(x=>x.id===activeId);if(!c){byId("detail-title").textContent="Selecione um clipe";status(byId("detail-status"),"detected");byId("details").replaceChildren(el("p","hint","Os detalhes de origem e permissão aparecerão aqui."));["render","approve","reject","hyperframes","transcribe"].forEach(id=>byId(id).disabled=true);clearPreview();return;}byId("detail-title").textContent=c.filename;status(byId("detail-status"),c.status);byId("details").replaceChildren(field("CRIADOR",c.creator),field("DURAÇÃO",Math.round(c.duration_sec)+"s"),field("DIREITOS DECLARADOS",c.rights_status),field("INÍCIO DO TRECHO",c.start_sec===null?"Seleção automática":c.start_sec+"s"),field("REFERÊNCIA DE ORIGEM",c.source_url),field("ERRO / AVISO",c.error),field("LEGENDAS",captionStates[c.id] ? ({"ready":"Geradas","queued":"Na fila","processing":"Transcrevendo","failed":"Falhou","stale":"Desatualizadas"}[captionStates[c.id].status]||captionStates[c.id].status) : "Não iniciadas"));byId("render").disabled=!["detected","failed","rejected"].includes(c.status);byId("hyperframes").disabled=!(c.output_path&&["ready","approved"].includes(c.status));byId("transcribe").disabled=!whisperAvailable||!(c.output_path&&["ready","approved"].includes(c.status))||["queued","processing"].includes((captionStates[c.id]||{}).status);byId("approve").disabled=c.status!=="ready";byId("reject").disabled=!["ready","approved"].includes(c.status);if(c.output_path&&["ready","approved"].includes(c.status))showPreview(c);else clearPreview();}
async function refresh(silent=true){try{const [data,captions]=await Promise.all([api("/api/clips"),api("/api/captions")]);clips=data.clips||[];captionStates=captions.captions||{};whisperAvailable=Boolean(captions.transcription_available);byId("transcribe").title=whisperAvailable?"Transcrever localmente":"Instale requirements-ai.txt no servidor para ativar legendas";byId("connection").textContent="Serviço online";byId("connection").className="tag good";const previousId=activeId;if(!clips.find(c=>c.id===activeId))activeId=clips.length?clips[0].id:null;stats();renderList();renderDetail();window.dispatchEvent(new Event("gta:clips-updated"));if(previousId!==activeId)window.dispatchEvent(new Event("gta:clip-selected"));}catch(e){byId("connection").textContent="Sem conexão";byId("connection").className="tag bad";if(!silent)toast(e.message);}}
async function action(name){if(!activeId)return;try{await api("/api/clips/"+activeId+"/"+name,"POST");toast(name==="render"?"AutoClip iniciado; escolha uma sugestão e revise antes de aprovar.":"Estado atualizado.");await refresh();if(window.GTAAgents)window.GTAAgents.refresh();}catch(e){toast(e.message);}}
byId("refresh").addEventListener("click",()=>refresh(false));
byId("scan").addEventListener("click",async()=>{try{const r=await api("/api/scan","POST");toast(r.added.length+" novo(s) clipe(s). "+r.errors.length+" erro(s).");if(r.errors.length)console.warn("Manifestos inválidos:",r.errors);await refresh();}catch(e){toast(e.message);}});
byId("render").addEventListener("click",()=>action("render"));
byId("transcribe").addEventListener("click",()=>action("transcribe"));
async function exportHyperFrames(){
  if(!activeId) return;
  const clipId=activeId;
  const button=byId("hyperframes");
  button.disabled=true;
  try{
    const exported=await api("/api/clips/"+clipId+"/hyperframes"+(byId("hyperframes-captions").checked?"?captions=1":""),"POST");
    const zip=await api(exported.download_path,"GET",true);
    const url=URL.createObjectURL(zip);
    const link=document.createElement("a");
    link.href=url;link.download="gta6-"+clipId+"-hyperframes.zip";
    document.body.appendChild(link);link.click();link.remove();
    setTimeout(()=>URL.revokeObjectURL(url),30000);
    toast("Pacote HyperFrames exportado com as opções escolhidas. O render final exige a CLI local.");
  }catch(err){toast("HyperFrames: "+err.message);}
  finally{renderDetail();}
}
byId("hyperframes").addEventListener("click",exportHyperFrames);
byId("approve").addEventListener("click",()=>window.NexusEditorial?window.NexusEditorial.approve():action("approve"));byId("reject").addEventListener("click",()=>window.NexusEditorial?window.NexusEditorial.reject():action("reject"));
document.querySelectorAll("[data-filter]").forEach(b=>b.addEventListener("click",()=>{filter=b.dataset.filter;document.querySelectorAll("[data-filter]").forEach(x=>x.classList.toggle("active",x===b));renderList();}));
byId("login-form").addEventListener("submit",e=>{e.preventDefault();token=byId("token").value;sessionStorage.setItem("gta_clips_token",token);byId("login-modal").close();refresh(false);window.dispatchEvent(new Event("gta:auth-updated"));});
function mountDesktopControls() {
  const bridge=window.pywebview?.api;
  const bar=byId("desktop-toolbar");
  if(!bridge||!bar||!bar.hidden) return;
  bar.hidden=false;
  const actions={
    "desktop-incoming":"open_incoming",
    "desktop-rendered":"open_rendered",
    "desktop-settings":"open_settings"
  };
  for(const [id,method] of Object.entries(actions)){
    byId(id).addEventListener("click",async()=>{
      try{
        const result=await bridge[method]();
        if(!result?.ok) toast(result?.error||"A pasta não pôde ser aberta");
      }catch(error){toast("Windows: "+error.message);}
    });
  }
  const connectButton=byId("desktop-twitch-connect");
  const twitchDialog=byId("twitch-oauth-modal");
  const twitchForm=byId("twitch-oauth-form");
  const twitchId=byId("twitch-client-id");
  const twitchSecret=byId("twitch-client-secret");
  const twitchSave=byId("twitch-oauth-save");
  connectButton.addEventListener("click",()=>twitchDialog.showModal());
  const authorizeButton=byId("desktop-twitch-authorize");
  authorizeButton.addEventListener("click",async()=>{
    authorizeButton.disabled=true;
    try{
      const result=await bridge.authorize_twitch_download();
      if(!result?.ok){toast(result?.error||"Não foi possível iniciar autorização Twitch.");return;}
      toast("Autorize no site oficial da Twitch. Depois o Nexus buscará seus clipes elegíveis.");
    }catch(error){toast("Twitch: não foi possível abrir autorização.");}
    finally{authorizeButton.disabled=false;}
  });
  let lastOAuthStatus="";
  async function checkDownloadOAuth(){
    try{
      const info=await bridge.twitch_download_status();
      if(info?.status!==lastOAuthStatus){
        lastOAuthStatus=info?.status;
        if(info?.status==="authorized"){
          toast("Twitch: downloads do seu canal autorizados. AutoClip pode iniciar quando o modelo estiver pronto.");
          window.dispatchEvent(new Event("gta:auth-updated"));
        }
        if(info?.status==="failed") toast("Twitch: "+(info.last_error||"autorização falhou."));
      }
      authorizeButton.textContent=info?.grant_present?"Renovar autorização Twitch":"Autorizar downloads Twitch";
    }catch(_){}
  }
  setInterval(checkDownloadOAuth,5000);
  checkDownloadOAuth();
  byId("twitch-oauth-cancel").addEventListener("click",()=>{
    twitchSecret.value="";
    twitchDialog.close();
  });
  twitchForm.addEventListener("submit",async(event)=>{
    event.preventDefault();
    if(twitchSave.disabled) return;
    twitchSave.disabled=true;
    try {
      const response=await bridge.save_twitch_credentials(
        twitchId.value.trim(),twitchSecret.value.trim()
      );
      if(!response?.ok) {
        toast(response?.error||"Não foi possível salvar credenciais");
        return;
      }
      twitchSecret.value="";
      twitchId.value="";
      twitchDialog.close();
      toast(response.restart_required ?
        "Credenciais verificadas e salvas. Reinicie o Nexus para conectar." :
        "Twitch autenticada e monitoramento ativado. Buscando clipes.");
      window.dispatchEvent(new Event("gta:auth-updated"));
    } catch(error) {
      toast("Twitch: falha na configuração local");
    } finally {
      twitchSecret.value="";
      twitchSave.disabled=false;
    }
  });
  const updateButton=byId("desktop-update");
  const updateStatus=byId("desktop-update-status");
  let available=false;
  let busy=false;
  async function checkUpdates(){
    if(busy) return;
    busy=true;
    updateButton.disabled=true;
    updateStatus.textContent="Conferindo GitHub...";
    try{
      const info=await bridge.check_updates();
      available=Boolean(info?.ok&&info.available);
      if(!info?.ok){
        updateStatus.textContent="GitHub indisponível";
        updateButton.textContent="Verificar novamente";
      }else if(available){
        updateStatus.textContent="Nova versão: "+info.latest;
        updateButton.textContent="Atualizar";
      }else{
        updateStatus.textContent="v"+info.version+" · Atualizado";
        updateButton.textContent="Verificar novamente";
      }
    }catch(error){
      available=false;
      updateStatus.textContent="Atualização indisponível";
      updateButton.textContent="Tentar novamente";
    }finally{
      busy=false;
      updateButton.disabled=false;
    }
  }
  updateButton.addEventListener("click",async()=>{
    if(busy) return;
    if(!available) return checkUpdates();
    busy=true;
    updateButton.disabled=true;
    updateStatus.textContent="Baixando, conferindo SHA-256 e testando...";
    try{
      const result=await bridge.install_update();
      if(!result?.ok){
        const reason=result?.error||"Falha ao verificar atualização";
        updateStatus.textContent="Não atualizou: "+reason;
        updateStatus.title=reason;
        toast(reason);
        busy=false;
        updateButton.disabled=false;
      }else{
        updateStatus.textContent="Reiniciando para "+result.latest;
      }
    }catch(error){
      updateStatus.textContent="Não atualizou: "+error.message;
      toast("Atualização: "+error.message);
      busy=false;
      updateButton.disabled=false;
    }
  });
  checkUpdates();
  setInterval(checkUpdates,3*60*60*1000);
}
window.addEventListener("pywebviewready",mountDesktopControls);
mountDesktopControls();


/* AutoClip: execução local opcional, sugestões isoladas da aprovação. */
let autoclipPreviewUrl="";
function clearAutoclipPreview(){
  const player=byId("autoclip-preview");
  player.pause();player.hidden=true;player.removeAttribute("src");
  if(autoclipPreviewUrl)URL.revokeObjectURL(autoclipPreviewUrl);
  autoclipPreviewUrl="";
}
async function refreshAutoclip(){
  const selected=activeId;
  const stateNode=byId("autoclip-status"), results=byId("autoclip-results");
  try{
    const data=await api("/api/autoclip");
    if(selected!==activeId)return;
    const job=(data.jobs||{})[selected]||null;
    const ready=Boolean(data.enabled&&data.installed);
    byId("autoclip-run").disabled=!selected||!ready||data.running;
    byId("render").disabled=!selected||!ready||data.running||
      !["detected","failed","rejected"].includes((clips.find(c=>c.id===selected)||{}).status);
    stateNode.textContent=!data.enabled?"AutoClip desativado (AUTOCLIP_ENABLED=0).":
      !data.installed?"Motor AutoClip não encontrado. No Windows ele vem no app (v0.5.0+); no Linux instale a CLI.":
      job?.imports?.length ? "AutoClip: "+job.imports.length+" edição(ões) pronta(s) na biblioteca para aprovação.":
      job ? "AutoClip: "+job.status+" · "+(job.import_errors?.join("; ")||"Aguardando saídas e validação.") :
      "Motor AutoClip instalado · confira abaixo se a IA local está pronta para editar.";
    results.replaceChildren();
    if(job&&job.error)results.appendChild(el("p","hint",job.error));
    if(job?.import_errors?.length) results.appendChild(el("p","hint","QA AutoClip: "+job.import_errors.join("; ")));
    const clipsToPreview=(job?.status==="complete"&&Array.isArray(job.suggestions))?job.suggestions:[];
    clipsToPreview.forEach((name,index)=>{
      const button=el("button","btn secondary","Assistir sugestão "+(index+1));
      button.type="button";
      button.addEventListener("click",async()=>{
        clearAutoclipPreview();
        try{
          const blob=await api("/api/clips/"+selected+"/autoclip-preview/"+index,"GET",true);
          if(selected!==activeId)return;
          autoclipPreviewUrl=URL.createObjectURL(blob);
          const player=byId("autoclip-preview");
          player.src=autoclipPreviewUrl;player.hidden=false;player.load();
        }catch(err){toast("AutoClip: "+err.message);}
      });
      results.appendChild(button);
      const importButton=el("button","btn secondary","Importar sugestão "+(index+1)+" para revisão");
      importButton.type="button";
      importButton.addEventListener("click",async()=>{
        importButton.disabled=true;
        try{
          const result=await api("/api/clips/"+selected+"/autoclip-import/"+index,"POST");
          activeId=result.clip_id;
          toast("MP4 criado pelo AutoClip importado sem reedição. Revise antes de aprovar.");
          clearAutoclipPreview();
          await refresh(false);
        }catch(err){toast("Importação AutoClip: "+err.message);}
        finally{importButton.disabled=false;}
      });
      results.appendChild(importButton);
    });
    if(!clipsToPreview.length)clearAutoclipPreview();
  }catch(e){
    stateNode.textContent="AutoClip: "+e.message;
    byId("autoclip-run").disabled=true;
  }
}
byId("autoclip-run").addEventListener("click",async()=>{
  if(!activeId)return;
  byId("autoclip-run").disabled=true;
  try{
    await api("/api/clips/"+activeId+"/autoclip","POST");
    toast("AutoClip iniciado. Os resultados ficarão disponíveis apenas para revisão.");
  }catch(e){toast("AutoClip: "+e.message);}
  await refreshAutoclip();
});
/* IA local: instala Ollama oficial e baixa o modelo com um clique (somente no PC). */
async function refreshLocalAI(){
  const node=byId("local-ai-status"),button=byId("local-ai-prepare"),select=byId("local-ai-model"),bar=byId("local-ai-progress");
  try{
    const data=await api("/api/local-ai");
    if(!select.options.length){(data.catalog||[]).forEach(m=>{const o=el("option","",m.label+" · ~"+m.size_gb+" GB");o.value=m.name;select.appendChild(o);});select.value=data.recommended;}
    const job=data.job,running=job&&job.state==="running";
    button.disabled=Boolean(running)||(!data.can_install&&!data.ollama_installed);
    bar.hidden=!running;
    if(running)bar.value=Number(job.progress)||0;
    if(running)node.textContent=job.phase+(job.progress?" · "+Math.round(job.progress*100)+"%":"");
    else if(job&&job.state==="failed")node.textContent="Falha ao preparar IA: "+job.error;
    else if(data.model_ready)node.textContent="✓ IA local pronta ("+data.models.join(", ")+"). O AutoClip já pode editar.";
    else if(data.ollama_running)node.textContent="Ollama ativo, mas sem modelo. Clique em Preparar para baixar o modelo.";
    else if(data.ollama_installed)node.textContent="Ollama instalado e parado. Preparar inicia o serviço e baixa o modelo.";
    else if(data.can_install)node.textContent="Falta a IA local. Preparar instala o Ollama oficial (assinatura verificada) e baixa o modelo. Gratuito, roda no seu PC.";
    else node.textContent="Instale o Ollama (ollama.com/download) neste sistema; depois use Preparar.";
    return data;
  }catch(e){node.textContent="IA local: "+e.message;button.disabled=true;return null;}
}
byId("local-ai-prepare").addEventListener("click",async()=>{
  byId("local-ai-prepare").disabled=true;
  try{await api("/api/local-ai/prepare","POST",false,{model:byId("local-ai-model").value});toast("Preparando IA do AutoClip. Pode levar vários minutos.");}
  catch(e){toast("IA local: "+e.message);}
  await refreshLocalAI();
});
setInterval(refreshLocalAI,4000);refreshLocalAI();window.addEventListener("gta:auth-updated",()=>{refreshLocalAI();refreshAutoclip();});
byId("connections-check").addEventListener("click",async()=>{
  const button=byId("connections-check"),list=byId("connections-result");
  button.disabled=true;list.replaceChildren(el("li","hint","Testando conexões (somente leitura, nada é postado)..."));
  try{
    const data=await api("/api/connections/check","POST");
    list.replaceChildren();
    [["twitch","Twitch"],["youtube","YouTube"],["tiktok","TikTok"],["postiz","Postiz"]].forEach(([key,label])=>{
      const r=data[key]||{};
      list.appendChild(el("li",r.ok?"good":(r.configured?"bad":"muted"),(r.ok?"✓ ":r.configured?"✗ ":"– ")+label+": "+(r.detail||"")));
    });
  }catch(e){list.replaceChildren(el("li","bad","Teste de conexões: "+e.message));}
  finally{button.disabled=false;}
});
window.addEventListener("gta:clip-selected",()=>{clearAutoclipPreview();refreshAutoclip();});
setInterval(refreshAutoclip,10000);
refreshAutoclip();

setInterval(()=>refresh(),6000);refresh();
