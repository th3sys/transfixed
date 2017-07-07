import quickfix as fix
import quickfix44 as fix44
import logging
import threading
from datetime import datetime
import calendar
import time


class AccountInquiry:
    CollateralInquiry = 'CollateralInquiry'
    RequestForPositions = 'RequestForPositions'


class Notify:
    Latency = 'Latency'
    Order = 'Order'
    Account = 'Account'


class OrderStatus:
    New = 'New'
    Filled = 'Filled'
    Cancelled = 'Cancelled'
    Rejected = 'Rejected'
    CancelRejected = 'CancelRejected'


class OrderSide:
    Buy = 'Buy'
    Sell = 'Sell'


class OrderType:
    Limit = 'Limit'
    Market = 'Market'


class Trade(object):
    def __init__(self, orderId, symbol, maturity, qty, ordType, ordSide, price=None):
        self.OrderId = orderId
        self.Symbol = symbol
        self.Maturity = maturity
        self.Quantity = qty
        self.OrderType = ordType
        self.OrderSide = ordSide
        self.Price = price
        self.CFICode = fix.CFICode('FXXXXS')


class BuyOrder(object):
    def __init__(self):
        super(BuyOrder, self).__init__()
        self.Side = fix.Side(fix.Side_BUY)


class SellOrder(object):
    def __init__(self):
        super(SellOrder, self).__init__()
        self.Side = fix.Side(fix.Side_SELL)


class FutureOrder(object):
    def __init__(self, symbol, maturity, qty):
        super(FutureOrder, self).__init__()
        self.CFICode = fix.CFICode('FXXXXS')
        self.Symbol = fix.Symbol(symbol)
        self.Maturity = fix.MaturityMonthYear(maturity)
        self.Quantity = fix.OrderQty(qty)
        self.TransactionTime = fix.TransactTime()


class FutureLimitOrder(FutureOrder):
    def __init__(self, symbol, maturity, qty, price):
        super(FutureLimitOrder, self).__init__(symbol, maturity, qty)
        self.OrdType = fix.OrdType(fix.OrdType_LIMIT)
        self.Price = fix.Price(price)


class FutureMarketOrder(FutureOrder):
    def __init__(self, symbol, maturity, qty):
        super(FutureMarketOrder, self).__init__(symbol, maturity, qty)
        self.OrdType = fix.OrdType(fix.OrdType_MARKET)


class BuyFutureLimitOrder(FutureLimitOrder, BuyOrder):
    def __init__(self, symbol, maturity, qty, price):
        FutureLimitOrder.__init__(self, symbol, maturity, qty, price)
        BuyOrder.__init__(self)


class SellFutureLimitOrder(FutureLimitOrder, SellOrder):
    def __init__(self, symbol, maturity, qty, price):
        FutureLimitOrder.__init__(self, symbol, maturity, qty, price)
        SellOrder.__init__(self)


class BuyFutureMarketOrder(FutureMarketOrder, BuyOrder):
    def __init__(self, symbol, maturity, qty):
        FutureMarketOrder.__init__(self, symbol, maturity, qty)
        BuyOrder.__init__(self)


class SellFutureMarketOrder(FutureMarketOrder, SellOrder):
    def __init__(self, symbol, maturity, qty):
        FutureMarketOrder.__init__(self, symbol, maturity, qty)
        SellOrder.__init__(self)


class FixEvent(object):
    pass


class FixClient(object):
    def __init__(self, init, logger):
        self.SocketInitiator = init
        self.Logger = logger

    @classmethod
    def Create(cls, logger, config, storeMessages):
        logger.setLevel(logging.INFO)
        logging.basicConfig(format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s')
        settings = fix.SessionSettings(config)
        application = GainApplication(settings, logger)
        storeFactory = fix.FileStoreFactory(settings) if storeMessages else fix.MemoryStoreFactory()
        logFactory = fix.FileLogFactory(settings) if storeMessages else None
        init = fix.SocketInitiator(application, storeFactory, settings, logFactory)
        client = FixClient(init, logger)
        application.FixClientRef = client
        return client

    def heartbeat(self):
        message = fix.Message()
        message.getHeader().setField(fix.MsgType(fix.MsgType_Heartbeat))
        self.SocketInitiator.application.send(message)

    def logout(self):
        message = fix44.Logout()
        self.SocketInitiator.application.send(message)

    def addAccountInquiryListener(self, callback):
        self.SocketInitiator.application.Notifier.addMessageHandler(Notify.Account, callback)

    def addOrderListener(self, callback):
        self.SocketInitiator.application.Notifier.addMessageHandler(Notify.Order, callback)

    def cancel(self, trade):
        orderId = self.SocketInitiator.application.genOrderID()
        account = self.SocketInitiator.application.Settings.get().getString('Account')

        cancel = fix44.OrderCancelRequest()
        cancel.setField(fix.Account(account))
        cancel.setField(fix.ClOrdID(orderId))
        cancel.setField(fix.OrigClOrdID(trade.OrderId))

        cancel.setField(trade.CFICode)
        cancel.setField(fix.TransactTime())
        cancel.setField(fix.OrderQty(trade.Quantity))
        cancel.setField(fix.Side(fix.Side_BUY if trade.OrderSide == OrderSide.Buy else fix.Side_SELL))
        cancel.setField(fix.Symbol(trade.Symbol))
        cancel.setField(fix.MaturityMonthYear(trade.Maturity))

        self.SocketInitiator.application.send(cancel)

    def requestForPositions(self):
        clrDate = datetime.now().strftime("%Y%m%d")
        inqId = self.SocketInitiator.application.genInquiryID()
        account = self.SocketInitiator.application.Settings.get().getString('Account')
        message = fix44.RequestForPositions()
        message.setField(fix.Account(account))
        message.setField(fix.TransactTime())
        message.setField(fix.AccountType(fix.AccountType_ACCOUNT_IS_CARRIED_ON_CUSTOMER_SIDE_OF_BOOKS))
        message.setField(fix.ClearingBusinessDate(clrDate))
        message.setField(fix.PosReqType(fix.PosReqType_POSITIONS))
        message.setField(fix.PosReqID(inqId))

        self.SocketInitiator.application.send(message)

        return inqId

    def collateralInquiry(self):
        inqId = self.SocketInitiator.application.genInquiryID()
        account = self.SocketInitiator.application.Settings.get().getString('Account')
        message = fix44.CollateralInquiry()
        message.setField(fix.Account(account))
        message.setField(fix.CollInquiryID(inqId))

        self.SocketInitiator.application.send(message)

        return inqId

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

        ordType = OrderType.Limit if isinstance(order, FutureLimitOrder) else OrderType.Market
        ordSide = OrderSide.Buy if isinstance(order, BuyOrder) else OrderSide.Sell
        price = order.Price.getValue() if isinstance(order, FutureLimitOrder) else None
        return Trade(orderId, order.Symbol.getString(), order.Maturity.getString(), order.Quantity.getValue(),
                     ordType, ordSide, price)

    def start(self):
        self.Logger.info("Open FIX Connection")
        self.SocketInitiator.start()
        while not self.SocketInitiator.application.connected:
            self.Logger.info('Waiting to logon ...')
            self.SocketInitiator.application.connection_trigger.wait(2)

    def stop(self):
        self.Logger.info("Close FIX Connection")
        self.SocketInitiator.application.Notifier.removeAllMsgHandler()
        self.SocketInitiator.stop()


class Observable(object):
    def __init__(self):
        super(Observable, self).__init__()
        self.__callbacks = {}

    def addMessageHandler(self, name, callback):
        if name in self.__callbacks:
            handlers = self.__callbacks[name]
            if callback not in handlers:
                handlers.append(callback)
        else:
            self.__callbacks[name] = [callback]

    def removeMsgHandler(self, name, callback):
        if name in self.__callbacks and callback in self.__callbacks[name]:
            self.__callbacks[name].remove(callback)

    def removeAllMsgHandler(self):
        for key in self.__callbacks:
            if self.__callbacks[key]:
                del self.__callbacks[key][:]

    def notifyMsgHandlers(self, name, **kwargs):
        e = FixEvent()
        e.source = self
        for k, v in list(kwargs.items()):
            setattr(e, k, v)
        if name in self.__callbacks:
            for fn in self.__callbacks[name]:
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

    @staticmethod
    def parse(date):
        return datetime.strptime(date, '%Y%m%d-%H:%M:%S.%f' if '.' in date else '%Y%m%d-%H:%M:%S')

    def __timeCheck(self, request, response):
        requestTime = MessageStore.parse(request)
        responseTime = MessageStore.parse(response)
        delta = responseTime - requestTime if responseTime > requestTime else requestTime - responseTime
        lag_in_seconds = (delta.seconds*1000 + delta.microseconds/1000.0)/1000.0
        if lag_in_seconds > self.__latency:
            self.notifyMsgHandlers(Notify.Latency, MaxLatency=self.__latency, CurrentTimeLag=lag_in_seconds)
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
        if val == fix.MsgType_NewOrderSingle or val == fix.MsgType_ExecutionReport \
                or val == fix.MsgType_OrderCancelRequest or val == fix.MsgType_OrderCancelReject:
            transTime = fix.TransactTime()
            message.getField(transTime)
            return transTime.getString()
        if val == fix.MsgType_CollateralInquiry or val == fix.MsgType_CollateralReport \
                or val == fix.MsgType_RequestForPositions or val == fix.MsgType_PositionReport \
                or val == fix.MsgType_RequestForPositionsAck:
            return datetime.now().strftime("%Y%m%d-%H:%M:%S")
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
        if msgType.getValue() == fix.MsgType_NewOrderSingle or msgType.getValue() == fix.MsgType_ExecutionReport \
                or msgType.getValue() == fix.MsgType_OrderCancelRequest \
                or msgType.getValue() == fix.MsgType_OrderCancelReject:
            cId = fix.ClOrdID()
            message.getField(cId)
            return cId.getValue()
        if msgType.getValue() == fix.MsgType_CollateralInquiry or msgType.getValue() == fix.MsgType_CollateralReport:
            colId = fix.CollInquiryID()
            message.getField(colId)
            return colId.getValue()
        if msgType.getValue() == fix.MsgType_RequestForPositions or msgType.getValue() == fix.MsgType_PositionReport \
                or msgType.getValue() == fix.MsgType_RequestForPositionsAck:
            posId = fix.PosReqID()
            message.getField(posId)
            return posId.getValue()
        return None

    def addTimeLagListener(self, callback):
        self.addMessageHandler(Notify.Latency, callback)

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


class GainApplication(fix.Application):
    def __init__(self, settings, logger):
        super(GainApplication, self).__init__()
        self.__messageStore = MessageStore(logger, settings)
        self.Notifier = Observable()
        self.Settings = settings
        self.sessionID = ''
        self.FixClientRef = None
        self.orderID = int(calendar.timegm(time.gmtime()))
        self.inquiryID = int(calendar.timegm(time.gmtime()))
        self.Logger = logger
        self._lock = threading.RLock()
        self.connection_trigger = threading.Event()
        self.connected = False
        self.__latency = int(self.Settings.get().getString('MaxLatency'))

    def onCreate(self, sessionID):
        self.Logger.info("Session created. Session: %s" % sessionID)
        return

    def onLogon(self, sessionID):
        self.sessionID = sessionID
        self.connected = True
        self.Logger.info("onLogon received from server. Session: %s" % sessionID)
        self.connection_trigger.set()
        return

    def onLogout(self, sessionID):
        self.connected = False
        self.Logger.info("onLogout received from server. Session: %s" % sessionID)
        self.connection_trigger.clear()
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
        except fix.RuntimeError as e:
            self.Logger.error('Error in toAdmin', e)
        return

    def toApp(self, message, sessionID):
        try:
            self.Logger.info("Sending Application message to server. Session: %s. Message: %s" % (sessionID, message))
            self.__messageStore.addRequest(message)
        except fix.RuntimeError as e:
            self.Logger.error('Error in toApp', e)
        return

    def fromAdmin(self, message, sessionID):
        try:
            self.Logger.info("Received Admin message from server. Session: %s. Message: %s" % (sessionID, message))
            self.__messageStore.addResponse(message)
        except fix.RuntimeError as e:
            self.Logger.error('Error in fromAdmin', e)
        return

    def __unpackMessage(self, message):
        msgType = fix.MsgType()
        message.getHeader().getField(msgType)
        if msgType.getValue() == fix.MsgType_RequestForPositionsAck:
            account = fix.Account()
            message.getField(account)
            posId = fix.PosReqID()
            message.getField(posId)
            self.Notifier.notifyMsgHandlers(Notify.Account, Account=account.getValue(), PosReqID=posId.getValue(),
                                            Symbol=None, Maturity=None,
                                            NoPositions=0,
                                            LongQty=0, ShortQty=0,
                                            PosAmt=0, SettlPrice=0,
                                            NoPosAmt=0, ClearingBusinessDate=None,
                                            AccountInquiry=AccountInquiry.RequestForPositions)
        elif msgType.getValue() == fix.MsgType_PositionReport:
            account = fix.Account()
            message.getField(account)
            posId = fix.PosReqID()
            message.getField(posId)
            symbol = fix.Symbol()
            message.getField(symbol)
            maturity = fix.MaturityMonthYear()
            message.getField(maturity)
            noPositions = fix.NoPositions()
            message.getField(noPositions)
            longQty = fix.LongQty()
            message.getField(longQty)
            shortQty = fix.ShortQty()
            message.getField(shortQty)
            posAmt = fix.PosAmt()
            message.getField(posAmt)
            cBusDate = fix.ClearingBusinessDate()
            message.getField(cBusDate)
            settlePrice = fix.SettlPrice()
            message.getField(settlePrice)
            noPosAmt = fix.NoPosAmt()
            message.getField(noPosAmt)
            self.Notifier.notifyMsgHandlers(Notify.Account, Account=account.getValue(), PosReqID=posId.getValue(),
                Symbol=symbol.getValue(), Maturity=maturity.getValue(), NoPositions=noPositions.getValue(),
                LongQty=longQty.getValue(), ShortQty = shortQty.getValue(), PosAmt=posAmt.getValue(),SettlPrice=settlePrice.getValue(),
                NoPosAmt=noPosAmt.getValue(), ClearingBusinessDate=cBusDate.getValue(), AccountInquiry=AccountInquiry.RequestForPositions)
        elif msgType.getValue() == fix.MsgType_CollateralReport:
            account = fix.Account()
            message.getField(account)
            ccy = fix.Currency()
            message.getField(ccy)
            csh = fix.CashOutstanding()
            message.getField(csh)
            colId = fix.CollInquiryID()
            message.getField(colId)
            self.Notifier.notifyMsgHandlers(Notify.Account, Account=account.getValue(), Currency=ccy.getValue(),
                                            Balance=csh.getValue(), CollInquiryID=colId.getValue(),
                                            AccountInquiry=AccountInquiry.CollateralInquiry)
        elif msgType.getValue() == fix.MsgType_OrderCancelReject:
            cId = fix.ClOrdID()
            message.getField(cId)
            origClOrdID = fix.OrigClOrdID()
            message.getField(origClOrdID)
            self.Notifier.notifyMsgHandlers(Notify.Order, ClientOrderId=cId.getValue(), Symbol=None,
                                            AvgPx=None, Quantity=None, Side=None, Status=OrderStatus.CancelRejected,
                                            OrigClOrdID=origClOrdID.getValue(), Sender=self.FixClientRef)
        elif msgType.getValue() == fix.MsgType_ExecutionReport:
            cId = fix.ClOrdID()
            message.getField(cId)
            fixStatus = fix.OrdStatus()
            message.getField(fixStatus)
            price = fix.AvgPx()
            message.getField(price)
            qty = fix.OrderQty()
            message.getField(qty)
            side = fix.Side()
            message.getField(side)
            symbol = fix.Symbol()
            message.getField(symbol)
            orderSide = None
            origOrderId = None
            if side.getValue() == fix.Side_BUY:
                orderSide = OrderSide.Buy
            elif side.getValue() == fix.Side_SELL:
                orderSide = OrderSide.Sell
            status = None
            if fixStatus.getValue() == fix.OrdStatus_NEW:
                status = OrderStatus.New
            elif fixStatus.getValue() == fix.OrdStatus_CANCELED:
                status = OrderStatus.Cancelled
                origClOrdID = fix.OrigClOrdID()
                message.getField(origClOrdID)
                origOrderId = origClOrdID.getValue()
            elif fixStatus.getValue() == fix.OrdStatus_FILLED:
                status = OrderStatus.Filled
            elif fixStatus.getValue() == fix.OrdStatus_REJECTED:
                status = OrderStatus.Rejected
            if status is not None:
                self.Notifier.notifyMsgHandlers(Notify.Order, ClientOrderId=cId.getValue(), Symbol=symbol.getValue(),
                                                AvgPx=price.getValue(), Quantity=qty.getValue(), Side=orderSide,
                                                Status=status, OrigClOrdID=origOrderId, Sender=self.FixClientRef)

    def fromApp(self, message, sessionID):
        try:
            self.Logger.info("Received Application message from server. Session: %s. Message: %s" % (sessionID, message))
            self.__messageStore.addResponse(message)
            self.__unpackMessage(message)
        except fix.RuntimeError as e:
            self.Logger.error('Error in fromApp', e)
        return

    def send(self, message):
        if self.connected:
            self.Logger.info("FixClient is sending: %s" % message.getHeader().getField(fix.MsgType()))
            fix.Session.sendToTarget(message, self.sessionID)
        else:
            self.Logger.error('Session Not Found. Not connected to FIX engine')
            while not self.connected:
                self.Logger.info('Waiting to reconnect ...')
                self.connection_trigger.wait(2)
            self.send(message)
        return

    def genOrderID(self):
        with self._lock:
            self.orderID += 1
            return str(self.orderID)

    def genInquiryID(self):
        with self._lock:
            self.inquiryID += 1
            return 'INQ%s' % str(self.inquiryID)
