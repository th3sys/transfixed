import quickfix as fix
import quickfix44 as fix44
import logging
import threading
from dateutil import parser
import datetime as dt


class FixClient(object):
    def __init__(self, init, logger):
        self.SocketInitiator = init
        self.Logger = logger

    @classmethod
    def Create(cls, logger, config):
        logger.setLevel(logging.INFO)
        logging.basicConfig(format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s')
        settings = fix.SessionSettings(config)
        application = GainApplication(settings, logger)
        storeFactory = fix.FileStoreFactory(settings)
        logFactory = fix.FileLogFactory(settings)
        init = fix.SocketInitiator(application, storeFactory, settings, logFactory)
        return FixClient(init, logger)

    def heartbeat(self):
        message = fix.Message()
        message.getHeader().setField(fix.MsgType(fix.MsgType_Heartbeat))
        self.SocketInitiator.application.send(message)

    def logout(self):
        message = fix44.Logout()
        self.SocketInitiator.application.send(message)

    def start(self):
        self.Logger.info("Open FIX Connection")
        self.SocketInitiator.start()

    def stop(self):
        self.Logger.info("Close FIX Connection")
        self.SocketInitiator.stop()


class MessageStore(object):
    def __init__(self, logger, settings):
        self.Logger = logger
        self.Settings = settings
        self.__lock = threading.RLock()
        self.__out = {}
        self.__in = {}
        self.__latency = int(self.Settings.get().getString('MaxLatency'))

    def __timeCheck(self, request, response):
        lag = abs(parser.parse(request) - parser.parse(response))
        if lag > dt.timedelta(seconds=self.__latency):
            self.Logger.error("Max Latency exceeded for messages: %s %s" % (request, response))

    @staticmethod
    def __uncorkKey(message):
        """
        Return a value that can be used as a key based on a message type
        :param message: FIX message
        :return: key
        """
        msgType = fix.MsgType()
        message.getHeader().getField(msgType)
        sequence = fix.MsgSeqNum()
        message.getHeader().getField(sequence)
        if msgType.getValue() == fix.MsgType_Logon:
            return '%s_%s' % (fix.MsgType_Logon, sequence.getValue())
        if msgType.getValue() == fix.MsgType_Logout:
            return '%s_%s' % (fix.MsgType_Logout, sequence.getValue())
        if msgType.getValue() == fix.MsgType_Heartbeat:
            return '%s_%s' % (fix.MsgType_Heartbeat, sequence.getValue())
        return None

    def addRequest(self, message):
        key = MessageStore.__uncorkKey(message)
        if key is None:
            self.Logger.error('Unknown request message type %s' % message)
            return
        with self.__lock:
            sndTime = fix.SendingTime()
            message.getHeader().getField(sndTime)
            self.__out[key] = sndTime.getString()
            if key in self.__in:
                self.__timeCheck(self.__out[key], self.__in[key])

    def addResponse(self, message):
        key = MessageStore.__uncorkKey(message)
        if key is None:
            self.Logger.error('Unknown response message type: %s' % message)
            return
        with self.__lock:
            sndTime = fix.SendingTime()
            message.getHeader().getField(sndTime)
            self.__in[key] = sndTime.getString()
            if key in self.__out:
                self.__timeCheck(self.__out[key], self.__in[key])


class GainApplication(fix.Application, object):
    def __init__(self, settings, logger):
        super(GainApplication, self).__init__()
        self.__adminMessages = MessageStore(logger, settings)
        self.Settings = settings
        self.sessionID = ''
        self.orderID = 0
        self.execID = 0
        self.Logger = logger

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
        try:
            msgType = fix.MsgType()
            message.getHeader().getField(msgType)
            if msgType.getValue() == fix.MsgType_Logon:
                uuid = self.Settings.get().getString('Username')
                password = self.Settings.get().getString('Password')
                message.getHeader().setField(fix.Password(password))
                message.getHeader().setField(fix.StringField(12003, uuid))
            self.Logger.info("Sending Admin message to server. Session: %s. Message: %s" % (sessionID, message))
            self.__adminMessages.addRequest(message)
        except fix.RuntimeError, e:
            self.Logger.error('Error in toAdmin', e)
        return

    def toApp(self, message, sessionID):
        self.Logger.info("Sending Application message to server. Session: %s. Message: %s" % (sessionID, message))
        return

    def fromAdmin(self, message, sessionID):
        try:
            self.Logger.info("Received Admin message from server. Session: %s. Message: %s" % (sessionID, message))
            self.__adminMessages.addResponse(message)
        except fix.RuntimeError, e:
            self.Logger.error('Error in fromAdmin', e)
        return

    def fromApp(self, message, sessionID):
        self.Logger.info("Received Application message from server. Session: %s. Message: %s" % (sessionID, message))
        return

    def send(self, message):
        self.Logger.info("FixClient is sending: %s" % type(message))
        fix.Session.sendToTarget(message, self.sessionID)
        return

    def genOrderID(self):
        self.orderID += 1
        return '%s' % str(self.orderID)

    def genExecID(self):
        self.execID += 1
        return str(self.execID)
