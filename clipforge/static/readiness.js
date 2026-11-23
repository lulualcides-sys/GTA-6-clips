/* Checklist "O que falta para funcionar" no Painel: estado real e botão que resolve. */
"use strict";
(function () {
  const list = document.getElementById("readiness-steps");
  const title = document.getElementById("readiness-title");
  const progress = document.getElementById("readiness-progress");
  if (!list) return;
  const make = (tag, text, cls) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; };

  async function act(action, button) {
    if (action.type === "view") { if (window.GTAShowView) window.GTAShowView(action.target); return; }
    button.disabled = true;
    try { await api(action.target, "POST", false, action.body || {}); toast(action.label + ": feito."); }
    catch (e) { toast(action.label + ": " + e.message); }
    finally { button.disabled = false; setTimeout(load, 1500); }
  }

  async function load() {
    try {
      const data = await api("/api/readiness");
      progress.textContent = `${data.done}/${data.total}`;
      progress.className = "tag " + (data.working ? "good" : "muted");
      title.textContent = data.working ? "✓ Tudo pronto: o app baixa, edita e manda os cortes para você revisar."
        : "O que falta para funcionar — siga o passo destacado:";
      list.replaceChildren();
      data.steps.forEach(step => {
        const li = make("li", undefined, "readiness-step" + (step.ok ? " ok" : "") + (step.key === data.next ? " next" : "") + (step.optional ? " optional" : ""));
        li.appendChild(make("span", step.ok ? "✓" : (step.key === data.next ? "➜" : "○"), "readiness-icon"));
        const text = make("div", undefined, "readiness-text");
        text.appendChild(make("strong", step.label + (step.optional ? " (opcional)" : "")));
        text.appendChild(make("small", step.detail));
        li.appendChild(text);
        if (!step.ok && step.action) {
          const b = make("button", step.action.label, "btn " + (step.key === data.next ? "primary" : "secondary"));
          b.type = "button"; b.addEventListener("click", () => act(step.action, b));
          li.appendChild(b);
        }
        list.appendChild(li);
      });
    } catch (e) { title.textContent = "Checklist: " + e.message; }
  }
  window.addEventListener("gta:auth-updated", load);
  window.addEventListener("gta:view", e => { if (e.detail === "inicio") load(); });
  setInterval(load, 20000);
  load();
})();
