/* Visual QA for the real Mission Control page, not a simulated dashboard. */
import assert from "node:assert/strict";
import fs from "node:fs";
import { createRequire } from "node:module";
const { chromium } = createRequire(import.meta.url)("playwright");

const base=process.env.MISSION_URL || "http://127.0.0.1:8000";
const token=process.env.DASHBOARD_TOKEN || "mission-test-token-0123456789";
const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH||undefined});
const out="ui-artifacts";
fs.mkdirSync(out,{recursive:true});
try {
  const page=await browser.newPage({viewport:{width:1440,height:900},deviceScaleFactor:1});
  await page.goto(base,{waitUntil:"domcontentloaded"});
  await page.locator("#login-modal").waitFor({state:"visible",timeout:15000});
  await page.locator("#token").fill(token);
  await page.locator("#login-form button[type=submit]").click();
  await page.waitForFunction(()=>{
    const label=document.querySelector("#mission-connection");
    return label && label.textContent.includes("DADOS REAIS");
  },null,{timeout:20000});
  await page.waitForFunction(()=>{
    const label=document.querySelector("#twitch-state");
    return label && label.textContent.includes("Twitch não conectada");
  },null,{timeout:20000});
  assert(!((await page.locator("#twitch-last").textContent())||"").includes("Informe o token"));
  assert(await page.locator("#message").isHidden(),"Login cannot leave stale unauthorized toast over the UI");
  // IA do AutoClip: estado real do Ollama local, catálogo fechado de modelos.
  await page.waitForFunction(()=>{
    const n=document.querySelector("#local-ai-status");
    return n && document.querySelectorAll("#local-ai-model option").length===2 &&
      !n.textContent.includes("Verificando") && !n.textContent.includes("token");
  },null,{timeout:20000});
  assert.equal(await page.locator("#local-ai-model option").count(),2);
  // Teste de conexões: somente leitura; sem credenciais todos ficam "não configurado".
  await page.locator('.app-tab[data-view="ajustes"]').click();
  assert(await page.locator("#local-ai").isVisible(),"Aba Ajustes deve mostrar a IA do AutoClip");
  await page.locator("#connections-check").click();
  await page.waitForFunction(()=>document.querySelectorAll("#connections-result li").length===5,null,{timeout:20000});
  assert.equal(await page.locator("#connections-result li.good").count(),0);
  // Radar viral: dados reais (vazios sem Twitch), nunca clipes inventados.
  await page.waitForFunction(()=>{const n=document.querySelector("#viral-state");return n&&n.textContent.includes("potencial viral");},null,{timeout:20000});
  assert.equal(await page.locator("#viral-clips li.hint").count(),1);
  assert.equal(await page.locator(".agent-unit").count(),9);
  const states=await page.locator(".agent-unit").evaluateAll(nodes=>
    nodes.map(x=>({name:x.querySelector(".agent-name")?.textContent,state:x.dataset.state}))
  );
  assert(states.some(s=>s.name==="PUBLICAÇÃO" && s.state==="blocked"));
  assert(states.every(s=>s.state!=="running"),"Empty database cannot claim any agent is running");
  assert.equal(await page.locator("#agent-tasks").textContent(),"0");
  assert.equal(await page.locator("#mission-activity-count").textContent(),"0");
  assert.match(await page.title(),/GTA CLIPS CONTROL/);
  const theme=await page.request.get(base+"/studio-v2.css");
  assert.equal(theme.status(),200,"Studio V2 stylesheet must be served by the real app");
  assert.match(await theme.text(),/Studio V2/);
  // Radar YouTube: sem chave, nada inventado; só pede a conexão.
  await page.locator('.app-tab[data-view="youtube"]').click();
  await page.waitForFunction(()=>{const n=document.querySelector("#youtube-state");return n&&n.textContent.includes("Conecte o YouTube");},null,{timeout:20000});
  assert.equal(await page.locator("#youtube-channels li.hint").count(),1);
  assert.equal(await page.locator("#youtube-videos li.hint").count(),1);
  assert(((await page.locator("#youtube-pipeline").textContent())||"").includes("conecte a chave"));
  assert.equal(await page.locator("#youtube-run").isDisabled(),true,"Sem chave/autorização não pode baixar");
  // Layout por abas: 6 seções, cada uma cabe na tela sem rolar a página inteira.
  assert.equal(await page.locator(".app-tab[data-view]").count(),6);
  assert.equal(await page.locator("#production-workspace").count(),1);
  assert.equal(await page.locator("#twitch-monitor").count(),1);
  for (const view of ["inicio","clipes","radar","youtube","publicar","ajustes"]) {
    await page.locator(`.app-tab[data-view="${view}"]`).click();
    assert.equal(await page.locator(`.view[data-view="${view}"]`).isVisible(),true,view+" visível");
    assert.equal(await page.locator(".view:not([hidden])").count(),1,"Somente uma aba visível");
    const overflow=await page.evaluate(()=>document.documentElement.scrollHeight-window.innerHeight);
    assert(overflow<=2,`Aba ${view} não pode rolar a página no desktop (${overflow}px)`);
  }
  await page.locator('.app-tab[data-view="inicio"]').click();
  const themeApplied=await page.locator(".panel").first().evaluate(node=>
    getComputedStyle(node).borderRadius
  );
  assert.equal(themeApplied,"17px","Visual theme must apply, not merely load");
  // Isolated CSS fixture; never changes real telemetry or renders fake activity.
  const animationCheck=await page.evaluate(()=>{
    const fixture=document.createElement("div");
    fixture.className="agent-unit";
    fixture.dataset.state="running";
    fixture.style.cssText="position:absolute;top:-9999px";
    document.body.appendChild(fixture);
    const running=getComputedStyle(fixture).animationName;
    const ring=getComputedStyle(fixture,"::before").animationName;
    fixture.dataset.state="idle";
    const idle=getComputedStyle(fixture).animationName;
    fixture.remove();
    return {running,ring,idle};
  });
  assert.match(animationCheck.running,/studio-live-card/,"Only active modules should pulse");
  assert.match(animationCheck.ring,/studio-live-ring/,"Active modules need a pulse halo");
  assert.equal(animationCheck.idle,"none","Inactive stages must remain still");
  // Render the real stage DOM, then inspect a detached off-screen copy.
  // This never reports invented execution in the dashboard or its snapshots.
  assert.equal(await page.locator(".agent-unit .agent-worker").count(),9);
  const operatorCheck=await page.evaluate(()=>{
    const original=document.querySelector(".agent-unit");
    const cloned=original.cloneNode(true);
    cloned.style.cssText="position:absolute;top:-9999px;left:0";
    document.body.append(cloned);
    const worker=cloned.querySelector(".agent-worker");
    const head=cloned.querySelector(".worker-head");
    const idle=getComputedStyle(worker).animationName;
    cloned.dataset.state="running";
    const running=getComputedStyle(worker).animationName;
    const headRunning=getComputedStyle(head).animationName;
    cloned.dataset.state="complete";
    const completed=getComputedStyle(worker).animationName;
    cloned.remove();
    return {idle,running,headRunning,completed};
  });
  assert.equal(operatorCheck.idle,"none","Idle operator must be still");
  assert.match(operatorCheck.running,/operator-bob/,"Real running state should animate its character");
  assert.match(operatorCheck.headRunning,/operator-nod/,"Working character must visibly act");
  assert.equal(operatorCheck.completed,"none","Completed operator must stop moving");
  await page.emulateMedia({reducedMotion:"reduce"});
  const reducedMotionCheck=await page.evaluate(()=>{
    const copy=document.querySelector(".agent-unit").cloneNode(true);
    copy.style.cssText="position:absolute;top:-9999px;left:0";
    copy.dataset.state="running";
    document.body.append(copy);
    const name=getComputedStyle(copy.querySelector(".agent-worker")).animationName;
    copy.remove();
    return name;
  });
  assert.equal(reducedMotionCheck,"none","Reduced-motion users must see a static character");
  await page.emulateMedia({reducedMotion:"no-preference"});
  await page.screenshot({path:out+"/mission-desktop.png",fullPage:true});

  // App Windows: token aleatório chega no fragmento #desktop-token=…; nenhum
  // pedido de token pode aparecer (regressão da v0.8.0, quando as abas apagavam o fragmento).
  const desktopPage=await browser.newPage({viewport:{width:1366,height:768}});
  await desktopPage.goto(base+"/#desktop-token="+encodeURIComponent(token),{waitUntil:"domcontentloaded"});
  await desktopPage.waitForFunction(()=>{
    const label=document.querySelector("#mission-connection");
    return label && label.textContent.includes("DADOS REAIS");
  },null,{timeout:20000});
  assert.equal(await desktopPage.locator("#login-modal").isVisible(),false,"App Windows não pode pedir token");
  assert(!desktopPage.url().includes("desktop-token"),"Token não pode permanecer na URL");
  await desktopPage.close();

  await page.setViewportSize({width:768,height:1024});
  const tabletOverflow=await page.evaluate(()=>
    document.documentElement.scrollWidth-window.innerWidth
  );
  assert(tabletOverflow<=2,"Tablet horizontal overflow: "+tabletOverflow+"px");

  await page.setViewportSize({width:390,height:844});
  await page.waitForTimeout(500);
  const overflow=await page.evaluate(()=>
    document.documentElement.scrollWidth - window.innerWidth
  );
  assert(overflow<=2,"Mobile horizontal overflow: "+overflow+"px");
  assert.equal(await page.locator(".agent-unit").count(),9);
  await page.screenshot({path:out+"/mission-mobile.png",fullPage:true});
  console.log("MISSION BROWSER PASS: actual Studio V2 theme, real idle/blocked states, 9 animated-when-running operators, tablet/mobile layout, 2 screenshots");
} finally {
  await browser.close();
}
