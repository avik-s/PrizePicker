"""
fanduelScraper.py

This script scrapes player prop odds from BettingPros.com, specifically targeting FanDuel and PrizePicks lines.
It collects data for various markets (e.g., Points, Rebounds, Assists) for NFL and NBA.

Key Features:
- Uses Selenium for dynamic page content loading (infinite scroll handling).
- Extracts player names, teams, and Prop lines.
- Calculates "Fair" odds by removing the vigorish (using Novig method) from FanDuel's two-way lines.
- Saves cleaned and processed data into CSV files in the 'props/' directory for use by find_bets.py.
"""
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import time
import os
from datetime import date

def calculate_novig(over_odds, under_odds):
    """
    Calculates the "Fair" win probability (Novig prob) for a two-way market.
    Removes the bookmaker's margin (vig) from American odds.

    Args:
        over_odds (int): American odds for the Over (e.g., -110, +100).
        under_odds (int): American odds for the Under.

    Returns:
        tuple: (fair_over_prob, fair_under_prob) as floats (0.0 - 1.0).
    """
    def get_implied(american_odds):
        if american_odds > 0:
            return 100 / (american_odds + 100)
        else:
            return abs(american_odds) / (abs(american_odds) + 100)

    try:
        prob_over = get_implied(over_odds)
        prob_under = get_implied(under_odds)
        
        market_sum = prob_over + prob_under
        
        fair_over = prob_over / market_sum
        fair_under = prob_under / market_sum
        return fair_over, fair_under
    except ZeroDivisionError:
        return 0.0, 0.0

def scrape_market(driver, sport, prop_name, url_suffix):
    """
    Scrapes a specific prop market (e.g., 'nba', 'Points') using Selenium.
    Handles page scrolling to ensure all players are loaded.
    """
    base_url = f"https://www.bettingpros.com/{sport}/odds/player-props/"
    url = f"{base_url}{url_suffix}?date={date.today()}"
    print(f"\n--- Starting Scrape: {sport.upper()} {prop_name} ---")
    print(f"Connecting to {url}")
    
    market_data = []
    
    # Retry logic for initial page load
    first_attempt = True
    while True:
        try:
            if not first_attempt:
                print(f"Retrying connection to {prop_name}")
            
            driver.get(url)
            
            wait = WebDriverWait(driver, 30)
            # Wait for main table container and at least one odds row
            container = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".grouped-items-with-sticky-footer")))
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "odds-offer")))
            break
            
        except Exception as e:
            print(f"Timeout/Error loading {prop_name}. Retrying in 5 seconds")
            time.sleep(5)
            first_attempt = False
            continue
            
    print("Page initial load complete.")

    try:
        # Locate the headers to find which column corresponds to FanDuel and PrizePicks
        # The column order can change, so we must identify dynamically
        header_items = container.find_elements(By.CSS_SELECTOR, ".odds-offers-header .odds-offers-header__item")
        
        fd_index = -1
        pp_index = -1
        
        for i, header in enumerate(header_items):
            text = header.text.strip()
            inner = header.get_attribute("innerHTML")
            
            if "FanDuel" in text or 'alt="FanDuel"' in inner or 'src' in inner and 'fanduel' in inner.lower():
                fd_index = i
            elif "PrizePicks" in text or 'alt="PrizePicks"' in inner or 'src' in inner and 'prizepicks' in inner.lower():
                pp_index = i
        
        if fd_index == -1: print(f"Warning: FanDuel column not found for {prop_name}.")
        if pp_index == -1: print(f"Warning: PrizePicks column not found for {prop_name}.")

        print(f"Scrolling to load all data for {prop_name}")
        
        # Infinite scroll handling - BettingPros loads data as you scroll down
        last_height = driver.execute_script("return document.body.scrollHeight")
        retries = 0
        max_retries = 5
        
        while True:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            
            time.sleep(.5)
            
            new_height = driver.execute_script("return document.body.scrollHeight")
            
            if new_height == last_height:
                retries += 1
                if retries <= max_retries:
                    print(f"  > Retrying at height {last_height} ({retries}/{max_retries})")
                    
                    # 'Refresh Maneuver': Scroll up a bit then back down to trigger load
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight - 1000);")
                    time.sleep(.5)

                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight - 500);")
                    time.sleep(.5)

                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    
                    new_height = driver.execute_script("return document.body.scrollHeight")
                    
                    if new_height > last_height:
                        rows_found = len(driver.find_elements(By.CLASS_NAME, "odds-offer"))
                        print(f"  > Loading more data (height: {new_height}, players: {rows_found})")
                        last_height = new_height
                        retries = 0
                else:
                    print("  > Reached end of page.")
                    break
            else:
                rows_found = len(driver.find_elements(By.CLASS_NAME, "odds-offer"))
                print(f"  > Loading more data (height: {new_height}, players: {rows_found})")
                last_height = new_height
                retries = 0

        container = driver.find_element(By.CSS_SELECTOR, ".grouped-items-with-sticky-footer")
        player_rows = container.find_elements(By.CLASS_NAME, "odds-offer")
        
        print(f"Parsing {len(player_rows)} rows")

        for row in player_rows:
            try:
                name_els = row.find_elements(By.CLASS_NAME, "odds-player__heading")
                if not name_els:
                    continue
                name = name_els[0].text.strip()
                
                try:
                    team_el = row.find_element(By.TAG_NAME, "p")
                    team = team_el.text.strip()
                except:
                    team = "Unknown"

                try:
                    img_el = row.find_element(By.TAG_NAME, "img")
                    img_url = img_el.get_attribute("src")
                except:
                    if sport == "nba":
                        img_url = "https://www.nba.com/assets/logos/teams/primary/web/MIN.svg" 
                    else:
                        img_url = "https://static.www.nfl.com/league/apps/fantasy/logos/200x200/NFL.png"

                row_data = {
                    "Player": name,
                    "Player Image": img_url,
                    "Team": team,
                    "Sport": sport.upper(),
                    "Prop Type": prop_name,
                    "FanDuel Line": "NL",
                    "FD Over Odds": "NL",
                    "FD Under Odds": "NL",
                    "PrizePicks Line": "NL",
                    "FD Fair Over %": 0,
                    "FD Fair Under %": 0
                }
                
                cells = row.find_elements(By.CLASS_NAME, "odds-offer__item")
                
                if fd_index != -1 and fd_index < len(cells):
                    cell = cells[fd_index]
                    try:
                        buttons = cell.find_elements(By.CSS_SELECTOR, ".odds-cell")
                        for btn in buttons:
                            line_text = btn.find_element(By.CLASS_NAME, "odds-cell__line").text.strip()
                            cost_text = btn.find_element(By.CLASS_NAME, "odds-cell__cost").text.strip().replace('(', '').replace(')', '')
                            
                            if line_text.startswith("O"):
                                row_data["FanDuel Line"] = line_text.replace('O', '').strip()
                                row_data["FD Over Odds"] = "+100" if cost_text == "EVEN" else cost_text
                            elif line_text.startswith("U"):
                                if row_data["FanDuel Line"] == "NL":
                                    row_data["FanDuel Line"] = line_text.replace('U', '').strip()
                                row_data["FD Under Odds"] = "+100" if cost_text == "EVEN" else cost_text
                    except:
                        pass
                
                if pp_index != -1 and pp_index < len(cells):
                    cell = cells[pp_index]
                    try:
                        lines = cell.find_elements(By.CLASS_NAME, "odds-cell__line")
                        for l in lines:
                            txt = l.text.strip()
                            if txt:
                                row_data["PrizePicks Line"] = txt.replace('O', '').replace('U', '').strip()
                                break
                    except:
                        pass
                        
                try:
                    o = row_data["FD Over Odds"]
                    u = row_data["FD Under Odds"]
                    if o != "NL" and u != "NL":
                        fair_o, fair_u = calculate_novig(int(o), int(u))
                        row_data["FD Fair Over %"] = round(fair_o * 100, 2)
                        row_data["FD Fair Under %"] = round(fair_u * 100, 2)
                except:
                    pass

                market_data.append(row_data)
                
            except Exception:
                continue
                
    except Exception as e:
        print(f"Unexpected error scraping {prop_name}: {e}")
        
    print(f"Collected {len(market_data)} items for {prop_name}.")
    return market_data

def scrape_multibook_props():
    """
    Main execution function.
    Initializes a Selenium WebDriver, defines markets to scrape,
    iterates through them, scrapes data, cleans duplicates,
    and saves the results to CSV files.
    """
    chrome_options = Options()
    # Run in headless mode (no GUI)
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("window-size=1280,800")
    # Disable automation detection
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    driver = webdriver.Chrome(options=chrome_options)
    
    # List of markets to scrape: (Sport, PropName, URL_Suffix)
    markets = [
        ("nba", "Points", "points/"),
        ("nba", "Rebounds", "rebounds/"),
        ("nba", "Assists", "assists/"),
        ("nba", "Steals", "steals/"),
        ("nba", "Blocks", "blocks/"),
        ("nba", "Points+Assists", "points-assists/"),
        ("nba", "Points+Rebounds", "points-rebounds/"),
        ("nba", "Rebounds+Assists", "rebounds-assists/"),
        ("nba", "Pts+Reb+Ast", "points-assists-rebounds/"),

        # ("nfl", "Receiving Yards", "receiving-yards/"),
        # ("nfl", "Receptions", "receptions/"),
        # ("nfl", "Rushing Yards", "rushing-yards/"),
        # ("nfl", "Rushing Attempts", "rushing-attempts/"),
        # ("nfl", "Passing Yards", "passing-yards/"),
        # ("nfl", "Passing Attempts", "passing-attempts/"),
        # ("nfl", "Passing Completions", "passing-completions/"),
    ]
    
    all_data = []
    
    output_folder = "props"
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    try:
        for sport, prop_name, suffix in markets:
            market_data = scrape_market(driver, sport, prop_name, suffix)
            
            if market_data:
                df_prop = pd.DataFrame(market_data)


                initial_count = len(df_prop)
                df_prop.drop_duplicates(subset=["Player", "Team", "Sport", "Prop Type"], keep='first', inplace=True)
                dropped_count = initial_count - len(df_prop)
                if dropped_count > 0:
                    print(f"Removed {dropped_count} duplicates for {prop_name}.")
                
                cols = ["Player", "Player Image", "Team", "Sport", "Prop Type", "FanDuel Line", "FD Over Odds", "FD Under Odds", "PrizePicks Line", "FD Fair Over %", "FD Fair Under %"]

                cols = [c for c in cols if c in df_prop.columns]
                df_prop = df_prop[cols]
                
                clean_name = prop_name.lower().replace("+", "_").replace(" ", "_")
                output_file = f"{output_folder}/{sport}_props_{clean_name}.csv" 
                df_prop.to_csv(output_file, index=False)
                print(f"Saved {len(df_prop)} rows to {output_file}")
                
                all_data.extend(market_data)
            
            time.sleep(2)
            
        if all_data:
            print(f"\nCollected {len(all_data)} total props.")
        else:
            print("No data collected.")

    finally:
        driver.quit()

if __name__ == "__main__":
    scrape_multibook_props()