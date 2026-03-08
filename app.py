"""
Sniper Signal Bot for Deriv - R_25
Render Deployment Ready
"""

import os
import asyncio
import json
import logging
import websockets
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, List
from flask import Flask, jsonify, render_template_string
from threading import Thread

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask app for Render
app = Flask(__name__)

# Global state
bot_state = {
    "status": "initializing",
    "last_signal": None,
    "signals_history": [],
    "current_price": None,
    "indicators": {},
    "uptime": datetime.now(),
    "connection_status": "disconnected",
    "total_signals": 0
}


@dataclass
class Signal:
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    confluence_score: int
    timestamp: datetime
    indicators: Dict[str, Any]
    
    def to_dict(self):
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data
    
    def to_telegram_message(self) -> str:
        emoji = "🟢" if self.direction == "BUY" else "🔴"
        rr_ratio = abs(self.take_profit - self.entry_price) / abs(self.entry_price - self.stop_loss)
        
        return f"""
{emoji} <b>SNIPER SIGNAL - R_25</b> {emoji}

📊 <b>Symbol:</b> <code>{self.symbol}</code>
📈 <b>Direction:</b> <b>{self.direction}</b>
💰 <b>Entry:</b> <code>{self.entry_price:.4f}</code>
🛑 <b>Stop Loss:</b> <code>{self.stop_loss:.4f}</code>
🎯 <b>Take Profit:</b> <code>{self.take_profit:.4f}</code>
📊 <b>Risk:Reward:</b> 1:{rr_ratio:.1f}
⭐ <b>Confluence Score:</b> {self.confluence_score}/5

📉 <b>Market Conditions:</b>
• RSI(14): {self.indicators.get('rsi', 'N/A'):.2f}
• ADX(14): {self.indicators.get('adx', 'N/A'):.2f} {'✅ Trending' if self.indicators.get('adx', 0) > 25 else '⚠️ Ranging'}
• MACD: {self.indicators.get('macd', 'N/A'):.6f}
• Signal: {self.indicators.get('macd_signal', 'N/A'):.6f}
• EMA9: {self.indicators.get('fast_ema', 'N/A'):.4f}
• EMA21: {self.indicators.get('slow_ema', 'N/A'):.4f}
• ATR(14): {self.indicators.get('atr', 'N/A'):.4f}

⏰ <b>Time:</b> {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC
🤖 <b>Bot:</b> Sniper R_25 on Render
⚠️ <b>Disclaimer:</b> For educational purposes only!
"""


class SniperR25Bot:
    """Sniper Bot for Deriv Volatility 25 Index"""
    
    DERIV_APP_ID = os.getenv("DERIV_APP_ID", "1234")
    DERIV_API_TOKEN = os.getenv("DERIV_API_TOKEN", "")
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
    
    SYMBOL = "R_25"
    TIMEFRAME_SECONDS = 300
    
    FAST_EMA = 9
    SLOW_EMA = 21
    RSI_PERIOD = 14
    ATR_PERIOD = 14
    ADX_PERIOD = 14
    MACD_FAST = 12
    MACD_SLOW = 26
    MACD_SIGNAL = 9
    
    ATR_MULT_SL = 2.0
    ATR_MULT_TP = 4.0
    MIN_CONFLUENCE = 3
    
    def __init__(self):
        self.ws = None
        self.candles = pd.DataFrame()
        self.last_signal_time = None
        self.cooldown_seconds = 300
        self.running = False
    
    def calculate_indicators(self):
        """Calculate indicators without TA-Lib"""
        if len(self.candles) < 50:
            return None
        
        closes = self.candles['close'].values
        highs = self.candles['high'].values
        lows = self.candles['low'].values
        
        # EMA
        def ema(data, period):
            multiplier = 2 / (period + 1)
            ema_values = [data[0]]
            for price in data[1:]:
                ema_values.append((price - ema_values[-1]) * multiplier + ema_values[-1])
            return np.array(ema_values)
        
        fast_ema = ema(closes, self.FAST_EMA)
        slow_ema = ema(closes, self.SLOW_EMA)
        
        # RSI
        def rsi(data, period):
            deltas = np.diff(data)
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)
            avg_gain = np.mean(gains[:period])
            avg_loss = np.mean(losses[:period])
            rsi_values = []
            for i in range(period, len(deltas)):
                avg_gain = (avg_gain * (period - 1) + gains[i]) / period
                avg_loss = (avg_loss * (period - 1) + losses[i]) / period
                rs = avg_gain / avg_loss if avg_loss != 0 else 0
                rsi_values.append(100 - (100 / (1 + rs)))
            return np.array([50] * (period + 1) + rsi_values)
        
        rsi_vals = rsi(closes, self.RSI_PERIOD)
        
        # ATR
        def atr(high, low, close, period):
            tr1 = high[1:] - low[1:]
            tr2 = np.abs(high[1:] - close[:-1])
            tr3 = np.abs(low[1:] - close[:-1])
            tr = np.maximum(np.maximum(tr1, tr2), tr3)
            atr_vals = [np.mean(tr[:period])]
            for i in range(period, len(tr)):
                atr_vals.append((atr_vals[-1] * (period - 1) + tr[i]) / period)
            return np.array([atr_vals[0]] * period + atr_vals)
        
        atr_vals = atr(highs, lows, closes, self.ATR_PERIOD)
        
        # MACD
        def macd(data, fast, slow, signal):
            ema_fast = ema(data, fast)
            ema_slow = ema(data, slow)
            macd_line = ema_fast - ema_slow
            signal_line = ema(macd_line, signal)
            return macd_line, signal_line
        
        macd_line, signal_line = macd(closes, self.MACD_FAST, self.MACD_SLOW, self.MACD_SIGNAL)
        
        # ADX approximation
        def adx(high, low, close, period):
            tr = np.maximum(high - low, np.maximum(np.abs(high - close), np.abs(low - close)))
            atr_vals = atr(high, low, close, period)
            return np.mean(atr_vals[-period:]) / np.mean(tr[-period:]) * 50 if len(tr) > period else 25
        
        adx_val = adx(highs, lows, closes, self.ADX_PERIOD)
        
        return {
            'fast_ema': fast_ema[-1],
            'slow_ema': slow_ema[-1],
            'fast_ema_prev': fast_ema[-2],
            'slow_ema_prev': slow_ema[-2],
            'rsi': rsi_vals[-1],
            'atr': atr_vals[-1],
            'macd': macd_line[-1],
            'macd_signal': signal_line[-1],
            'adx': adx_val,
            'current_price': closes[-1]
        }
    
    def generate_signal(self, ind):
        """Generate trading signal"""
        if not ind:
            return None
        
        fast, slow = ind['fast_ema'], ind['slow_ema']
        fast_prev, slow_prev = ind['fast_ema_prev'], ind['slow_ema_prev']
        rsi, macd, macd_sig = ind['rsi'], ind['macd'], ind['macd_signal']
        adx, atr, price = ind['adx'], ind['atr'], ind['current_price']
        
        bull_score = sum([rsi > 50, macd > macd_sig, fast > slow, adx > 25])
        bear_score = sum([rsi < 50, macd < macd_sig, fast < slow, adx > 25])
        
        buy_cross = fast_prev < slow_prev and fast > slow
        sell_cross = fast_prev > slow_prev and fast < slow
        
        if self.last_signal_time:
            if (datetime.now() - self.last_signal_time).seconds < self.cooldown_seconds:
                return None
        
        signal = None
        
        if buy_cross and bull_score >= self.MIN_CONFLUENCE:
            self.last_signal_time = datetime.now()
            signal = Signal(
                symbol=self.SYMBOL,
                direction="BUY",
                entry_price=price,
                stop_loss=price - (atr * self.ATR_MULT_SL),
                take_profit=price + (atr * self.ATR_MULT_TP),
                confluence_score=bull_score,
                timestamp=datetime.now(),
                indicators=ind
            )
            bot_state["total_signals"] += 1
            
        elif sell_cross and bear_score >= self.MIN_CONFLUENCE:
            self.last_signal_time = datetime.now()
            signal = Signal(
                symbol=self.SYMBOL,
                direction="SELL",
                entry_price=price,
                stop_loss=price + (atr * self.ATR_MULT_SL),
                take_profit=price - (atr * self.ATR_MULT_TP),
                confluence_score=bear_score,
                timestamp=datetime.now(),
                indicators=ind
            )
            bot_state["total_signals"] += 1
        
        return signal
    
    def send_telegram(self, signal):
        """Send Telegram alert"""
        if not self.TELEGRAM_BOT_TOKEN or not self.TELEGRAM_CHAT_ID:
            logger.warning("Telegram not configured")
            return
        
        url = f"https://api.telegram.org/bot{self.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': self.TELEGRAM_CHAT_ID,
            'text': signal.to_telegram_message(),
            'parse_mode': 'HTML'
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                logger.info(f"✅ Telegram sent: {signal.direction}")
            else:
                logger.error(f"Telegram error: {response.text}")
        except Exception as e:
            logger.error(f"Telegram failed: {e}")
    
    async def connect(self):
        """Connect to Deriv"""
        ws_url = f"wss://ws.derivws.com/websockets/v3?app_id={self.DERIV_APP_ID}"
        
        try:
            self.ws = await websockets.connect(ws_url)
            logger.info("Connected to Deriv")
            bot_state["connection_status"] = "connected"
            
            await self.ws.send(json.dumps({"authorize": self.DERIV_API_TOKEN}))
            auth_resp = await self.ws.recv()
            auth_data = json.loads(auth_resp)
            
            if 'error' in auth_data:
                logger.error(f"Auth failed: {auth_data['error']}")
                bot_state["connection_status"] = "auth_failed"
                return False
            
            logger.info("Authorized")
            return True
            
        except Exception as e:
            logger.error(f"Connection error: {e}")
            bot_state["connection_status"] = "error"
            return False
    
    async def subscribe_candles(self):
        """Subscribe to R_25 candles"""
        subscribe_msg = {
            "ticks_history": self.SYMBOL,
            "adjust_start_time": 1,
            "count": 100,
            "end": "latest",
            "start": 1,
            "style": "candles",
            "granularity": self.TIMEFRAME_SECONDS
        }
        await self.ws.send(json.dumps(subscribe_msg))
    
    def process_candles(self, data):
        """Process candle data"""
        if 'candles' not in data:
            return
        
        candles = data['candles']
        df = pd.DataFrame(candles)
        df['epoch'] = pd.to_datetime(df['epoch'], unit='s')
        self.candles = df
        bot_state["current_price"] = float(df['close'].iloc[-1])
    
    async def run(self):
        """Main loop"""
        self.running = True
        bot_state["status"] = "running"
        
        while self.running:
            try:
                if not self.ws or bot_state["connection_status"] != "connected":
                    success = await self.connect()
                    if not success:
                        await asyncio.sleep(10)
                        continue
                    await self.subscribe_candles()
                
                msg = await self.ws.recv()
                data = json.loads(msg)
                
                if 'candles' in data or 'ohlc' in data:
                    self.process_candles(data)
                    ind = self.calculate_indicators()
                    
                    if ind:
                        bot_state["indicators"] = {k: round(v, 4) if isinstance(v, float) else v for k, v in ind.items()}
                        signal = self.generate_signal(ind)
                        
                        if signal:
                            logger.info(f"🎯 SIGNAL: {signal.direction}")
                            self.send_telegram(signal)
                            bot_state["last_signal"] = signal.to_dict()
                            bot_state["signals_history"].append(signal.to_dict())
                            if len(bot_state["signals_history"]) > 50:
                                bot_state["signals_history"] = bot_state["signals_history"][-50:]
                
                elif 'error' in data:
                    logger.error(f"API Error: {data['error']}")
                    
            except websockets.exceptions.ConnectionClosed:
                logger.warning("Connection closed, reconnecting...")
                bot_state["connection_status"] = "reconnecting"
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Loop error: {e}")
                await asyncio.sleep(5)
        
        bot_state["status"] = "stopped"


# Flask Routes
@app.route('/')
def dashboard():
    """Main dashboard"""
    uptime = datetime.now() - bot_state["uptime"]
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Sniper R_25 Bot</title>
        <meta http-equiv="refresh" content="30">
        <style>
            body { font-family: Arial, sans-serif; background: #1a1a2e; color: #eee; padding: 20px; }
            .container { max-width: 800px; margin: 0 auto; }
            .header { text-align: center; margin-bottom: 30px; }
            .status-box { background: #16213e; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
            .signal-box { background: #0f3460; padding: 15px; border-radius: 8px; margin: 10px 0; }
            .buy { border-left: 5px solid #00d9ff; }
            .sell { border-left: 5px solid #ff006e; }
            .indicator { display: inline-block; margin: 5px 10px; padding: 5px 10px; background: #1a1a2e; border-radius: 5px; }
            .online { color: #00ff88; }
            .offline { color: #ff4444; }
            .value { color: #ffd700; font-weight: bold; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎯 Sniper R_25 Signal Bot</h1>
                <p>Volatility 25 Index - Deriv API</p>
            </div>
            
            <div class="status-box">
                <h3>📊 System Status</h3>
                <p>Status: <span class="{% if status == 'running' %}online{% else %}offline{% endif %}">{{ status.upper() }}</span></p>
                <p>Uptime: {{ uptime_str }}</p>
                <p>Connection: {{ connection_status }}</p>
                <p>Current Price: <span class="value">{{ current_price or 'Waiting...' }}</span></p>
                <p>Total Signals: {{ total_signals }}</p>
            </div>
            
            <div class="status-box">
                <h3>📈 Current Indicators</h3>
                {% for key, value in indicators.items() %}
                    <span class="indicator">{{ key }}: <span class="value">{{ value }}</span></span>
                {% endfor %}
            </div>
            
            <div class="status-box">
                <h3>🚨 Latest Signal</h3>
                {% if last_signal %}
                    <div class="signal-box {{ 'buy' if last_signal.direction == 'BUY' else 'sell' }}">
                        <h4>{{ last_signal.direction }} {{ last_signal.symbol }}</h4>
                        <p>Entry: {{ last_signal.entry_price }} | SL: {{ last_signal.stop_loss }} | TP: {{ last_signal.take_profit }}</p>
                        <p>Score: {{ last_signal.confluence_score }}/5 | Time: {{ last_signal.timestamp }}</p>
                    </div>
                {% else %}
                    <p>No signals yet...</p>
                {% endif %}
            </div>
        </div>
    </body>
    </html>
    """
    
    return render_template_string(
        html,
        status=bot_state["status"],
        connection_status=bot_state["connection_status"],
        current_price=bot_state["current_price"],
        total_signals=bot_state["total_signals"],
        indicators=bot_state["indicators"],
        last_signal=bot_state["last_signal"],
        uptime_str=f"{hours}h {minutes}m {seconds}s"
    )


@app.route('/health')
def health_check():
    """Health check"""
    return jsonify({
        "status": "healthy" if bot_state["status"] == "running" else "unhealthy",
        "bot_status": bot_state["status"],
        "connection": bot_state["connection_status"],
        "signals_count": bot_state["total_signals"]
    })


@app.route('/api/signals')
def api_signals():
    """API endpoint"""
    return jsonify({
        "current": bot_state["last_signal"],
        "history": bot_state["signals_history"][-20:],
        "indicators": bot_state["indicators"],
        "price": bot_state["current_price"]
    })


def run_bot():
    """Run bot in background"""
    bot = SniperR25Bot()
    asyncio.run(bot.run())


def main():
    """Start Flask and Bot"""
    bot_thread = Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    port = int(os.getenv("PORT", 10000))
    app.run(host='0.0.0.0', port=port)


if __name__ == "__main__":
    main()
