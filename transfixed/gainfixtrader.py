import quickfix as fix
import quickfix44 as fix44
import logging
import threading
from dateutil import parser
import datetime as dt
import calendar
import time


class FutureOrder(object):
    def __init__(self, symbol, maturity, qty):
        self.CFICode = fix.CFICode('FXXXXS')
        self.Symbol = fix.Symbol(symbol)
        self.Maturity = fix.MaturityMonthYear(maturity)
        self.Quantity = fix.OrderQty(qty)
        self.TransactionTime = fix.TransactTime()


class FutureLimitOrder(FutureOrder):
    def __init__(self, symbol, maturity, qty, price):
        self.OrdType = fix.OrdType(fix.OrdType_LIMIT)
        self.Price = fix.Price(price)
        super(FutureLimitOrder, self).__init__(symbol, maturity, qty)


class FutureMarketOrder(FutureOrder):
    def __init__(self, symbol, maturity, qty):
        self.OrdType = fix.OrdType(fix.OrdType_MARKET)
        super(FutureMarketOrder, self).__init__(symbol, maturity, qty)


class BuyFutureLimitOrder(FutureLimitOrder):
    def __init__(self, symbol, maturity, qty, price):
        self.Side = fix.Side(fix.Side_BUY)
        super(BuyFutureLimitOrder, self).__init__(symbol, maturity, qty, price)


class SellFutureLimitOrder(FutureLimitOrder):
    def __init__(self, symbol, maturity, qty, price):
        self.Side = fix.Side(fix.Side_SELL)
        super(SellFutureLimitOrder, self).__init__(symbol, maturity, qty, price)


class BuyFutureMarketOrder(FutureMarketOrder):
    def __init__(self, symbol, maturity, qty):
        self.Side = fix.Side(fix.Side_BUY)
        super(BuyFutureMarketOrder, self).__init__(symbol, maturity, qty)


class SellFutureMarketOrder(FutureMarketOrder):
    def __init__(self, symbol, maturity, qty):
        self.Side = fix.Side(fix.Side_SELL)
        super(SellFutureMarketOrder, self).__init__(symbol, maturity, qty)


class FixEvent(object):
    pass


class FixClient(object):
    def __init__(self, init, logger):
        self.SocketInitiator = init
        self.Logger = logger

    @classmethod
    def Create(cls, logger, config):
        logger.setLevel(logging.INFO)
        logging.basicConfig(format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s')
        settings = fix.SessionSettings(config)
        application = GainApplication(settings, logger)
        storeFactory = fix.FileStoreFactory(settings)
        logFactory = fix.FileLogFactory(settings)
        init = fix.SocketInitiator(application, storeFactory, settings, logFactory)
        return FixClient(init, logger)

    def heartbeat(self):
        message = fix.Message()
        message.getHeader().setField(fix.MsgType(fix.MsgType_Heartbeat))
        self.SocketInitiator.application.send(message)

    def logout(self):
        message = fix44.Logout()
        self.SocketInitiator.application.send(message)

    def addOrderListener(self, callback):
        self.SocketInitiator.application.addMessageHandler(callback)

    def send(self, order):
        orderId = self.SocketInitiator.application.genOrderID()
        account = self.SocketInitiator.application.Settings.get().getString('Account')

        trade = fix44.NewOrderSingle()
        trade.setField(fix.Account(account))
        trade.setField(fix.ClOrdID(orderId))

        trade.setField(order.CFICode)
        trade.setField(order.TransactionTime)
        trade.setField(order.Quantity)
        trade.setField(order.OrdType)
        trade.setField(order.Side)
        trade.setField(order.Symbol)
        trade.setField(order.Maturity)

        if isinstance(order, FutureLimitOrder):
            trade.setField(order.Price)

        self.SocketInitiator.application.send(trade)

    def start(self):
        self.Logger.info("Open FIX Connection")
        self.SocketInitiator.start()

    def stop(self):
        self.Logger.info("Close FIX Connection")
        self.SocketInitiator.application.removeAllMsgHandler()
        self.SocketInitiator.stop()


class Observable(object):
    def __init__(self):
        self.__callbacks = []

    def addMessageHandler(self, callback):
        if callback not in self.__callbacks:
            self.__callbacks.append(callback)

    def removeMsgHandler(self, callback):
        if callback in self.__callbacks:
            self.__callbacks.remove(callback)

    def removeAllMsgHandler(self):
        if self.__callbacks:
            del self.__callbacks[:]

    def notifyMsgHandlers(self, **kwargs):
        e = FixEvent()
        e.source = self
        for k, v in kwargs.items():
            setattr(e, k, v)
        for fn in self.__callbacks:
            fn(e)


class MessageStore(Observable):
    def __init__(self, logger, settings):
        super(MessageStore, self).__init__()
        self.Logger = logger
        self.Settings = settings
        self.__out = {}
        self.__in = {}
        self.__lock = threading.RLock()
        self.__latency = int(self.Settings.get().getString('MaxLatency'))

    def __timeCheck(self, request, response):
        requestTime = parser.parse(request)
        responseTime = parser.parse(response)
        delta = responseTime - requestTime if responseTime > requestTime else requestTime - responseTime
        lag_in_seconds = (delta.seconds*1000 + delta.microseconds/1000.0)/1000.0
        if lag_in_seconds > self.__latency:
            self.notifyMsgHandlers(MaxLatency=self.__latency, CurrentTimeLag=lag_in_seconds)
            self.Logger.error("Max Latency exceeded for messages: %s %s" % (request, response))

    @staticmethod
    def __uncorkValue(message):
        msgType = fix.MsgType()
        message.getHeader().getField(msgType)
        val = msgType.getValue()
        if val == fix.MsgType_Logon or val == fix.MsgType_Logout or val == fix.MsgType_Heartbeat:
            sndTime = fix.SendingTime()
            message.getHeader().getField(sndTime)
            return sndTime.getString()
        if val == fix.MsgType_NewOrderSingle or val == fix.MsgType_ExecutionReport:
            transTime = fix.TransactTime()
            message.getField(transTime)
            return transTime.getString()
        return None

    @staticmethod
    def __uncorkKey(message):
        """
        Return a value that can be used as a key based on a message type
        :param message: FIX message
        :return: key
        """
        msgType = fix.MsgType()
        message.getHeader().getField(msgType)
        if msgType.getValue() == fix.MsgType_Logon:
            sequence = fix.MsgSeqNum()
            message.getHeader().getField(sequence)
            return '%s_%s' % (fix.MsgType_Logon, sequence.getValue())
        if msgType.getValue() == fix.MsgType_Logout:
            sequence = fix.MsgSeqNum()
            message.getHeader().getField(sequence)
            return '%s_%s' % (fix.MsgType_Logout, sequence.getValue())
        if msgType.getValue() == fix.MsgType_Heartbeat:
            sequence = fix.MsgSeqNum()
            message.getHeader().getField(sequence)
            return '%s_%s' % (fix.MsgType_Heartbeat, sequence.getValue())
        if msgType.getValue() == fix.MsgType_NewOrderSingle or msgType.getValue() == fix.MsgType_ExecutionReport:
            cId = fix.ClOrdID()
            message.getField(cId)
            return cId.getValue()
        return None

    def addTimeLagListener(self, callback):
        self.addMessageHandler(callback)

    def addRequest(self, message):
        key = MessageStore.__uncorkKey(message)
        value = MessageStore.__uncorkValue(message)
        if key is None or value is None:
            self.Logger.error('Unknown request message type %s' % message)
            return
        with self.__lock:
            self.__out[key] = value
            if key in self.__in:
                self.__timeCheck(self.__out[key], self.__in[key])

    def addResponse(self, message):
        key = MessageStore.__uncorkKey(message)
        value = MessageStore.__uncorkValue(message)
        if key is None or value is None:
            self.Logger.error('Unknown response message type: %s' % message)
            return
        with self.__lock:
            self.__in[key] = value
            if key in self.__out:
                self.__timeCheck(self.__out[key], self.__in[key])


class GainApplication(fix.Application, Observable):
    def __init__(self, settings, logger):
        super(GainApplication, self).__init__()
        self.__messageStore = MessageStore(logger, settings)
        self.Settings = settings
        self.sessionID = ''
        self.orderID = int(calendar.timegm(time.gmtime()))
        self.Logger = logger
        self._lock = threading.RLock()
        self.__connected = False
        self.__latency = int(self.Settings.get().getString('MaxLatency'))

    def onCreate(self, sessionID):
        self.Logger.info("Session created. Session: %s" % sessionID)
        return

    def onLogon(self, sessionID):
        self.sessionID = sessionID
        self.__connected = True
        self.Logger.info("onLogon received from server. Session: %s" % sessionID)
        return

    def onLogout(self, sessionID):
        self.__connected = False
        self.Logger.info("onLogout received from server. Session: %s" % sessionID)
        return

    def toAdmin(self, message, sessionID):
        try:
            msgType = fix.MsgType()
            message.getHeader().getField(msgType)
            if msgType.getValue() == fix.MsgType_Logon:
                uuid = self.Settings.get().getString('Username')
                password = self.Settings.get().getString('Password')
                message.getHeader().setField(fix.Password(password))
                message.getHeader().setField(fix.StringField(12003, uuid))
            self.Logger.info("Sending Admin message to server. Session: %s. Message: %s" % (sessionID, message))
            self.__messageStore.addRequest(message)
        except fix.RuntimeError, e:
            self.Logger.error('Error in toAdmin', e)
        return

    def toApp(self, message, sessionID):
        try:
            self.Logger.info("Sending Application message to server. Session: %s. Message: %s" % (sessionID, message))
            self.__messageStore.addRequest(message)
        except fix.RuntimeError, e:
            self.Logger.error('Error in toApp', e)
        return

    def fromAdmin(self, message, sessionID):
        try:
            self.Logger.info("Received Admin message from server. Session: %s. Message: %s" % (sessionID, message))
            self.__messageStore.addResponse(message)
        except fix.RuntimeError, e:
            self.Logger.error('Error in fromAdmin', e)
        return

    def fromApp(self, message, sessionID):
        try:
            self.Logger.info("Received Application message from server. Session: %s. Message: %s" % (sessionID, message))
            self.__messageStore.addResponse(message)
        except fix.RuntimeError, e:
            self.Logger.error('Error in fromApp', e)
        return

    def send(self, message):
        if self.__connected:
            self.Logger.info("FixClient is sending: %s" % message.getHeader().getField(fix.MsgType()))
            fix.Session.sendToTarget(message, self.sessionID)
        else:
            self.Logger.error('Session Not Found. Not connected to FIX engine')
        return

    def genOrderID(self):
        with self._lock:
            self.orderID += 1
            return str(self.orderID)
