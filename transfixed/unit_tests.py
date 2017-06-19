import unittest
import logging
import quickfix as fix
import quickfix44 as fix44
import datetime as dt
from transfixed import gainfixtrader as gain


class TestTimeLags(unittest.TestCase):

    def setUp(self):
        logger = logging.getLogger()
        settings = fix.SessionSettings('gain_config.ini')
        self.Store = gain.MessageStore(logger, settings)

    def test_logon(self):
        sequence = fix.MsgSeqNum(1)
        requestTime = fix.SendingTime()
        requestTime.setString('20170606-03:52:24.324')
        request = fix44.Logon()
        request.getHeader().setField(requestTime)
        request.getHeader().setField(sequence)

        responseTime = fix.SendingTime()
        responseTime.setString('20170606-03:52:34.824')
        response = fix44.Logon()
        response.getHeader().setField(responseTime)
        response.getHeader().setField(sequence)
        currentLag = {}

        def receive(event):
            currentLag[0] = event.CurrentTimeLag
        self.Store.addTimeLagListener(receive)
        self.Store.addRequest(request)
        self.Store.addResponse(response)
        self.assertEqual(currentLag[0], 10.5)

    def test_heartbeat(self):
        sequence = fix.MsgSeqNum(1)
        requestTime = fix.SendingTime()
        requestTime.setString('20170606-03:52:34.924')
        request = fix44.Heartbeat()
        request.getHeader().setField(requestTime)
        request.getHeader().setField(sequence)

        responseTime = fix.SendingTime()
        responseTime.setString('20170606-03:52:14.824')
        response = fix44.Heartbeat()
        response.getHeader().setField(responseTime)
        response.getHeader().setField(sequence)
        currentLag = {}

        def receive(event):
            currentLag[0] = event.CurrentTimeLag
        self.Store.addTimeLagListener(receive)
        self.Store.addRequest(request)
        self.Store.addResponse(response)
        self.assertEqual(currentLag[0], 20.1)

    def test_order(self):
        cid = fix.ClOrdID('100')
        requestTime = fix.TransactTime()
        requestTime.setString('20170606-03:52:34.924')
        request = fix44.NewOrderSingle()
        request.setField(requestTime)
        request.setField(cid)

        responseTime = fix.TransactTime()
        responseTime.setString('20170606-03:52:14.824')
        response = fix44.ExecutionReport()
        response.setField(responseTime)
        response.setField(cid)
        currentLag = {}

        def receive(event):
            currentLag[0] = event.CurrentTimeLag
        self.Store.addTimeLagListener(receive)
        self.Store.addRequest(request)
        self.Store.addResponse(response)
        self.assertEqual(currentLag[0], 20.1)

    def tearDown(self):
        pass

if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestTimeLags)
    unittest.TextTestRunner(verbosity=2).run(suite)
