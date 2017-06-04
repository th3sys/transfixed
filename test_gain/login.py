import quickfix as fix
from transfixed import gainfixtrader as gain
import time
import logging


def main():
    logger = logging.getLogger()
    try:
        init = gain.FixClient.CreateInitiator(logger, 'config.ini')
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
