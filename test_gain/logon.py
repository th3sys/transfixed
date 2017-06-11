import quickfix as fix
from transfixed import gainfixtrader as gain
import logging
import gevent
import signal

logger = logging.getLogger()
client = None


def start():
    global client
    client = gain.FixClient.Create(logger, 'config.ini')
    client.start()


def poll():
    global client
    i = 10
    while i > 0:
        i -= 1
        gevent.sleep(10)
        logger.info('Waiting for FIX messages')
    client.stop()


def main():

    try:
        gevent.joinall([
            gevent.spawn(start()),
            gevent.spawn(poll()),
        ])

    except (fix.ConfigError, fix.RuntimeError), e:
        logger.error(e)


if __name__ == '__main__':
    gevent.signal(signal.SIGQUIT, gevent.kill)
    main()
