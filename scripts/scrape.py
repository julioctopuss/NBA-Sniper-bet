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
# Permite filtrar injuries del bloque Rotowire solo para los equipos del partido
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
    results = []

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

        competitors = comp.get("competitors", [])
        my_team = next((c for c in competitors if str(c.get("team",{}).get("id","")) == str(team_id)), None)
        opp     = next((c for c in competitors if str(c.get("team",{}).get("id","")) != str(team_id)), None)
        if not my_team or not opp:
            continue

        winner = my_team.get("winner", False)
        results.append("G" if winner else "P")

        if len(results) == 5:
            break

    return results


# ── Rotowire ──────────────────────────────────────────────────────────

def parse_rotowire(html):
    """
    Parsea el HTML de Rotowire y retorna una lista de bloques por hora ET.
    Cada bloque contiene TODAS las injuries de esa hora (todos los equipos).
    El filtrado por equipo se hace luego en filter_injuries_by_teams().
    """
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
            "injuries": all_injuries,   # todos los equipos de esa hora
        })

    total_inj = sum(len(b["injuries"]) for b in blocks)
    print(f"  Rotowire: {len(blocks)} bloques horarios, {total_inj} injuries totales")
    return blocks


def filter_injuries_by_teams(all_injuries, home_team, away_team):
    """
    Dado el listado de injuries de un bloque horario (puede incluir varios equipos),
    filtra solo los jugadores que pertenecen a home_team o away_team usando TEAM_KEYWORDS.
    """
    home_kws = [kw.lower() for kw in TEAM_KEYWORDS.get(home_team, [])]
    away_kws = [kw.lower() for kw in TEAM_KEYWORDS.get(away_team, [])]
    allowed_kws = set(home_kws + away_kws)

    filtered = []
    for inj in all_injuries:
        player_lower = inj["player"].lower()
        # El jugador pertenece al partido si alguna keyword del equipo está en su nombre
        # O si su nombre (completo o apellido) está en las keywords
        match = any(
            kw in player_lower or player_lower in kw
            for kw in allowed_kws
        )
        if match:
            filtered.append(inj)

    return filtered


def build_alerta(injuries):
    """Construye alerta y alerta_msg desde una lista de injuries filtrada."""
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


# ── Recomendación ─────────────────────────────────────────────────────

def calcular_rec(home, away, odds, injuries, home_stats, away_stats):
    notas = []
    pick, tipo, confianza = "Sin pick", "NO BET", "—"
    hs, as_ = home.split()[-1], away.split()[-1]

    high_out = [i for i in injuries if i["weight"] >= 2 and i["high_impact"]]
    any_out  = [i for i in injuries if i["weight"] >= 2]
    doubtful = [i for i in injuries if i["weight"] == 1]

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
        ml_h = odds["home_ml"]; ml_a = odds["away_ml"]
        if ml_a is not None and ml_a >= 250:
            notas.append(f"{as_} underdog grande (+{ml_a}) — evaluar si el mercado exagera")
            pick, tipo, confianza = away, f"ML {as_} (underdog)", "baja"
        elif ml_h is not None and ml_h >= 180:
            notas.append(f"{hs} local underdog (+{ml_h}) — situación atípica")
            pick, tipo, confianza = home, f"ML {hs} (local underdog)", "baja"
        else:
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
        ppg_h  = float(str(home_stats.get("ppg", 0)))
        ppg_a  = float(str(away_stats.get("ppg", 0)))
        papg_h = float(str(home_stats.get("papg", 0)))
        papg_a = float(str(away_stats.get("papg", 0)))
        total_ou_line = odds.get("total_ou")

        if ppg_h > 0 and ppg_a > 0 and total_ou_line:
            proj_home_score = (ppg_h + papg_a) / 2
            proj_away_score = (ppg_a + papg_h) / 2
            proj_total = round(proj_home_score + proj_away_score, 1)

            baja_penalty = len(any_out) * 2.5
            proj_total_ajustado = round(proj_total - baja_penalty, 1)
            diff_ajustado = round(proj_total_ajustado - float(total_ou_line), 1)

            umbral = 4.5

            if diff_ajustado >= umbral:
                ou_pick = "OVER"
                ou_notas.append(
                    f"Proyección total: {proj_total_ajustado} pts vs línea {total_ou_line} "
                    f"(+{diff_ajustado} pts) — sugiere OVER"
                )
                confianza_ou = "media" if diff_ajustado >= 7 else "baja"
            elif diff_ajustado <= -umbral:
                ou_pick = "UNDER"
                ou_notas.append(
                    f"Proyección total: {proj_total_ajustado} pts vs línea {total_ou_line} "
                    f"({diff_ajustado} pts) — sugiere UNDER"
                )
                confianza_ou = "media" if diff_ajustado <= -7 else "baja"
                if baja_penalty > 0:
                    ou_notas.append(f"Bajas deprimen el total esperado ({len(any_out)} jugadores Out/Doubtful)")
            else:
                ou_notas.append(
                    f"Proyección total: {proj_total_ajustado} pts vs línea {total_ou_line} "
                    f"— diferencia insuficiente para pick O/U ({diff_ajustado:+.1f} pts)"
                )
    except Exception as e:
        ou_notas.append("Sin datos suficientes para proyección O/U.")

    return {
        "pick": pick,
        "tipo": tipo,
        "confianza": confianza,
        "notas": " | ".join(notas) if notas else "Sin señal de lado clara.",
        "ou_pick": ou_pick,
        "ou_confianza": confianza_ou if ou_pick else "—",
        "ou_notas": " | ".join(ou_notas) if ou_notas else ""
    }


# ── Main ──────────────────────────────────────────────────────────────

def main():
    today_et = get_today_et()
    print(f"\n[{datetime.now(timezone.utc).isoformat()}] Iniciando scrape...")
    print(f"  Filtrando partidos del día: {today_et} (ET)")

    print("\n[1/4] ESPN...")
    scoreboard  = fetch_espn_scoreboard()
    standings   = fetch_espn_standings()
    print(f"  Standings: {len(standings)} equipos")

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

        # Odds
        odds = extract_odds(odds_ev)

        # ── Rotowire: buscar bloque por hora y filtrar por equipo ────
        odds_min = et_to_min(time_et)
        roto_block = None
        best_diff = 20  # tolerancia 20 min
        for b in roto_blocks:
            d = abs(et_to_min(b["time_et"]) - odds_min)
            if d < best_diff:
                best_diff = d
                roto_block = b
        # NUEVO: no marcar como _matched — cada partido busca su bloque
        # y luego filtra por sus propios equipos
        if roto_block:
            injuries = filter_injuries_by_teams(
                roto_block["injuries"], home, away
            )
        else:
            injuries = []

        alerta, alerta_msg = build_alerta(injuries)
        rec = calcular_rec(home, away, odds, injuries, home_stats, away_stats)

        games.append({
            "id": odds_ev.get("id"),
            "home_team": home,
            "away_team": away,
            "commence_time": commence,
            "time_et": time_et,
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
