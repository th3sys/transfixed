import quickfix as fix
from transfixed import gainfixtrader as gain
import logging
import threading
from queue import Queue
from queue import Empty

pending_trades = Queue()
pending_orders = Queue()
pending_cancels = Queue()
logger = logging.getLogger()


def OrderNotificationReceived(event):
    logger.info('OrderId: %s Status: %s Side: %s' % (event.ClientOrderId, event.Status, event.Side))
    logger.info('Symbol: %s AvgPx: %s Quantity: %s' % (event.Symbol, event.AvgPx, event.Quantity))
    if event.Status == gain.OrderStatus.CancelRejected:
        logger.error('Cancel Order failed. OrigClOrdID %s' % event.OrigClOrdID)
    if event.Status == gain.OrderStatus.Cancelled:
        pending_cancels.put(event)
        pending_cancels.task_done()
    if event.Status == gain.OrderStatus.New and event.Side == gain.OrderSide.Sell:
        pending_orders.put(event)
        pending_orders.task_done()
    if event.Status == gain.OrderStatus.Filled and event.Side == gain.OrderSide.Buy:
        pending_trades.put(event)
        pending_trades.task_done()


def limitTrader(client):
    while True:
        order = gain.SellFutureLimitOrder('6E', '201707', 1, 2)
        trade = client.send(order)
        try:
            event = pending_orders.get(True, 5)
            if trade.OrderId == event.ClientOrderId and event.Status == gain.OrderStatus.New \
                    and trade.OrderType == gain.OrderType.Limit:
                logger.info('Cancelling OrderId %s' % trade.OrderId)
                client.cancel(trade)
                cancel_event = pending_cancels.get(True, 5)
                if cancel_event.OrigClOrdID == trade.OrderId:
                    logger.info('OrderId %s successfully cancelled' % trade.OrderId)
        except Empty:
            logger.info('Nothing on the queue')


def marketTrader(client):
    while True:
        order = gain.BuyFutureMarketOrder('6E', '201707', 1)
        trade = client.send(order)
        try:
            event = pending_trades.get(True, 5)
            if trade.OrderId == event.ClientOrderId and event.Status == gain.OrderStatus.Filled:
                logger.info('OrderId %s is filled' % trade.OrderId)
        except Empty:
            logger.info('Nothing on the queue')


def main():
    try:
        client = gain.FixClient.Create(logger, 'config.ini')
        client.addOrderListener(OrderNotificationReceived)
        client.start()

        traderA = threading.Thread(target=limitTrader, args=(client,))
        traderA.daemon = True
        traderA.name = 'Limit Trader'
        traderA.start()

        traderB = threading.Thread(target=marketTrader, args=(client,))
        traderB.daemon = True
        traderB.name = 'Market Trader'
        traderB.start()

        traderA.join()
        traderB.join()
        client.stop()

    except (fix.ConfigError, fix.RuntimeError), e:
        logger.error(e)


if __name__ == '__main__':
    main()
