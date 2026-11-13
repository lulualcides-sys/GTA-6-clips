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
async function api(path,method="GET",asBlob=false){const headers={};if(token)headers.Authorization="Bearer "+token;const r=await fetch(path,{method,headers,cache:"no-store"});if(r.status===401){if(!byId("login-modal").open)byId("login-modal").showModal();throw new Error("Informe o token do painel.");}if(!r.ok){let msg="HTTP "+r.status;try{msg=(await r.json()).error||msg;}catch(_){}throw new Error(msg);}return asBlob?r.blob():r.json();}
function el(type,cls,label){const n=document.createElement(type);if(cls)n.className=cls;if(label!==undefined)n.textContent=label;return n;}
function status(node,state){node.textContent=LABELS[state]||state;node.className="tag "+(["approved","ready"].includes(state)?"good":["failed","rejected"].includes(state)?"bad":"muted");}
function stats(){byId("stat-total").textContent=clips.length;byId("stat-progress").textContent=clips.filter(c=>["queued","rendering"].includes(c.status)).length;byId("stat-ready").textContent=clips.filter(c=>c.status==="ready").length;byId("stat-approved").textContent=clips.filter(c=>c.status==="approved").length;}
function renderList(){const list=byId("clip-list");list.replaceChildren();const shown=clips.filter(c=>filter==="all"||c.status===filter);if(!shown.length){list.appendChild(el("p","placeholder","Nenhum clipe nesta categoria."));return;}shown.forEach(c=>{const btn=el("button","clip"+(c.id===activeId?" selected":""));btn.type="button";btn.appendChild(el("span","clip-name",c.filename));const row=el("span","clip-row");row.appendChild(el("small","",c.creator));row.appendChild(el("span","status "+c.status,LABELS[c.status]||c.status));btn.appendChild(row);btn.addEventListener("click",()=>{activeId=c.id;renderList();renderDetail();window.dispatchEvent(new Event("gta:clip-selected"));});list.appendChild(btn);});}
function field(label,value){const w=el("div");w.appendChild(el("small","",label));w.appendChild(el("strong","",value===null||value===undefined||value===""?"—":String(value)));return w;}
function clearPreview(){byId("player").pause();byId("player").hidden=true;byId("player").removeAttribute("src");byId("player-placeholder").hidden=false;if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl="";previewKey="";}
async function showPreview(c){const key=c.id+":"+c.output_path;if(previewKey===key)return;clearPreview();previewKey=key;try{const b=await api("/api/clips/"+c.id+"/video","GET",true);if(activeId!==c.id)return;previewUrl=URL.createObjectURL(b);byId("player").src=previewUrl;byId("player").hidden=false;byId("player-placeholder").hidden=true;}catch(e){previewKey="";toast("Prévia: "+e.message);}}
function renderDetail(){const c=clips.find(x=>x.id===activeId);if(!c){byId("detail-title").textContent="Selecione um clipe";status(byId("detail-status"),"detected");byId("details").replaceChildren(el("p","hint","Os detalhes de origem e permissão aparecerão aqui."));["render","approve","reject","hyperframes","transcribe"].forEach(id=>byId(id).disabled=true);clearPreview();return;}byId("detail-title").textContent=c.filename;status(byId("detail-status"),c.status);byId("details").replaceChildren(field("CRIADOR",c.creator),field("DURAÇÃO",Math.round(c.duration_sec)+"s"),field("DIREITOS DECLARADOS",c.rights_status),field("INÍCIO DO TRECHO",c.start_sec===null?"Seleção automática":c.start_sec+"s"),field("REFERÊNCIA DE ORIGEM",c.source_url),field("ERRO / AVISO",c.error),field("LEGENDAS",captionStates[c.id] ? ({"ready":"Geradas","queued":"Na fila","processing":"Transcrevendo","failed":"Falhou","stale":"Desatualizadas"}[captionStates[c.id].status]||captionStates[c.id].status) : "Não iniciadas"));byId("render").disabled=!["detected","failed","rejected"].includes(c.status);byId("hyperframes").disabled=!(c.output_path&&["ready","approved"].includes(c.status));byId("transcribe").disabled=!whisperAvailable||!(c.output_path&&["ready","approved"].includes(c.status))||["queued","processing"].includes((captionStates[c.id]||{}).status);byId("approve").disabled=c.status!=="ready";byId("reject").disabled=!["ready","approved"].includes(c.status);if(c.output_path&&["ready","approved"].includes(c.status))showPreview(c);else clearPreview();}
async function refresh(silent=true){try{const [data,captions]=await Promise.all([api("/api/clips"),api("/api/captions")]);clips=data.clips||[];captionStates=captions.captions||{};whisperAvailable=Boolean(captions.transcription_available);byId("transcribe").title=whisperAvailable?"Transcrever localmente":"Instale requirements-ai.txt no servidor para ativar legendas";byId("connection").textContent="Serviço online";byId("connection").className="tag good";const previousId=activeId;if(!clips.find(c=>c.id===activeId))activeId=clips.length?clips[0].id:null;stats();renderList();renderDetail();if(previousId!==activeId)window.dispatchEvent(new Event("gta:clip-selected"));}catch(e){byId("connection").textContent="Sem conexão";byId("connection").className="tag bad";if(!silent)toast(e.message);}}
async function action(name){if(!activeId)return;try{await api("/api/clips/"+activeId+"/"+name,"POST");toast(name==="render"?"Renderização enviada à fila.":"Estado atualizado.");await refresh();if(window.GTAAgents)window.GTAAgents.refresh();}catch(e){toast(e.message);}}
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
    const exported=await api("/api/clips/"+clipId+"/hyperframes","POST");
    const zip=await api(exported.download_path,"GET",true);
    const url=URL.createObjectURL(zip);
    const link=document.createElement("a");
    link.href=url;link.download="gta6-"+clipId+"-hyperframes.zip";
    document.body.appendChild(link);link.click();link.remove();
    setTimeout(()=>URL.revokeObjectURL(url),30000);
    toast("Pacote HyperFrames exportado com legendas disponíveis. O render final exige a CLI local.");
  }catch(err){toast("HyperFrames: "+err.message);}
  finally{renderDetail();}
}
byId("hyperframes").addEventListener("click",exportHyperFrames);
byId("approve").addEventListener("click",()=>action("approve"));byId("reject").addEventListener("click",()=>action("reject"));
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
      toast("Credenciais salvas no PC. Feche e reabra o aplicativo para ativar a busca Twitch.");
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
        updateStatus.textContent="Instalação atual preservada";
        toast(result?.error||"Falha ao verificar atualização");
        busy=false;
        updateButton.disabled=false;
      }else{
        updateStatus.textContent="Reiniciando para "+result.latest;
      }
    }catch(error){
      updateStatus.textContent="Instalação atual preservada";
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

setInterval(()=>refresh(),6000);refresh();
