#!/usr/bin/env python3
"""
NBA Sniper Bet - Scraper
Fuentes: ESPN API (scoreboard + standings + schedules) + Rotowire + The Odds API
Output: data/games.json
"""

import json, re, sys, os
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError

ODDS_API_KEY  = "1823578c582e34ab968083d68997a9d1"
ODDS_API_URL  = (
    "https://api.the-odds-api.com/v4/sports/basketball_nba/odds/"
    f"?apiKey={ODDS_API_KEY}&regions=us&markets=h2h,spreads,totals&oddsFormat=american"
)
ROTOWIRE_URL  = "https://www.rotowire.com/basketball/nba-lineups.php"
ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
ESPN_STANDINGS  = "https://site.api.espn.com/apis/v2/sports/basketball/nba/standings?season=2025"
ESPN_SCHEDULE   = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/schedule?season=2025"

HIGH_IMPACT = [
    "embiid","jokic","giannis","lebron","curry","durant","luka","tatum",
    "mitchell","fox","wembanyama","booker","towns","lillard","morant",
    "brunson","harden","george","davis","edwards","siakam","sabonis","sga"
]
STATUS_W = {"out":3,"doubtful":2,"doubt":2,"questionable":1,"ques":1,"probable":0,"prob":0,"ofs":0}

# Zona horaria ET (UTC-4 verano / UTC-5 invierno)
ET_OFFSET = timedelta(hours=-4)

# Mapa de nombre de equipo NBA (The Odds API) → palabras clave de jugadores en Rotowire
TEAM_KEYWORDS = {
    "Atlanta Hawks":            ["hawks","trae","young","murray","capela","hunter","johnson","bogdanovic","okongwu"],
    "Boston Celtics":           ["celtics","tatum","brown","white","holiday","porzingis","horford","pritchard"],
    "Brooklyn Nets":            ["nets","bridges","thomas","claxton","johnson","curry","warren"],
    "Charlotte Hornets":        ["hornets","lamelo","ball","miller","washington","plumlee","richards"],
    "Chicago Bulls":            ["bulls","lavine","vucevic","derozan","white","drummond","caruso","ball"],
    "Cleveland Cavaliers":      ["cavaliers","cavs","mitchell","garland","mobley","allen","strus","wade","max strus","dean wade","tyson","isaac okoro"],
    "Dallas Mavericks":         ["mavericks","mavs","luka","doncic","irving","kleber","hardaway","green","gafford"],
    "Denver Nuggets":           ["nuggets","jokic","murray","gordon","porter","caldwell","nnaji","brown"],
    "Detroit Pistons":          ["pistons","cunningham","ivey","stewart","duren","hayes","levert","bey","robinson","harris"],
    "Golden State Warriors":    ["warriors","curry","thompson","green","wiggins","looney","kuminga","moody"],
    "Houston Rockets":          ["rockets","green","porter","brooks","sengun","tate","christopher","edwards"],
    "Indiana Pacers":           ["pacers","haliburton","siakam","nembhard","mathurin","turner","nesmith"],
    "Los Angeles Clippers":     ["clippers","george","harden","zubac","mann","batum","coffey","powell"],
    "Los Angeles Lakers":       ["lakers","lebron","davis","reaves","vanderbilt","hayes","walker","westbrook"],
    "Memphis Grizzlies":        ["grizzlies","morant","aldama","brooks","bane","adams","tillman","ziaire","tyus","ja morant","wells","pippen","mashack","small","ty jerome","clarke"],
    "Miami Heat":               ["heat","butler","adebayo","herro","lowry","robinson","vincent","strus","highsmith"],
    "Milwaukee Bucks":          ["bucks","giannis","middleton","dame","lillard","portis","lopez","brook"],
    "Minnesota Timberwolves":   ["timberwolves","wolves","edwards","towns","gobert","conley","mcdaniels","naz"],
    "New Orleans Pelicans":     ["pelicans","zion","williamson","ingram","mccollum","valanciunas","jones","murphy"],
    "New York Knicks":          ["knicks","brunson","randle","barrett","robinson","hartenstein","quickley"],
    "Oklahoma City Thunder":    ["thunder","sga","holmgren","dort","giddey","williams","jalen","manning","wallace"],
    "Orlando Magic":            ["magic","banchero","suggs","fultz","harris","wagner","black","isaac","carter","howard","levert"],
    "Philadelphia 76ers":       ["76ers","sixers","embiid","maxey","harden","harris","thybulle","house","niang","drummond","bryant","gibson","hendricks","paul","george"],
    "Phoenix Suns":             ["suns","booker","paul","ayton","bridges","johnson","shamet","landry"],
    "Portland Trail Blazers":   ["blazers","lillard","grant","sharpe","simons","nurkic","little","krejci","vit krejci","jones","watson","brown","nnaji"],
    "Sacramento Kings":         ["kings","fox","sabonis","huerter","murray","holmes","monk","barnes"],
    "San Antonio Spurs":        ["spurs","wembanyama","keldon","johnson","sochan","vassell","collins","primo","zach edey","edey","pope","aldama","clarke"],
    "Toronto Raptors":          ["raptors","siakam","anunoby","quickley","barrett","koloko","trent","gary"],
    "Utah Jazz":                ["jazz","markkanen","clarkson","sexton","beasley","olynyk","vanderbilt","hendricks"],
    "Washington Wizards":       ["wizards","beal","kuzma","porzingis","avdija","gafford","holiday","kispert"],
}


def get_today_et():
    now_et = datetime.now(timezone.utc) + ET_OFFSET
    return now_et.date()


def es_partido_de_hoy(commence_iso):
    try:
        dt_utc = datetime.fromisoformat(commence_iso.replace("Z", "+00:00"))
        dt_et  = dt_utc + ET_OFFSET
        return dt_et.date() == get_today_et()
    except:
        return False


def fetch_url(url):
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html,application/json,*/*"
    })
    try:
        with urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8", errors="ignore")
    except URLError as e:
        print(f"  ERROR {url[:60]}: {e}", file=sys.stderr)
        return None


def fetch_json(url):
    raw = fetch_url(url)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except:
        return None


# ── ESPN ──────────────────────────────────────────────────────────────

def fetch_espn_scoreboard():
    print("  ESPN scoreboard...")
    return fetch_json(ESPN_SCOREBOARD) or {}


def build_live_scores_map(scoreboard):
    """
    Extrae score, periodo, reloj y estado de cada partido del scoreboard ESPN.
    Retorna dict keyed por nombres de equipo normalizados.
    """
    live_map = {}
    for ev in scoreboard.get("events", []):
        comp  = ev.get("competitions", [{}])[0]
        comps = comp.get("competitors", [])
        status = comp.get("status", {})
        state  = status.get("type", {}).get("state", "pre")  # pre / in / post
        period = status.get("period", 0)
        clock  = status.get("displayClock", "")
        desc   = status.get("type", {}).get("description", "")

        home = next((c for c in comps if c.get("homeAway") == "home"), None)
        away = next((c for c in comps if c.get("homeAway") == "away"), None)
        if not home or not away:
            continue

        home_name  = home.get("team", {}).get("displayName", "")
        away_name  = away.get("team", {}).get("displayName", "")
        home_score = home.get("score", "")
        away_score = away.get("score", "")

        # Normalizar score — a veces viene como dict
        if isinstance(home_score, dict):
            home_score = home_score.get("displayValue", home_score.get("value", ""))
        if isinstance(away_score, dict):
            away_score = away_score.get("displayValue", away_score.get("value", ""))

        entry = {
            "state":      state,
            "period":     period,
            "clock":      clock,
            "description": desc,
            "home_score": str(home_score) if home_score != "" else None,
            "away_score": str(away_score) if away_score != "" else None,
        }

        live_map[home_name] = entry
        live_map[away_name] = entry

    return live_map


def fetch_espn_standings():
    print("  ESPN standings...")
    data = fetch_json(ESPN_STANDINGS)
    if not data:
        return {}

    lookup = {}
    for conference in data.get("children", []):
        conf_name = conference.get("name", "")
        conf_label = "Este" if "East" in conf_name else "Oeste"
        entries = conference.get("standings", {}).get("entries", [])
        for entry in entries:
            team_id = str(entry.get("team", {}).get("id", ""))
            team_name = entry.get("team", {}).get("displayName", "")
            stats = {s["name"]: s.get("displayValue", s.get("value","")) for s in entry.get("stats", [])}
            lookup[team_id] = {
                "team_name": team_name,
                "conference": conf_label,
                "record":   stats.get("overall", "—"),
                "seed":     stats.get("playoffSeed", "—"),
                "ppg":      stats.get("avgPointsFor", "—"),
                "papg":     stats.get("avgPointsAgainst", "—"),
                "diff":     stats.get("differential", "—"),
                "home_rec": stats.get("Home", "—"),
                "away_rec": stats.get("Road", "—"),
                "streak":   stats.get("streak", "—"),
                "win_pct":  stats.get("winPercent", "—"),
            }
    return lookup


def fetch_team_form(team_id, game_date_iso):
    data = fetch_json(ESPN_SCHEDULE.format(team_id=team_id))
    if not data:
        return []

    target_ts = datetime.fromisoformat(game_date_iso.replace("Z", "+00:00")).timestamp()
    
    # Filtrar partidos completados ANTES del partido actual
    completed = []
    for event in data.get("events", []):
        ev_date = event.get("date", "")
        try:
            ev_ts = datetime.fromisoformat(ev_date.replace("Z", "+00:00")).timestamp()
        except:
            continue
        if ev_ts >= target_ts:
            continue
        comp = event.get("competitions", [{}])[0]
        status = comp.get("status", {}).get("type", {})
        if not status.get("completed"):
            continue
        completed.append((ev_ts, event))

    # Ordenar descendente — más reciente primero
    completed.sort(key=lambda x: x[0], reverse=True)

    results = []
    for _, event in completed:
        comp = event.get("competitions", [{}])[0]
        competitors = comp.get("competitors", [])
        my_team = next((c for c in competitors if str(c.get("team",{}).get("id","")) == str(team_id)), None)
        if not my_team:
            continue
        winner = my_team.get("winner", False)
        results.append("G" if winner else "P")
        if len(results) == 5:
            break

    return results


# ── Rotowire ──────────────────────────────────────────────────────────

def parse_rotowire(html):
    clean = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    clean = re.sub(r'<style[^>]*>.*?</style>',  '', clean, flags=re.DOTALL)
    clean = re.sub(r'<[^>]+>', ' ', clean)
    clean = re.sub(r'&amp;','&', clean)
    clean = re.sub(r'&nbsp;',' ', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()

    player_pat = re.compile(
        r'([A-Z][a-z]+(?:\s[A-Z][a-z.-]+)*)\s+(Out|Doubtful|Doubt|Questionable|Ques|Probable|Prob|OFS)',
        re.IGNORECASE
    )
    time_pat = re.compile(
        r'(\d+:\d+\s*[AP]M\s*ET)(.*?)(?=\d+:\d+\s*[AP]M\s*ET|\Z)', re.DOTALL
    )

    blocks = []
    for time_et, block in time_pat.findall(clean):
        mnp_sections = re.findall(
            r'MAY NOT PLAY(.*?)(?=MAY NOT PLAY|LINE\s|\Z)', block, re.DOTALL
        )
        all_injuries = []
        for section in mnp_sections:
            for player, status in player_pat.findall(section):
                sl = status.lower()
                w  = STATUS_W.get(sl, 0)
                is_key = any(kw in player.lower() for kw in HIGH_IMPACT)
                all_injuries.append({
                    "player": player.strip(),
                    "status": status.capitalize(),
                    "weight": w,
                    "high_impact": is_key
                })

        blocks.append({
            "time_et": time_et.strip(),
            "injuries": all_injuries,
        })

    total_inj = sum(len(b["injuries"]) for b in blocks)
    print(f"  Rotowire: {len(blocks)} bloques horarios, {total_inj} injuries totales")
    return blocks


def filter_injuries_by_teams(all_injuries, home_team, away_team):
    home_kws = [kw.lower() for kw in TEAM_KEYWORDS.get(home_team, [])]
    away_kws = [kw.lower() for kw in TEAM_KEYWORDS.get(away_team, [])]
    allowed_kws = set(home_kws + away_kws)

    filtered = []
    for inj in all_injuries:
        player_lower = inj["player"].lower()
        match = any(
            kw in player_lower or player_lower in kw
            for kw in allowed_kws
        )
        if match:
            filtered.append(inj)

    return filtered


def build_alerta(injuries):
    alerta, msgs = False, []
    for inj in injuries:
        if inj["weight"] >= 2:
            alerta = True
            msgs.append(f"{inj['player']} ({inj['status']})" + (" ⚠️ CLAVE" if inj["high_impact"] else ""))
        elif inj["weight"] >= 1 and inj["high_impact"]:
            alerta = True
            msgs.append(f"{inj['player']} (Questionable) — jugador clave")
    return alerta, " | ".join(msgs)


def et_to_min(et_str):
    try:
        m = re.match(r'(\d+):(\d+)\s*([AP]M)', et_str.strip(), re.IGNORECASE)
        if not m: return -1
        h, mi, p = int(m.group(1)), int(m.group(2)), m.group(3).upper()
        if p == 'PM' and h != 12: h += 12
        if p == 'AM' and h == 12: h = 0
        return h * 60 + mi
    except:
        return -1


# ── The Odds API ──────────────────────────────────────────────────────

def fetch_odds():
    print("  The Odds API...")
    data = fetch_url(ODDS_API_URL)
    if not data: return []
    try:    return json.loads(data)
    except: return []


def extract_odds(odds_event):
    home = odds_event.get("home_team","")
    away = odds_event.get("away_team","")
    best_home_ml, best_away_ml, spread_home, total_ou, best_book = None, None, None, None, ""

    for bm in odds_event.get("bookmakers", []):
        for mkt in bm.get("markets", []):
            if mkt["key"] == "h2h":
                for o in mkt["outcomes"]:
                    if o["name"] == home and (best_home_ml is None or o["price"] > best_home_ml):
                        best_home_ml = o["price"]; best_book = bm["title"]
                    if o["name"] == away and (best_away_ml is None or o["price"] > best_away_ml):
                        best_away_ml = o["price"]
            elif mkt["key"] == "spreads" and spread_home is None:
                for o in mkt["outcomes"]:
                    if o["name"] == home: spread_home = o.get("point")
            elif mkt["key"] == "totals" and total_ou is None:
                for o in mkt["outcomes"]:
                    if o["name"] == "Over": total_ou = o.get("point")

    return {"home_ml": best_home_ml, "away_ml": best_away_ml,
            "spread_home": spread_home, "total_ou": total_ou,
            "best_book": best_book, "num_books": len(odds_event.get("bookmakers",[]))}


# ── EV ────────────────────────────────────────────────────────────────

def ml_to_prob(ml):
    """Convierte moneyline americano a probabilidad implícita del mercado (sin vig)."""
    if ml is None:
        return None
    if ml > 0:
        return 100 / (ml + 100)
    else:
        return abs(ml) / (abs(ml) + 100)


def calcular_win_prob(home_stats, away_stats, injuries, es_local):
    """
    Estima win probability del equipo LOCAL usando fórmula revisada:
      - Diferencial de puntos:        55%
      - PPG/PAPG relativo:            25%
      - Home/Away record específico:  15%
      - Forma últimos 5:               5%
    Retorna (prob_home_win, prob_away_win)
    """
    try:
        # ── 1. Diferencial (55%) ──────────────────────────────────────
        diff_h = float(str(home_stats.get("diff", "0")).replace("+", ""))
        diff_a = float(str(away_stats.get("diff", "0")).replace("+", ""))
        # El diferencial máximo real en NBA es ~+12, usamos 24 como rango total
        raw_diff = diff_h - diff_a
        score_diff = max(min(raw_diff / 12.0, 1.0), -1.0)  # normalizado [-1, 1]

        # ── 2. PPG/PAPG relativo (25%) ────────────────────────────────
        ppg_h  = float(str(home_stats.get("ppg",  "110")))
        papg_h = float(str(home_stats.get("papg", "110")))
        ppg_a  = float(str(away_stats.get("ppg",  "110")))
        papg_a = float(str(away_stats.get("papg", "110")))
        # Proyección de margen basada en eficiencia cruzada
        proj_home = (ppg_h + papg_a) / 2
        proj_away = (ppg_a + papg_h) / 2
        proj_margin = proj_home - proj_away
        score_ppg = max(min(proj_margin / 15.0, 1.0), -1.0)  # normalizado [-1, 1]

        # ── 3. Home/Away record específico (15%) ──────────────────────
        def rec_to_pct(rec_str):
            try:
                w, l = map(int, rec_str.split("-"))
                return w / (w + l) if (w + l) > 0 else 0.5
            except:
                return 0.5

        home_home_pct = rec_to_pct(home_stats.get("home_rec", "0-0"))  # local como local
        away_away_pct = rec_to_pct(away_stats.get("away_rec", "0-0"))  # visitante como visitante
        score_rec = (home_home_pct - away_away_pct)  # rango aprox [-1, 1]

        # ── 4. Forma últimos 5 (5%) ───────────────────────────────────
        forma_h = home_stats.get("forma", [])
        forma_a = away_stats.get("forma", [])
        wins_h = sum(1 for r in forma_h if r == "G") / max(len(forma_h), 1)
        wins_a = sum(1 for r in forma_a if r == "G") / max(len(forma_a), 1)
        score_forma = (wins_h - wins_a)  # rango [-1, 1]

        # ── Score compuesto ponderado ─────────────────────────────────
        score = (
            0.55 * score_diff  +
            0.25 * score_ppg   +
            0.15 * score_rec   +
            0.05 * score_forma
        )

        # ── Penalización por bajas ────────────────────────────────────
        # Bajas del equipo local reducen su probabilidad
        any_out = [i for i in injuries if i["weight"] >= 2]
        high_out = [i for i in injuries if i["weight"] >= 2 and i["high_impact"]]
        baja_penalty = len(any_out) * 0.02 + len(high_out) * 0.05
        score -= baja_penalty

        # ── Mapeo logístico a probabilidad ───────────────────────────
        # Usamos función logística: prob = 1 / (1 + e^(-k*score))
        # k=3 da una curva razonablemente empinada sin extremos
        import math
        k = 3.0
        prob_home = 1 / (1 + math.exp(-k * score))
        prob_away = 1 - prob_home

        return round(prob_home, 4), round(prob_away, 4)

    except Exception as e:
        return 0.5, 0.5


def calcular_ev_ml(prob_estimada, ml):
    """
    EV% = (prob_estimada * pago_neto) - (1 - prob_estimada)
    donde pago_neto = ml/100 si ml>0, o 100/abs(ml) si ml<0
    Retorna EV como porcentaje (ej: +5.2 o -3.1)
    """
    if ml is None or prob_estimada is None:
        return None
    if ml > 0:
        pago_neto = ml / 100
    else:
        pago_neto = 100 / abs(ml)
    ev = (prob_estimada * pago_neto) - (1 - prob_estimada)
    return round(ev * 100, 1)  # como porcentaje


def calcular_ev_ou(proj_total, linea, num_bajas=0):
    """
    Para O/U, la prob. implícita del mercado es ~52.4% (precio -110 estándar).
    Estimamos prob. del OVER basada en distancia proyección vs línea.
    EV% = (prob_over * 0.909) - (1 - prob_over)  → precio -110 paga 0.909x
    """
    if proj_total is None or linea is None:
        return None, None
    import math
    diff = proj_total - linea
    # Función logística sobre la diferencia: k=0.25 da curva suave
    prob_over = 1 / (1 + math.exp(-0.25 * diff))
    prob_under = 1 - prob_over
    pago = 100 / 110  # precio estándar -110

    ev_over  = round(((prob_over  * pago) - prob_under) * 100, 1)
    ev_under = round(((prob_under * pago) - prob_over)  * 100, 1)
    return ev_over, ev_under


def calcular_ev_spread(proj_margin, spread_home, num_bajas=0):
    """
    Estimamos prob de cubrir el spread local usando logística sobre
    (margen proyectado - spread de mercado).
    Precio estándar -110.
    """
    if proj_margin is None or spread_home is None:
        return None, None
    import math
    # spread_home es negativo si el local es favorito (ej: -7.5)
    # El local cubre si gana por más que abs(spread_home)
    edge = proj_margin - abs(spread_home) if spread_home < 0 else proj_margin + spread_home
    prob_cover_home = 1 / (1 + math.exp(-0.3 * edge))
    prob_cover_away = 1 - prob_cover_home
    pago = 100 / 110

    ev_home = round(((prob_cover_home * pago) - prob_cover_away) * 100, 1)
    ev_away = round(((prob_cover_away * pago) - prob_cover_home) * 100, 1)
    return ev_home, ev_away


# ── Recomendación ─────────────────────────────────────────────────────

def calcular_rec(home, away, odds, injuries, home_stats, away_stats):
    notas = []
    pick, tipo, confianza = "Sin pick", "NO BET", "—"
    hs, as_ = home.split()[-1], away.split()[-1]

    high_out = [i for i in injuries if i["weight"] >= 2 and i["high_impact"]]
    any_out  = [i for i in injuries if i["weight"] >= 2]
    doubtful = [i for i in injuries if i["weight"] == 1]

    # ── Calcular probabilidades estimadas ────────────────────────────
    prob_home, prob_away = calcular_win_prob(home_stats, away_stats, injuries, es_local=True)

    # ── EV Moneyline ─────────────────────────────────────────────────
    ev_ml_home = calcular_ev_ml(prob_home, odds.get("home_ml"))
    ev_ml_away = calcular_ev_ml(prob_away, odds.get("away_ml"))

    # ── EV O/U ───────────────────────────────────────────────────────
    try:
        ppg_h  = float(str(home_stats.get("ppg",  "0")))
        ppg_a  = float(str(away_stats.get("ppg",  "0")))
        papg_h = float(str(home_stats.get("papg", "0")))
        papg_a = float(str(away_stats.get("papg", "0")))
        total_ou_line = odds.get("total_ou")

        proj_home_score = (ppg_h + papg_a) / 2
        proj_away_score = (ppg_a + papg_h) / 2
        proj_total_base = proj_home_score + proj_away_score
        baja_penalty    = len(any_out) * 2.5
        proj_total      = round(proj_total_base - baja_penalty, 1)
        proj_margin     = round(proj_home_score - proj_away_score, 1)

        ev_over, ev_under = calcular_ev_ou(proj_total, total_ou_line)
        diff_ou = round(proj_total - float(total_ou_line), 1) if total_ou_line else None
    except:
        proj_total, proj_margin, diff_ou = None, None, None
        ev_over, ev_under = None, None

    # ── EV Spread ────────────────────────────────────────────────────
    ev_spread_home, ev_spread_away = calcular_ev_spread(
        proj_margin, odds.get("spread_home"), len(any_out)
    )

    # ── Pick de lado (ML) ─────────────────────────────────────────────
    if high_out:
        names = ", ".join(i["player"] for i in high_out)
        notas.append(f"Baja clave: {names} — mercado puede no haberlo ajustado aún")
        if odds["away_ml"] is not None:
            pick, tipo, confianza = away, f"ML {as_}", "media-alta"

    elif any_out:
        names = ", ".join(i["player"] for i in any_out)
        notas.append(f"Bajas confirmadas: {names} — revisar impacto en línea")
        tipo, confianza = "REVISAR", "pendiente"

    elif doubtful:
        names = ", ".join(i["player"] for i in doubtful)
        notas.append(f"En duda: {names} — esperar confirmación")
        tipo, confianza = "ESPERAR", "pendiente"

    if tipo == "NO BET":
        ml_h = odds.get("home_ml")
        ml_a = odds.get("away_ml")
        # ── Lógica contextual con EV: solo sugerir si EV > 0 ─────────
        if ev_ml_away is not None and ev_ml_away > 0 and ml_a is not None and ml_a >= 250:
            # Filtros contextuales anti-mecánicos
            diff_h = float(str(home_stats.get("diff", "0")).replace("+", ""))
            diff_a = float(str(away_stats.get("diff", "0")).replace("+", ""))
            spread = abs(odds.get("spread_home") or 0)
            forma_a = away_stats.get("forma", [])
            wins_recientes_a = sum(1 for r in forma_a if r == "G")
            # Solo sugerir si: diferencial no es enorme Y spread no excesivo Y forma tolerable
            if (diff_a > diff_h - 8) and (spread <= 12) and (wins_recientes_a >= 1):
                notas.append(f"{as_} underdog con EV positivo (+{ev_ml_away}%) — mercado puede exagerar")
                pick, tipo, confianza = away, f"ML {as_} (underdog)", "baja" if ev_ml_away < 5 else "media"
            else:
                notas.append(f"{as_} underdog pero sin valor contextual (spread {spread:.1f}, forma {wins_recientes_a}/5, diff gap {diff_h-diff_a:.1f})")
        elif ev_ml_home is not None and ev_ml_home > 0 and ml_h is not None and ml_h >= 180:
            notas.append(f"{hs} local underdog con EV positivo (+{ev_ml_home}%) — situación atípica")
            pick, tipo, confianza = home, f"ML {hs} (local underdog)", "baja" if ev_ml_home < 5 else "media"
        else:
            # Sin pick de ML con EV claro — usar diferencial como LEAN
            try:
                diff_h = float(str(home_stats.get("diff","0")).replace("+",""))
                diff_a = float(str(away_stats.get("diff","0")).replace("+",""))
                if diff_h > diff_a + 3:
                    notas.append(f"{hs} mejor diferencial ({home_stats.get('diff')}) vs {as_} ({away_stats.get('diff')})")
                    tipo, confianza = "LEAN LOCAL", "baja"
                elif diff_a > diff_h + 3:
                    notas.append(f"{as_} mejor diferencial ({away_stats.get('diff')}) como visitante")
                    tipo, confianza = "LEAN VISITANTE", "baja"
                else:
                    notas.append("Partido equilibrado por diferencial. Analizar O/U.")
            except:
                notas.append("Sin señal de lado clara.")

    # ── Pick O/U ─────────────────────────────────────────────────────
    ou_pick = None
    ou_notas = []
    confianza_ou = "—"
    try:
        umbral = 4.5
        if diff_ou is not None and total_ou_line:
            if diff_ou >= umbral and ev_over is not None and ev_over > 0:
                ou_pick = "OVER"
                ou_notas.append(
                    f"Proyección: {proj_total} pts vs línea {total_ou_line} "
                    f"(+{diff_ou} pts) | EV: +{ev_over}%"
                )
                confianza_ou = "media" if diff_ou >= 7 else "baja"
            elif diff_ou <= -umbral and ev_under is not None and ev_under > 0:
                ou_pick = "UNDER"
                ou_notas.append(
                    f"Proyección: {proj_total} pts vs línea {total_ou_line} "
                    f"({diff_ou} pts) | EV: +{ev_under}%"
                )
                confianza_ou = "media" if diff_ou <= -7 else "baja"
                if baja_penalty > 0:
                    ou_notas.append(f"Bajas deprimen total ({len(any_out)} jugadores Out/Doubtful)")
            else:
                ou_notas.append(
                    f"Proyección: {proj_total} pts vs línea {total_ou_line} "
                    f"({diff_ou:+.1f} pts) — diferencia insuficiente"
                )
    except Exception as e:
        ou_notas.append("Sin datos suficientes para proyección O/U.")

    # ── Mejor pick EV global ──────────────────────────────────────────
    ev_candidates = []
    if ev_ml_home is not None: ev_candidates.append(("ML " + hs, ev_ml_home))
    if ev_ml_away is not None: ev_candidates.append(("ML " + as_, ev_ml_away))
    if ev_spread_home is not None: ev_candidates.append(("Spread " + hs, ev_spread_home))
    if ev_spread_away is not None: ev_candidates.append(("Spread " + as_, ev_spread_away))
    if ev_over  is not None: ev_candidates.append(("OVER",  ev_over))
    if ev_under is not None: ev_candidates.append(("UNDER", ev_under))

    mejor_ev = max(ev_candidates, key=lambda x: x[1]) if ev_candidates else None

    return {
        "pick": pick,
        "tipo": tipo,
        "confianza": confianza,
        "notas": " | ".join(notas) if notas else "Sin señal de lado clara.",
        "ou_pick": ou_pick,
        "ou_confianza": confianza_ou if ou_pick else "—",
        "ou_notas": " | ".join(ou_notas) if ou_notas else "",
        "ev": {
            "prob_home": prob_home,
            "prob_away": prob_away,
            "ml_home":   ev_ml_home,
            "ml_away":   ev_ml_away,
            "spread_home": ev_spread_home,
            "spread_away": ev_spread_away,
            "over":  ev_over,
            "under": ev_under,
            "mejor_pick": f"{mejor_ev[0]} ({'+' if mejor_ev[1]>0 else ''}{mejor_ev[1]}%)" if mejor_ev else None
        }
    }


# ── Main ──────────────────────────────────────────────────────────────

def main():
    today_et = get_today_et()
    print(f"\n[{datetime.now(timezone.utc).isoformat()}] Iniciando scrape...")
    print(f"  Filtrando partidos del día: {today_et} (ET)")

    print("\n[1/4] ESPN...")
    scoreboard       = fetch_espn_scoreboard()
    standings        = fetch_espn_standings()
    live_scores_map  = build_live_scores_map(scoreboard)
    print(f"  Standings: {len(standings)} equipos")
    print(f"  Partidos en scoreboard: {len(live_scores_map)//2 if live_scores_map else 0}")

    print("\n[2/4] Rotowire...")
    roto_html   = fetch_url(ROTOWIRE_URL)
    roto_blocks = parse_rotowire(roto_html) if roto_html else []

    print("\n[3/4] The Odds API...")
    odds_events = fetch_odds()
    print(f"  {len(odds_events)} partidos con odds (sin filtrar)")

    # ── FILTRO: solo partidos de hoy en ET ───────────────────────────
    odds_events = [ev for ev in odds_events if es_partido_de_hoy(ev.get("commence_time", ""))]
    print(f"  {len(odds_events)} partidos de hoy ({today_et} ET)")

    print("\n[4/4] Cruzando datos...")

    # Mapa equipo → team_id desde scoreboard
    team_id_map = {}
    for ev in scoreboard.get("events", []):
        for comp in ev.get("competitions", []):
            for c in comp.get("competitors", []):
                name = c.get("team", {}).get("displayName", "")
                tid  = str(c.get("team", {}).get("id", ""))
                if name and tid:
                    team_id_map[name] = tid

    games = []
    for odds_ev in odds_events:
        home     = odds_ev.get("home_team", "")
        away     = odds_ev.get("away_team", "")
        commence = odds_ev.get("commence_time", "")

        # Hora ET
        try:
            dt_utc  = datetime.fromisoformat(commence.replace("Z","+00:00"))
            et_h    = (dt_utc.hour - 4) % 24
            et_m    = dt_utc.minute
            per     = "PM" if et_h >= 12 else "AM"
            h12     = et_h % 12 or 12
            time_et = f"{h12}:{et_m:02d} {per} ET"
        except:
            time_et = ""

        # Standings
        home_id    = team_id_map.get(home, "")
        away_id    = team_id_map.get(away, "")
        home_stats = standings.get(home_id, {})
        away_stats = standings.get(away_id, {})

        # Forma últimos 5
        home_form, away_form = [], []
        if home_id:
            home_form = fetch_team_form(home_id, commence)
        if away_id:
            away_form = fetch_team_form(away_id, commence)

        # Añadir forma al stats dict para que calcular_rec lo use
        home_stats["forma"] = home_form
        away_stats["forma"] = away_form

        # Odds
        odds = extract_odds(odds_ev)

        # ── Rotowire ────────────────────────────────────────────────
        odds_min = et_to_min(time_et)
        roto_block = None
        best_diff = 20
        for b in roto_blocks:
            if b.get("_matched"):
                continue
            d = abs(et_to_min(b["time_et"]) - odds_min)
            if d < best_diff:
                best_diff = d
                roto_block = b
        if roto_block:
            roto_block["_matched"] = True

        if roto_block:
            injuries = filter_injuries_by_teams(roto_block["injuries"], home, away)
        else:
            injuries = []

        alerta, alerta_msg = build_alerta(injuries)
        rec = calcular_rec(home, away, odds, injuries, home_stats, away_stats)

        # Score en vivo desde ESPN scoreboard
        live = live_scores_map.get(home) or live_scores_map.get(away) or {}

        games.append({
            "id": odds_ev.get("id"),
            "home_team": home,
            "away_team": away,
            "commence_time": commence,
            "time_et": time_et,
            "live": {
                "state":      live.get("state", "pre"),
                "period":     live.get("period", 0),
                "clock":      live.get("clock", ""),
                "description": live.get("description", ""),
                "home_score": live.get("home_score"),
                "away_score": live.get("away_score"),
            },
            "home_stats": {
                "conference": home_stats.get("conference","—"),
                "record":     home_stats.get("record","—"),
                "seed":       home_stats.get("seed","—"),
                "ppg":        home_stats.get("ppg","—"),
                "papg":       home_stats.get("papg","—"),
                "diff":       home_stats.get("diff","—"),
                "home_rec":   home_stats.get("home_rec","—"),
                "away_rec":   home_stats.get("away_rec","—"),
                "streak":     home_stats.get("streak","—"),
                "forma":      home_form,
            },
            "away_stats": {
                "conference": away_stats.get("conference","—"),
                "record":     away_stats.get("record","—"),
                "seed":       away_stats.get("seed","—"),
                "ppg":        away_stats.get("ppg","—"),
                "papg":       away_stats.get("papg","—"),
                "diff":       away_stats.get("diff","—"),
                "home_rec":   away_stats.get("home_rec","—"),
                "away_rec":   away_stats.get("away_rec","—"),
                "streak":     away_stats.get("streak","—"),
                "forma":      away_form,
            },
            "odds": odds,
            "injuries": injuries,
            "alerta": alerta,
            "alerta_msg": alerta_msg,
            "recomendacion": rec
        })

    os.makedirs("data", exist_ok=True)
    output = {"updated_at": datetime.now(timezone.utc).isoformat(), "games": games}
    with open("data/games.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n  ✓ data/games.json — {len(games)} partidos (solo hoy {today_et} ET)")

    alertas = [g for g in games if g["alerta"]]
    if alertas:
        print(f"\n⚠️  ALERTAS ({len(alertas)}):")
        for a in alertas:
            print(f"  {a['away_team']} @ {a['home_team']}: {a['alerta_msg']}")
    else:
        print("  Sin alertas activas.")


if __name__ == "__main__":
    main()
