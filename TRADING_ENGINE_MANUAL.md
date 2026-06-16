# TRADING ENGINE - Complete Platform Manual
## Multi-Engine Trading Management System

---

## TABLE OF CONTENTS

1. [What Is This Platform?](#1-what-is-this-platform)
2. [The Big Picture: Architecture](#2-the-big-picture)
3. [The Global Kitty & How Money Works](#3-the-global-kitty)
4. [Understanding the TopBar](#4-understanding-the-topbar)
5. [Tab 1: Crypto Bots](#5-crypto-bots)
6. [Tab 2: Crypto Data](#6-crypto-data)
7. [Tab 3: Crypto Markets](#7-crypto-markets)
8. [Tab 4: Exchange Data](#8-exchange-data)
9. [Tab 5: Exchange Markets](#9-exchange-markets)
10. [Tab 6: The Brain](#10-the-brain)
11. [The 10-Step Processing Pipeline](#11-the-pipeline)
12. [Self-Improvement: How Engines Learn](#12-self-improvement)
13. [The Bible: Collective Intelligence](#13-the-bible)
14. [Dual-Regime Trading (SWING vs DAY)](#14-dual-regime)
15. [Engine Intervention: Nudge, Pause, Reset](#15-engine-intervention)
16. [Brokers: IBKR + Pionex](#16-brokers)
17. [Reading the Pipeline Table](#17-reading-the-table)
18. [Glossary](#18-glossary)

---

## 1. WHAT IS THIS PLATFORM?

This is a **Multi-Engine Trading Management System** — a real-time platform that runs **50 independent trading engines** simultaneously across cryptocurrency and global stock exchange markets.

Each engine:
- Watches a single market (e.g., Bitcoin, S&P 500, Nikkei 225)
- Analyzes price data using mathematical models (not simple indicators like RSI/MACD)
- Generates BUY/SELL signals when conditions align
- Executes trades (simulated or live) with automated stop-loss and take-profit
- **Learns from its own results** and adapts its strategy over time
- **Consults other engines** via a shared intelligence system called "The Bible"

The platform has **three types of engines**:

| Type | Count | What They Do |
|------|-------|-------------|
| **Crypto Coin Engines** | 24 | Trade individual cryptocurrencies (BTC, ETH, SOL, etc.) |
| **Exchange Market Engines** | 24 | Trade global stock indices (S&P 500, FTSE, DAX, Nikkei, etc.) |
| **Scalper Bots** | 2 | Autonomous BTC & ETH trading bots that scalp rapid moves |

All 50 engines share a single pool of money called the **Global Kitty**.

---

## 2. THE BIG PICTURE

```
                    TRADING ENGINE PLATFORM
                    
    [Yahoo Finance]  [Binance WebSocket]    <-- Price Data Sources
          |                  |
          v                  v
    +------------------------------------------+
    |        50 TRADING ENGINES                |
    |                                          |
    |  24 Crypto Coins    24 Exchange Markets  |
    |  2 Scalper Bots (BTC + ETH)              |
    |                                          |
    |  Each engine runs a 10-step pipeline:    |
    |  Data > Seed > Hours > Regime > Eligibility > |
    |  Performance > Signal > Sizing > Stops > Learn |
    +------------------------------------------+
          |                  |
          v                  v
    [SIM Trades]      [LIVE Trades]
    (Paper trading)   (Real money via brokers)
          |                  |
          v                  v
    +------------------+  +------------------+
    | IBKR             |  | Pionex           |
    | Stock exchanges  |  | Crypto markets   |
    | $1.70/trade      |  | 0.05% commission |
    +------------------+  +------------------+
```

**Data flow:**
1. Real market prices stream in every 2 seconds
2. Each engine processes the data through its 10-step pipeline
3. If all gates pass, a trade signal is generated
4. The trade is executed (SIM or LIVE depending on configuration)
5. Stop loss / trailing stop / take profit manage the position
6. Results feed back into the self-improvement module

---

## 3. THE GLOBAL KITTY & HOW MONEY WORKS

The **Kitty** is the shared trading fund. Currently set at **$300**.

- Every trade draws from the Kitty
- When a trade profits, the profit goes back into the Kitty
- When a trade loses, the loss comes out of the Kitty
- The Kitty is universal — all 50 engines share it

**Position sizing** is controlled globally:
- At $25 per trade, you get 12 shots from a $300 Kitty
- At $50 per trade, you get 6 shots
- At $100 per trade, you get 3 shots

The current position size also determines the **trading regime** (explained in Section 14).

**SIM vs LIVE:**
- **SIM** (Simulated): No real money. The platform tracks paper P&L using real market prices. This is how engines learn before going live.
- **LIVE**: Real money through a broker (IBKR for stocks, Pionex for crypto). Real commissions, real profit/loss.

Currently, all engines run in SIM mode. LIVE trading activates when:
1. The broker connection is established (IB Gateway for stocks, Pionex for crypto)
2. An engine meets performance thresholds
3. The engine is manually promoted to LIVE

---

## 4. UNDERSTANDING THE TOPBAR

The TopBar is the horizontal strip below the tab navigation. It appears on every tab and shows **scoped statistics** — meaning the numbers change depending on which tab you're viewing.

| Element | What It Shows |
|---------|-------------|
| **W/L** (e.g., "48 65 42%") | Wins / Losses / Win Rate for the currently selected department |
| **KITTY $61.50** | Current Kitty balance (global, same on all tabs) |
| **TODAY -$2.81** | Today's P&L for the selected department |
| **ALL TIME +$0.83** | Cumulative P&L for the selected department |
| **OPEN 2 -$0.00** | Number of currently open positions and their unrealised P&L |
| **$10 $15 $25 $50 $100 $150** | Position size selector. Click to change trade size. Highlighted = active. |
| **SWING** or **DAY** | Current trading regime (see Section 14) |
| **IB OFF** | Interactive Brokers connection status |
| **PIONEX ON** | Pionex exchange connection status |

**Important:** When you click "Crypto Data" or "Crypto Markets", the W/L, Today P&L, and Open counts show **only crypto** stats. When you click "Exchange Data" or "Exchange Markets", they show **only exchange** stats. This prevents mixing the two pools.

---

## 5. TAB 1: CRYPTO BOTS

**What you see:** Two large bot cards — the **BTC Bot** (Bitcoin Scalper) and the **ETH Bot** (Ethereum Scalper).

These are the only engines that trade **autonomously** — they don't wait for you to click anything. They watch the price stream and scalp rapid moves.

**Each bot card shows:**

| Field | Meaning |
|-------|---------|
| **Price** (e.g., 66,908) | Current live price |
| **WIN RATE** (e.g., 50.8%) | Percentage of winning trades |
| **TRADES** (e.g., 59) | Total trades executed this session |
| **W/L** (e.g., 30/29) | Wins and losses breakdown |
| **CONSEC L** (e.g., 1) | Current consecutive losses. If this hits 3+, the engine enters "maintenance" mode |
| **30M ACC** | 30-minute rolling accuracy. Shows how well the bot is performing RIGHT NOW |
| **SESSION P&L** | Profit/loss since the session started |
| **CUMULATIVE** | All-time profit/loss |
| **CURRENT THRESHOLDS** | The bot's active parameters (SL, TS, TP, Signal Prob) — these change as the bot learns |
| **LEARNING LOG** | Shows the bot's self-improvement history. Each generation (Gen) represents an adaptation cycle |
| **LIVE POSITION** | The currently open trade, showing entry price, stop loss, trailing stop, and size |

**The "GEN" badge** (e.g., "GEN 1"): This means the bot has gone through one self-improvement cycle. It reviewed its performance and adjusted its parameters. Gen 0 = default settings. Gen 1 = first adaptation. Higher = more refined.

**Learning Log entries show:**
- **LOSING** (red): Bot was losing, so it widened stops and cut volume
- **WINNING_HARD** (green): Bot was winning, so it tightened take-profit and increased volume
- **HOLD_STEADY**: Near break-even, no changes needed

---

## 6. TAB 2: CRYPTO DATA

**What you see:** A full **Pipeline Table** showing all 24 cryptocurrency engines in a single matrix.

This is the "intelligence dashboard" — it shows every engine's internal state, ranked from best performer (#1) to worst.

**Key features:**
- Engines are **ranked by performance** — #1 is your strongest engine right now
- **Top 3 are green numbered**, #4-6 are amber, rest are grey
- **Hover any row** to see a tooltip with detailed status
- **Click any row** to expand the tweak panel (adjust parameters, pause, or reset)
- **Red pulsing rows** indicate engines needing attention

The columns are explained in detail in Section 17.

---

## 7. TAB 3: CRYPTO MARKETS

**What you see:** Two sections:
1. **Open Trades** — Any cryptocurrency positions currently held
2. **Recent Trades** — History of recently closed crypto trades

This tab shows **only trade activity**, not the engine intelligence data. Use this to monitor what the crypto engines are actually doing with real positions.

Each trade entry shows: symbol, side (BUY/SELL), entry price, current price, unrealised P&L, stop loss, and trailing stop levels.

---

## 8. TAB 4: EXCHANGE DATA

**What you see:** Same Pipeline Table as Crypto Data, but for the **24 global stock exchange engines**.

**Extra column — STATUS:**
Since stock exchanges have opening hours (unlike 24/7 crypto), this column shows:
- **OPEN** (green) — Market is currently trading
- **CLOSED** (red) — Market is closed, with a countdown: e.g., "Opens 1d 8h" tells you exactly when it reopens

**Country flags** appear next to each market symbol:
- US flag for SPX, NDX, DJI, RUSSELL, VIX
- UK flag for FTSE
- German flag for DAX
- Japanese flag for NIKKEI
- etc.

The platform is holiday-aware — it knows about Easter, public holidays, and correctly skips non-trading days in the countdown.

---

## 9. TAB 5: EXCHANGE MARKETS

**What you see:** Same as Crypto Markets but for exchanges — open positions and recent trade history for stock index engines.

Since most exchanges are only open during business hours, this tab will be more active during weekdays in the relevant time zones.

---

## 10. TAB 6: THE BRAIN

**What you see:** The complete **Engine Processing Pipeline** — the 10-step logic chain that every engine follows on every price tick.

This tab reveals the "thinking" behind the system. It uses one of the scalper bots as a live example, showing real values at each step.

Below the pipeline steps, you'll find **The Bible** section (see Section 13).

---

## 11. THE 10-STEP PROCESSING PIPELINE

Every engine — whether it's trading BTC, the S&P 500, or the Nikkei — runs through these 10 gates on every price tick (every 2 seconds). Each gate must pass before the next one fires.

### Step 1: MARKET DATA FEED
**What it does:** Receives the latest price from Yahoo Finance (exchanges) or Binance WebSocket (crypto).
**Status:** Shows current price. "LIVE" = data is flowing. If this fails, the engine can't do anything.

### Step 2: SEED MODE
**What it does:** When an engine first starts, it needs historical price data to calibrate its models. During seeding, it collects data without trading.
**Status:** "PASSED" = seeding complete. A percentage means it's still collecting.

### Step 3: MARKET HOURS
**What it does:** Checks if the market is currently open. Crypto is 24/7 so always passes. Stock exchanges are checked against their local trading hours + holiday calendar.
**Status:** "OPEN" = can trade. "CLOSED" = waiting for market to reopen.

### Step 4: REGIME DETECTION
**What it does:** Analyses price patterns to determine the current market condition:
- **TRENDING_UP** — Price is moving upward with momentum
- **TRENDING_DOWN** — Price is moving downward with momentum
- **CHOPPY_LOW/MEDIUM/HIGH** — Price is moving sideways with varying volatility
- **REVERSAL** — Trend is potentially changing direction
**Why it matters:** Different regimes require different trading strategies. The engine won't trade in unfavourable conditions.

### Step 5: ELIGIBILITY CHECK
**What it does:** Calculates three critical metrics:
- **R.Fit** (Regime Fit, 0-1): How well does the current price behaviour fit the detected regime? Higher = clearer pattern.
- **Confidence** (0-1): How certain is the model about the regime? Higher = more reliable.
- **Tier** (0-5): Overall eligibility tier. Tier 3+ is eligible to trade.
**Status:** "ELIGIBLE" if tier >= 3. "INELIGIBLE" if not.

### Step 6: PERFORMANCE GATES
**What it does:** Checks historical performance to decide if the engine deserves to keep trading:
- **PF** (Profit Factor): Total wins / total losses. Above 2.5 is strong.
- **Acc** (Accuracy): Percentage of winning trades. Above 75% is strong.
- **Health** (0-100): Overall engine health score. Above 40 is healthy.
**Status:** "ACTIVE" if all gates pass.

### Step 7: SIGNAL GENERATION
**What it does:** A probabilistic signal generator. Even if all previous gates pass, a trade signal only fires with a certain probability (the "Signal Probability").
- Higher signal_prob = more trades
- Lower signal_prob = fewer, more selective trades
The self-improvement module adjusts this probability based on performance.
**Status:** "ARMED" = ready to generate signals.

### Step 8: POSITION SIZING & ENTRY
**What it does:** Calculates how much capital to allocate:
- Scalpers: Fixed at $2 per trade
- Market/Coin engines: Uses the global position size ($10-$150)
- Checks the Kitty has enough funds
**Status:** Shows "$ per trade" amount.

### Step 9: STOP LOSS / TRAILING STOP / TAKE PROFIT
**What it does:** Once a position is opened, three exit mechanisms are set:
- **Stop Loss (SL):** Maximum acceptable loss. If price drops this far, close immediately.
- **Trailing Stop (TS):** Follows the price upward, locking in profit. If price reverses by TS%, close.
- **Take Profit (TP):** Target profit level. When price reaches this, close and book the win.
**Status:** "MONITORING" with current SL% and TP% values.

### Step 10: SELF-IMPROVEMENT + THE BIBLE
**What it does:** Periodically reviews performance and adapts parameters. Consults The Bible for collective wisdom. See Sections 12 and 13.
**Status:** Shows current generation and Bible entry count.

---

## 12. SELF-IMPROVEMENT: HOW ENGINES LEARN

Every engine has a **self-improvement module** that reviews its trading results and adapts.

**When does it review?**
- Scalper bots: Every 20 trades
- Market/Coin engines: Every 5 trades

**What does it review?**
- Win rate (% of trades that were profitable)
- Cumulative P&L (total profit/loss)
- Consecutive losses (how many in a row)

**What decisions can it make?**

| Decision | Trigger | Action |
|----------|---------|--------|
| **WINNING_HARD** | WR > 70%, positive P&L | Tighten TP, increase volume, tighten SL |
| **HIGH_WR_NEG_PNL** | WR > 70%, but P&L negative | Widen TP (losses too big per trade) |
| **DECENT** | WR > 60% | Small tighten on TP, nudge volume up |
| **HOLD_STEADY** | WR 55-60% | No changes |
| **BELOW_BREAKEVEN** | WR 45-55% | Widen stops, reduce signal frequency |
| **LOSING** | WR < 45% | Widen stops significantly, cut volume hard |

**What parameters change?**
- `stop_loss_pct` — How much loss to tolerate
- `trailing_stop_pct` — How close the trailing stop follows
- `take_profit_pct` — Target profit percentage
- `signal_prob` — How often to generate trade signals

Each review cycle increments the **generation counter** (Gen 0, Gen 1, Gen 2...). You can see the full history in the Learning Log on each bot card.

---

## 13. THE BIBLE: COLLECTIVE INTELLIGENCE

**The Bible** is the breakthrough feature that separates this system from standard trading bots. It's a **shared intelligence layer** across all 50 engines.

**How it works:**

1. **Writing:** After every self-improvement cycle, the engine writes an entry to The Bible:
   - What regime was it in? (TRENDING_UP, CHOPPY_HIGH, etc.)
   - What volatility class? (LOW, MEDIUM, HIGH, EXTREME)
   - What problem did it face? (LOSING, BELOW_BREAKEVEN, etc.)
   - What parameter changes did it make?
   - Did those changes actually work? (effectiveness score, added later)

2. **Consulting:** Before an engine makes its own adaptation, it asks The Bible:
   > "Has any other engine faced this exact situation?"
   
   If Bitcoin's engine was LOSING in a CHOPPY_HIGH regime and widened its SL from 0.3% to 0.5%, and that change improved its win rate — that wisdom is available to ETH, SOL, or even the NIKKEI engine if they face the same pattern.

3. **Blending:** When The Bible has relevant advice, the engine blends it:
   - **70% own decision** (what it calculated from its own data)
   - **30% Bible wisdom** (what another engine proved works)
   
   This prevents blind copying while still benefiting from collective experience.

4. **Effectiveness Tracking:** Each Bible entry gets an effectiveness score after the next review cycle. Positive = the change helped. Negative = it didn't. This means The Bible self-corrects — bad advice naturally gets deprioritised.

**The Bible UI** (visible on The Brain tab):
- **Entries:** Total experiences written
- **Scored:** How many have been evaluated for effectiveness
- **Helpful:** How many had a positive effectiveness score
- **Help Rate:** Percentage of advice that actually worked
- **Top Lessons:** The most effective patterns discovered
- **Recent Entries:** Latest experiences from all engines

---

## 14. DUAL-REGIME TRADING (SWING vs DAY)

The position size you select doesn't just determine how much money per trade — it changes the entire trading strategy.

### SWING Mode ($10 - $75 per trade)
- **Stop Loss:** 3.5%
- **Trailing Stop:** 2.5%
- **Take Profit:** 8%
- **Signal Probability:** 12%
- **Max Hold:** Up to 5 days
- **Why:** Small positions need bigger moves to overcome IBKR's $1.70 commission. At $25, you need 6.8% just to break even. So the engine holds longer, waiting for multi-day swings (5-day average swing: Nikkei 9.18%, DAX 6.70%, ASX 6.20%).

### DAY Mode ($75+ per trade)
- **Stop Loss:** 2%
- **Trailing Stop:** 1.5%
- **Take Profit:** 3%
- **Signal Probability:** 15%
- **Max Hold:** 1-2 days
- **Why:** Larger positions can profit on smaller moves. At $100, a 3% move = $3.00 gain minus $1.70 commission = $1.30 profit. The average daily range for SPX, Nasdaq, and DAX hits 1.5-2.3%, so even a normal day can produce winners.

**The label "SWING" or "DAY"** appears next to the position size selector in the TopBar, so you always know which regime is active.

**Self-improvement bounds scale with the regime:** In SWING mode, engines can learn TP targets from 5-12%. In DAY mode, they learn within 2-6%. This prevents a swing engine from accidentally tightening to day-trade levels and vice versa.

---

## 15. ENGINE INTERVENTION: NUDGE, PAUSE, RESET

You have three levels of manual intervention for any engine:

### Level 1: DO NOTHING (let it self-correct)
The self-improvement module is always running. A losing engine will automatically widen its stops and cut its signal frequency. Give it time.

### Level 2: NUDGE (manual tweak)
**How:** Click any row in the Crypto Data or Exchange Data table. A tweak panel expands below the row.

You can adjust:
- **SL%** — Stop loss percentage
- **TS%** — Trailing stop percentage
- **TP%** — Take profit percentage
- **SIG%** — Signal probability
- **PAUSE** — Temporarily stop the engine from trading
- **RESUME** — Restart a paused engine

Click **NUDGE** to apply. The engine keeps its generation history and continues learning from the new parameters.

### Level 3: FULL RESET (nuclear option)
Click the **FULL RESET** button in the tweak panel, or the **RST** button that appears on red/flashing rows. This:
- Wipes all learned parameters back to defaults
- Resets the generation counter to 0
- Clears the trade history
- The engine starts learning from scratch

**When to use:** Only when an engine is truly broken — stuck in a losing loop that self-improvement can't escape.

### Red Row Alert System
When an engine triggers any of these conditions, its entire row turns red and pulses:
- 3+ consecutive losses
- Accuracy below 40% (with 5+ trades)
- Health score below 20
- No price data flowing
- Win rate below 35% (with 5+ trades)

A red dot appears next to the market name, and a **RST** button appears in the last column.

---

## 16. BROKERS: IBKR + PIONEX

The platform connects to two brokers:

### Interactive Brokers (IBKR)
- **Used for:** Stock exchange markets (SPX, FTSE, DAX, Nikkei, etc.)
- **Commission:** ~$1.70 per round-trip trade
- **Connection:** Via IB Gateway running locally. Status shows "IB OFF" or "IB LIVE" in the TopBar.
- **Minimum viable trade:** $100+ per trade (at $25, commission eats 7% of the trade value)

### Pionex
- **Used for:** Cryptocurrency scalping (BTC, ETH)
- **Commission:** 0.05% per trade (0.10% round-trip) — 17x cheaper than IBKR for crypto
- **Connection:** API key authenticated. Status shows "Pionex ON" or "Pionex OFF" in the TopBar.
- **USDT deposit needed** before live trading can begin

**Strategy:**
- Market engines trade via IBKR (SWING mode, multi-day holds)
- Crypto scalpers trade via Pionex (rapid scalps, low commission)
- All engines start in SIM mode, promoted to LIVE when proven profitable

---

## 17. READING THE PIPELINE TABLE

The Pipeline Table (visible on Crypto Data and Exchange Data tabs) shows every engine's complete state. Here's every column explained:

| Column | Full Name | What It Means |
|--------|-----------|--------------|
| **#** | Rank | Performance ranking. #1 = best engine. Green = top 3, Amber = #4-6. |
| **MARKET** | Symbol | The asset being traded, with its icon/flag. Red text = needs maintenance. |
| **WPS** | Win Probability Score | -100 to +100 composite score. Green (50+) = strong. Amber (25+) = decent. Red (-25 or below) = weak. |
| **PRICE** | Current Price | Live market price. |
| **STATUS** | Market Status | (Exchange only) OPEN/CLOSED with countdown to next open. |
| **SD** | Seed | OK = seeded and ready. Percentage = still collecting data. |
| **RGM** | Regime | UP = trending up. DN = trending down. CL/CM/CH = choppy (low/med/high). RV = reversal. |
| **VOL** | Volatility Class | GREEN=LOW, BLUE=MEDIUM, AMBER=HIGH, RED=EXTREME. |
| **FIT/CN/T** | R.Fit / Confidence / Tier | Three eligibility metrics. Green = passing, Red = failing. Tier 3+ = eligible. |
| **PF/AC/H** | Profit Factor / Accuracy / Health | Performance metrics. PF 2.5+ is strong. Acc 75%+ is strong. Health 40+ is healthy. |
| **SG** | Signal | Current signal probability %. Higher = more active. |
| **TIER** | Signal Tier | HIGH (green), MEDIUM (amber), BLOCKED (red). |
| **POS** | Position | Current open position: BUY/SELL + unrealised P&L. Dash = no position. |
| **SL/TR/TP** | Stop Loss / Trail / Take Profit | In percentages. Red numbers = loss limits. Green = profit target. |
| **GEN** | Generation | Self-improvement generation. "G2 65%" means Gen 2 with 65% win rate. |
| **W/L** | Wins / Losses | Today's trade results. |
| **P&L** | Profit & Loss | Cumulative P&L. Green = profit, Red = loss. |

---

## 18. GLOSSARY

| Term | Definition |
|------|-----------|
| **Engine** | An independent trading unit that watches one market and makes autonomous decisions |
| **Kitty** | The shared money pool all engines draw from |
| **SIM** | Simulated trading — paper trades using real prices but no real money |
| **LIVE** | Real trading through a broker with real money |
| **WPS** | Win Probability Score — composite metric from -100 to +100 |
| **R.Fit** | Regime Fit — how clearly the current price matches the detected market pattern (0-1) |
| **Regime** | The detected market condition: trending, choppy, or reversal |
| **Vol Class** | Volatility classification: LOW, MEDIUM, HIGH, EXTREME |
| **Signal Tier** | Whether the engine is cleared to generate signals: HIGH, MEDIUM, or BLOCKED |
| **Self-Improve** | The module that reviews trade results and adapts parameters automatically |
| **Generation (Gen)** | Each self-improvement cycle increments the generation counter |
| **The Bible** | Shared experience log across all 50 engines — collective intelligence |
| **Effectiveness** | Score tracking whether a Bible entry's advice actually improved results |
| **SWING** | Trading regime for small positions ($10-75): wider targets, longer holds |
| **DAY** | Trading regime for larger positions ($75+): tighter targets, shorter holds |
| **Nudge** | Manual parameter adjustment that preserves learning history |
| **Full Reset** | Wipes engine back to Gen 0 defaults |
| **Stop Loss (SL)** | Maximum loss tolerance — auto-closes trade if breached |
| **Trailing Stop (TS)** | Follows price up, locks in profit — closes if price reverses by TS% |
| **Take Profit (TP)** | Target profit level — auto-closes trade when reached |
| **Profit Factor (PF)** | Total winning dollars / total losing dollars |
| **IBKR** | Interactive Brokers — broker for stock exchange trades |
| **Pionex** | Cryptocurrency exchange — broker for crypto scalper trades |
| **Scalper** | A bot that makes rapid, small trades (seconds to minutes) |
| **Pipeline** | The 10-step logic chain every engine runs on every price tick |

---

## QUICK START GUIDE

1. **Open the platform** and you'll land on **Crypto Bots** — see the two scalper bots working
2. Click **Crypto Data** to see all 24 crypto engines ranked by performance
3. Click **Exchange Data** to see all 24 stock exchange engines (all say "CLOSED" on weekends/holidays)
4. Check the **TopBar** for Kitty balance, W/L ratio, and current P&L
5. Click **The Brain** to understand the 10-step pipeline and see The Bible
6. Hover any row in Data tables for a status tooltip
7. Click any row to expand the tweak panel for manual intervention

**The system is self-managing.** The engines trade, learn, adapt, and share intelligence via The Bible. Your job is to monitor, intervene when needed, and decide when to promote engines from SIM to LIVE.

---

*Manual generated: April 2026*
*Platform Version: Trading Engine v2.0*
