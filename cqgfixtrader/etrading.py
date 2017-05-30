import quickfix as fix
import logging


class FixClient(fix.Application, object):
    def __init__(self, settings, logger):
        super(FixClient, self).__init__()
        self.Settings = settings
        self.sessionID = ''
        self.orderID = 0
        self.execID = 0
        self.Logger = logger

    @classmethod
    def CreateInitiator(cls, logger, config):
        logger.setLevel(logging.INFO)
        logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s')
        settings = fix.SessionSettings(config)
        application = FixClient(settings, logger)
        storeFactory = fix.FileStoreFactory(settings)
        logFactory = fix.FileLogFactory(settings)
        return fix.SocketInitiator(application, storeFactory, settings, logFactory)

    def onCreate(self, sessionID):
        self.Logger.info("Session created. Session: %s" % sessionID)
        return

    def onLogon(self, sessionID):
        self.sessionID = sessionID
        self.Logger.info("onLogon received from server. Session: %s" % sessionID)
        return

    def onLogout(self, sessionID):
        self.Logger.info("onLogout received from server. Session: %s" % sessionID)
        return

    def toAdmin(self, message, sessionID):
        # This allows you to add fields to an administrative message before it is sent out.
        senderSubId = self.Settings.get().getString('SenderSubID')
        message.getHeader().setField(fix.SenderSubID(senderSubId))
        self.Logger.info("Sending Admin message to server. Session: %s. Message: %s" % (sessionID, message))
        return

    def toApp(self, message, sessionID):
        self.Logger.info("Sending Application message to server. Session: %s. Message: %s" % (sessionID, message))
        return

    def fromAdmin(self, message, sessionID):
        self.Logger.info("Received Admin message from server. Session: %s. Message: %s" % (sessionID, message))
        return

    def fromApp(self, message, sessionID):
        self.Logger.info("Received Application message from server. Session: %s. Message: %s" % (sessionID, message))
        return

    def genOrderID(self):
        self.orderID += 1
        return 'CQG_%s' % str(self.orderID)

    def genExecID(self):
        self.execID += 1
        return str(self.execID)
