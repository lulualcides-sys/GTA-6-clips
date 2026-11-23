/* Atividade (histórico, lives, falhas), configurações do AutoClip e exportação.
   Tudo vem da API real; textContent em todo dado vindo do servidor. */
"use strict";
(function () {
  const $ = id => document.getElementById(id);
  const make = (tag, text, cls) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; };
  const when = iso => { if (!iso) return "—"; const d = new Date(iso); return isNaN(d) ? iso : d.toLocaleString("pt-BR"); };
  const STATUS = {downloading: "Baixando", done: "Concluído", failed: "Falhou", queued: "Na fila", skipped: "Ignorado"};
  const LIVE = {live: "Ao vivo agora", ended: "Encerrada", vod_found: "VOD encontrada", vod_downloaded: "VOD baixada → AutoClip",
    vod_failed: "VOD falhou", no_vod: "Sem gravação", vod_error: "Erro ao buscar VOD"};

  /* ---------- Histórico / lives / falhas ---------- */
  let seenFailures = null;
  async function loadActivity() {
    try {
      const filter = $("ingest-filter").value;
      const data = await api("/api/ingest/history" + (filter ? "?status=" + filter : ""));
      const c = data.counts || {};
      $("ingest-summary").textContent = `Concluídos ${c.done || 0} · Baixando ${c.downloading || 0} · Falhas ${c.failed || 0}. ` +
        `Twitch: ${data.twitch?.ready ? "pronto" : "aguardando requisitos"} · YouTube: ${data.youtube?.ready ? "pronto" : "aguardando requisitos"}.`;
      const body = $("ingest-rows"); body.replaceChildren();
      if (!data.items.length) { const tr = make("tr"); const td = make("td", "Nenhum download ainda. Autorize canais no Radar e ligue o download.", "hint"); td.colSpan = 5; tr.appendChild(td); body.appendChild(tr); }
      data.items.forEach(r => {
        const tr = make("tr");
        tr.appendChild(make("td", when(r.updated_at)));
        tr.appendChild(make("td", `${r.platform === "twitch" ? "Twitch" : "YouTube"} · ${r.source_name || r.source_id}`));
        tr.appendChild(make("td", `${r.kind === "vod" ? "VOD" : r.kind === "clip" ? "Clipe" : "Vídeo"}: ${r.title || r.item_id}`));
        const st = make("td", STATUS[r.status] || r.status, "status " + (r.status === "failed" ? "failed" : r.status === "done" ? "ready" : ""));
        if (r.error) st.title = r.error;
        tr.appendChild(st);
        tr.appendChild(make("td", r.trigger === "manual" ? "Manual" : "Automático"));
        body.appendChild(tr);
        if (r.error) { const er = make("tr"); const td = make("td", "↳ " + r.error, "hint bad"); td.colSpan = 5; er.appendChild(td); body.appendChild(er); }
      });
    } catch (e) { $("ingest-summary").textContent = "Histórico: " + e.message; }
    try {
      const live = await api("/api/live");
      $("live-summary").textContent = !live.enabled ? "Monitor de lives desligado (TWITCH_LIVE_MONITOR=0)." :
        `${live.live_now.length} ao vivo agora · verificação a cada ${Math.round(live.poll_seconds / 60)} min · ` +
        (live.vod_download ? "VOD baixada automaticamente ao fim da live." : "Download de VOD desligado: marque a opção acima.") +
        (live.last_error ? " · " + live.last_error : "");
      $("live-vod").checked = !!live.vod_download;
      const list = $("live-rows"); list.replaceChildren();
      if (!live.sessions.length) list.appendChild(make("li", "Nenhuma live registrada dos streamers autorizados ainda.", "hint"));
      live.sessions.forEach(s => {
        const li = make("li");
        li.appendChild(make("strong", s.broadcaster_name || s.broadcaster_id));
        li.appendChild(make("span", ` · ${LIVE[s.status] || s.status} · ${s.title || ""}`, s.status === "live" ? "ok" : ""));
        li.appendChild(make("span", `Início ${when(s.started_at)}${s.ended_at ? " · fim " + when(s.ended_at) : ""}${s.error ? " · " + s.error : ""}`, "meta"));
        list.appendChild(li);
      });
    } catch (e) { $("live-summary").textContent = "Lives: " + e.message; }
    try {
      const n = await api("/api/notifications");
      const list = $("notify-rows"); list.replaceChildren();
      if (!n.items.length) list.appendChild(make("li", "Nenhuma falha nas últimas 24 horas.", "hint"));
      n.items.forEach(item => {
        const li = make("li");
        li.appendChild(make("strong", `${item.area}${item.platform ? " · " + item.platform : ""} — ${item.automatic ? "Automático" : "Manual"}`));
        li.appendChild(make("span", `${item.title}: ${item.message}`, "meta bad"));
        if (item.at) li.appendChild(make("span", when(item.at), "meta"));
        list.appendChild(li);
      });
      const badge = $("tab-badge-atividade");
      badge.textContent = String(n.count); badge.hidden = n.count === 0;
      badge.title = n.count + " falha(s) nas últimas 24 h";
      if (seenFailures !== null && n.count > seenFailures && typeof toast === "function")
        toast("Nova falha registrada. Veja a aba Atividade.");
      seenFailures = n.count;
    } catch (_) { /* token ainda não informado */ }
  }
  $("ingest-filter").addEventListener("change", loadActivity);
  $("live-vod").addEventListener("change", async () => {
    const on = $("live-vod").checked;
    try { await api("/api/live/settings", "POST", false, on ? {vod_download: true, public_download: true} : {vod_download: false});
      toast(on ? "Download de VOD ligado (inclui o download público dos autorizados)." : "Download de VOD desligado."); }
    catch (e) { toast("Lives: " + e.message); $("live-vod").checked = !on; }
    loadActivity();
  });
  $("ingest-run").addEventListener("click", async () => {
    $("ingest-run").disabled = true;
    try {
      const r = await api("/api/ingest/run", "POST");
      const s = r.started || {};
      toast(`Verificação manual: Twitch ${s.twitch ? "iniciada" : "sem requisitos/ocupada"} · YouTube ${s.youtube ? "iniciada" : "sem requisitos/ocupada"} · lives verificando.`);
    } catch (e) { toast("Verificar agora: " + e.message); }
    finally { $("ingest-run").disabled = false; setTimeout(loadActivity, 3000); }
  });

  /* ---------- Configurações do AutoClip ---------- */
  function fillSelect(sel, entries, value) {
    sel.replaceChildren();
    entries.forEach(([k, label]) => { const o = make("option", label); o.value = k; sel.appendChild(o); });
    sel.value = value;
  }
  function preview() {
    const box = $("acs-preview"), text = $("acs-preview-text");
    text.style.fontFamily = $("acs-font").value === "Inter" ? "Inter, sans-serif" : "Anton, Impact, sans-serif";
    text.style.fontSize = (Number($("acs-size").value) * 2.4) + "px";
    text.style.color = $("acs-primary").value;
    text.style.textTransform = $("acs-caps").checked ? "uppercase" : "none";
    text.style.background = $("acs-boxed").checked ? "rgba(0,0,0,.7)" : "transparent";
    text.style.webkitTextStroke = $("acs-boxed").checked ? "0" : "1px " + $("acs-outline").value;
    text.style.bottom = $("acs-position").value + "%";
    text.style.setProperty("--acs-accent", $("acs-noaccent").checked ? $("acs-primary").value : $("acs-accent").value);
    box.dataset.preset = $("acs-preset").value;
  }
  async function loadSettings() {
    try {
      const d = await api("/api/autoclip/settings"), s = d.settings;
      fillSelect($("acs-preset"), Object.entries(d.presets), s.caption_preset);
      fillSelect($("acs-framing"), Object.entries(d.framing), s.framing);
      fillSelect($("acs-font"), d.fonts.map(f => [f, f]), s.font);
      $("acs-max").value = s.max_clips; $("acs-size").value = s.size_percent; $("acs-position").value = s.position_percent;
      $("acs-primary").value = s.primary; $("acs-accent").value = s.accent || "#FFE500"; $("acs-outline").value = s.outline;
      $("acs-words").value = s.max_words; $("acs-boxed").checked = s.boxed; $("acs-caps").checked = s.all_caps;
      $("acs-noaccent").checked = !s.accent;
      $("acs-state").textContent = d.custom_supported ? "Vale para as próximas edições. Vertical 9:16, legendas sincronizadas pelo Whisper do AutoClip." :
        "Legenda personalizada exige o AutoClip do app Windows; aqui ela usa o estilo pronto mais próximo.";
      preview();
    } catch (e) { $("acs-state").textContent = "AutoClip: " + e.message; }
  }
  ["acs-font", "acs-size", "acs-primary", "acs-accent", "acs-outline", "acs-position", "acs-boxed", "acs-caps", "acs-noaccent", "acs-preset"]
    .forEach(id => $(id).addEventListener("input", preview));
  $("acs-form").addEventListener("submit", async e => {
    e.preventDefault();
    const body = {max_clips: Number($("acs-max").value), framing: $("acs-framing").value, caption_preset: $("acs-preset").value,
      font: $("acs-font").value, size_percent: Number($("acs-size").value), position_percent: Number($("acs-position").value),
      primary: $("acs-primary").value.toUpperCase(), accent: $("acs-noaccent").checked ? "" : $("acs-accent").value.toUpperCase(),
      outline: $("acs-outline").value.toUpperCase(), max_words: Number($("acs-words").value),
      boxed: $("acs-boxed").checked, all_caps: $("acs-caps").checked};
    try { await api("/api/autoclip/settings", "POST", false, body); $("acs-state").textContent = "✓ Salvo. As próximas edições do AutoClip usam essas opções."; }
    catch (err) { $("acs-state").textContent = "Não salvou: " + err.message; }
  });

  /* ---------- Exportação ---------- */
  async function loadExports() {
    const list = $("exp-list"); list.replaceChildren();
    const id = window.activeId || (typeof activeId !== "undefined" ? activeId : null);
    const clip = (typeof clips !== "undefined" ? clips : []).find(c => c.id === id);
    $("exp-run").disabled = !clip || !["ready", "approved"].includes(clip.status);
    if (clip && !$("exp-title").value) $("exp-title").value = clip.filename.replace(/\.[^.]+$/, "");
    if (!id) return;
    try {
      const d = await api("/api/exports");
      d.exports.filter(x => x.clip_id === id).forEach(x => {
        const li = make("li");
        const link = make("button", "Baixar " + x.file, "btn text-btn"); link.type = "button";
        link.addEventListener("click", async () => {
          try { const blob = await api("/api/exports/" + encodeURIComponent(x.file), "GET", true);
            const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = x.file; a.click();
            setTimeout(() => URL.revokeObjectURL(a.href), 5000); } catch (err) { toast("Download: " + err.message); }
        });
        li.appendChild(link);
        li.appendChild(make("span", `${x.options.format.toUpperCase()} · ${x.options.resolution} · ${x.lossless ? "sem perda (cópia direta)" : "qualidade " + x.options.quality} · ${(x.size_bytes / 1048576).toFixed(1)} MB`, "meta"));
        const del = make("button", "Apagar", "btn text-btn"); del.type = "button";
        del.addEventListener("click", async () => { try { await api("/api/exports/" + encodeURIComponent(x.file) + "/delete", "POST"); loadExports(); } catch (err) { toast(err.message); } });
        li.appendChild(del);
        list.appendChild(li);
      });
    } catch (_) { /* sem token */ }
  }
  $("export-form").addEventListener("submit", async e => {
    e.preventDefault();
    const id = typeof activeId !== "undefined" ? activeId : null;
    if (!id) return;
    $("exp-run").disabled = true; $("exp-state").textContent = "Exportando… (vídeos longos com reencode podem levar minutos)";
    const body = {format: $("exp-format").value, resolution: $("exp-res").value, quality: $("exp-quality").value,
      start: Number($("exp-start").value || 0), title: $("exp-title").value};
    if ($("exp-end").value) body.end = Number($("exp-end").value);
    try { const r = await api("/api/clips/" + id + "/export", "POST", false, body);
      $("exp-state").textContent = "✓ " + r.file + (r.lossless ? " (sem perda de qualidade)" : "");
      loadExports(); }
    catch (err) { $("exp-state").textContent = "Exportação: " + err.message; }
    finally { $("exp-run").disabled = false; }
  });
  window.addEventListener("gta:clip-selected", () => { $("exp-title").value = ""; $("exp-state").textContent = ""; setTimeout(loadExports, 50); });
  window.addEventListener("gta:auth-updated", () => { loadActivity(); loadSettings(); loadExports(); });
  setInterval(loadActivity, 30000);
  loadActivity(); loadSettings();
})();
