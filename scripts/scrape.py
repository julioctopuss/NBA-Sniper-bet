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

# Jugadores con alto impacto — si están Out/Doubtful se genera alerta
HIGH_IMPACT_KEYWORDS = [
    "embiid", "jokic", "giannis", "lebron", "curry", "durant", "luka",
    "tatum", "mitchell", "fox", "wembanyama", "booker", "towns",
    "lillard", "morant", "brunson", "harden", "george", "davis"
]

STATUS_WEIGHTS = {
    "out": 3,
    "doubtful": 2,
    "doubt": 2,
    "questionable": 1,
    "ques": 1,
    "probable": 0,
    "prob": 0,
    "ofs": 0,  # out for season
}


def fetch_url(url):
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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
    """
    Parsea el HTML de Rotowire para extraer lineups e injury report por partido.
    Retorna lista de dicts con estructura estandarizada.
    """
    games = []

    # Buscar bloques de partido — cada uno tiene un par de equipos
    # Rotowire usa estructura con abreviaturas de equipo y secciones MAY NOT PLAY
    
    # Extraer texto limpio
    # Remover scripts y estilos
    clean = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    clean = re.sub(r'<style[^>]*>.*?</style>', '', clean, flags=re.DOTALL)
    clean = re.sub(r'<[^>]+>', ' ', clean)
    clean = re.sub(r'&amp;', '&', clean)
    clean = re.sub(r'&nbsp;', ' ', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()

    # Buscar secciones de partido por horario ET
    # Patrón: "7:00 PM ET" seguido de equipos
    game_pattern = re.compile(
        r'(\d+:\d+\s*[AP]M\s*ET).*?(?=\d+:\d+\s*[AP]M\s*ET|$)',
        re.DOTALL
    )

    # Alternativo: buscar por abreviaturas NBA conocidas
    # Extraer pares equipo-equipo con sus bajas
    
    # Buscar "MAY NOT PLAY" sections
    mnp_pattern = re.compile(
        r'MAY NOT PLAY\s*(.*?)(?=MAY NOT PLAY|Expected Lineup|LINE\s|$)',
        re.DOTALL
    )

    # Buscar líneas de jugadores con status
    player_status_pattern = re.compile(
        r'([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\s+(Out|Doubtful|Doubt|Questionable|Ques|Probable|Prob|OFS)',
        re.IGNORECASE
    )

    # Buscar secciones de partido completas
    # Rotowire tiene estructura: TIME TEAM1 TEAM2 ... MAY NOT PLAY ... MAY NOT PLAY ... LINE
    section_pattern = re.compile(
        r'(\d+:\d+\s*[AP]M\s*ET).*?LINE\s+([\w\s\-]+?)(?=\d+:\d+\s*[AP]M\s*ET|$)',
        re.DOTALL | re.IGNORECASE
    )

    sections = section_pattern.findall(clean)

    if not sections:
        # Fallback: parsear texto completo buscando patrones de jugadores
        print("Usando fallback parser...", file=sys.stderr)
        injuries = player_status_pattern.findall(clean)
        if injuries:
            games.append({
                "game_id": "fallback",
                "time_et": "N/A",
                "injuries": [
                    {"player": p, "status": s, "team": "unknown"}
                    for p, s in injuries
                ],
                "lineups": {},
                "alerta": False,
                "alerta_msg": ""
            })
        return games

    for time_et, section_text in sections:
        injuries = []
        
        # Extraer jugadores con status
        for player, status in player_status_pattern.findall(section_text):
            status_lower = status.lower()
            weight = STATUS_WEIGHTS.get(status_lower, 0)
            
            # Detectar si es jugador de alto impacto
            is_high_impact = any(
                kw in player.lower() for kw in HIGH_IMPACT_KEYWORDS
            )
            
            injuries.append({
                "player": player.strip(),
                "status": status.capitalize(),
                "weight": weight,
                "high_impact": is_high_impact
            })

        # Determinar si hay alerta
        alerta = False
        alerta_msgs = []
        
        for inj in injuries:
            if inj["weight"] >= 2:  # Out o Doubtful
                alerta = True
                alerta_msgs.append(
                    f"{inj['player']} ({inj['status']})"
                    + (" ⚠️ IMPACTO ALTO" if inj["high_impact"] else "")
                )
            elif inj["weight"] >= 1 and inj["high_impact"]:
                alerta = True
                alerta_msgs.append(f"{inj['player']} (Questionable) — jugador clave")

        games.append({
            "time_et": time_et.strip(),
            "injuries": injuries,
            "alerta": alerta,
            "alerta_msg": " | ".join(alerta_msgs) if alerta_msgs else ""
        })

    return games


def match_game_with_odds(roto_games, odds_events):
    """
    Cruza los datos de Rotowire con los de The Odds API por horario.
    """
    result = []

    for odds in odds_events:
        home = odds.get("home_team", "")
        away = odds.get("away_team", "")
        commence = odds.get("commence_time", "")

        # Convertir hora UTC a ET para matching con Rotowire
        try:
            dt_utc = datetime.fromisoformat(commence.replace("Z", "+00:00"))
            # ET = UTC - 4 (EDT) o UTC - 5 (EST)
            et_hour = (dt_utc.hour - 4) % 24
            et_min = dt_utc.minute
            period = "PM" if et_hour >= 12 else "AM"
            et_hour_12 = et_hour % 12 or 12
            time_et_str = f"{et_hour_12}:{et_min:02d} {period} ET"
        except Exception:
            time_et_str = ""

        # Extraer mejor odds para cada mercado
        best_home_ml = None
        best_away_ml = None
        spread_home = None
        total_ou = None
        best_book_home = ""

        for bm in odds.get("bookmakers", []):
            for mkt in bm.get("markets", []):
                if mkt["key"] == "h2h":
                    for o in mkt["outcomes"]:
                        if o["name"] == home:
                            if best_home_ml is None or o["price"] > best_home_ml:
                                best_home_ml = o["price"]
                                best_book_home = bm["title"]
                        elif o["name"] == away:
                            if best_away_ml is None or o["price"] > best_away_ml:
                                best_away_ml = o["price"]
                elif mkt["key"] == "spreads" and spread_home is None:
                    for o in mkt["outcomes"]:
                        if o["name"] == home:
                            spread_home = o.get("point")
                elif mkt["key"] == "totals" and total_ou is None:
                    for o in mkt["outcomes"]:
                        if o["name"] == "Over":
                            total_ou = o.get("point")

        # Buscar partido correspondiente en Rotowire por hora
        roto_match = None
        for rg in roto_games:
            roto_time = rg.get("time_et", "").upper().replace(" ", "")
            odds_time = time_et_str.upper().replace(" ", "")
            if roto_time and odds_time and roto_time[:5] == odds_time[:5]:
                roto_match = rg
                break

        injuries = roto_match.get("injuries", []) if roto_match else []
        alerta = roto_match.get("alerta", False) if roto_match else False
        alerta_msg = roto_match.get("alerta_msg", "") if roto_match else ""

        # Calcular recomendación simple basada en odds + injuries
        recomendacion = calcular_recomendacion(
            home, away, best_home_ml, best_away_ml,
            spread_home, total_ou, injuries
        )

        result.append({
            "id": odds.get("id"),
            "home_team": home,
            "away_team": away,
            "commence_time": commence,
            "time_et": time_et_str,
            "odds": {
                "home_ml": best_home_ml,
                "away_ml": best_away_ml,
                "spread_home": spread_home,
                "total_ou": total_ou,
                "best_book": best_book_home,
                "num_books": len(odds.get("bookmakers", []))
            },
            "injuries": injuries,
            "alerta": alerta,
            "alerta_msg": alerta_msg,
            "recomendacion": recomendacion
        })

    return result


def calcular_recomendacion(home, away, ml_home, ml_away, spread, total, injuries):
    """
    Lógica de recomendación básica.
    En producción esto se enriquece con histórico de jugadores (nba_api).
    """
    notas = []
    pick = None
    tipo = None
    confianza = "baja"

    # Detectar bajas importantes
    home_outs = [i for i in injuries if i.get("weight", 0) >= 2]
    home_high_impact_out = any(i["high_impact"] for i in home_outs)
    
    if home_high_impact_out and ml_away is not None:
        notas.append(f"Baja de alto impacto en {home} — línea puede estar rezagada")
        pick = away
        tipo = "ML Visitante"
        confianza = "media"

    # Sin injury report significativo — análisis por odds puras
    if not pick:
        if ml_home is not None and ml_away is not None:
            # Detectar valor en underdog grande
            if ml_away > 200:
                notas.append(f"Underdog grande ({away} a +{ml_away}) — evaluar si hay valor")
                pick = away
                tipo = "ML Visitante (underdog)"
                confianza = "baja"
            elif ml_home > 150:
                notas.append(f"Local underdog ({home} a +{ml_home}) — situación atípica")
                pick = home
                tipo = "ML Local (underdog)"
                confianza = "baja"
            else:
                notas.append("Sin valor claro detectado por odds. Esperar injury report.")
                pick = "Sin pick"
                tipo = "NO BET"
                confianza = "—"

    if not pick:
        pick = "Sin pick"
        tipo = "NO BET"

    return {
        "pick": pick,
        "tipo": tipo,
        "confianza": confianza,
        "notas": " | ".join(notas) if notas else "Análisis basado en histórico ESPN + odds."
    }


def main():
    print(f"[{datetime.now(timezone.utc).isoformat()}] Iniciando scrape...")

    # 1. Fetch Odds API
    odds_events = fetch_odds()
    print(f"  Odds: {len(odds_events)} partidos")

    # 2. Fetch Rotowire
    print("Fetching Rotowire...")
    roto_html = fetch_url(ROTOWIRE_URL)
    roto_games = []
    if roto_html:
        roto_games = parse_rotowire(roto_html)
        print(f"  Rotowire: {len(roto_games)} secciones parseadas")
    else:
        print("  Rotowire: sin datos", file=sys.stderr)

    # 3. Cruzar datos
    games = match_game_with_odds(roto_games, odds_events)
    print(f"  Total partidos procesados: {len(games)}")

    # 4. Guardar JSON
    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "games": games
    }

    os.makedirs("data", exist_ok=True)
    with open("data/games.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("  Guardado en data/games.json ✓")

    # Alertas encontradas
    alertas = [g for g in games if g.get("alerta")]
    if alertas:
        print(f"\n⚠️  ALERTAS ({len(alertas)}):")
        for a in alertas:
            print(f"  {a['away_team']} @ {a['home_team']}: {a['alerta_msg']}")
    else:
        print("\n  Sin alertas activas.")


if __name__ == "__main__":
    main()
