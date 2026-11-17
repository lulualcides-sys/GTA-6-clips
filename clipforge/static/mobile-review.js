"use strict";
const $=id=>document.getElementById(id);
let current=null;
let queue=[];
async function request(path,method="GET",body=null){
  const opts={method,credentials:"same-origin",cache:"no-store",headers:{}};
  if(body!==null){opts.headers["Content-Type"]="application/json";opts.body=JSON.stringify(body);}
  const res=await fetch(path,opts);
  if(!res.ok){let message="HTTP "+res.status;try{message=(await res.json()).error||message;}catch(_){}throw new Error(message);}
  return res.json();
}
function tell(value){$("message").textContent=value;}
function showPair(){ $("pair").hidden=false;$("review").hidden=true;$("video").pause();$("video").removeAttribute("src"); }
function info(analysis){
  if(!analysis || !analysis.analysis) return "Análise editorial ainda não realizada. Assista ao vídeo completo.";
  const item=analysis.analysis;
  if(item.error) return "Análise automática falhou: "+item.error+"\nRevise manualmente.";
  const tech=item.technical||{},vision=item.semantic||{};
  return [
    "QUALIDADE TÉCNICA: "+(tech.status||"não verificada"),
    ...(tech.warnings||[]),
    "CENA: "+(vision.status==="visual_partial"?(vision.category||"outro")+" — "+(vision.event||"sem descrição"):"Sem modelo com visão disponível"),
    vision.status==="visual_partial"?"Confiança relatada pelo modelo: "+Math.round(100*(vision.confidence||0))+"%":"Não há avaliação confiável de contexto.",
    "Limite: imagens amostradas; áudio e humor exigem conferência humana.",
  ].join("\n");
}
async function load(){
  try{
    const data=await request("/api/clips");
    queue=(data.clips||[]).filter(c=>c.status==="ready"&&c.output_path);
    $("pair").hidden=true;$("review").hidden=false;
    $("count").textContent=queue.length+" vídeo(s) aguardando aprovação";
    const host=$("items");host.replaceChildren();
    queue.forEach(item=>{
      const b=document.createElement("button");b.type="button";
      b.textContent=item.creator+" · "+item.filename.slice(0,33);
      b.setAttribute("aria-pressed",String(item.id===current));
      b.onclick=()=>openClip(item.id);
      host.appendChild(b);
    });
    if(!queue.length){current=null;$("selected").hidden=true;$("video").pause();$("video").removeAttribute("src");}
    else if(!queue.some(c=>c.id===current))await openClip(queue[0].id);
    const [learned,metrics]=await Promise.all([request("/api/editorial/summary"),request("/api/metrics")]);
    $("summary").textContent=(learned.reviewed||0)+" avaliações · "+(learned.approval_rate??"—")+"% de aprovações (quando disponível).";
    $("performance").textContent=metrics.measured_publications?
      "Métricas oficiais em "+metrics.measured_publications+" vídeo(s): "+(metrics.totals?.views||0)+" visualizações; retenção indisponível.":
      "Sem dados de desempenho verificados das plataformas. Nenhum número estimado.";
  }catch(e){if(/401|403|Unauthorized|não autorizado/i.test(e.message))showPair();tell(e.message);}
}
async function openClip(id){
  current=id;const item=queue.find(c=>c.id===id);if(!item)return;
  $("selected").hidden=false;$("clip-title").textContent=item.filename;
  $("clip-creator").textContent="Criador: "+item.creator;
  const video=$("video");video.pause();video.src="/api/clips/"+encodeURIComponent(id)+"/video";video.load();
  $("note").value="";
  try{const report=await request("/api/clips/"+encodeURIComponent(id)+"/editorial");
    $("qa").textContent=info(report);
  }catch(e){$("qa").textContent="Falha ao consultar análise: "+e.message;}
  document.querySelectorAll("#items button").forEach((node,i)=>node.setAttribute("aria-pressed",String(queue[i].id===id)));
}
async function decide(decision){
  if(!current)return;
  const id=current;const reason=decision==="reject"?$("reason").value:null;
  const button=$(decision);button.disabled=true;
  try{
    await request("/api/clips/"+encodeURIComponent(id)+"/review","POST",
      {decision,reason,note:$("note").value});
    tell("Decisão registrada. Nenhuma publicação automática.");
    await load();
  }catch(e){tell(e.message);}
  finally{button.disabled=false;}
}
$("pair-form").addEventListener("submit",async e=>{
  e.preventDefault();
  try{
    await request("/api/mobile/connect","POST",{code:$("pair-code").value});
    $("pair-code").value="";tell("Celular vinculado à revisão privada.");await load();
  }catch(err){tell("Vinculação: "+err.message);}
});
$("reload").addEventListener("click",load);
$("approve").addEventListener("click",()=>decide("approve"));
$("reject").addEventListener("click",()=>decide("reject"));
load();
