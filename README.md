# 💰 PrizePicker

PrizePicker is a high-performance **Prop Betting Analyzer & Parlay Generator**. It leverages real-time sports data to identify +EV (Expected Value) opportunities by comparing PrizePicks lines against "Fair Odds" (vig-removed) derived from major sportsbooks like FanDuel.

---

## 🔥 Key Features

- **🚀 Automated Scraper**: High-speed Selenium scraper for extraction of player props across multiple markets (Points, Rebounds, Assists, etc.) for NBA and NFL.
- **📈 EV Analysis Engine**: Calculates "No-Vig" fair win probabilities to find the mathematical edge on every bet.
- **🎯 Optimal Slip Generation**:
    - **2-Man Power Plays**: High-conviction pairings.
    - **3-6 Man Flex Plays**: Diversified slips using Monte Carlo sampling for large pools.
- **🖥️ Web Dashboard**: A sleek, interactive Flask-based UI to view, filter, and analyze the best available slips in real-time.

---

## 🛠️ Tech Stack

- **Backend**: Python, Flask
- **Scraping**: Selenium, Pandas
- **Logic**: Monte Carlo Simulations, Itertools for combination analysis
- **Frontend**: HTML5, Vanilla CSS (Modern, Responsive Design)

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.8+
- Chrome Browser (for Selenium)

### 2. Installation
Clone the repository and install dependencies:
```bash
pip install -r requirements.txt
```

### 3. Usage
#### Step 1: Scrape Fresh Odds
Run the scraper to collect the latest lines and calculate fair odds:
```bash
python scraper.py
```
*Data is saved to the `/props` directory.*

#### Step 2: Launch the Dashboard
Start the Flask server to generate and view optimal slips:
```bash
python find_bets.py
```
Visit `http://127.0.0.1:5001` in your browser.

---

## 📊 How it Works

![PrizePicks +EV Thresholds](prizepicks_thresholds.png)

1. **Vig Removal**: The system takes FanDuel's Over/Under odds and removes the "vig" (bookmaker's margin) to find the true "Fair" win probability.
2. **Line Comparison**: It compares the PrizePicks line to the FanDuel line. If the lines are identical or very close (within 0.5), it calculates the edge.
3. **Threshold Filtering**: Only bets with a win probability higher than the break-even threshold (e.g., ~54.21% for 6-man flex) are considered.
4. **Diversity Rule**: The generator ensures that slips contain unique players and multiple teams to satisfy sportsbook requirements.

---

## 📂 Project Structure

- `scraper.py`: The data collection engine using Selenium.
- `find_bets.py`: The core logic for slip generation and the Flask web server.
- `templates/index.html`: The interactive dashboard frontend.
- `props/`: Storage for scraped CSV data.

---
*Disclaimer: This tool is for informational and educational purposes only. Always gamble responsibly.*
