import quickfix as fix
from transfixed import gainfixtrader as gain
import logging
import time
import threading

def OrderNotificationReceived(order):
    pass

def limitTrader(client):
    while 1:
        time.sleep(2)
        order = gain.SellFutureLimitOrder('6E', '201706', 1, 2)
        client.send(order)

def marketTrader(client):
    while 1:
        time.sleep(5)
        order = gain.BuyFutureMarketOrder('6E', '201706', 1)
        client.send(order)

def main():
    logger = logging.getLogger()
    try:
        client = gain.FixClient.Create(logger, 'config.ini')
        client.start()

        traderA = threading.Thread(target=limitTrader, args=(client, ))
        traderA.daemon = True
        traderA.name = 'Limit Trader'
        traderA.start()

        traderB = threading.Thread(target=marketTrader, args=(client, ))
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
