#!/usr/bin/env python3
"""
NBA Sniper Bet - Scraper
Fuentes: ESPN API (scoreboard + standings + schedules) + Rotowire + The Odds API
Output: data/games.json
"""

import json, re, sys, os
from datetime import datetime, timezone
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

    lookup = {}  # team_id → stats dict
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
                "record": stats.get("overall", "—"),
                "seed": stats.get("playoffSeed", "—"),
                "ppg": stats.get("avgPointsFor", "—"),
                "papg": stats.get("avgPointsAgainst", "—"),
                "diff": stats.get("differential", "—"),
                "home_rec": stats.get("Home", "—"),
                "away_rec": stats.get("Road", "—"),
                "streak": stats.get("streak", "—"),
                "win_pct": stats.get("winPercent", "—"),
            }
    return lookup


def fetch_team_form(team_id, game_date_iso):
    """Últimos 5 resultados antes del partido."""
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

    games = []
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
                all_injuries.append({"player": player.strip(), "status": status.capitalize(),
                                     "weight": w, "high_impact": is_key})

        alerta, msgs = False, []
        for inj in all_injuries:
            if inj["weight"] >= 2:
                alerta = True
                msgs.append(f"{inj['player']} ({inj['status']})" + (" ⚠️ CLAVE" if inj["high_impact"] else ""))
            elif inj["weight"] >= 1 and inj["high_impact"]:
                alerta = True
                msgs.append(f"{inj['player']} (Questionable) — jugador clave")

        games.append({"time_et": time_et.strip(), "injuries": all_injuries,
                      "alerta": alerta, "alerta_msg": " | ".join(msgs)})

    total_inj = sum(len(g["injuries"]) for g in games)
    print(f"  Rotowire: {len(games)} partidos, {total_inj} injuries")
    return games


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

    # Sin injuries relevantes → análisis por stats + odds
    if tipo in ("NO BET",):
        ml_h = odds["home_ml"]; ml_a = odds["away_ml"]
        if ml_a is not None and ml_a >= 250:
            notas.append(f"{as_} underdog grande (+{ml_a}) — evaluar si el mercado exagera")
            pick, tipo, confianza = away, f"ML {as_} (underdog)", "baja"
        elif ml_h is not None and ml_h >= 180:
            notas.append(f"{hs} local underdog (+{ml_h}) — situación atípica")
            pick, tipo, confianza = home, f"ML {hs} (local underdog)", "baja"
        else:
            # Comparar stats ESPN
            try:
                diff_h = float(str(home_stats.get("diff","0")).replace("+",""))
                diff_a = float(str(away_stats.get("diff","0")).replace("+",""))
                if diff_h > diff_a + 3:
                    notas.append(f"{hs} tiene mejor diferencial de puntos ({home_stats.get('diff')}) vs {as_} ({away_stats.get('diff')})")
                    tipo, confianza = "LEAN LOCAL", "baja"
                elif diff_a > diff_h + 3:
                    notas.append(f"{as_} tiene mejor diferencial ({away_stats.get('diff')}) como visitante")
                    tipo, confianza = "LEAN VISITANTE", "baja"
                else:
                    notas.append("Partido equilibrado. Sin señal clara.")
            except:
                notas.append("Sin señales claras por stats. Esperar injury report completo.")

    return {"pick": pick, "tipo": tipo, "confianza": confianza,
            "notas": " | ".join(notas) if notas else "Sin señales claras."}


# ── Main ──────────────────────────────────────────────────────────────

def main():
    print(f"\n[{datetime.now(timezone.utc).isoformat()}] Iniciando scrape...")

    print("\n[1/4] ESPN...")
    scoreboard  = fetch_espn_scoreboard()
    standings   = fetch_espn_standings()
    print(f"  Standings: {len(standings)} equipos")

    print("\n[2/4] Rotowire...")
    roto_html   = fetch_url(ROTOWIRE_URL)
    roto_games  = parse_rotowire(roto_html) if roto_html else []

    print("\n[3/4] The Odds API...")
    odds_events = fetch_odds()
    print(f"  {len(odds_events)} partidos con odds")

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

        # Forma últimos 5 (desde schedule ESPN)
        home_form, away_form = [], []
        if home_id:
            home_form = fetch_team_form(home_id, commence)
        if away_id:
            away_form = fetch_team_form(away_id, commence)

        # Odds
        odds = extract_odds(odds_ev)

        # Rotowire match por hora (tolerancia 20 min)
        odds_min = et_to_min(time_et)
        roto = None
        best_diff = 20
        for g in roto_games:
            d = abs(et_to_min(g["time_et"]) - odds_min)
            if d < best_diff and not g.get("_matched"):
                best_diff = d; roto = g
        if roto:
            roto["_matched"] = True

        injuries  = roto["injuries"]  if roto else []
        alerta    = roto["alerta"]    if roto else False
        alerta_msg= roto["alerta_msg"]if roto else ""

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
    print(f"\n  ✓ data/games.json — {len(games)} partidos")

    alertas = [g for g in games if g["alerta"]]
    if alertas:
        print(f"\n⚠️  ALERTAS ({len(alertas)}):")
        for a in alertas:
            print(f"  {a['away_team']} @ {a['home_team']}: {a['alerta_msg']}")
    else:
        print("  Sin alertas activas.")


if __name__ == "__main__":
    main()
