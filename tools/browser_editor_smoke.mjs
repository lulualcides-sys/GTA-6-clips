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
  await page.locator("#reject").click();
  await page.waitForFunction(()=>!document.querySelector("#edit-fields").disabled);
  await page.locator("#edit-title").fill("CORES EM MOVIMENTO — TESTE PRÓPRIO");
  await page.locator("#edit-verified").check();
  await page.locator("#edit-layout").selectOption("shorts");
  await page.locator("#edit-facecam").fill("0, 0, 240, 180");
  await page.locator("#edit-action").fill("240, 0, 500, 540");
  await page.locator("#edit-form button[type=submit]").click();
  await page.waitForFunction(()=>document.querySelector("#detail-status").textContent==="Detectado");
  await page.locator("#render").click();
  await page.waitForFunction(()=>document.querySelector("#detail-status").textContent==="Pronto para revisar",null,{timeout:180000});
  await page.waitForFunction(()=>document.querySelector("#player").readyState>=2);
  await page.locator(".editor-panel details").evaluate(e=>e.open=true);
  await page.locator("#batch-clips input").check();
  await page.locator("#approve-batch").click();
  await page.waitForFunction(()=>document.querySelector("#detail-status").textContent==="Aprovado");
  assert.equal(await page.locator("#hyperframes-captions").isChecked(),false);
  assert.match(await page.locator("#publication-jobs").textContent(),/SIMULATED-NOT-A-PUBLICATION/);
  assert.match(await page.locator("#publication-jobs").textContent(),/local-test-only/);
  await page.screenshot({path:"ui-artifacts/editor-desktop.png",fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)<=2,"Editor mobile sem overflow horizontal");
  await page.screenshot({path:"ui-artifacts/editor-mobile.png",fullPage:true});
  assert.deepEqual(errors,[]);
  console.log("EDITOR BROWSER PASS: MP4 original/editado, proteção aprovado, edição salva, render real, aprovação em lote, IDs/visibilidade, mobile");
} finally {await browser.close();}
