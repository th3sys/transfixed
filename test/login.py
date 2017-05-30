import quickfix as fix
from cqgfixtrader import etrading as et
import time
import logging


def main():
    logger = logging.getLogger()
    try:
        init = et.FixClient.CreateInitiator(logger, 'config.ini')
        init.start()
        # replace with asyncio
        while True:
            logger.info('Send heartbeat and sleep')
            time.sleep(10)
        init.stop()
    except (fix.ConfigError, fix.RuntimeError), e:
        logger.error(e)


if __name__ == '__main__':
    main()
