"""
find_bets.py

This Flask application serves as the analyze and tracking engine for the PrizePicker system.
It reads the scraped prop data (CSV files), identifies +EV (Expected Value) bets by comparing
PrizePicks lines against FanDuel's "Fair" odds (vig-removed), and constructs optimal parlay slips.

Key Features:
- Loads CSV props from the 'props/' directory.
- Filters bets based on win probability thresholds.
- Generates 2-man Power Plays and 3-6 man Flex plays.
- Provides a web dashboard to view and analyze potential slips.
"""
import pandas as pd
import glob
import os
from flask import Flask, render_template, request
import itertools

app = Flask(__name__)

# Winning probability thresholds required to consider a slip "+EV"
# These values represent the break-even win percentage needed for each slip type/size
# to be profitable against the payout multipliers.
THRESHOLDS = {
    "power": {
        2: 57.74,
        3: 55.05,
        4: 56.23,
        5: 54.93,
        6: 54.66
    },
    "flex": {
        3: 57.74,
        4: 55.04,
        5: 54.26,
        6: 54.21
    }
}

def get_slips(target_size=6, style="Power"):
    """
    Generates optimal betting slips based on available prop data.

    Args:
        target_size (int): Number of legs (bets) in the slip (e.g., 2, 3, 4, 5, 6).
        style (str): "Power" or "Flex" slip type.

    Returns:
        list: A list of dictionaries representing valid, +EV betting slips.
    """
    files = glob.glob("props/*_props_*.csv")
    if not files:
        return []

    # Load all prop CSVs into a single DataFrame
    dfs = []
    for f in files:
        try:
            df = pd.read_csv(f)
            # Tag the sport based on filename if missing
            if "Sport" not in df.columns:
                if "nfl" in f:
                    df["Sport"] = "NFL"
                else:
                    df["Sport"] = "NBA"
            dfs.append(df)
        except Exception:
            pass

    if not dfs:
        return []

    all_props = pd.concat(dfs, ignore_index=True)

    # Filter individual props to find candidates with positive EV
    candidates = []

    # Minimum probability to even consider a leg
    min_candidate_prob = 53.5

    for index, row in all_props.iterrows():
        try:
            fd_line_str = str(row.get("FanDuel Line", "NL"))
            pp_line_str = str(row.get("PrizePicks Line", "NL"))
            
            # Skip props where lines are missing
            if fd_line_str in ["NL", "FF"] or pp_line_str in ["NL", "FF", "nan"]:
                continue
                
            fd_line = float(fd_line_str)
            pp_line = float(pp_line_str)
            
            fair_over = float(row.get("FD Fair Over %", 0))
            fair_under = float(row.get("FD Fair Under %", 0))
            img_url = str(row.get("Player Image", ""))
            
            # Determine if we should bet OVER or UNDER based on line comparison and fair odds
            # We only bet if the PrizePicks line is within 0.5 of the FanDuel line
            if abs(fd_line - pp_line) <= 0.5:
                bet_type = None
                fair_prob = 0.0
                
                if fair_over > min_candidate_prob:
                    bet_type = "OVER"
                    fair_prob = fair_over
                elif fair_under > min_candidate_prob:
                    bet_type = "UNDER"
                    fair_prob = fair_under
                
                if bet_type:
                    # Clean up team and player strings
                    team_raw = str(row.get("Team", ""))
                    team_name = team_raw.split(" - ")[0] if " - " in team_raw else team_raw
                    position = team_raw.split(" - ")[1] if " - " in team_raw and len(team_raw.split(" - ")) > 1 else "N/A"
                    player_name = str(row.get("Player", ""))
                    initials = "".join([n[0] for n in player_name.split()[:2]]).upper() if player_name else "??"
                    if img_url in ["nan", "None", "", "NL"]: img_url = ""

                    bet_info = {
                        "id": f"{player_name}_{row.get('Prop Type')}",
                        "Player": player_name,
                        "Initials": initials,
                        "Player_Image": img_url,
                        "Team": team_name,
                        "Position": position,
                        "Sport": row.get("Sport", "NBA"),
                        "Prop_Type": row.get("Prop Type"),
                        "FanDuel_Line": fd_line,
                        "PrizePicks_Line": pp_line,
                        "Line_Diff": abs(fd_line - pp_line),
                        "Bet_Direction": bet_type,
                        "Fair_Win_Pct": fair_prob,
                        "Edge": round(fair_prob - 54.21, 2)
                    }
                    candidates.append(bet_info)
        except Exception:
            continue
            
    if not candidates:
        return []
        
    pool = candidates
    all_valid_slips = []
    
    # CASE 1: Single Prop View (Not actual slips, just top props)
    if target_size == 1:
        pool.sort(key=lambda x: x["Fair_Win_Pct"], reverse=True)
        top_props = pool[:51]
        for prop in top_props:
            slip = {
                "Avg_Win_Pct": prop["Fair_Win_Pct"],
                "Total_Edge": prop["Edge"],
                "Legs": [prop],
                "Leg_Ids": [prop["id"]],
                "Is_Fallback": True
            }
            all_valid_slips.append(slip)
        return all_valid_slips


    # Get the required win threshold for this slip configuration
    threshold = THRESHOLDS.get(style, {}).get(target_size, 54.21)
    
    # Sort candidates by win probability to prioritize best bets
    pool.sort(key=lambda x: x["Fair_Win_Pct"], reverse=True)
    
    # Use Monte Carlo / Random sampling for larger slip sizes to be more efficient
    is_monte_carlo = target_size >= 5
    
    # STRATEGY 1: 2-Man Power Play pair finding
    # We greedily pair the highest EV plays with other high EV plays from valid teams
    if target_size == 2 and style == 'power':
        search_pool = list(pool)
        while len(search_pool) >= 2:
            # Take best remaining prop
            leg1 = search_pool.pop(0)
            
            # Find the best match
            matched = False
            # Search from bottom up? (Logic here searches reverse, likely to balance or find pairing)
            for i in range(len(search_pool) - 1, -1, -1):
                leg2 = search_pool[i]
                
                # Check average EV
                avg_win_pct = (leg1["Fair_Win_Pct"] + leg2["Fair_Win_Pct"]) / 2
                if avg_win_pct <= threshold:
                    # If this pairing isn't good enough, skip (since sorted, others might be worse, but we cont)
                    continue
                
                # Prevent same team correlation (often restricted)
                if leg1["Team"] == leg2["Team"]:
                    continue
                    
                # Create Slip
                slip = {
                    "Avg_Win_Pct": round(avg_win_pct, 2),
                    "Total_Edge": round(avg_win_pct - threshold, 2),
                    "Legs": [leg1, leg2],
                    "Leg_Ids": {leg1["id"], leg2["id"]}
                }
                all_valid_slips.append(slip)
                search_pool.pop(i) # Remove used leg
                matched = True
                break
            
            # If no match found, leg1 is discarded as it couldn't be paired
            
    # STRATEGY 2: Brute Force Combinations (Small sizes < 5)
    elif not is_monte_carlo:
        # Generate all combinations of 'target_size'
        combos = itertools.combinations(pool, target_size)
        
        limit_check = 0
        max_slips = 2000
        
        for combo in combos:
            limit_check += 1
            if limit_check > 3000000: break # Safety break
            
            avg_win_pct = sum([leg["Fair_Win_Pct"] for leg in combo]) / target_size
            if avg_win_pct <= threshold:
                continue
            
            # Ensure unique players
            players = [leg["Player"] for leg in combo]
            if len(set(players)) != target_size: continue
            
            # Ensure minimum number of teams (diversity rule)
            teams = [leg["Team"] for leg in combo]
            if len(set(teams)) < 2: continue
            
            slip = {
                "Avg_Win_Pct": round(avg_win_pct, 2),
                "Total_Edge": round(avg_win_pct - threshold, 2),
                "Legs": combo,
                "Leg_Ids": set(leg["id"] for leg in combo)
            }
            all_valid_slips.append(slip)
            if len(all_valid_slips) >= max_slips: break

    # STRATEGY 3: Monte Carlo Sampling (Large sizes >= 5)
    else:

        import random
        iterations = 200000
        
        for _ in range(iterations):
            try:
                combo = random.sample(pool, target_size)
            except ValueError:
                break
                
            avg_win_pct = sum([leg["Fair_Win_Pct"] for leg in combo]) / target_size
            if avg_win_pct <= threshold:
                continue

            players = [leg["Player"] for leg in combo]
            if len(set(players)) != target_size: continue
            teams = [leg["Team"] for leg in combo]
            if len(set(teams)) < 2: continue

            slip = {
                "Avg_Win_Pct": round(avg_win_pct, 2),
                "Total_Edge": round(avg_win_pct - threshold, 2),
                "Legs": combo,
                "Leg_Ids": set(leg["id"] for leg in combo)
            }
            all_valid_slips.append(slip)
    
    # Filter and sort final results
    all_valid_slips.sort(key=lambda x: x["Avg_Win_Pct"], reverse=True)
    final_slips = []
    used_prop_ids = set()
    
    # Limit number of slips shown and ensure diversity
    # We try not to reuse the exact same props too many times to give variety
    limit = 1000
    for slip in all_valid_slips:
        # Check if slip contains extensively used props (Logic here just checks intersection, 
        # might be strict if it prevents any reuse, but seems to enforce unique sets effectively)
        if not slip["Leg_Ids"].intersection(used_prop_ids):
            final_slips.append(slip)
            used_prop_ids.update(slip["Leg_Ids"])
            
        if len(final_slips) >= limit: 
            break
            
    # Convert sets back to lists for JSON serialization
    for s in final_slips:
        s["Leg_Ids"] = list(s["Leg_Ids"])
        
    return final_slips

@app.route('/')
def dashboard():
    style = request.args.get('style', 'Power')
    size_arg = request.args.get('size', '6')
    try:
        size = int(size_arg)
    except:
        size = 6

    if style not in ["power", "flex", "props"]: style = "power"
    if size == 1: style = "props"
    
    slips = get_slips(target_size=size, style=style)
    return render_template('index.html', slips=slips, current_size=size, current_style=style)

if __name__ == "__main__":
    print("Starting PrizePicker Parlay Generator")
    print("http://127.0.0.1:5001")
    app.run(debug=True, port=5001)
