// NBA Sniper Bet - app.js v3

const statusEl     = document.getElementById("status");
const gamesCont    = document.getElementById("games");
const modal        = document.getElementById("game-modal");
const modalClose   = document.getElementById("modal-close");
const modalBg      = document.getElementById("modal-close-bg");
const analysisPanel= document.getElementById("analysis-panel");
const updatedAtEl  = document.getElementById("updated-at");

let allGames = [];
let filtroActual = "todos";

function openModal()  { modal.classList.remove("hidden"); modal.setAttribute("aria-hidden","false"); }
function closeModal() { modal.classList.add("hidden");    modal.setAttribute("aria-hidden","true"); }

function esc(v) {
  return String(v??"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
    .replace(/"/g,"&quot;").replace(/'/g,"&#39;");
}

function fmtHora(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString("es-CL",{hour:"2-digit",minute:"2-digit",timeZone:"America/Santiago"});
}

function fmtFecha(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("es-CL",{weekday:"long",day:"numeric",month:"long",timeZone:"America/Santiago"});
}

function fmtUpdated(iso) {
  if (!iso) return "";
  return "Actualizado: "+new Date(iso).toLocaleString("es-CL",{hour:"2-digit",minute:"2-digit",day:"numeric",month:"short",timeZone:"America/Santiago"});
}

function fmtOdds(v) {
  if (v===null||v===undefined) return "—";
  return v>0?"+"+v:String(v);
}

function oddsClass(v) {
  if (v===null||v===undefined) return "muted";
  return v>0?"pos":"neg";
}

function esProximo(g) { return new Date(g.commence_time)>new Date(); }
function esVivo(g)    { const d=(Date.now()-new Date(g.commence_time))/60000; return d>0&&d<180; }

function statusInfo(g) {
  if (esVivo(g))    return {txt:"En vivo",    cls:""};
  if (esProximo(g)) return {txt:"Próximo",    cls:"is-scheduled"};
  return                   {txt:"Finalizado", cls:"is-final"};
}

function pickCls(tipo) {
  if (!tipo) return "neu";
  const t = tipo.toUpperCase();
  if (t.includes("NO BET"))                  return "neu";
  if (t.includes("ESPERAR")||t.includes("REVISAR")) return "wait";
  if (t.includes("LEAN"))                    return "warn";
  return "pos";
}

function ouCls(ou_pick) {
  if (ou_pick==="OVER")  return "over";
  if (ou_pick==="UNDER") return "under";
  return "neu";
}

function formaChips(forma, right) {
  if (!forma||!forma.length) return `<span style="color:#94a3b8;font-size:12px">Sin datos</span>`;
  return `<div class="form-chips${right?" right":""}">
    ${forma.map(r=>`<span class="form-chip ${r==="G"?"win":"loss"}">${r}</span>`).join("")}
  </div>`;
}

function injStatusCls(s) {
  const v=(s||"").toLowerCase();
  if(v==="out"||v==="ofs")            return "out";
  if(v==="doubtful"||v==="doubt")     return "doubt";
  if(v==="questionable"||v==="ques")  return "ques";
  return "prob";
}

// ── CARD ─────────────────────────────────────────────────────────────

function renderCard(g) {
  const odds = g.odds||{};
  const rec  = g.recomendacion||{};
  const st   = statusInfo(g);
  const pCls = pickCls(rec.tipo);

  const alertaHtml = g.alerta ? `
    <div class="alerta-banner">
      <div class="alerta-titulo">⚠️ Alerta — injury report</div>
      ${esc(g.alerta_msg)}
    </div>` : "";

  // Odds row
  const oddsHtml = `
    <div class="odds-row">
      <div class="odds-cell">
        <div class="odds-cell-label">Moneyline</div>
        <div class="odds-pair">
          <span class="odds-val ${oddsClass(odds.away_ml)}">${fmtOdds(odds.away_ml)}</span>
          <span class="odds-val ${oddsClass(odds.home_ml)}">${fmtOdds(odds.home_ml)}</span>
        </div>
      </div>
      <div class="odds-cell">
        <div class="odds-cell-label">Spread</div>
        <div class="odds-pair">
          <span class="odds-val muted">—</span>
          <span class="odds-val neu">${odds.spread_home!=null?(odds.spread_home>0?"+":"")+odds.spread_home:"—"}</span>
        </div>
      </div>
      <div class="odds-cell">
        <div class="odds-cell-label">Total O/U</div>
        <div class="odds-pair">
          <span class="odds-val neu" style="font-size:12px">${odds.total_ou?"O/U "+odds.total_ou:"—"}</span>
        </div>
      </div>
    </div>`;

  // Pick lado
  const pickHtml = rec.tipo && rec.tipo!=="NO BET" ? `
    <div class="pick-badge pick-${pCls}">
      <span class="pick-icono">🎯</span>
      <div class="pick-content">
        <span class="pick-label">Pick lado</span>
        <span class="pick-tipo ${pCls}">${esc(rec.tipo)}</span>
      </div>
      <span class="pick-confianza">${rec.confianza!=="—"?"★ "+esc(rec.confianza):""}</span>
    </div>` : "";

  // Pick O/U
  const ouHtml = rec.ou_pick ? `
    <div class="pick-badge pick-ou pick-${ouCls(rec.ou_pick)}">
      <span class="pick-icono">${rec.ou_pick==="OVER"?"📈":"📉"}</span>
      <div class="pick-content">
        <span class="pick-label">Pick total</span>
        <span class="pick-tipo ${ouCls(rec.ou_pick)}">${esc(rec.ou_pick)} ${odds.total_ou?"O/U "+odds.total_ou:""}</span>
      </div>
      <span class="pick-confianza">${rec.ou_confianza!=="—"?"★ "+esc(rec.ou_confianza):""}</span>
    </div>` : "";

  const gData = encodeURIComponent(JSON.stringify(g));

  return `
  <article class="game-card ${g.alerta?"has-alerta":""}">
    ${alertaHtml}
    <div class="game-top">
      <span class="game-status">${esc(st.txt)}</span>
      <span class="game-date">${fmtHora(g.commence_time)}</span>
    </div>
    <div class="teams">
      <div class="team-row">
        <span class="team-name">${esc(g.away_team)}</span>
        <strong class="team-label-role">V</strong>
      </div>
      <div class="team-row">
        <span class="team-name">${esc(g.home_team)}</span>
        <strong class="team-label-role">L</strong>
      </div>
    </div>
    ${oddsHtml}
    ${pickHtml}
    ${ouHtml}
    <div class="live-extra ${st.cls}">${esc(st.txt)} · ${fmtHora(g.commence_time)}</div>
    <div class="game-actions">
      <button class="analyze-btn" data-game="${gData}">Analizar partido</button>
    </div>
  </article>`;
}

// ── MODAL ─────────────────────────────────────────────────────────────

function renderAnalysis(g) {
  const hs   = g.home_stats||{};
  const as_  = g.away_stats||{};
  const odds = g.odds||{};
  const rec  = g.recomendacion||{};
  const pCls = pickCls(rec.tipo);

  // Recomendación lado
  const recHtml = `
  <div class="rec-box ${pCls}">
    <div class="rec-kicker">Pick de lado</div>
    <div class="rec-pick">${esc(rec.pick||"Sin pick")}</div>
    <span class="rec-tipo ${pCls}">${esc(rec.tipo||"NO BET")}${rec.confianza&&rec.confianza!=="—"?" · Confianza: "+esc(rec.confianza):""}</span>
    <p class="rec-notas">${esc(rec.notas||"—")}</p>
  </div>`;

  // Recomendación O/U
  const ouHtml = rec.ou_pick ? `
  <div class="rec-box ${ouCls(rec.ou_pick)} ou-box">
    <div class="rec-kicker">Pick de total (Over/Under)</div>
    <div class="rec-pick">${rec.ou_pick==="OVER"?"📈":"📉"} ${esc(rec.ou_pick)} ${odds.total_ou?"— Línea "+odds.total_ou:""}</div>
    <span class="rec-tipo ${ouCls(rec.ou_pick)}">${rec.ou_pick}${rec.ou_confianza&&rec.ou_confianza!=="—"?" · Confianza: "+esc(rec.ou_confianza):""}</span>
    <p class="rec-notas">${esc(rec.ou_notas||"—")}</p>
  </div>` : `
  <div class="rec-box neu ou-box">
    <div class="rec-kicker">Pick de total (Over/Under)</div>
    <span class="rec-tipo neu">Sin señal suficiente</span>
    <p class="rec-notas">${esc(rec.ou_notas||"Datos insuficientes para proyección.")}</p>
  </div>`;

  // Injuries
  const injuries = (g.injuries||[]).filter(i=>i.weight>0);
  const injHtml = injuries.length ? `
  <div class="injury-section">
    <div class="injury-title">Injury Report</div>
    <div class="injury-list">
      ${injuries.map(i=>`
        <div class="injury-item ${i.high_impact?"clave":""}">
          <span class="inj-status ${injStatusCls(i.status)}">${esc(i.status)}</span>
          <span>${esc(i.player)}</span>
          ${i.high_impact?`<span class="inj-clave">⚠️ Jugador clave</span>`:""}
        </div>`).join("")}
    </div>
  </div>` : `<div class="injury-section"><div class="injury-title">Injury Report</div><p style="font-size:13px;color:#94a3b8">Sin bajas confirmadas.</p></div>`;

  // Comparativa
  function wins(r){ return parseInt((r||"0-0").split("-")[0])||0; }
  const wH=wins(hs.record), wA=wins(as_.record);

  function row(vA,label,vH,eA,eH){
    return `<div class="pregame-row">
      <div class="away ${eA?"edge":""}">${vA}</div>
      <div class="metric">${esc(label)}</div>
      <div class="home ${eH?"edge":""}">${vH}</div>
    </div>`;
  }

  const compareHtml = `
  <div class="pregame-shell">
    <div class="pregame-compare">
      <div class="pregame-row pregame-head">
        <div>${esc(g.away_team)}</div><div>Métrica</div><div>${esc(g.home_team)}</div>
      </div>
      ${row(esc(as_.conference||"—"),"Conferencia",esc(hs.conference||"—"),false,false)}
      ${row(esc(`${as_.record||"—"} · #${as_.seed||"—"}`),"Récord / Posición",esc(`${hs.record||"—"} · #${hs.seed||"—"}`),wA>wH,wH>wA)}
      ${row(formaChips(as_.forma,false),"Últimos 5",formaChips(hs.forma,true),false,false)}
      ${row(esc(as_.ppg||"—"),"Puntos anotados",esc(hs.ppg||"—"),parseFloat(as_.ppg)>parseFloat(hs.ppg),parseFloat(hs.ppg)>parseFloat(as_.ppg))}
      ${row(esc(as_.papg||"—"),"Puntos recibidos",esc(hs.papg||"—"),parseFloat(as_.papg)<parseFloat(hs.papg),parseFloat(hs.papg)<parseFloat(as_.papg))}
      ${row(esc(as_.diff||"—"),"Diferencial",esc(hs.diff||"—"),parseFloat(as_.diff)>parseFloat(hs.diff),parseFloat(hs.diff)>parseFloat(as_.diff))}
      ${row(esc(`Visita: ${as_.away_rec||"—"}`),"Forma fuera/casa",esc(`Casa: ${hs.home_rec||"—"}`),false,false)}
      ${row(esc(as_.streak||"—"),"Racha",esc(hs.streak||"—"),false,false)}
    </div>
  </div>`;

  // Odds table
  const oddsHtml = `
  <div class="odds-section">
    <div class="odds-section-title">Cuotas por casa de apuestas</div>
    <table class="odds-table">
      <thead><tr>
        <th>Casa</th>
        <th>${esc((g.away_team||"").split(" ").slice(-1)[0])} ML</th>
        <th>${esc((g.home_team||"").split(" ").slice(-1)[0])} ML</th>
        <th>Spread local</th>
        <th>Total O/U</th>
      </tr></thead>
      <tbody>
        <tr>
          <td><strong>${esc(odds.best_book||"Mejor")}</strong><span class="best-tag">mejor ML</span></td>
          <td class="${oddsClass(odds.away_ml)}">${fmtOdds(odds.away_ml)}</td>
          <td class="${oddsClass(odds.home_ml)}">${fmtOdds(odds.home_ml)}</td>
          <td>${odds.spread_home!=null?(odds.spread_home>0?"+":"")+odds.spread_home:"—"}</td>
          <td>${odds.total_ou||"—"}</td>
        </tr>
        <tr>
          <td colspan="5" style="font-size:11px;color:#94a3b8">${odds.num_books||0} casas consultadas</td>
        </tr>
      </tbody>
    </table>
  </div>`;

  return `
  <div class="analysis-box">
    <div class="analysis-header">
      <h3>${esc(g.away_team)} vs ${esc(g.home_team)}</h3>
      <p class="analysis-subtitle">Análisis pregame NBA</p>
      <p class="analysis-date">${fmtFecha(g.commence_time)} · ${fmtHora(g.commence_time)} (Chile)</p>
    </div>
    ${recHtml}
    ${ouHtml}
    ${injHtml}
    ${compareHtml}
    ${oddsHtml}
  </div>`;
}

// ── Filtro ────────────────────────────────────────────────────────────

function setFilter(tipo, el) {
  filtroActual = tipo;
  document.querySelectorAll(".tab").forEach(t=>t.classList.remove("active"));
  el.classList.add("active");
  renderGames();
}

function renderGames() {
  let lista = filtroActual==="alerta" ? allGames.filter(g=>g.alerta) : allGames;
  if (!lista.length) {
    gamesCont.innerHTML=`<div class="no-games">${filtroActual==="alerta"?"Sin alertas activas hoy.":"Sin partidos disponibles."}</div>`;
    return;
  }
  gamesCont.innerHTML = lista.map(renderCard).join("");
}

// ── Carga ─────────────────────────────────────────────────────────────

async function cargarDatos() {
  statusEl.textContent = "Cargando datos...";
  try {
    const res = await fetch(`data/games.json?t=${Date.now()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    allGames = data.games||[];
    const proximos = allGames.filter(esProximo).length;
    const alertas  = allGames.filter(g=>g.alerta).length;
    const ouPicks  = allGames.filter(g=>g.recomendacion?.ou_pick).length;
    statusEl.innerHTML = `Se cargaron <strong>${allGames.length}</strong> partidos · <strong>${proximos}</strong> próximos · `
      +`<strong style="color:${alertas?"#b45309":"#64748b"}">${alertas} alertas</strong> · `
      +`<strong style="color:#1d428a">${ouPicks} picks O/U</strong>`;
    if (data.updated_at) updatedAtEl.textContent = fmtUpdated(data.updated_at);
    renderGames();
  } catch(e) {
    statusEl.textContent = "Error: "+e.message;
  }
}

// ── Events ────────────────────────────────────────────────────────────

gamesCont.addEventListener("click", e => {
  const btn = e.target.closest(".analyze-btn");
  if (!btn) return;
  const g = JSON.parse(decodeURIComponent(btn.dataset.game));
  document.getElementById("modal-title").textContent = `${g.away_team} vs ${g.home_team}`;
  analysisPanel.innerHTML = renderAnalysis(g);
  openModal();
});

modalClose.addEventListener("click", closeModal);
modalBg.addEventListener("click", closeModal);
document.addEventListener("keydown", e=>{ if(e.key==="Escape") closeModal(); });

cargarDatos();
