import quickfix as fix
from cqgfixtrader import etrading as et
import time
import logging


def main():
    logger = logging.getLogger()
    try:
        logger.setLevel(logging.INFO)
        logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s')
        settings = fix.SessionSettings('config.ini')
        application = et.FixClient(settings, logger)
        storeFactory = fix.FileStoreFactory(settings)
        logFactory = fix.FileLogFactory(settings)
        init = fix.SocketInitiator(application, storeFactory, settings, logFactory)
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
