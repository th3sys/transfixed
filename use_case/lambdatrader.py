import logging
import json
import datetime
import decimal
import boto3
from queue import Queue
from queue import Empty
import trollius as asyncio
from transfixed import gainfixtrader as gain
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError
from trollius import Return, From

# Helper class to convert a DynamoDB item to JSON.
class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            if o % 1 > 0:
                return float(o)
            else:
                return int(o)
        return super(DecimalEncoder, self).default(o)

class LambdaTrader(object):
    def __init__(self, logger):
        self.Logger = logger
        self.CurrentPositions = Queue()
        self.CurrentBalance = Queue()
        self.Loop = asyncio.get_event_loop()
        self.PendingOrders = asyncio.Queue(loop=self.Loop)
        db = boto3.resource('dynamodb', region_name='us-east-1')
        self.__Securities = db.Table('Securities')
        self.FixClient = gain.FixClient.Create(self.Logger, 'config.ini', False)
        self.FixClient.addOrderListener(self.OrderNotificationReceived)
        self.FixClient.addAccountInquiryListener(self.AccountInquiryReceived)

    def AccountInquiryReceived(self, event):
        if event.AccountInquiry == gain.AccountInquiry.CollateralInquiry:
            self.Logger.info('CollInquiryID: %s Account: %s' % (event.CollInquiryID, event.Account))
            self.Logger.info('Balance: %s Currency: %s' % (event.Balance, event.Currency))
            self.CurrentBalance.put((event.CollInquiryID, event.Balance, event.Currency))
            self.CurrentBalance.task_done()
        if event.AccountInquiry == gain.AccountInquiry.RequestForPositions:
            self.Logger.info('PosReqID: %s Account: %s' % (event.PosReqID, event.Account))
            self.Logger.info('Quantity: %s Amount: %s' % (event.LongQty - event.ShortQty, event.PosAmt))
            self.CurrentPositions.put((event.PosReqID, event.LongQty - event.ShortQty))
            self.CurrentPositions.task_done()

    def OrderNotificationReceived(self, event):
        pass

    def SendOrder(self, future):
        side, quantity, symbol, maturity = future.result()
        self.Logger.info('Submitting Validated order %s %s %s %s' % (side, quantity, symbol, maturity))
        if side.upper() == gain.OrderSide.Buy.upper():
            order = gain.BuyFutureMarketOrder(symbol, maturity, quantity)
        elif side.upper() == gain.OrderSide.Sell.upper():
            order = gain.SellFutureMarketOrder(symbol, maturity, quantity)
        self.FixClient.send(order)

    def SendReport(self, message):
        self.Logger.info('Send Email: %s', message)

    def Run(self):
        self.FixClient.start()
        if not self.PendingOrders.empty():
            validate = asyncio.ensure_future(self.validate(), loop=self.Loop)
            tasks = asyncio.gather(*[validate])
            self.Loop.run_until_complete(tasks)
        self.Loop.close()
        self.FixClient.stop()

    @asyncio.coroutine
    def validate_order(self, order):
        try:
            side = str(order['Details']['M']['Side']['S'])
            ordType = str(order['Details']['M']['OrdType']['S'])
            colReqId = self.FixClient.collateralInquiry()
            receiveColReqId, balance, ccy = self.CurrentBalance.get(True, 5)
            while colReqId != receiveColReqId:
                self.Logger.error('requests do not match colReqId: %s, receiveColReqId: %s' % (colReqId, receiveColReqId))
                self.CurrentBalance.put((receiveColReqId, balance, ccy))
                self.CurrentBalance.task_done()
                receiveColReqId, balance, ccy = self.CurrentBalance.get(True, 5)
            # check balance
        except Exception as e:
            self.Logger.error(e)
            self.SendReport('Error validate_order NewOrderId: %s. %s' % (order['NewOrderId'], e))
            raise Return(False, None)
        else:
            if ordType.upper() != gain.OrderType.Market.upper():
                supported = 'Only MARKET Orders are supported'
                self.Logger.error(supported)
                self.SendReport('Error validate_order NewOrderId: %s. %s' % (order['NewOrderId'], supported))
                raise Return(False, None)
            if side.upper() == gain.OrderSide.Buy.upper() or side.upper() == gain.OrderSide.Sell.upper():
                raise Return(True, side)
            else:
                error = 'Unknown side received. Side: %s' % side
                self.Logger.error(error)
                self.SendReport('Error validate_order NewOrderId: %s. %s' % (order['NewOrderId'], error))
                raise Return(False, None)

    @asyncio.coroutine
    def validate_quantity(self, order, security):
        try:
            quantity = int(order['Details']['M']['Quantity']['N'])
            side = order['Details']['M']['Side']['S']
            maxPosition = security['Risk']['MaxPosition']
            reqId = self.FixClient.requestForPositions()
            receiveReqId, position = self.CurrentPositions.get(True, 5)
            while reqId != receiveReqId:
                self.Logger.error('requests do not match reqId: %s, receivedId: %s' % (reqId, receiveReqId))
                self.CurrentPositions.put((receiveReqId, position))
                self.CurrentPositions.task_done()
                receiveReqId, position = self.CurrentPositions.get(True, 5)

            if side.upper() == gain.OrderSide.Buy.upper() and  maxPosition < position + quantity:
                raise Exception('MaxPosition exceeded for %s' % security['Symbol'])
            if side.upper()== gain.OrderSide.Sell.upper() and  maxPosition < abs(position - quantity):
                raise Exception('MaxPosition exceeded for %s' % security['Symbol'])
        except Empty:
            error = 'No reply to requestForPositions'
            self.Logger.error(error)
            self.SendReport('Error validate_quantity NewOrderId: %s. %s' % (order['NewOrderId'], error))
            raise Return(0)
        except Exception as e:
            self.Logger.error(e)
            self.SendReport('Error validate_quantity NewOrderId: %s. %s' % (order['NewOrderId'], e))
            raise Return(0)
        else:
            raise Return(quantity)

    @asyncio.coroutine
    def validate_maturity(self, order):
        try:
            maturity = order['Details']['M']['Maturity']['S']
            year = int(maturity[:4])
            month = int(maturity[-2:])
            date = datetime.date(year, month, 1)
            expiry = self.get_expiry_date(date)
            if expiry < datetime.date.today():
                raise Exception('%s maturity date has expired' % expiry)

        except Exception as e:
            self.Logger.error(e)
            self.SendReport('Error validate_maturity NewOrderId: %s. %s' % (order['NewOrderId'], e))
            raise Return(None)
        else:
            raise Return(maturity)

    @asyncio.coroutine
    def validate_symbol(self, order):
        try:
            symbol = order['Details']['M']['Symbol']['S']
            self.Logger.info('Validating %s' % symbol)
            response = self.__Securities.get_item(
                Key={
                    'Symbol': symbol
                }
            )
        except ClientError as e:
            self.Logger.error(e.response['Error']['Message'])
            self.SendReport('ClientError validate_symbol NewOrderId: %s. %s' % (order['NewOrderId'], e))
            raise Return(False, None)
        except Exception as e:
            self.Logger.error(e)
            self.SendReport('Error validate_symbol NewOrderId: %s. %s' % (order['NewOrderId'], e))
            raise Return(False, None)
        else:
            # self.Logger.info(json.dumps(security, indent=4, cls=DecimalEncoder))
            if response.has_key('Item') and response['Item']['Symbol'] == symbol and response['Item']['TradingEnabled']:
                raise Return(True, response['Item'])
            self.SendReport('Symbol is unknown or not enabled for trading %s' % symbol)
            raise Return(False, None)

    @asyncio.coroutine
    def validate(self):
        while not self.PendingOrders.empty():
            future = asyncio.Future()
            future.add_done_callback(self.SendOrder)
            order = yield From(self.PendingOrders.get())
            found, security = yield From(self.validate_symbol(order))
            if not found: continue

            maturity = yield From(self.validate_maturity(order))
            if not maturity: continue

            quantity = yield From(self.validate_quantity(order, security))
            if quantity < 1: continue

            good, side = yield From(self.validate_order(order))
            if not good: continue

            future.set_result((str(side), int(quantity), str(security['Symbol']), str(maturity)))


    # lifted from https://github.com/conor10/examples/blob/master/python/expiries/vix.py
    @staticmethod
    def get_expiry_date(date):
        """
        http://cfe.cboe.com/products/spec_vix.aspx

        TERMINATION OF TRADING:

        Trading hours for expiring VIX futures contracts end at 7:00 a.m. Chicago
        time on the final settlement date.

        FINAL SETTLEMENT DATE:

        The Wednesday that is thirty days prior to the third Friday of the
        calendar month immediately following the month in which the contract
        expires ("Final Settlement Date"). If the third Friday of the month
        subsequent to expiration of the applicable VIX futures contract is a
        CBOE holiday, the Final Settlement Date for the contract shall be thirty
        days prior to the CBOE business day immediately preceding that Friday.
        """
        # Date of third friday of the following month
        if date.month == 12:
            third_friday_next_month = datetime.date(date.year + 1, 1, 15)
        else:
            third_friday_next_month = datetime.date(date.year,
                                                    date.month + 1, 15)

        one_day = datetime.timedelta(days=1)
        thirty_days = datetime.timedelta(days=30)
        while third_friday_next_month.weekday() != 4:
            # Using += results in a timedelta object
            third_friday_next_month = third_friday_next_month + one_day

        # TODO: Incorporate check that it's a trading day, if so move the 3rd
        # Friday back by one day before subtracting
        return third_friday_next_month - thirty_days

def main(event, context):
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s')

    logger.info('event %s' % event)
    logger.info('context %s' % context)

    response = {'State':'OK'}
    try:
        logger.info('Start fix trader')
        trader = LambdaTrader(logger)
        for record in event['Records']:
            if record['eventName'] == 'INSERT':
                logger.info('New Order received NewOrderId: %s', record['dynamodb']['Keys']['NewOrderId'])
                trader.PendingOrders.put_nowait(record['dynamodb']['NewImage'])
            else:
                logger.info('Not INSERT event is ignored')

        if not trader.PendingOrders.empty():
            trader.Run()
        logger.info('Stop fix trader')

    except Exception as e:
        logger.error(e)
        response['State']='ERROR'

    return response

def lambda_handler(event, context):
    res = main(event, context)
    return json.dumps(res)

if __name__ == '__main__':
    with open("event.json") as json_file:
        test_event = json.load(json_file, parse_float=decimal.Decimal)
    re = main(test_event, None)
    print(json.dumps(re))