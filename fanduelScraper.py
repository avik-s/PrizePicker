from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import time
import random
import os

def calculate_novig(over_odds, under_odds):
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

def scrape_market(driver, prop_name, url_suffix):
    base_url = "https://www.bettingpros.com/nba/odds/player-props/"
    url = f"{base_url}{url_suffix}"
    print(f"\n--- Starting Scrape: {prop_name} ---")
    print(f"Connecting to {url}...")
    
    market_data = []
    
    try:
        driver.get(url)
        
        wait = WebDriverWait(driver, 30)
        try:
            container = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".grouped-items-with-sticky-footer")))
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "odds-offer")))
        except:
            print(f"Timeout loading {prop_name}. Skipping...")
            return []
            
        print("Page initial load complete.")

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

        print(f"Scrolling to load all data for {prop_name}...")
        
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
                    print(f"  > stuck at height {last_height}. trying a scroll shake to fix it ({retries}/{max_retries})...")
                    
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight - 1000);")
                    time.sleep(.5)

                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight - 500);")
                    time.sleep(.5)

                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    
                    new_height = driver.execute_script("return document.body.scrollHeight")
                    
                    if new_height > last_height:
                        print("  > Loading more data...")
                        last_height = new_height
                        retries = 0
                else:
                    print("  > Reached end of page.")
                    break
            else:
                rows_found = len(driver.find_elements(By.CLASS_NAME, "odds-offer"))
                print(f"  > Loading more data... (height: {new_height}, players: {rows_found})")
                last_height = new_height
                retries = 0

        container = driver.find_element(By.CSS_SELECTOR, ".grouped-items-with-sticky-footer")
        player_rows = container.find_elements(By.CLASS_NAME, "odds-offer")
        
        print(f"Parsing {len(player_rows)} rows...")

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
                
                row_data = {
                    "Player": name,
                    "Team": team,
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

def scrape_nba_multibook_props():
    chrome_options = Options()
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("window-size=1280,800")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    driver = webdriver.Chrome(options=chrome_options)
    
    markets = [
        ("Points", "points/"),
        ("Rebounds", "rebounds/"),
        ("Assists", "assists/"),
        ("Steals", "steals/"),
        ("Blocks", "blocks/"),
        ("Points+Assists", "points-assists/"),
        ("Points+Rebounds", "points-rebounds/"),
        ("Rebounds+Assists", "rebounds-assists/"),
        ("Pts+Reb+Ast", "points-assists-rebounds/")
    ]
    
    all_data = []
    
    output_folder = "props"
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    try:
        for prop_name, suffix in markets:
            market_data = scrape_market(driver, prop_name, suffix)
            
            if market_data:
                df_prop = pd.DataFrame(market_data)
                
                cols = ["Player", "Team", "Prop Type", "FanDuel Line", "FD Over Odds", "FD Under Odds", "PrizePicks Line", "FD Fair Over %", "FD Fair Under %"]
                cols = [c for c in cols if c in df_prop.columns]
                df_prop = df_prop[cols]
                
                clean_name = prop_name.lower().replace("+", "_").replace(" ", "_")
                output_file = f"{output_folder}/nba_props_{clean_name}.csv"
                df_prop.to_csv(output_file, index=False)
                print(f"Saved {len(df_prop)} rows to {output_file}")
                
                all_data.extend(market_data)
            
            time.sleep(2)
            
        if all_data:
            print(f"\nCollectd {len(all_data)} total props.")
        else:
            print("No data collected.")

    finally:
        driver.quit()

if __name__ == "__main__":
    scrape_nba_multibook_props()