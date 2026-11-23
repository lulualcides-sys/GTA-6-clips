/* Navegação por abas: cada seção ocupa uma tela, sem rolar a página inteira. */
"use strict";
(function () {
  const VIEWS = ["inicio", "clipes", "radar", "youtube", "atividade", "publicar", "ajustes"];
  const tabs = Array.from(document.querySelectorAll(".app-tab[data-view]"));
  const views = Array.from(document.querySelectorAll(".view[data-view]"));
  if (!tabs.length || !views.length) return;

  // O app Windows entrega o token do painel no #desktop-token=…; app.js lê e
  // limpa esse fragmento. Nunca sobrescrevê-lo antes disso.
  const carriesToken = () => location.hash.startsWith("#desktop-token=");

  function remembered() {
    if (carriesToken()) return "inicio";
    const fromHash = location.hash.replace("#", "");
    if (VIEWS.includes(fromHash)) return fromHash;
    try {
      const saved = localStorage.getItem("nexus_view");
      if (VIEWS.includes(saved)) return saved;
    } catch (_) { /* armazenamento indisponível */ }
    return "inicio";
  }

  function show(name) {
    if (!VIEWS.includes(name)) name = "inicio";
    views.forEach(v => { v.hidden = v.dataset.view !== name; });
    tabs.forEach(t => {
      const active = t.dataset.view === name;
      t.classList.toggle("active", active);
      if (active) t.setAttribute("aria-current", "page"); else t.removeAttribute("aria-current");
    });
    document.body.dataset.view = name;
    try { localStorage.setItem("nexus_view", name); } catch (_) { /* opcional */ }
    if (!carriesToken() && location.hash !== "#" + name) history.replaceState(null, "", "#" + name);
    window.dispatchEvent(new CustomEvent("gta:view", { detail: name }));
  }

  tabs.forEach(t => t.addEventListener("click", () => show(t.dataset.view)));
  window.addEventListener("hashchange", () => { if (!carriesToken()) show(location.hash.replace("#", "")); });
  window.GTAShowView = show;
  // Selecionar um clipe em qualquer lugar leva à aba de revisão.
  window.addEventListener("gta:clip-selected", () => {
    if (document.body.dataset.view !== "clipes") show("clipes");
  });

  // Avisos nas abas a partir dos próprios dados exibidos (sem chamadas extras).
  function watch(id, update) {
    const node = document.getElementById(id);
    if (!node) return;
    update(node);
    new MutationObserver(() => update(node)).observe(node, { childList: true, characterData: true, subtree: true });
  }
  watch("stat-ready", node => {
    const badge = document.getElementById("tab-badge-clipes");
    const count = parseInt(node.textContent, 10) || 0;
    badge.textContent = String(count);
    badge.hidden = count === 0;
    badge.title = count + " clipe(s) aguardando revisão";
  });
  watch("local-ai-status", node => {
    const badge = document.getElementById("tab-badge-ajustes");
    const text = node.textContent || "";
    badge.hidden = text.includes("pronta") || text.includes("Verificando") || text.includes("token");
    badge.title = "A IA do AutoClip ainda não está pronta";
  });

  const pubState = document.getElementById("publication-state");
  if (pubState) {
    pubState.title = "Clique para ver os detalhes";
    pubState.addEventListener("click", () => pubState.classList.toggle("expanded"));
  }

  show(remembered());
})();
