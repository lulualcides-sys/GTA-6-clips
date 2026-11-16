/* QA real do editor. Executar somente contra uma cópia da demo sintética. */
import assert from "node:assert/strict";
import fs from "node:fs";
import { createRequire } from "node:module";
const { chromium } = createRequire(import.meta.url)("playwright");
const base=process.env.MISSION_URL||"http://127.0.0.1:8012";
const token=process.env.DASHBOARD_TOKEN||"mission-test-token-0123456789";
const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH||undefined});
fs.mkdirSync("ui-artifacts",{recursive:true});
try {
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  const errors=[];page.on("pageerror",e=>errors.push(e.message));
  await page.goto(base);
  await page.locator("#token").fill(token);
  await page.locator("#login-form button[type=submit]").click();
  try {
    await page.waitForFunction(()=>document.querySelector("#player").readyState>=2);
  } catch(error) {
    console.error("Diagnóstico de mídia",await page.locator("#player").evaluate(v=>({
      readyState:v.readyState,networkState:v.networkState,error:v.error?.message,
      h264:v.canPlayType('video/mp4; codecs="avc1.42E01E, mp4a.40.2"'),
      hasSource:Boolean(v.src),status:document.querySelector("#detail-status").textContent
    })),errors);
    await page.screenshot({path:"ui-artifacts/editor-failure.png",fullPage:true});
    throw error;
  }
  assert.equal(await page.locator("#player").evaluate(v=>v.videoWidth),1080);
  assert.equal(await page.locator("#player-placeholder").isHidden(),true,"Aviso de prévia deve desaparecer quando o vídeo carrega");
  assert.equal(await page.locator("#edit-title").isDisabled(),true,"Aprovado deve ficar protegido");
  await page.locator("#load-original").click();
  await page.waitForFunction(()=>document.querySelector("#original-player").readyState>=2);
  assert.equal(await page.locator("#original-player").evaluate(v=>v.videoWidth),960);
  // Nunca acionar FFmpeg quando a CLI AutoClip está ausente.
  assert.equal(await page.locator("#edit-fields").isDisabled(),true);
  await page.waitForFunction(()=>document.querySelector("#autoclip-status").textContent.includes("desativado"));
  await page.waitForFunction(()=>document.querySelector("#render").disabled);
  const videoId=await page.evaluate(()=>activeId);
  assert(videoId,"Clipe de teste não localizado");
  // Rejeitar versão anterior para permitir tentativa explícita de reedição.
  await page.locator("#reject").click();
  await page.waitForFunction(()=>document.querySelector("#detail-status").textContent==="Rejeitado");
  const preserved=await page.request.get(base+"/api/clips/"+videoId+"/video",{
    headers:{"Authorization":"Bearer "+token}
  });
  assert.equal(preserved.status(),200,"O MP4 antigo deve permanecer preservado");
  const renderDenied=await page.request.post(base+"/api/clips/"+videoId+"/render",{
    headers:{"Authorization":"Bearer "+token}
  });
  assert.equal(renderDenied.status(),409,"Render deve falhar sem AutoClip");
  assert.match((await renderDenied.json()).error,/AutoClip|desativado/i);
  const manualDenied=await page.request.post(base+"/api/clips/"+videoId+"/edit",{
    headers:{"Authorization":"Bearer "+token},
    data:{"layout":"focus"}
  });
  assert.equal(manualDenied.status(),409,"API de edição manual deve ser bloqueada");
  assert.match((await manualDenied.json()).error,/AutoClip/);
  assert.equal(await page.locator("#detail-status").textContent(),"Rejeitado");
  assert.equal(await page.locator("#hyperframes-captions").isChecked(),false);
  await page.screenshot({path:"ui-artifacts/editor-desktop.png",fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)<=2,"Editor mobile sem overflow horizontal");
  await page.screenshot({path:"ui-artifacts/editor-mobile.png",fullPage:true});
  assert.deepEqual(errors,[]);
  console.log("EDITOR BROWSER PASS: vídeo anterior preservado, original acessível, edição manual e fallback FFmpeg bloqueados, mobile");
} finally {await browser.close();}
