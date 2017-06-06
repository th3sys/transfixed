import quickfix as fix
from transfixed import gainfixtrader as gain
import logging
import gevent
import signal

logger = logging.getLogger()
init = None


def start():
    global init
    init = gain.FixClient.CreateInitiator(logger, 'config.ini')
    init.start()


def poll(cond):
    global init
    while cond:
        gevent.sleep(10)
        logger.info('Waiting for FIX messages')
    init.stop()


def main():

    try:
        gevent.joinall([
            gevent.spawn(start()),
            gevent.spawn(poll(True)),
        ])

    except (fix.ConfigError, fix.RuntimeError), e:
        logger.error(e)


if __name__ == '__main__':
    gevent.signal(signal.SIGQUIT, gevent.kill)
    main()
