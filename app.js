// NBA Sniper Bet - app.js v4 - FIXED LIVE UPDATES ✅

const statusEl      = document.getElementById("status");
const gamesCont     = document.getElementById("games");
const modal         = document.getElementById("game-modal");
const modalClose    = document.getElementById("modal-close");
const modalBg       = document.getElementById("modal-close-bg");
const analysisPanel = document.getElementById("analysis-panel");
const updatedAtEl   = document.getElementById("updated-at");

let allGames     = [];
let filtroActual = "todos";

function openModal()  { modal.classList.remove("hidden"); modal.setAttribute("aria-hidden","false"); }
function closeModal() { modal.classList.add("hidden");    modal.setAttribute("aria-hidden","true"); }

function esc(v) {
  return String(v??'')
    .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
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

function pickCls(tipo) {
  if (!tipo) return "neu";
  const t = tipo.toUpperCase();
  if (t.includes("NO BET"))                        return "neu";
  if (t.includes("ESPERAR")||t.includes("REVISAR")) return "wait";
  if (t.includes("LEAN"))                           return "warn";
  return "pos";
}

function ouCls(ou) {
  if (ou==="OVER")  return "over";
  if (ou==="UNDER") return "under";
  return "neu";
}

// ── Estado de partido desde live data ─────────────────────────────────
function getGameState(g) {
  const live = g.live || {};
  const state = live.state || "pre";
  if (state === "in")   return "live";
  if (state === "post") return "final";
  return "upcoming";
}

function buildLiveBadge(g) {
  const live  = g.live || {};
  const state = live.state || "pre";

  if (state === "in") {
    const period = live.period || "?";
    const clock  = live.clock  || "";
    const hs = live.home_score ?? "—";
    const as_ = live.away_score ?? "—";
    return {
      badgeHtml: `<span class="game-badge badge-live">🔴 Q${period}${clock ? " · "+clock : ""}</span>`,
      scoreHtml: `<div class="score-live"><span class="score-val away">${esc(as_)}</span><span class="score-sep">—</span><span class="score-val home">${esc(hs)}</span></div>`
    };
  }

  if (state === "post") {
    const hs  = live.home_score ?? "—";
    const as_ = live.away_score ?? "—";
    return {
      badgeHtml: `<span class="game-badge badge-final">Final</span>`,
      scoreHtml: `<div class="score-final"><span class="score-val away">${esc(as_)}</span><span class="score-sep">—</span><span class="score-val home">${esc(hs)}</span></div>`
    };
  }

  // Upcoming
  return {
    badgeHtml: `<span class="game-badge badge-upcoming">${fmtHora(g.commence_time)}</span>`,
    scoreHtml: ""
  };
}

function formaChips(forma, right) {
  if (!forma||!forma.length) return `<span style="color:#94a3b8;font-size:12px">Sin datos</span>`;
  return `<div class="form-chips${right?" right":""}">
    ${forma.map(r=>`<span class="form-chip ${r==="G"?"win":"loss"}">${r}</span>`).join("")}
  </div>`;
}

function injStatusCls(s) {
  const v=(s||"").toLowerCase();
  if(v==="out"||v==="ofs")           return "out";
  if(v==="doubtful"||v==="doubt")    return "doubt";
  if(v==="questionable"||v==="ques") return "ques";
  return "prob";
}

// ── CARD ──────────────────────────────────────────────────────────────
function renderCard(g) {
  const odds    = g.odds || {};
  const rec     = g.recomendacion || {};
  const pCls    = pickCls(rec.tipo);
  const gameState = getGameState(g);
  const {badgeHtml, scoreHtml} = buildLiveBadge(g);

  const alertaHtml = g.alerta ? `
    <div class="alerta-banner">
      <div class="alerta-titulo">⚠️ Alerta — injury report</div>
      ${esc(g.alerta_msg)}
    </div>` : "";

  const hasOdds = odds.home_ml !== null && odds.home_ml !== undefined;
  const oddsHtml = hasOdds ? `
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
    </div>` : "";

  const evStr = rec.ev ? `EV +${rec.ev}%` : "";
  const pickHtml = rec.tipo && rec.tipo !== "NO BET" ? `
    <div class="pick-badge pick-${pCls}${gameState==="live"?" pick-historical":""}">
      <span class="pick-icono">🎯</span>
      <div class="pick-content">
        <span class="pick-label">${gameState==="live"?"Pick pre-partido":"Pick lado"}</span>
        <span class="pick-tipo ${pCls}">${esc(rec.tipo)}</span>
      </div>
      <div style="text-align:right">
        ${rec.ev ? `<span class="ev-tag">${evStr}</span>` : ""}
        <span class="pick-confianza">${rec.confianza&&rec.confianza!=="—"?"★ "+esc(rec.confianza):""}</span>
      </div>
    </div>` : "";

  const spreadHtml = rec.spread_lado ? `
    <div class="pick-badge pick-spread${gameState==="live"?" pick-historical":""}">
      <span class="pick-icono">📊</span>
      <div class="pick-content">
        <span class="pick-label">${gameState==="live"?"Spread pre-partido":"Pick spread"}</span>
        <span class="pick-tipo pos">${esc(rec.spread_lado)} ${odds.spread_home!=null?(odds.spread_home>0?"+":"")+odds.spread_home:""}</span>
      </div>
      <div style="text-align:right">
        ${rec.spread_ev ? `<span class="ev-tag">EV +${rec.spread_ev}%</span>` : ""}
        <span class="pick-confianza">${rec.spread_conf&&rec.spread_conf!=="—"?"★ "+esc(rec.spread_conf):""}</span>
      </div>
    </div>` : "";

  const ouHtml = rec.ou_pick ? `
    <div class="pick-badge pick-ou pick-${ouCls(rec.ou_pick)}${gameState==="live"?" pick-historical":""}">
      <span class="pick-icono">${rec.ou_pick==="OVER"?"📈":"📉"}</span>
      <div class="pick-content">
        <span class="pick-label">${gameState==="live"?"Total pre-partido":"Pick total"}</span>
        <span class="pick-tipo ${ouCls(rec.ou_pick)}">${esc(rec.ou_pick)} ${odds.total_ou?"O/U "+odds.total_ou:""}</span>
      </div>
      <div style="text-align:right">
        ${rec.ou_ev ? `<span class="ev-tag">EV +${rec.ou_ev}%</span>` : ""}
        <span class="pick-confianza">${rec.ou_confianza&&rec.ou_confianza!=="—"?"★ "+esc(rec.ou_confianza):""}</span>
      </div>
    </div>` : "";

  const gData = encodeURIComponent(JSON.stringify(g));

  return `
  <article class="game-card ${g.alerta?"has-alerta":""} card-${gameState}" data-game-id="${esc(g.id)}">
    ${alertaHtml}
    <div class="game-top">
      ${badgeHtml}
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
    ${scoreHtml}
    ${oddsHtml}
    ${pickHtml}
    ${spreadHtml}
    ${ouHtml}
    <div class="game-actions">
      <button class="analyze-btn" data-game="${gData}">Analizar partido</button>
    </div>
  </article>`;
}

// ── MODAL ─────────────────────────────────────────────────────────────
function renderAnalysis(g) {
  const hs       = g.home_stats || {};
  const as_      = g.away_stats || {};
  const odds     = g.odds || {};
  const rec      = g.recomendacion || {};
  const pCls     = pickCls(rec.tipo);
  const gameState = getGameState(g);
  const live     = g.live || {};

  let liveBannerHtml = "";
  if (gameState === "live") {
    liveBannerHtml = `
    <div class="live-result-banner banner-live">
      🔴 <strong>En vivo — Q${live.period}${live.clock?" · "+live.clock:""}</strong>
      &nbsp;&nbsp; ${esc(g.away_team.split(" ").slice(-1)[0])} <strong>${live.away_score||"—"}</strong>
      &nbsp;—&nbsp;
      <strong>${live.home_score||"—"}</strong> ${esc(g.home_team.split(" ").slice(-1)[0])}
      <span class="historical-note">· Análisis basado en datos pre-partido</span>
    </div>`;
  } else if (gameState === "final") {
    const winner = parseInt(live.home_score||0) > parseInt(live.away_score||0)
      ? g.home_team.split(" ").slice(-1)[0]
      : g.away_team.split(" ").slice(-1)[0];
    liveBannerHtml = `
    <div class="live-result-banner banner-final">
      ✅ <strong>Final</strong>
      &nbsp;&nbsp; ${esc(g.away_team.split(" ").slice(-1)[0])} <strong>${live.away_score||"—"}</strong>
      &nbsp;—&nbsp;
      <strong>${live.home_score||"—"}</strong> ${esc(g.home_team.split(" ").slice(-1)[0])}
      &nbsp; · Ganó <strong>${esc(winner)}</strong>
    </div>`;
  }

  const recLabel = gameState === "upcoming" ? "Pick recomendado" : "Pick pre-partido";
  const recHtml = `
  <div class="rec-box ${pCls}">
    <div class="rec-kicker">${recLabel}</div>
    <div class="rec-pick-row">
      <div class="rec-pick">${esc(rec.pick||"Sin pick")}</div>
      ${rec.ev ? `<div class="ev-badge-modal">${rec.ev > 0 ? "+" : ""}${rec.ev}% EV</div>` : ""}
    </div>
    <span class="rec-tipo ${pCls}">${esc(rec.tipo||"NO BET")}${rec.confianza&&rec.confianza!=="—"?" · Confianza: "+esc(rec.confianza):""}</span>
    <p class="rec-notas">${esc(rec.notas||"—")}</p>
    ${rec.prob_modelo ? `<div class="prob-row">
      <span class="prob-item">🤖 Modelo: <strong>${rec.prob_modelo}%</strong></span>
      <span class="prob-item">🏦 Mercado: <strong>${rec.prob_mercado}%</strong></span>
    </div>` : ""}
  </div>`;

  const spreadModalHtml = rec.spread_lado ? `
  <div class="rec-box pos ou-box">
    <div class="rec-kicker">Pick de spread</div>
    <div class="rec-pick-row">
      <div class="rec-pick">📊 ${esc(rec.spread_lado)} ${odds.spread_home!=null?(odds.spread_home>0?"+":"")+odds.spread_home:""}</div>
      ${rec.spread_ev ? `<div class="ev-badge-modal">+${rec.spread_ev}% EV</div>` : ""}
    </div>
    <span class="rec-tipo pos">SPREAD ${esc(rec.spread_lado)}${rec.spread_conf&&rec.spread_conf!=="—"?" · Confianza: "+esc(rec.spread_conf):""}</span>
    <p class="rec-notas">${esc(rec.spread_notas||"—")}</p>
  </div>` : `
  <div class="rec-box neu ou-box">
    <div class="rec-kicker">Pick de spread</div>
    <span class="rec-tipo neu">Sin EV suficiente</span>
    <p class="rec-notas">${esc(rec.spread_notas||"—")}</p>
  </div>`;

  const ouHtml = rec.ou_pick ? `
  <div class="rec-box ${ouCls(rec.ou_pick)} ou-box">
    <div class="rec-kicker">Pick de total (Over/Under)</div>
    <div class="rec-pick-row">
      <div class="rec-pick">${rec.ou_pick==="OVER"?"📈":"📉"} ${esc(rec.ou_pick)} ${odds.total_ou?"— Línea "+odds.total_ou:""}</div>
      ${rec.ou_ev ? `<div class="ev-badge-modal">+${rec.ou_ev}% EV</div>` : ""}
    </div>
    <span class="rec-tipo ${ouCls(rec.ou_pick)}">${rec.ou_pick}${rec.ou_confianza&&rec.ou_confianza!=="—"?" · Confianza: "+esc(rec.ou_confianza):""}</span>
    <p class="rec-notas">${esc(rec.ou_notas||"—")}</p>
  </div>` : `
  <div class="rec-box neu ou-box">
    <div class="rec-kicker">Pick de total (Over/Under)</div>
    <span class="rec-tipo neu">Sin señal suficiente</span>
    <p class="rec-notas">${esc(rec.ou_notas||"Sin datos suficientes para proyección.")}</p>
  </div>`;

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

  const oddsHtml = `
  <div class="odds-section">
    <div class="odds-section-title">Cuotas de apertura (pre-partido)</div>
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
    ${liveBannerHtml}
    ${recHtml}
    ${spreadModalHtml}
    ${ouHtml}
    ${injHtml}
    ${compareHtml}
    ${oddsHtml}
  </div>`;
}

// ── Filtro y render ────────────────────────────────────────────────────
function setFilter(tipo, el) {
  filtroActual = tipo;
  document.querySelectorAll(".tab").forEach(t=>t.classList.remove("active"));
  el.classList.add("active");
  renderGames();
}

function renderGames() {
  let lista = filtroActual === "alerta" ? allGames.filter(g=>g.alerta) : allGames;
  if (!lista.length) {
    gamesCont.innerHTML = `<div class="no-games">${filtroActual==="alerta"?"Sin alertas activas hoy.":"Sin partidos disponibles."}</div>`;
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

    const vivos    = allGames.filter(g=>g.live?.state==="in").length;
    const proximos = allGames.filter(g=>g.live?.state==="pre").length;
    const finales  = allGames.filter(g=>g.live?.state==="post").length;
    const alertas  = allGames.filter(g=>g.alerta).length;
    const ouPicks  = allGames.filter(g=>g.recomendacion?.ou_pick).length;

    statusEl.innerHTML =
      `<strong>${allGames.length}</strong> partidos · `
      + (vivos    ? `<strong style="color:#dc2626">🔴 ${vivos} en vivo</strong> · ` : "")
      + `<strong>${proximos}</strong> próximos · `
      + (finales  ? `<strong style="color:#64748b">${finales} finales</strong> · ` : "")
      + `<strong style="color:${alertas?"#b45309":"#64748b"}">${alertas} alertas</strong> · `
      + `<strong style="color:#1d428a">${ouPicks} picks O/U</strong>`;

    if (data.updated_at) updatedAtEl.textContent = fmtUpdated(data.updated_at);
    renderGames();
  } catch(e) {
    statusEl.textContent = "Error: "+e.message;
  }
}

// ── LIVE SCORES FIXED ─────────────────────────────────────────────────
const ESPN_SCOREBOARD_URL = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard';
let liveInterval = null;

async function actualizarScores() {
  try {
    const res = await fetch(ESPN_SCOREBOARD_URL);
    if (!res.ok) return;
    const data = await res.json();

    const scoreMap = {};
    for (const ev of data.events || []) {
      const comp   = ev.competitions?.[0];
      const status = comp?.status || {};
      const state  = status.type?.state || 'pre';
      const period = status.period || 0;
      const clock  = status.displayClock || '';
      const comps  = comp?.competitors || [];
      const home   = comps.find(c => c.homeAway === 'home');
      const away   = comps.find(c => c.homeAway === 'away');
      if (!home || !away) continue;

      const parseScore = s =>
        typeof s === 'object' ? (s.displayValue ?? s.value ?? '0') : String(s ?? '0');

      scoreMap[home.team.displayName] = {
        state, period, clock,
        home_score: parseScore(home.score),
        away_score: parseScore(away.score),
        away_name: away.team.displayName
      };
    }

    for (const g of allGames) {
      const fresh = scoreMap[g.home_team];
      if (!fresh) continue;

      g.live = fresh;

      const card = document.querySelector(`[data-game-id="${g.id}"]`);
      if (!card) continue;

      // Actualizar badge
      const badgeEl = card.querySelector('.game-badge');
      if (badgeEl) {
        if (fresh.state === 'in') {
          badgeEl.className = 'game-badge badge-live';
          badgeEl.innerHTML = `🔴 Q${fresh.period}${fresh.clock ? ' · ' + fresh.clock : ''}`;
          card.className = card.className.replace(/card-(upcoming|final)/g, 'card-live');
        } else if (fresh.state === 'post') {
          badgeEl.className = 'game-badge badge-final';
          badgeEl.textContent = 'Final';
          card.className = card.className.replace(/card-(upcoming|live)/g, 'card-final');
        }
      }

      // Actualizar score
      let scoreDiv = card.querySelector('.score-live, .score-final');
      if (!scoreDiv) {
        scoreDiv = document.createElement('div');
        const teamsDiv = card.querySelector('.teams');
        if (teamsDiv) teamsDiv.after(scoreDiv);
      }
      scoreDiv.className = fresh.state === 'in' ? 'score-live' : 'score-final';
      scoreDiv.innerHTML = `
        <span class="score-val away">${fresh.away_score}</span>
        <span class="score-sep">—</span>
        <span class="score-val home">${fresh.home_score}</span>
      `;
    }

  } catch(e) {
    console.warn('ESPN score update failed:', e.message);
  }
}

// ✅ FIX: Intervalo SIEMPRE activo cada 10s — sin condiciones
function iniciarLiveScores() {
  if (liveInterval) return;
  console.log("🔴 Live polling iniciado (10s)");
  actualizarScores();
  liveInterval = setInterval(actualizarScores, 10000);
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
iniciarLiveScores(); // ✅ SIEMPRE activo desde el inicio
