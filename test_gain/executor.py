import time
import quickfix as fix


class Application(fix.Application):

    def __init__(self):
        super(Application, self).__init__()

    def onCreate(self, sessionID):
        print('onCreate')
        return

    def onLogon(self, sessionID):
        print('onLogon')
        return

    def onLogout(self, sessionID):
        print('onLogout')
        return

    def toAdmin(self, message, sessionID):
        print('toAdmin')
        return

    def fromAdmin(self, message, sessionID):
        print('fromAdmin')
        return

    def toApp(self, message, sessionID):
        print('toApp')
        return

    def fromApp(self, message, sessionID):
        print('fromApp')
        return


def main(file_name):

    try:
        settings = fix.SessionSettings(file_name)
        application = Application()
        storeFactory = fix.FileStoreFactory(settings)
        logFactory = fix.FileLogFactory(settings)

        acceptor = fix.SocketAcceptor(application, storeFactory, settings, logFactory)
        print 'starting acceptor'
        acceptor.start()

        while 1:
            time.sleep(1)
    except (fix.ConfigError, fix.RuntimeError), e:
        print e

if __name__ == '__main__':
    main('executor.ini')
