#!/usr/bin/env python3
"""
NBA Sniper Bet - Scraper
Scrapea Rotowire (lineups + injury report) y The Odds API
Guarda resultado en data/games.json
"""

import json
import re
import sys
import os
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from urllib.error import URLError

ODDS_API_KEY = "1823578c582e34ab968083d68997a9d1"
ODDS_API_URL = (
    "https://api.the-odds-api.com/v4/sports/basketball_nba/odds/"
    f"?apiKey={ODDS_API_KEY}&regions=us&markets=h2h,spreads,totals&oddsFormat=american"
)
ROTOWIRE_URL = "https://www.rotowire.com/basketball/nba-lineups.php"

HIGH_IMPACT_PLAYERS = [
    "embiid", "jokic", "giannis", "lebron", "curry", "durant", "luka",
    "tatum", "mitchell", "fox", "wembanyama", "booker", "towns",
    "lillard", "morant", "brunson", "harden", "george", "davis",
    "edwards", "siakam", "bam", "sabonis", "gilgeous-alexander", "sga"
]

STATUS_WEIGHTS = {
    "out": 3, "doubtful": 2, "doubt": 2,
    "questionable": 1, "ques": 1,
    "probable": 0, "prob": 0, "ofs": 0,
}


def fetch_url(url):
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    })
    try:
        with urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8", errors="ignore")
    except URLError as e:
        print(f"ERROR fetching {url}: {e}", file=sys.stderr)
        return None


def fetch_odds():
    print("Fetching Odds API...")
    data = fetch_url(ODDS_API_URL)
    if not data:
        return []
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return []


def parse_rotowire(html):
    """Parsea Rotowire extrayendo injury report por partido y por equipo."""
    # Limpiar HTML
    clean = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    clean = re.sub(r'<style[^>]*>.*?</style>', '', clean, flags=re.DOTALL)
    clean = re.sub(r'<[^>]+>', ' ', clean)
    clean = re.sub(r'&amp;', '&', clean)
    clean = re.sub(r'&nbsp;', ' ', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()

    player_pattern = re.compile(
        r'([A-Z][a-z]+(?:\s[A-Z][a-z.-]+)*)\s+(Out|Doubtful|Doubt|Questionable|Ques|Probable|Prob|OFS)',
        re.IGNORECASE
    )

    # Dividir por horarios ET — cada bloque es un partido
    time_pattern = re.compile(
        r'(\d+:\d+\s*[AP]M\s*ET)(.*?)(?=\d+:\d+\s*[AP]M\s*ET|\Z)',
        re.DOTALL
    )

    games = []
    for time_et, block in time_pattern.findall(clean):
        # Cada bloque tiene dos secciones MAY NOT PLAY (away, home)
        mnp_sections = re.findall(
            r'MAY NOT PLAY(.*?)(?=MAY NOT PLAY|LINE\s|\Z)',
            block, re.DOTALL
        )

        injuries_by_team = []
        for section in mnp_sections:
            players = []
            for player, status in player_pattern.findall(section):
                status_lower = status.lower()
                weight = STATUS_WEIGHTS.get(status_lower, 0)
                is_key = any(kw in player.lower() for kw in HIGH_IMPACT_PLAYERS)
                players.append({
                    "player": player.strip(),
                    "status": status.capitalize(),
                    "weight": weight,
                    "high_impact": is_key
                })
            injuries_by_team.append(players)

        # Flatten injuries para el partido
        all_injuries = []
        for team_injuries in injuries_by_team:
            all_injuries.extend(team_injuries)

        # Detectar alerta
        alerta = False
        alerta_msgs = []
        for inj in all_injuries:
            if inj["weight"] >= 2:
                alerta = True
                suffix = " ⚠️ JUGADOR CLAVE" if inj["high_impact"] else ""
                alerta_msgs.append(f"{inj['player']} ({inj['status']}){suffix}")
            elif inj["weight"] >= 1 and inj["high_impact"]:
                alerta = True
                alerta_msgs.append(f"{inj['player']} (Questionable) — jugador clave")

        games.append({
            "time_et": time_et.strip(),
            "injuries": all_injuries,
            "alerta": alerta,
            "alerta_msg": " | ".join(alerta_msgs)
        })

    print(f"  Rotowire: {len(games)} partidos, "
          f"{sum(len(g['injuries']) for g in games)} injuries totales")
    return games


def match_and_build(odds_events, roto_games):
    """Cruza odds con injury report de Rotowire por hora ET."""
    result = []

    for odds in odds_events:
        home = odds.get("home_team", "")
        away = odds.get("away_team", "")
        commence = odds.get("commence_time", "")

        # Convertir UTC → ET (UTC-4)
        try:
            dt_utc = datetime.fromisoformat(commence.replace("Z", "+00:00"))
            et_hour = (dt_utc.hour - 4) % 24
            et_min = dt_utc.minute
            period = "PM" if et_hour >= 12 else "AM"
            h12 = et_hour % 12 or 12
            time_et = f"{h12}:{et_min:02d} {period} ET"
        except Exception:
            time_et = ""

        # Extraer odds
        best_home_ml = None
        best_away_ml = None
        spread_home = None
        total_ou = None
        best_book = ""

        for bm in odds.get("bookmakers", []):
            for mkt in bm.get("markets", []):
                if mkt["key"] == "h2h":
                    for o in mkt["outcomes"]:
                        if o["name"] == home and (best_home_ml is None or o["price"] > best_home_ml):
                            best_home_ml = o["price"]
                            best_book = bm["title"]
                        elif o["name"] == away and (best_away_ml is None or o["price"] > best_away_ml):
                            best_away_ml = o["price"]
                elif mkt["key"] == "spreads" and spread_home is None:
                    for o in mkt["outcomes"]:
                        if o["name"] == home:
                            spread_home = o.get("point")
                elif mkt["key"] == "totals" and total_ou is None:
                    for o in mkt["outcomes"]:
                        if o["name"] == "Over":
                            total_ou = o.get("point")

        # Match con Rotowire por hora (tolerancia ±15 min)
        # Convertir hora ET a minutos para comparar
        def et_to_minutes(et_str):
            try:
                m = re.match(r'(\d+):(\d+)\s*([AP]M)', et_str.strip(), re.IGNORECASE)
                if not m: return -1
                h, mins, period = int(m.group(1)), int(m.group(2)), m.group(3).upper()
                if period == 'PM' and h != 12: h += 12
                if period == 'AM' and h == 12: h = 0
                return h * 60 + mins
            except: return -1

        odds_mins = et_to_minutes(time_et)
        # Buscar el partido de Rotowire más cercano en tiempo que no fue ya asignado
        roto = None
        best_diff = 20  # tolerancia máxima 20 minutos
        for g in roto_games:
            roto_mins = et_to_minutes(g["time_et"])
            diff = abs(odds_mins - roto_mins)
            if diff < best_diff and not g.get("_matched"):
                best_diff = diff
                roto = g
        if roto:
            roto["_matched"] = True

        injuries = roto["injuries"] if roto else []
        alerta = roto["alerta"] if roto else False
        alerta_msg = roto["alerta_msg"] if roto else ""

        rec = calcular_recomendacion(home, away, best_home_ml, best_away_ml,
                                      spread_home, total_ou, injuries)

        result.append({
            "id": odds.get("id"),
            "home_team": home,
            "away_team": away,
            "commence_time": commence,
            "time_et": time_et,
            "odds": {
                "home_ml": best_home_ml,
                "away_ml": best_away_ml,
                "spread_home": spread_home,
                "total_ou": total_ou,
                "best_book": best_book,
                "num_books": len(odds.get("bookmakers", []))
            },
            "injuries": injuries,
            "alerta": alerta,
            "alerta_msg": alerta_msg,
            "recomendacion": rec
        })

    return result


def calcular_recomendacion(home, away, ml_home, ml_away, spread, total, injuries):
    notas = []
    pick = "Sin pick"
    tipo = "NO BET"
    confianza = "—"

    home_short = home.split()[-1]
    away_short = away.split()[-1]

    # Bajas críticas
    high_out_home = [i for i in injuries if i["weight"] >= 2 and i["high_impact"]]
    high_out_any = [i for i in injuries if i["weight"] >= 2]
    doubtful_any = [i for i in injuries if i["weight"] == 1]

    if high_out_home:
        names = ", ".join(i["player"] for i in high_out_home)
        notas.append(f"Baja clave en {home_short}: {names} — línea puede no reflejar el impacto aún")
        if ml_away is not None:
            pick = away
            tipo = f"ML {away_short}"
            confianza = "media-alta"

    elif high_out_any:
        names = ", ".join(i["player"] for i in high_out_any)
        notas.append(f"Bajas confirmadas: {names}")
        tipo = "REVISAR"
        confianza = "pendiente"

    elif doubtful_any:
        names = ", ".join(i["player"] for i in doubtful_any)
        notas.append(f"En duda: {names} — esperar confirmación antes de apostar")
        tipo = "ESPERAR"
        confianza = "pendiente"

    # Sin injuries — análisis por odds
    if tipo == "NO BET" and ml_home is not None and ml_away is not None:
        if ml_away >= 250:
            notas.append(f"{away_short} es underdog grande (+{ml_away}) — evaluar valor real")
            pick = away
            tipo = f"ML {away_short} (underdog)"
            confianza = "baja"
        elif ml_home >= 180:
            notas.append(f"{home_short} es local underdog (+{ml_home}) — situación atípica")
            pick = home
            tipo = f"ML {home_short} (local underdog)"
            confianza = "baja"
        else:
            notas.append("Sin valor detectado por odds ni injuries. Análisis ESPN en curso.")

    return {
        "pick": pick,
        "tipo": tipo,
        "confianza": confianza,
        "notas": " | ".join(notas) if notas else "Sin señales claras. Esperar injury report completo."
    }


def main():
    print(f"[{datetime.now(timezone.utc).isoformat()}] Iniciando scrape...")

    odds_events = fetch_odds()
    print(f"  Odds: {len(odds_events)} partidos")

    print("Fetching Rotowire...")
    roto_html = fetch_url(ROTOWIRE_URL)
    roto_games = parse_rotowire(roto_html) if roto_html else []

    games = match_and_build(odds_events, roto_games)
    print(f"  Total partidos procesados: {len(games)}")

    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "games": games
    }

    os.makedirs("data", exist_ok=True)
    with open("data/games.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("  Guardado en data/games.json ✓")

    alertas = [g for g in games if g.get("alerta")]
    if alertas:
        print(f"\n⚠️  ALERTAS ({len(alertas)}):")
        for a in alertas:
            print(f"  {a['away_team']} @ {a['home_team']}: {a['alerta_msg']}")
    else:
        print("\n  Sin alertas activas.")


if __name__ == "__main__":
    main()
