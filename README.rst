TRANSFIXED - FIX TRADING LIBRARY
================================

This is an implementation of the following FIX APIs:

- GAIN CAPITAL FUTURES FIX API
- CQG FIX API

.. image:: https://badge.fury.io/py/transfixed.svg
    :target: https://pypi.python.org/pypi/transfixed/1.0.5

.. image:: https://travis-ci.org/th3sys/transfixed.svg?branch=master
 :target: https://travis-ci.org/th3sys/transfixed/

Features
========
Transfixed is a FIX API trading library that has passed conformance tests with `Gain Capital Futures <https://gainfutures.com/>`_. It implements the following application messages:

- Send Market Order
- Send Limit Order
- Order Cancel Request
- Request For Positions
- Collateral Inquiry

It is written in pure python and you can use it with your choice of python event loop - ``gevent``, ``threading``, ``asyncio``, etc. See Usage for more details.

Installation
============

You can install using the Python Package Index (PyPI)
or from source.

To install using ``pip``:

::

    $ pip install transfixed

Usage
=====
Copy the FIX directory with FIX dictionary and the ``config.ini`` into your application directory. Use any of these tests as an example.


1. Login, send market orders, limit orders and cancels and receive the execution report using ``threading``:
::

	import quickfix as fix
	from transfixed import gainfixtrader as gain
	import logging
	import threading
	from queue import Queue
	from queue import Empty

	pending_trades = Queue()
	pending_orders = Queue()
	pending_cancels = Queue()
	logger = logging.getLogger()


	def OrderNotificationReceived(event):
		logger.info('OrderId: %s Status: %s Side: %s' % (event.ClientOrderId, event.Status, event.Side))
		logger.info('Symbol: %s AvgPx: %s Quantity: %s' % (event.Symbol, event.AvgPx, event.Quantity))
		if event.Status == gain.OrderStatus.CancelRejected:
			logger.error('Cancel Order failed. OrigClOrdID %s' % event.OrigClOrdID)
		if event.Status == gain.OrderStatus.Cancelled:
			pending_cancels.put(event)
			pending_cancels.task_done()
		if event.Status == gain.OrderStatus.New and event.Side == gain.OrderSide.Sell:
			pending_orders.put(event)
			pending_orders.task_done()
		if event.Status == gain.OrderStatus.Filled and event.Side == gain.OrderSide.Buy:
			pending_trades.put(event)
			pending_trades.task_done()


	def limitTrader(client):
		while True:
			order = gain.SellFutureLimitOrder('6E', '201707', 1, 2)
			trade = client.send(order)
			try:
				event = pending_orders.get(True, 5)
				if trade.OrderId == event.ClientOrderId and event.Status == gain.OrderStatus.New \
						and trade.OrderType == gain.OrderType.Limit:
					logger.info('Cancelling OrderId %s' % trade.OrderId)
					client.cancel(trade)
					cancel_event = pending_cancels.get(True, 5)
					if cancel_event.OrigClOrdID == trade.OrderId:
						logger.info('OrderId %s successfully cancelled' % trade.OrderId)
			except Empty:
				logger.info('Nothing on the queue')


	def marketTrader(client):
		while True:
			order = gain.BuyFutureMarketOrder('6E', '201707', 1)
			trade = client.send(order)
			try:
				event = pending_trades.get(True, 5)
				if trade.OrderId == event.ClientOrderId and event.Status == gain.OrderStatus.Filled:
					logger.info('OrderId %s is filled' % trade.OrderId)
			except Empty:
				logger.info('Nothing on the queue')


	def main():
		try:
			client = gain.FixClient.Create(logger, 'config.ini', False)
			client.addOrderListener(OrderNotificationReceived)
			client.start()

			traderA = threading.Thread(target=limitTrader, args=(client,))
			traderA.daemon = True
			traderA.name = 'Limit Trader'
			traderA.start()

			traderB = threading.Thread(target=marketTrader, args=(client,))
			traderB.daemon = True
			traderB.name = 'Market Trader'
			traderB.start()

			traderA.join()
			traderB.join()
			client.stop()

		except (fix.ConfigError, fix.RuntimeError) as e:
			logger.error(e)


	def lambda_handler(event, context):
		main()

	if __name__ == '__main__':
		main()






2. Login and count heartbeats using ``gevent``:

::

	import quickfix as fix
	from transfixed import gainfixtrader as gain
	import logging
	import gevent
	import signal

	logger = logging.getLogger()
	client = None


	def start():
		global client
		client = gain.FixClient.Create(logger, 'config.ini', True)
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

		except (fix.ConfigError, fix.RuntimeError) as e:
			logger.error(e)


	if __name__ == '__main__':
		gevent.signal(signal.SIGQUIT, gevent.kill)
		main()


3. Send orders, receive reports, check account balance and send for position report:

::

	import quickfix as fix
	from transfixed import gainfixtrader as gain
	import logging
	import threading
	import time
	from queue import Queue
	from queue import Empty


	class FixTrader:
		def __init__(self):
			self.Logger = logging.getLogger()
			self.Logger.setLevel(logging.INFO)
			logging.basicConfig(format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s')
			self.Run = True
			self.ReceivedOrders = Queue()
			self.PendingConfOrders = Queue()
			self.ConfirmedTrades = Queue()

		def AccountInquiryReceived(self, event):
			if event.AccountInquiry == gain.AccountInquiry.CollateralInquiry:
				self.Logger.info('CollInquiryID: %s Account: %s' % (event.CollInquiryID, event.Account))
				self.Logger.info('Balance: %s Currency: %s' % (event.Balance, event.Currency))
			elif event.AccountInquiry == gain.AccountInquiry.RequestForPositions:
				self.Logger.info('PosReqID: %s Account: %s' % (event.PosReqID, event.Account))
				self.Logger.info('Quantity: %s Amount: %s' % (event.LongQty - event.ShortQty, event.PosAmt))
			self.Logger.info('account request notification received')

		def OrderNotificationReceived(self, event):
			self.Logger.info('OrderId: %s Status: %s Side: %s' % (event.ClientOrderId, event.Status, event.Side))
			self.Logger.info('Symbol: %s AvgPx: %s Quantity: %s' % (event.Symbol, event.AvgPx, event.Quantity))
			self.Logger.info('order notification received')
			if event.Status == gain.OrderStatus.Filled or event.Status == gain.OrderStatus.Rejected:
				try:
					trade = self.PendingConfOrders.get(True, 5)
					if trade.OrderId == event.ClientOrderId:
						self.ConfirmedTrades.put(trade)
						self.Logger.info('Confirmed ClientOrderId: %s' % event.ClientOrderId)
					else:
						self.PendingConfOrders.put(trade)
						self.Logger.info('Returning to pending queue ClientOrderId: %s' % event.ClientOrderId)

				except Empty:
					self.Logger.info('No pending trades on the queue')

		def Loop(self):
			client = gain.FixClient.Create(self.Logger, 'config.ini', False)
			client.addOrderListener(self.OrderNotificationReceived)
			client.addAccountInquiryListener(self.AccountInquiryReceived)
			client.start()
			client.collateralInquiry()
			client.requestForPositions()
			while self.Run:
				try:
					order = self.ReceivedOrders.get(True, 5)
					self.Logger.info('order received')
					trade = client.send(order)
					self.PendingConfOrders.put(trade)
					self.PendingConfOrders.task_done()
				except Empty:
					self.Logger.error('No orders on the queue')
			client.stop()


	def test_orders(trader):
		def send(t):
			i = 2
			while i > 0:
				t.Logger.info('sending test order %s' % i)
				order = gain.BuyFutureMarketOrder('6E', '201707', 1)
				t.ReceivedOrders.put(order)
				t.ReceivedOrders.task_done()
				time.sleep(3)
				i -= 1
		tester = threading.Thread(target=send, args=(trader,))
		tester.daemon = True
		tester.name = 'Market Trader'
		tester.start()


	def main():
		trader = FixTrader()
		try:
			test_orders(trader)
			trader.Logger.info('Start fix trader')
			trader.Loop()
			trader.Logger.info('Stop fix trader')
		except (fix.ConfigError, fix.RuntimeError) as e:
			trader.Logger.error(e)


	def lambda_handler(event, context):
		main()

	if __name__ == '__main__':
		main()



*This product includes software developed by quickfixengine.org (http://www.quickfixengine.org/).*