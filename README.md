R25 Sniper Signal Bot (Deriv)

A Python-based signal alert bot that analyzes Deriv Volatility 25 Index (R_25) and sends trading alerts to Telegram.

The bot uses multiple indicators to detect high-probability entries and sends alerts with Entry Price, Stop Loss, and Take Profit calculated using ATR.

This bot does NOT execute trades. It only sends alerts so the trader can place trades manually.

---

Features

• Real-time Volatility 25 Index analysis
• EMA 9 / EMA 21 crossover strategy
• RSI momentum confirmation
• MACD trend confirmation
• ATR-based Stop Loss & Take Profit
• Telegram BUY / SELL alerts
• Render deployment ready
• WebSocket connection to Deriv API

---

Example Telegram Alert

🟢 R25 BUY SIGNAL

Entry: 3456.21
Stop Loss: 3449.60
Take Profit: 3472.80

Indicators
RSI: 55.3
MACD: 0.0018
ATR: 3.40

Time: 2026-03-09

---

Strategy Logic

The bot sends a signal when the following conditions align:

BUY Signal

- EMA 9 crosses above EMA 21
- RSI above 50
- MACD above signal line

SELL Signal

- EMA 9 crosses below EMA 21
- RSI below 50
- MACD below signal line

Stop Loss and Take Profit are calculated using ATR volatility measurement.

Stop Loss = Entry − (ATR × 2)
Take Profit = Entry + (ATR × 4)

---

Project Structure

project
│
├── bot.py
├── requirements.txt
├── render.yaml
└── README.md

---

Installation (Local)

Install dependencies:

pip install -r requirements.txt

Run the bot:

python bot.py

---

Environment Variables

Set these variables before running the bot:

DERIV_APP_ID
DERIV_API_TOKEN
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID

Example:

DERIV_APP_ID=1089
DERIV_API_TOKEN=your_deriv_token
TELEGRAM_BOT_TOKEN=your_telegram_token
TELEGRAM_CHAT_ID=your_chat_id

---

Deploy on Render

1. Push project to GitHub
2. Go to Render
3. Click New → Blueprint
4. Connect your GitHub repository
5. Render will read "render.yaml" and deploy automatically.

---

Requirements

Python 3.10+

Libraries used:

- flask
- websockets
- pandas
- numpy
- requests

---

Disclaimer

This project is for educational purposes only.

Trading involves risk. Always test strategies before using real funds.

---

Author

Daniel Televisa
Algorithmic trading enthusiast focusing on Deriv Volatility indices.
