import quickfix as fix
from transfixed import gainfixtrader as gain
import logging
import threading
import time
from queue import Queue
from queue import Empty


class FixTrader:
    def __init__(self):
        self.Logger = logging.getLogger()
        self.Logger.setLevel(logging.INFO)
        logging.basicConfig(format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s')
        self.Run = True
        self.ReceivedOrders = Queue()
        self.PendingConfOrders = Queue()
        self.ConfirmedTrades = Queue()

    def AccountInquiryReceived(self, event):
        if event.AccountInquiry == gain.AccountInquiry.CollateralInquiry:
            self.Logger.info('CollInquiryID: %s Account: %s' % (event.CollInquiryID, event.Account))
            self.Logger.info('Balance: %s Currency: %s' % (event.Balance, event.Currency))
        elif event.AccountInquiry == gain.AccountInquiry.RequestForPositions:
            self.Logger.info('PosReqID: %s Account: %s' % (event.PosReqID, event.Account))
            self.Logger.info('Quantity: %s Amount: %s' % (event.LongQty - event.ShortQty, event.PosAmt))
        self.Logger.info('account request notification received')

    def OrderNotificationReceived(self, event):
        self.Logger.info('OrderId: %s Status: %s Side: %s' % (event.ClientOrderId, event.Status, event.Side))
        self.Logger.info('Symbol: %s AvgPx: %s Quantity: %s' % (event.Symbol, event.AvgPx, event.Quantity))
        self.Logger.info('order notification received')
        if event.Status == gain.OrderStatus.Filled or event.Status == gain.OrderStatus.Rejected:
            try:
                trade = self.PendingConfOrders.get(True, 5)
                if trade.OrderId == event.ClientOrderId:
                    self.ConfirmedTrades.put(trade)
                    self.Logger.info('Confirmed ClientOrderId: %s' % event.ClientOrderId)
                else:
                    self.PendingConfOrders.put(trade)
                    self.Logger.info('Returning to pending queue ClientOrderId: %s' % event.ClientOrderId)

            except Empty:
                self.Logger.info('No pending trades on the queue')

    def Loop(self):
        client = gain.FixClient.Create(self.Logger, 'config.ini', False)
        client.addOrderListener(self.OrderNotificationReceived)
        client.addAccountInquiryListener(self.AccountInquiryReceived)
        client.start()
        client.collateralInquiry()
        client.requestForPositions()
        while self.Run:
            try:
                order = self.ReceivedOrders.get(True, 5)
                self.Logger.info('order received')
                trade = client.send(order)
                self.PendingConfOrders.put(trade)
                self.PendingConfOrders.task_done()
            except Empty:
                self.Logger.error('No orders on the queue')
        client.stop()


def test_orders(trader):
    def send(t):
        i = 2
        while i > 0:
            t.Logger.info('sending test order %s' % i)
            order = gain.BuyFutureMarketOrder('6E', '201707', 1)
            t.ReceivedOrders.put(order)
            t.ReceivedOrders.task_done()
            time.sleep(3)
            i -= 1
    tester = threading.Thread(target=send, args=(trader,))
    tester.daemon = True
    tester.name = 'Market Trader'
    tester.start()


def main():
    trader = FixTrader()
    try:
        test_orders(trader)
        trader.Logger.info('Start fix trader')
        trader.Loop()
        trader.Logger.info('Stop fix trader')
    except (fix.ConfigError, fix.RuntimeError) as e:
        trader.Logger.error(e)


def lambda_handler(event, context):
    main()

if __name__ == '__main__':
    main()
