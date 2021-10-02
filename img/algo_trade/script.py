# -*- coding: utf-8 -*-
"""
Created on Sun Sep 12 23:20:17 2021

@author: jooer
"""
from AlgoAPI import AlgoAPIUtil, AlgoAPI_Backtest
from datetime import datetime, timedelta
from talib import RSI, MACD, EMA, ADX
import numpy as np

class AlgoEvent:
    def __init__(self):
        self.lasttradetime = datetime(2000,1,1)

        # RSI
        self.timer = datetime(1970,1,1)
        self.rsi_period = 14
        self.rsi_overbought = 75
        self.rsi_oversold = 25
        
        # ADX
        self.adx_period = 14
        
        # capital management
        self.max_daily_invest_percentage = 10  # %
        
        
    def start(self, mEvt):
        self.instrument_list = mEvt['subscribeList']
        self.position = {}
        self.last_tradeID = {}
        for instrument in self.instrument_list:
            self.position[instrument] = 0
            self.last_tradeID[instrument] = ""        
        self.evt = AlgoAPI_Backtest.AlgoEvtHandler(self, mEvt)
        self.evt.start()
        
    def open_order(self, instrument, buysell, vol):
        order = AlgoAPIUtil.OrderObject()
        order.instrument = instrument
        order.openclose = 'open'
        order.buysell = buysell    #1=buy, -1=sell
        order.ordertype = 0  #0=market, 1=limit
        order.volume = vol
        order.orderRef = 'RSI'
        self.evt.sendOrder(order)

    def close_order(self, instrument, buysell):
        pos, oo, pendOrder = self.evt.getSystemOrders()
        open_buy_RSI_orders = []
        open_sell_RSI_orders = []
        open_buy_RSP_orders = []
        open_sell_RSP_orders = []
        
        for order_ID in oo:
            if oo[order_ID]['orderRef'] == 'RSI' and oo[order_ID]['instrument'] == instrument and oo[order_ID]['buysell'] == 1:
                open_buy_RSI_orders.append(order_ID)    
            if oo[order_ID]['orderRef'] == 'RSI' and oo[order_ID]['instrument'] == instrument and oo[order_ID]['buysell'] == -1:
                open_sell_RSI_orders.append(order_ID) 
            if oo[order_ID]['orderRef'] == 'RSP' and oo[order_ID]['instrument'] == instrument and oo[order_ID]['buysell'] == 1:
                open_buy_RSP_orders.append(order_ID)    
            if oo[order_ID]['orderRef'] == 'RSP' and oo[order_ID]['instrument'] == instrument and oo[order_ID]['buysell'] == -1:
                open_sell_RSP_orders.append(order_ID)  
                
        self.evt.consoleLog('OPEN BUY RSI ORDERS: ',open_buy_RSI_orders)
        self.evt.consoleLog('OPEN SELL RSI ORDERS: ',open_sell_RSI_orders)
        self.evt.consoleLog('OPEN BUY RSP ORDERS: ',open_buy_RSP_orders)
        self.evt.consoleLog('OPEN SELL RSP ORDERS: ',open_sell_RSP_orders)
        
        if buysell == 1:
            for order_ID in open_buy_RSI_orders:
                order = AlgoAPIUtil.OrderObject()
                order.openclose = 'close'
                order.tradeID = order_ID
                self.evt.sendOrder(order)
        elif buysell == -1:
            for order_ID in open_sell_RSI_orders:
                order = AlgoAPIUtil.OrderObject()
                order.openclose = 'close'
                order.tradeID = order_ID
                self.evt.sendOrder(order)    
    
    
    def on_newsdatafeed(self, nd):
        pass
        
    def on_bulkdatafeed(self, isSync, bd, ab):
        # execute strategy every 24 hours
        if bd[self.instrument_list[0]]['timestamp'] >= self.timer+timedelta(hours=24):
            max_daily_invest_amt = ab['availableBalance']*self.max_daily_invest_percentage
            rsi_list = []
            adx_list = []
            ema_list = []
            macd_list = []
            
            ## Calculate RSI, ADX, EMA, MACD
            for instrument in self.instrument_list:                
                # get last 200 prices                
                res = self.evt.getHistoricalBar({"instrument":instrument}, 500, "D")
                close = np.array([res[t]['c'] for t in res])
                high = np.array([res[t]['h'] for t in res])
                low = np.array([res[t]['l'] for t in res])
            
                # calculate the current RSI value
                RSI_cur = RSI(close[-(self.rsi_period+1):], self.rsi_period)[-1]
                rsi_list.append(RSI_cur)
                
                # ADX value
                ADX_cur = ADX(high, low, close, timeperiod=self.adx_period)[-1]
                adx_list.append(ADX_cur)
                
                # EMA value
                EMA_cur = EMA(close, timeperiod=200)[-1]
                ema_list.append(EMA_cur)
                
                # MACD values
                macd, macdsignal, macdhist = MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
                macd_list.append((macd[-1], macdsignal[-1]))

            # print out RSI values to console
            self.evt.consoleLog("RSI_cur = ", rsi_list)
            self.evt.consoleLog("ADX_cur = ", adx_list)
            self.evt.consoleLog("MACD_cur = ", macd_list)
            self.evt.consoleLog("EMA_cur = ", ema_list)
            
            ### Calculate Investment Amounts ###
            
            # investment for rsi strategy, scaled based on rsi (overbought/underbought value)
            rsi_daily_invest_amt = 0
            rsi_weight_list = [abs(rsi-50) if (rsi>self.rsi_overbought or rsi<self.rsi_oversold) else 0 for rsi in rsi_list]
            rsi_tot_weight = sum(rsi_weight_list)
            
            if rsi_tot_weight != 0:
                # scale investment amount based on top 3 rsi
                ave_top3_weights = sum(sorted(rsi_weight_list)[-3:])/3
                rsi_daily_invest_amt = max_daily_invest_amt * ave_top3_weights/50
    
                # scale for each instrument
                rsi_weight_list = [w/rsi_tot_weight for w in rsi_weight_list]
                
            
            # investment for macd strategy, scaled based on adx (strength of trend)
            macd_daily_invest_amt = 0
            macd_weight_list = []
            for i in range(len(self.instrument_list)):
                ADX_cur = adx_list[i]
                ema200 = ema_list[i]
                macd, macdsignal = macd_list[i]
                
                if ((macd > macdsignal and macd < 0) and bd[instrument]['lowPrice'] > ema200) or ((macd < macdsignal and macd > 0) and bd[instrument]['highPrice'] < ema200):
                    macd_weight_list.append(ADX_cur)
                else:
                    macd_weight_list.append(0)
                    
            macd_tot_weight = sum(macd_weight_list)            
            if macd_tot_weight != 0:
                # scale investment amount based on top 3 adx
                ave_top3_weights = sum(sorted(macd_weight_list)[-3:])/3
                macd_daily_invest_amt = max_daily_invest_amt * ave_top3_weights/50
                
                # scale for each instrument
                macd_weight_list = [w/macd_tot_weight for w in macd_weight_list]
            
    
    
            ### Execute Strategies ###
            for i in range(len(self.instrument_list)):
                RSI_cur = rsi_list[i]
                ADX_cur = adx_list[i]
                ema200 = ema_list[i]
                macd, macdsignal = macd_list[i]
                
                rsi_weight = rsi_weight_list[i]
                macd_weight = macd_weight_list[i]
                
                instrument = self.instrument_list[i]
                position = self.position[instrument]
                contractSize = self.evt.getContractSpec(instrument)["contractSize"]
                
                ### RSI ORDERS
                # open an order if we have no outstanding position
                if position<=10 and position>=-10 and rsi_weight!=0:                
                
                    # open a sell order if it is overbought
                    if RSI_cur>self.rsi_overbought:
                        vol = max(0.1, 10*rsi_daily_invest_amt/(bd[instrument]['bidPrice']*contractSize)*rsi_weight)
                        self.open_order(instrument, -1, vol=vol)
                    # open a buy order if it is oversold
                    elif RSI_cur<self.rsi_oversold:
                        vol = max(0.1, 10*rsi_daily_invest_amt/(bd[instrument]['askPrice']*contractSize)*rsi_weight)
                        self.open_order(instrument, 1, vol=vol)
                        
                # check condition to close an order

                # close a position if we have previously open a buy order and RSI now reverse above 50 
                if RSI_cur>self.rsi_overbought:
                    self.close_order(instrument,1)
            
                # close a position if we have previously open a sell order and RSI now reverse below 50 
                elif RSI_cur<self.rsi_oversold:
                    self.close_order(instrument,-1)
            
                

                ### RSP STYLE ORDERS TO HEDGE AGAINST PURE RSI LOGIC
                # open a buy order if momentum on uptrend
                if RSI_cur<self.rsi_overbought-5 and RSI_cur>55:
                    vol = max(0.1,0.1*abs(RSI_cur - (55+self.rsi_overbought-5)/2))
                    self.evt.consoleLog('Uptrend Order Made: ', vol, bd[instrument]['askPrice'])
                    order = AlgoAPIUtil.OrderObject(
                        instrument=instrument,
                        volume=vol,
                        openclose='open',
                        buysell=1,          #1=long_order, -1=short_order
                        ordertype=0,         #0=market_order, 1=limit_ordercon
                        takeProfitLevel = 1.01*bd[instrument]['askPrice'],
                        stopLossLevel = 0.995*bd[instrument]['askPrice'],
                        orderRef = 'RSP'
                    )
                    self.evt.sendOrder(order)
               # open a sell order if momentum on downtrend
                elif RSI_cur>self.rsi_oversold+5 and RSI_cur<45:
                    vol = max(0.1,0.1*abs(RSI_cur - (self.rsi_oversold+5+45)/2))
                    self.evt.consoleLog('Downtrend Order Made: ',vol, bd[instrument]['bidPrice'])
                    order = AlgoAPIUtil.OrderObject(
                            instrument=instrument,
                            volume=vol,
                            openclose='open',
                            buysell=-1,          #1=long_order, -1=short_order
                            ordertype=0,         #0=market_order, 1=limit_order
                            takeProfitLevel = 0.99*bd[instrument]['bidPrice'],
                            stopLossLevel = 1.005*bd[instrument]['bidPrice'],
                            orderRef = 'RSP'
                        )
                    self.evt.sendOrder(order)
                    
                ### MACD ORDERS
                if (macd > macdsignal and macd < 0) and bd[instrument]['lowPrice'] > ema200:
                    # open buy order
                    stoploss = ema200
                    askPrice = bd[instrument]['askPrice']
                    profitPrice = askPrice + 1.5*(askPrice-stoploss)
                    vol = max(0.1, 5*macd_daily_invest_amt/(bd[instrument]['askPrice']*contractSize)*macd_weight)
                    self.evt.consoleLog('MACD Buy Order Made: ',vol, askPrice)
                    order = AlgoAPIUtil.OrderObject(
                            instrument=instrument,
                            volume=vol,
                            openclose='open',
                            buysell=1,          #1=long_order, -1=short_order
                            ordertype=0,         #0=market_order, 1=limit_order
                            takeProfitLevel =  profitPrice,
                            stopLossLevel = stoploss,
                            orderRef = 'MACD'
                        )
                    self.evt.sendOrder(order)
                
                elif (macd < macdsignal and macd > 0) and bd[instrument]['highPrice'] < ema200:
                    # open sell order
                    stoploss = ema200
                    bidPrice = bd[instrument]['bidPrice']
                    profitPrice = bidPrice - 1.5*(stoploss-bidPrice)
                    vol = max(0.1, 5*macd_daily_invest_amt/(bd[instrument]['bidPrice']*contractSize)*macd_weight)
                    self.evt.consoleLog('MACD Sell Order Made: ',vol, bidPrice)
                    order = AlgoAPIUtil.OrderObject(
                            instrument=instrument,
                            volume=vol,
                            openclose='open',
                            buysell=-1,          #1=long_order, -1=short_order
                            ordertype=0,         #0=market_order, 1=limit_order
                            takeProfitLevel = profitPrice,
                            stopLossLevel = stoploss,
                            orderRef = 'MACD'
                        )
                    self.evt.sendOrder(order)

            
            # update timer
            self.timer = bd[self.instrument_list[0]]['timestamp']

    def on_marketdatafeed(self, md, ab):
        pass

    def on_orderfeed(self, of):
        # when system confirm an order, update position
        if of.status=="success":
            instrument = of.instrument
            self.position[instrument] += of.fill_volume*of.buysell
            if self.position[instrument] == 0:
                self.last_tradeID[instrument] = ""
            else:
                self.last_tradeID[instrument] = of.tradeID

    def on_dailyPLfeed(self, pl):
        pass

    def on_openPositionfeed(self, op, oo, uo):
        pass
























