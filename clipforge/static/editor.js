"use strict";
// Ajustes explícitos: nenhum título ou facecam é inventado pelo painel.
let editClipId=null, originalUrl="", batchSelected=new Set(), publicationBusy=false;
function clearOriginal(){const player=byId("original-player");player.pause();player.removeAttribute("src");player.hidden=true;if(originalUrl)URL.revokeObjectURL(originalUrl);originalUrl="";}
async function loadEdit(){
  const c=clips.find(x=>x.id===activeId);
  byId("load-original").disabled=!c;
  byId("edit-fields").disabled=!c||["approved","queued","rendering"].includes(c.status);
  if(!c){editClipId=null;clearOriginal();return;}
  if(editClipId===c.id)return;
  editClipId=c.id;clearOriginal();
  try{const e=await api("/api/clips/"+c.id+"/edit");if(activeId!==c.id)return;
    byId("edit-start").value=e.start_sec??c.start_sec??0;
    byId("edit-duration").value=e.duration_sec??c.duration_sec;
    byId("edit-title").value=e.title||"";byId("edit-verified").checked=Boolean(e.title_verified);
    byId("edit-layout").value=e.layout||"preserve";
    byId("edit-focus-x").value=e.focus_x??0.5;byId("edit-focus-y").value=e.focus_y??0.5;
    byId("edit-facecam").value=(e.facecam_region||[]).join(", ");
    byId("edit-action").value=(e.action_region||[]).join(", ");
    byId("publication-title").value=e.title||"";
  }catch(e){editClipId=null;toast("Editor: "+e.message);}
}
function renderBatch(){const box=byId("batch-clips");box.replaceChildren();const ready=clips.filter(c=>c.status==="ready");batchSelected=new Set([...batchSelected].filter(id=>ready.some(c=>c.id===id)));for(const c of ready){const label=el("label","check-label");const input=el("input");input.type="checkbox";input.checked=batchSelected.has(c.id);input.addEventListener("change",()=>input.checked?batchSelected.add(c.id):batchSelected.delete(c.id));label.append(input,document.createTextNode(c.filename+" · "+c.creator));box.append(label);}if(!ready.length)box.append(el("p","hint","Nenhum clipe pronto para aprovação."));}
byId("load-original").addEventListener("click",async()=>{if(!activeId)return;const id=activeId;byId("load-original").disabled=true;try{const blob=await api("/api/clips/"+id+"/original","GET",true);if(id!==activeId)return;clearOriginal();originalUrl=URL.createObjectURL(blob);const player=byId("original-player");player.src=originalUrl;player.hidden=false;}catch(e){toast("Original: "+e.message);}finally{byId("load-original").disabled=!activeId;}});
byId("edit-form").addEventListener("submit",async event=>{event.preventDefault();if(!activeId)return;const fields={start_sec:Number(byId("edit-start").value),duration_sec:Number(byId("edit-duration").value),title:byId("edit-title").value.trim(),title_verified:byId("edit-verified").checked,layout:byId("edit-layout").value,focus_x:Number(byId("edit-focus-x").value),focus_y:Number(byId("edit-focus-y").value)};fields.facecam_region=byId("edit-facecam").value.trim()?byId("edit-facecam").value.split(",").map(v=>Number(v.trim())):null;fields.action_region=byId("edit-action").value.trim()?byId("edit-action").value.split(",").map(v=>Number(v.trim())):null;try{await api("/api/clips/"+activeId+"/edit","POST",false,fields);toast("Ajustes salvos. Renderize e confira a nova versão antes de aprovar.");editClipId=null;await refresh(false);}catch(e){toast(e.message);}});
byId("approve-batch").addEventListener("click",async()=>{if(!batchSelected.size){toast("Selecione os clipes que você revisou.");return;}try{const result=await api("/api/clips/approve-batch","POST",false,{clip_ids:[...batchSelected]});toast(result.approved.length+" aprovados; "+result.skipped.length+" ignorados por mudança de estado.");batchSelected.clear();await refresh();}catch(e){toast(e.message);}});
async function refreshPublishing(){if(publicationBusy)return;publicationBusy=true;try{const data=await api("/api/publishing");const platforms=data.platforms||[];byId("publication-state").textContent=(data.enabled?"Worker habilitado. ":"Publicação desativada. ")+platforms.map(p=>p.platform+": "+(p.connected?"credenciais configuradas":"não configurada")+(p.limitations?" · "+(Array.isArray(p.limitations)?p.limitations.join("; "):p.limitations):"")).join(" | ");byId("publication-process").disabled=!data.enabled;const list=byId("publication-jobs");list.replaceChildren();for(const job of data.jobs||[]){const card=el("article","notice");card.append(el("strong","",job.platform+" · "+job.status),el("p","hint",job.title||job.clip_id));if(job.remote_id)card.append(el("p","hint","ID confirmado: "+job.remote_id));if(job.visibility)card.append(el("p","hint","Visibilidade: "+job.visibility));if(job.error)card.append(el("p","hint",job.error));list.append(card);}if(!(data.jobs||[]).length)list.append(el("p","hint","Nenhuma publicação agendada."));}catch(e){byId("publication-state").textContent="Fila indisponível: "+e.message;}finally{publicationBusy=false;}}
byId("publication-form").addEventListener("submit",async event=>{event.preventDefault();if(!activeId){toast("Selecione um clipe aprovado.");return;}const payload={platform:byId("publication-platform").value,title:byId("publication-title").value.trim()};if(byId("publication-schedule").value)payload.scheduled_at=new Date(byId("publication-schedule").value).getTime()/1000;try{await api("/api/clips/"+activeId+"/publish","POST",false,payload);toast("Publicação enfileirada; aguardando confirmação da plataforma.");await refreshPublishing();}catch(e){toast(e.message);}});
byId("publication-process").addEventListener("click",async()=>{try{await api("/api/publishing/process","POST");await refreshPublishing();}catch(e){toast(e.message);}});
window.addEventListener("gta:clip-selected",loadEdit);
window.addEventListener("gta:clips-updated",()=>{loadEdit();renderBatch();refreshPublishing();});
window.addEventListener("gta:auth-updated",refreshPublishing);
