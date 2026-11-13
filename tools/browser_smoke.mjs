/* Visual QA for the real Mission Control page, not a simulated dashboard. */
import assert from "node:assert/strict";
import fs from "node:fs";
import { chromium } from "playwright";

const base=process.env.MISSION_URL || "http://127.0.0.1:8000";
const token=process.env.DASHBOARD_TOKEN || "mission-test-token-0123456789";
const browser=await chromium.launch({headless:true});
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
    return label && label.textContent.includes("OAuth não configurado");
  },null,{timeout:20000});
  assert(!((await page.locator("#twitch-last").textContent())||"").includes("Informe o token"));
  assert.equal(await page.locator(".agent-unit").count(),9);
  const states=await page.locator(".agent-unit").evaluateAll(nodes=>
    nodes.map(x=>({name:x.querySelector(".agent-name")?.textContent,state:x.dataset.state}))
  );
  assert(states.some(s=>s.name==="PUBLICAÇÃO" && s.state==="blocked"));
  assert(states.every(s=>s.state!=="running"),"Empty database cannot claim any agent is running");
  assert.equal(await page.locator("#agent-tasks").textContent(),"0");
  assert.equal(await page.locator("#mission-activity-count").textContent(),"0");
  assert.match(await page.title(),/GTA CLIPS CONTROL/);
  await page.screenshot({path:out+"/mission-desktop.png",fullPage:true});

  await page.setViewportSize({width:390,height:844});
  await page.waitForTimeout(500);
  const overflow=await page.evaluate(()=>
    document.documentElement.scrollWidth - window.innerWidth
  );
  assert(overflow<=2,"Mobile horizontal overflow: "+overflow+"px");
  assert.equal(await page.locator(".agent-unit").count(),9);
  await page.screenshot({path:out+"/mission-mobile.png",fullPage:true});
  console.log("MISSION BROWSER PASS: real idle/blocked states, 9 cards, mobile layout, 2 screenshots");
} finally {
  await browser.close();
}
