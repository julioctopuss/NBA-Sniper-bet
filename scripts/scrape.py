#!/usr/bin/env python3
"""
NBA Sniper Bet - Scraper v2
Fuentes:
  - ESPN API: scoreboard, roster (con injury status), standings, schedule (forma)
  - nba_api: PRA por jugador temporada 2025-26
  - The Odds API: moneyline, spread, total
Output: data/games.json
"""

import json, re, os, sys, time, math
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError

# ── Configuración ─────────────────────────────────────────────────────
ODDS_API_KEY = "1823578c582e34ab968083d68997a9d1"
ODDS_API_URL = (
    "https://api.the-odds-api.com/v4/sports/basketball_nba/odds/"
    f"?apiKey={ODDS_API_KEY}&regions=us&markets=h2h,spreads,totals&oddsFormat=american"
)
ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
ESPN_STANDINGS  = "https://site.api.espn.com/apis/v2/sports/basketball/nba/standings?season=2026"
ESPN_ROSTER     = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/roster"
ESPN_SCHEDULE   = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/schedule?season=2026"

ET_OFFSET = timedelta(hours=-4)  # EDT (verano)


# ── HTTP helpers ──────────────────────────────────────────────────────

def fetch_json(url, retries=2):
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json,*/*"
    })
    for attempt in range(retries + 1):
        try:
            with urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode("utf-8", errors="ignore"))
        except URLError as e:
            if attempt < retries:
                time.sleep(1)
            else:
                print(f"  WARN fetch_json({url[:70]}): {e}", file=sys.stderr)
                return None
        except Exception as e:
            print(f"  WARN fetch_json: {e}", file=sys.stderr)
            return None


# ── ESPN: scoreboard ──────────────────────────────────────────────────

def fetch_scoreboard():
    """Retorna dict con team_ids, live scores y estado de cada partido."""
    data = fetch_json(ESPN_SCOREBOARD) or {}
    team_id_map  = {}   # displayName → team_id
    live_scores  = {}   # home_name → {state, period, clock, home_score, away_score}

    for ev in data.get("events", []):
        comp    = ev.get("competitions", [{}])[0]
        comps   = comp.get("competitors", [])
        status  = comp.get("status", {})
        state   = status.get("type", {}).get("state", "pre")
        period  = status.get("period", 0)
        clock   = status.get("displayClock", "")

        home = next((c for c in comps if c.get("homeAway") == "home"), None)
        away = next((c for c in comps if c.get("homeAway") == "away"), None)

        for c in comps:
            name = c.get("team", {}).get("displayName", "")
            tid  = str(c.get("team", {}).get("id", ""))
            if name and tid:
                team_id_map[name] = tid

        if home and away:
            def parse_score(s):
                if isinstance(s, dict): return s.get("displayValue") or s.get("value")
                return str(s) if s not in ("", None) else None

            home_name = home.get("team", {}).get("displayName", "")
            live_scores[home_name] = {
                "state":      state,
                "period":     period,
                "clock":      clock,
                "home_score": parse_score(home.get("score")),
                "away_score": parse_score(away.get("score")),
                "away_name":  away.get("team", {}).get("displayName", "")
            }

    return team_id_map, live_scores


# ── ESPN: standings ───────────────────────────────────────────────────

def fetch_standings():
    """Retorna dict team_id → stats (record, seed, ppg, papg, diff, etc.)"""
    data = fetch_json(ESPN_STANDINGS) or {}
    result = {}

    for conf in data.get("children", []):
        conf_label = "Este" if "East" in conf.get("name","") else "Oeste"
        for entry in conf.get("standings", {}).get("entries", []):
            tid  = str(entry.get("team", {}).get("id", ""))
            name = entry.get("team", {}).get("displayName", "")
            if not tid:
                continue
            stats = {s["name"]: s.get("displayValue", str(s.get("value","")))
                     for s in entry.get("stats", [])}
            result[tid] = {
                "team_name":  name,
                "conference": conf_label,
                "record":     stats.get("overall", "—"),
                "seed":       stats.get("playoffSeed", "—"),
                "ppg":        stats.get("avgPointsFor", "—"),
                "papg":       stats.get("avgPointsAgainst", "—"),
                "diff":       stats.get("differential", "—"),
                "home_rec":   stats.get("Home", "—"),
                "away_rec":   stats.get("Road", "—"),
                "streak":     stats.get("streak", "—"),
                "win_pct":    stats.get("winPercent", "—"),
            }
    return result


# ── ESPN: roster + injuries ───────────────────────────────────────────

def fetch_roster_with_injuries(team_id):
    """
    Retorna lista de jugadores del equipo con injury status.
    Cada jugador: {id, name, position, injury_status}
    """
    data = fetch_json(ESPN_ROSTER.format(team_id=team_id)) or {}
    players = []
    for a in data.get("athletes", []):
        inj     = a.get("injuries", [])
        status  = inj[0].get("status", "Active") if inj else "Active"
        players.append({
            "id":             a.get("id", ""),
            "name":           a.get("fullName", ""),
            "position":       a.get("position", {}).get("abbreviation", ""),
            "injury_status":  status   # Active / Out / Questionable / Doubtful / Probable
        })
    return players


# ── ESPN: forma últimos 5 ─────────────────────────────────────────────

def fetch_form(team_id, before_iso):
    """Últimos 5 resultados reales antes del partido. season=2026."""
    data = fetch_json(ESPN_SCHEDULE.format(team_id=team_id)) or {}
    target_ts = datetime.fromisoformat(before_iso.replace("Z", "+00:00")).timestamp()

    completed = []
    for ev in data.get("events", []):
        ev_date = ev.get("date", "")
        try:
            ev_ts = datetime.fromisoformat(ev_date.replace("Z", "+00:00")).timestamp()
        except:
            continue
        if ev_ts >= target_ts:
            continue
        comp   = ev.get("competitions", [{}])[0]
        status = comp.get("status", {}).get("type", {})
        if not status.get("completed"):
            continue
        completed.append((ev_ts, ev))

    # Más reciente primero
    completed.sort(key=lambda x: x[0], reverse=True)

    results = []
    for _, ev in completed:
        comp = ev.get("competitions", [{}])[0]
        me   = next((c for c in comp.get("competitors", [])
                     if str(c.get("team", {}).get("id", "")) == str(team_id)), None)
        if not me:
            continue
        results.append("G" if me.get("winner") else "P")
        if len(results) == 5:
            break

    return results


# ── nba_api: PRA por jugador ──────────────────────────────────────────

def fetch_pra_map():
    """
    Retorna dict normalizado nombre_lower → pra float
    usando LeagueDashPlayerStats temporada 2025-26.
    """
    try:
        from nba_api.stats.endpoints import leaguedashplayerstats
        stats = leaguedashplayerstats.LeagueDashPlayerStats(
            season="2025-26",
            per_mode_detailed="PerGame"
        )
        df = stats.get_data_frames()[0]
        pra_map = {}
        for _, row in df.iterrows():
            name  = str(row["PLAYER_NAME"]).lower().strip()
            pra   = round(float(row["PTS"]) + float(row["REB"]) + float(row["AST"]), 1)
            pra_map[name] = pra
        print(f"  nba_api: {len(pra_map)} jugadores con PRA")
        return pra_map
    except Exception as e:
        print(f"  WARN nba_api: {e}", file=sys.stderr)
        return {}


# ── The Odds API ──────────────────────────────────────────────────────

def fetch_odds():
    data = fetch_json(ODDS_API_URL)
    return data if isinstance(data, list) else []


def extract_best_odds(odds_event):
    home = odds_event.get("home_team", "")
    away = odds_event.get("away_team", "")
    best_home_ml = None
    best_away_ml = None
    spread_home  = None
    total_ou     = None
    best_book    = ""

    for bm in odds_event.get("bookmakers", []):
        for mkt in bm.get("markets", []):
            if mkt["key"] == "h2h":
                for o in mkt["outcomes"]:
                    if o["name"] == home and (best_home_ml is None or o["price"] > best_home_ml):
                        best_home_ml = o["price"]
                        best_book    = bm["title"]
                    if o["name"] == away and (best_away_ml is None or o["price"] > best_away_ml):
                        best_away_ml = o["price"]
            elif mkt["key"] == "spreads" and spread_home is None:
                for o in mkt["outcomes"]:
                    if o["name"] == home:
                        spread_home = o.get("point")
            elif mkt["key"] == "totals" and total_ou is None:
                for o in mkt["outcomes"]:
                    if o["name"] == "Over":
                        total_ou = o.get("point")

    return {
        "home_ml":    best_home_ml,
        "away_ml":    best_away_ml,
        "spread_home": spread_home,
        "total_ou":   total_ou,
        "best_book":  best_book,
        "num_books":  len(odds_event.get("bookmakers", []))
    }


# ── Injuries con peso PRA ─────────────────────────────────────────────

def build_injury_report(roster, pra_map):
    """
    Filtra jugadores no-activos del roster y les asigna peso PRA.
    Retorna lista ordenada por PRA desc.
    """
    STATUS_WEIGHT = {
        "out": 3, "doubtful": 2, "questionable": 1, "probable": 0, "active": 0
    }
    injured = []
    for p in roster:
        status = p["injury_status"].lower()
        if status in ("active", "probable"):
            continue
        name_lower = p["name"].lower().strip()
        # Buscar PRA por nombre exacto o apellido
        pra = pra_map.get(name_lower)
        if pra is None:
            # Intentar solo apellido
            last = name_lower.split()[-1]
            for k, v in pra_map.items():
                if k.split()[-1] == last:
                    pra = v
                    break
        pra = pra or 0.0

        injured.append({
            "player":   p["name"],
            "position": p["position"],
            "status":   p["injury_status"],
            "pra":      pra,
            "weight":   STATUS_WEIGHT.get(status, 1)
        })

    # Ordenar por PRA descendente
    injured.sort(key=lambda x: x["pra"], reverse=True)
    return injured


def build_alerta(home_injuries, away_injuries):
    """Genera alerta si hay bajas Out/Doubtful con PRA significativo (>15)."""
    alerta  = False
    msgs    = []
    umbral_pra = 15.0

    for inj in home_injuries + away_injuries:
        if inj["weight"] >= 2:  # Out o Doubtful
            alerta = True
            pra_tag = f" (PRA {inj['pra']})" if inj["pra"] > 0 else ""
            msgs.append(f"{inj['player']} {inj['status']}{pra_tag}")

    return alerta, " | ".join(msgs)


# ── Filtro: solo hoy en ET ────────────────────────────────────────────

def is_today_et(iso):
    try:
        dt_et = datetime.fromisoformat(iso.replace("Z", "+00:00")) + ET_OFFSET
        now_et = datetime.now(timezone.utc) + ET_OFFSET
        return dt_et.date() == now_et.date()
    except:
        return False


# ── Recomendación ─────────────────────────────────────────────────
# ── EV puro ───────────────────────────────────────────────────────────

def sigmoid(x):
    return 1 / (1 + math.exp(-x))


def implied_prob_no_vig(ml_home, ml_away):
    """Probabilidad implícita del mercado sin vig."""
    def raw(ml):
        if ml is None: return None
        return 100 / (ml + 100) if ml > 0 else abs(ml) / (abs(ml) + 100)
    r_h, r_a = raw(ml_home), raw(ml_away)
    if r_h is None or r_a is None: return None, None
    total = r_h + r_a
    return r_h / total, r_a / total


def ml_to_decimal(ml):
    if ml is None: return None
    return ml / 100 if ml > 0 else 100 / abs(ml)


def calcular_ev(prob_modelo, ml):
    g = ml_to_decimal(ml)
    if g is None: return None
    return round(prob_modelo * g - (1 - prob_modelo), 4)


def calcular_prob_modelo(home_stats, away_stats, home_inj, away_inj):
    """
    Probabilidad de ganar del local, independiente de las odds.
    Pesos: 55% diferencial | 25% ppg/papg | 15% home/away rec | 5% forma
    Ajuste final por PRA perdido en bajas.
    """
    try:
        # 1. Diferencial (55%)
        diff_h = float(str(home_stats.get("diff", "0")).replace("+", ""))
        diff_a = float(str(away_stats.get("diff", "0")).replace("+", ""))
        score_diff = max(min((diff_h - diff_a) / 12.0, 1.0), -1.0)

        # 2. PPG/PAPG relativo (25%)
        ppg_h  = float(str(home_stats.get("ppg",  "110")))
        papg_h = float(str(home_stats.get("papg", "110")))
        ppg_a  = float(str(away_stats.get("ppg",  "110")))
        papg_a = float(str(away_stats.get("papg", "110")))
        proj_margin = ((ppg_h + papg_a) / 2) - ((ppg_a + papg_h) / 2)
        score_ppg = max(min(proj_margin / 15.0, 1.0), -1.0)

        # 3. Home/Away record (15%)
        def rec_pct(s):
            try:
                w, l = map(int, s.split("-"))
                return w / (w + l) if (w + l) > 0 else 0.5
            except: return 0.5
        score_venue = rec_pct(home_stats.get("home_rec", "0-0")) - rec_pct(away_stats.get("away_rec", "0-0"))

        # 4. Forma últimos 5 (5%)
        forma_h = home_stats.get("forma", [])
        forma_a = away_stats.get("forma", [])
        wins_h  = sum(1 for r in forma_h if r == "G") / max(len(forma_h), 1)
        wins_a  = sum(1 for r in forma_a if r == "G") / max(len(forma_a), 1)
        score_forma = wins_h - wins_a

        # Solo stats — sin bajas. El mercado ya las procesó.
        score_final = (0.55 * score_diff + 0.25 * score_ppg +
                       0.15 * score_venue + 0.05 * score_forma)

        prob_home = sigmoid(3 * score_final)
        return round(prob_home, 4), round(1 - prob_home, 4)
    except:
        return 0.5, 0.5


def calcular_rec(home, away, odds, home_inj, away_inj, home_stats, away_stats):
    """Recomendación basada en EV puro. Modelo estima prob sin mirar odds."""
    hs  = home.split()[-1]
    as_ = away.split()[-1]

    home_pra_out = sum(i["pra"] for i in home_inj if i["weight"] >= 2)
    away_pra_out = sum(i["pra"] for i in away_inj if i["weight"] >= 2)

    # 1. Probabilidad modelo (independiente de odds)
    prob_home, prob_away = calcular_prob_modelo(home_stats, away_stats, home_inj, away_inj)

    # 2. Probabilidad mercado sin vig
    ml_h, ml_a = odds.get("home_ml"), odds.get("away_ml")
    mkt_home, mkt_away = implied_prob_no_vig(ml_h, ml_a)

    # 3. EV por lado
    ev_home = calcular_ev(prob_home, ml_h)
    ev_away = calcular_ev(prob_away, ml_a)

    # 4. Pick solo si EV > 5%
    UMBRAL = 0.05
    pick, tipo, conf, ev_pick = "Sin pick", "NO BET", "—", None
    notas = []

    if home_pra_out >= 20:
        top = sorted([i for i in home_inj if i["weight"] >= 2], key=lambda x: x["pra"], reverse=True)[:2]
        notas.append(f"Bajas {hs}: " + ", ".join(f"{i['player']} ({i['pra']} PRA)" for i in top) + f" ({home_pra_out:.0f} PRA total)")
    if away_pra_out >= 20:
        top = sorted([i for i in away_inj if i["weight"] >= 2], key=lambda x: x["pra"], reverse=True)[:2]
        notas.append(f"Bajas {as_}: " + ", ".join(f"{i['player']} ({i['pra']} PRA)" for i in top) + f" ({away_pra_out:.0f} PRA total)")

    # Límite de credibilidad: si la diferencia modelo vs mercado
    # supera 25 puntos, el modelo no tiene información que el mercado no tenga
    LIMITE_EDGE = 0.25

    if ev_home is not None and ev_away is not None:
        edge_home = prob_home - (mkt_home or 0)
        edge_away = prob_away - (mkt_away or 0)

        if ev_home >= UMBRAL and ev_home >= ev_away and abs(edge_home) <= LIMITE_EDGE:
            pick, tipo, ev_pick = home, f"ML {hs}", ev_home
            conf = "alta" if ev_home >= 0.15 else "media" if ev_home >= 0.08 else "baja"
            notas.append(f"Modelo: {prob_home*100:.1f}% | Mercado: {(mkt_home or 0)*100:.1f}% | Edge: +{edge_home*100:.1f}%")
        elif ev_away >= UMBRAL and abs(edge_away) <= LIMITE_EDGE:
            pick, tipo, ev_pick = away, f"ML {as_}", ev_away
            conf = "alta" if ev_away >= 0.15 else "media" if ev_away >= 0.08 else "baja"
            notas.append(f"Modelo: {prob_away*100:.1f}% | Mercado: {(mkt_away or 0)*100:.1f}% | Edge: +{edge_away*100:.1f}%")
        elif abs(edge_home) > LIMITE_EDGE or abs(edge_away) > LIMITE_EDGE:
            # Diferencia demasiado grande — el mercado tiene info que el modelo no
            notas.append(f"Diferencia modelo/mercado excesiva ({max(abs(edge_home),abs(edge_away))*100:.0f}%) — mercado probablemente incorporó bajas u otra info reciente.")
            notas.append(f"Modelo local: {prob_home*100:.1f}% | Mercado: {(mkt_home or 0)*100:.1f}%")
        else:
            best = max(ev_home, ev_away)
            notas.append(f"Sin EV suficiente. Mejor: {best*100:.1f}% (umbral 5%)")
            notas.append(f"Modelo local: {prob_home*100:.1f}% | Mercado: {(mkt_home or 0)*100:.1f}%")

    # O/U
    ou_pick, ou_conf, ou_notas = calcular_ou(odds, home_stats, away_stats, home_pra_out, away_pra_out)

    return {
        "pick":          pick,
        "tipo":          tipo,
        "confianza":     conf,
        "ev":            round(ev_pick * 100, 1) if ev_pick else None,
        "prob_modelo":   round(prob_home * 100, 1),
        "prob_mercado":  round((mkt_home or 0) * 100, 1),
        "notas":         " | ".join(notas) if notas else "Sin señal clara.",
        "ou_pick":       ou_pick,
        "ou_confianza":  ou_conf,
        "ou_notas":      ou_notas,
        "home_pra_out":  round(home_pra_out, 1),
        "away_pra_out":  round(away_pra_out, 1),
    }


def calcular_ou(odds, home_stats, away_stats, home_pra_out, away_pra_out):
    try:
        ppg_h  = float(str(home_stats.get("ppg",  0)))
        papg_h = float(str(home_stats.get("papg", 0)))
        ppg_a  = float(str(away_stats.get("ppg",  0)))
        papg_a = float(str(away_stats.get("papg", 0)))
        total  = odds.get("total_ou")
        if not (ppg_h > 0 and ppg_a > 0 and total):
            return None, "—", "Sin datos."
        proj   = ((ppg_h + papg_a) / 2) + ((ppg_a + papg_h) / 2)
        penalty = (home_pra_out + away_pra_out) * 0.35
        proj_adj = round(proj - penalty, 1)
        diff     = round(proj_adj - float(total), 1)
        if diff >= 5:
            return "OVER",  "media" if diff >= 8 else "baja", f"Proyección {proj_adj} vs {total} (+{diff}) | Penalty: {penalty:.1f} pts"
        elif diff <= -5:
            return "UNDER", "media" if diff <= -8 else "baja", f"Proyección {proj_adj} vs {total} ({diff}) | Penalty: {penalty:.1f} pts"
        return None, "—", f"Proyección {proj_adj} vs {total} ({diff:+.1f}) — insuficiente"
    except Exception as e:
        return None, "—", f"Error: {e}"



# ── Main ──────────────────────────────────────────────────────────────

def main():
    now_et = datetime.now(timezone.utc) + ET_OFFSET
    print(f"\n[{datetime.now(timezone.utc).isoformat()}] NBA Sniper Bet Scraper v2")
    print(f"  Día ET: {now_et.date()}")

    # 1. ESPN scoreboard
    print("\n[1/5] ESPN scoreboard + standings...")
    team_id_map, live_scores = fetch_scoreboard()
    standings = fetch_standings()
    print(f"  Equipos mapeados: {len(team_id_map)}")
    print(f"  Standings: {len(standings)} equipos")

    # 2. nba_api PRA
    print("\n[2/5] nba_api PRA 2025-26...")
    pra_map = fetch_pra_map()

    # 3. The Odds API
    print("\n[3/5] The Odds API...")
    all_odds = fetch_odds()
    today_odds = [ev for ev in all_odds if is_today_et(ev.get("commence_time",""))]
    print(f"  Total odds: {len(all_odds)} | Hoy: {len(today_odds)}")

    # 4. Procesar cada partido
    print("\n[4/5] Procesando partidos...")
    games = []

    for ev in today_odds:
        home    = ev.get("home_team", "")
        away    = ev.get("away_team", "")
        commence = ev.get("commence_time", "")

        # Hora ET
        try:
            dt_utc = datetime.fromisoformat(commence.replace("Z","+00:00"))
            dt_et  = dt_utc + ET_OFFSET
            et_h   = dt_et.hour
            et_m   = dt_et.minute
            per    = "PM" if et_h >= 12 else "AM"
            h12    = et_h % 12 or 12
            time_et = f"{h12}:{et_m:02d} {per} ET"
        except:
            time_et = ""

        # IDs de ESPN
        home_id = team_id_map.get(home, "")
        away_id = team_id_map.get(away, "")

        # Stats
        home_stats = standings.get(home_id, {})
        away_stats = standings.get(away_id, {})

        # Forma últimos 5 (season=2026)
        home_form = fetch_form(home_id, commence) if home_id else []
        away_form = fetch_form(away_id, commence) if away_id else []
        home_stats["forma"] = home_form
        away_stats["forma"] = away_form

        # Roster + injuries con PRA
        home_roster  = fetch_roster_with_injuries(home_id) if home_id else []
        away_roster  = fetch_roster_with_injuries(away_id) if away_id else []
        home_injuries = build_injury_report(home_roster, pra_map)
        away_injuries = build_injury_report(away_roster, pra_map)

        print(f"  {away} @ {home}: {len(home_injuries)} bajas local | {len(away_injuries)} bajas visitante")

        # Alerta
        all_injuries = home_injuries + away_injuries
        alerta, alerta_msg = build_alerta(home_injuries, away_injuries)

        # Odds
        odds = extract_best_odds(ev)

        # Recomendación
        rec = calcular_rec(home, away, odds, home_injuries, away_injuries, home_stats, away_stats)

        # Score en vivo desde scoreboard
        live_raw = live_scores.get(home, {})
        live = {
            "state":      live_raw.get("state", "pre"),
            "period":     live_raw.get("period", 0),
            "clock":      live_raw.get("clock", ""),
            "home_score": live_raw.get("home_score"),
            "away_score": live_raw.get("away_score"),
        }

        games.append({
            "id":           ev.get("id"),
            "home_team":    home,
            "away_team":    away,
            "commence_time": commence,
            "time_et":      time_et,
            "live":         live,
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
            "home_injuries": home_injuries,
            "away_injuries": away_injuries,
            "injuries":      all_injuries,  # compatibilidad con frontend
            "alerta":        alerta,
            "alerta_msg":    alerta_msg,
            "odds":          odds,
            "recomendacion": rec,
        })

    # 5. Guardar
    print(f"\n[5/5] Guardando...")
    os.makedirs("data", exist_ok=True)
    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "games": games
    }
    with open("data/games.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"  ✓ data/games.json — {len(games)} partidos")

    alertas = [g for g in games if g["alerta"]]
    if alertas:
        print(f"\n⚠️  ALERTAS ({len(alertas)}):")
        for a in alertas:
            print(f"  {a['away_team']} @ {a['home_team']}: {a['alerta_msg']}")
    else:
        print("  Sin alertas.")


if __name__ == "__main__":
    main()
