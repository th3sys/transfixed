import quickfix as fix
from transfixed import gainfixtrader as gain
import logging
import time


def main():
    logger = logging.getLogger()
    try:
        client = gain.FixClient.Create(logger, 'config.ini')
        client.start()
        while 1:
            time.sleep(3)
            client.sendFuturesOrder('6E', '201706', 1, fix.OrdType_MARKET, fix.Side_BUY)
            # client.sendFuturesOrder('6E', '201706', 1, fix.OrdType_LIMIT, fix.Side_BUY, 50)
        client.stop()

    except (fix.ConfigError, fix.RuntimeError), e:
        logger.error(e)


if __name__ == '__main__':
    main()
