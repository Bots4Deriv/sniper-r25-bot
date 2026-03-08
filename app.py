import os
import asyncio
import json
import logging
import websockets
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from flask import Flask
from threading import Thread

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

bot_state = {
    "status":"starting",
    "connection":"disconnected",
    "price":None,
    "signals":0
}

class R25SignalBot:

    SYMBOL="R_25"
    GRANULARITY=300

    FAST_EMA=9
    SLOW_EMA=21
    RSI_PERIOD=14
    ATR_PERIOD=14

    ATR_SL_MULT=2
    ATR_TP_MULT=4

    DERIV_APP_ID=os.getenv("DERIV_APP_ID")
    DERIV_TOKEN=os.getenv("DERIV_API_TOKEN")

    TELEGRAM_TOKEN=os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT=os.getenv("TELEGRAM_CHAT_ID")

    def __init__(self):
        self.ws=None
        self.candles=pd.DataFrame()

    def ema(self,data,period):
        return pd.Series(data).ewm(span=period).mean().values

    def rsi(self,data,period):
        delta=np.diff(data)
        gain=np.maximum(delta,0)
        loss=np.abs(np.minimum(delta,0))

        avg_gain=pd.Series(gain).rolling(period).mean()
        avg_loss=pd.Series(loss).rolling(period).mean()

        rs=avg_gain/avg_loss
        rsi=100-(100/(1+rs))

        return np.append(np.zeros(period),rsi[period:])

    def atr(self,high,low,close,period):

        high=np.array(high)
        low=np.array(low)
        close=np.array(close)

        tr1=high[1:]-low[1:]
        tr2=np.abs(high[1:]-close[:-1])
        tr3=np.abs(low[1:]-close[:-1])

        tr=np.maximum(tr1,np.maximum(tr2,tr3))

        atr=pd.Series(tr).rolling(period).mean()

        return np.append(np.zeros(period),atr[period:])

    def macd(self,data):

        ema12=pd.Series(data).ewm(span=12).mean()
        ema26=pd.Series(data).ewm(span=26).mean()

        macd=ema12-ema26
        signal=macd.ewm(span=9).mean()

        return macd.values,signal.values

    def calculate_indicators(self):

        if len(self.candles)<50:
            return None

        close=self.candles["close"].astype(float).values
        high=self.candles["high"].astype(float).values
        low=self.candles["low"].astype(float).values

        ema_fast=self.ema(close,self.FAST_EMA)
        ema_slow=self.ema(close,self.SLOW_EMA)

        rsi=self.rsi(close,self.RSI_PERIOD)

        macd,signal=self.macd(close)

        atr=self.atr(high,low,close,self.ATR_PERIOD)

        return {
            "fast":ema_fast[-1],
            "slow":ema_slow[-1],
            "fast_prev":ema_fast[-2],
            "slow_prev":ema_slow[-2],
            "rsi":rsi[-1],
            "macd":macd[-1],
            "signal":signal[-1],
            "atr":atr[-1],
            "price":close[-1]
        }

    def send_telegram(self,msg):

        if not self.TELEGRAM_TOKEN:
            return

        url=f"https://api.telegram.org/bot{self.TELEGRAM_TOKEN}/sendMessage"

        requests.post(url,json={
            "chat_id":self.TELEGRAM_CHAT,
            "text":msg,
            "parse_mode":"HTML"
        })

    def generate_signal(self,ind):

        price=ind["price"]
        atr=ind["atr"]

        buy_cross=ind["fast_prev"]<ind["slow_prev"] and ind["fast"]>ind["slow"]
        sell_cross=ind["fast_prev"]>ind["slow_prev"] and ind["fast"]<ind["slow"]

        if buy_cross and ind["rsi"]>50 and ind["macd"]>ind["signal"]:

            sl=price-(atr*self.ATR_SL_MULT)
            tp=price+(atr*self.ATR_TP_MULT)

            bot_state["signals"]+=1

            msg=f"""
🟢 <b>R25 BUY SIGNAL</b>

💰 Entry: {price:.2f}
🛑 Stop Loss: {sl:.2f}
🎯 Take Profit: {tp:.2f}

📊 Indicators
RSI: {ind['rsi']:.2f}
MACD: {ind['macd']:.4f}
ATR: {atr:.2f}

⏰ {datetime.utcnow()}
"""

            self.send_telegram(msg)

        elif sell_cross and ind["rsi"]<50 and ind["macd"]<ind["signal"]:

            sl=price+(atr*self.ATR_SL_MULT)
            tp=price-(atr*self.ATR_TP_MULT)

            bot_state["signals"]+=1

            msg=f"""
🔴 <b>R25 SELL SIGNAL</b>

💰 Entry: {price:.2f}
🛑 Stop Loss: {sl:.2f}
🎯 Take Profit: {tp:.2f}

📊 Indicators
RSI: {ind['rsi']:.2f}
MACD: {ind['macd']:.4f}
ATR: {atr:.2f}

⏰ {datetime.utcnow()}
"""

            self.send_telegram(msg)

    async def connect(self):

        url=f"wss://ws.derivws.com/websockets/v3?app_id={self.DERIV_APP_ID}"

        self.ws=await websockets.connect(url)

        await self.ws.send(json.dumps({
            "authorize":self.DERIV_TOKEN
        }))

        bot_state["connection"]="connected"

    async def subscribe(self):

        await self.ws.send(json.dumps({
            "ticks_history":self.SYMBOL,
            "count":100,
            "end":"latest",
            "style":"candles",
            "granularity":self.GRANULARITY,
            "subscribe":1
        }))

    async def run(self):

        await self.connect()
        await self.subscribe()

        bot_state["status"]="running"

        while True:

            msg=await self.ws.recv()
            data=json.loads(msg)

            if "candles" in data:

                df=pd.DataFrame(data["candles"])
                self.candles=df

                bot_state["price"]=float(df["close"].iloc[-1])

                ind=self.calculate_indicators()

                if ind:
                    self.generate_signal(ind)

bot=R25SignalBot()

def start_bot():
    asyncio.run(bot.run())

@app.route("/")
def status():
    return bot_state

def main():

    Thread(target=start_bot).start()

    port=int(os.getenv("PORT",10000))
    app.run(host="0.0.0.0",port=port)

if __name__=="__main__":
    main()
