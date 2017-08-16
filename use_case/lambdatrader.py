import logging
import json
import datetime
from datetime import timedelta
import decimal
import boto3
from queue import Queue
from queue import Empty
from transfixed import gainfixtrader as gain
import base64
import hmac
import hashlib
import os
import smtplib
import atexit
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from botocore.exceptions import ClientError

# Helper class to convert a DynamoDB item to JSON.
class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            if o % 1 > 0:
                return float(o)
            else:
                return int(o)
        return super(DecimalEncoder, self).default(o)

class Singleton(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class LambdaTrader(object):
    __metaclass__ = Singleton
    def __init__(self, logger):
        self.Logger = logger
        self.CurrentPositions = Queue()
        self.CurrentBalance = Queue()
        self.SubmittedOrders = Queue()
        self.Messages = []
        self.PendingOrders = Queue()
        db = boto3.resource('dynamodb', region_name='us-east-1')
        self.__Securities = db.Table('Securities')
        self.__Orders = db.Table('Orders')
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
            self.CurrentPositions.put((event.PosReqID, event.Symbol, event.Maturity, event.LongQty - event.ShortQty))
            self.CurrentPositions.task_done()

    def OrderNotificationReceived(self, event):
        self.Logger.info('OrderId: %s Status: %s Side: %s' % (event.ClientOrderId, event.Status, event.Side))
        self.Logger.info('Symbol: %s AvgPx: %s Quantity: %s' % (event.Symbol, event.AvgPx, event.Quantity))
        self.Logger.info('order notification received')
        if event.Status == gain.OrderStatus.Filled or event.Status == gain.OrderStatus.Rejected:
            self.SubmittedOrders.put((event.ClientOrderId, event.Status, event.AvgPx))
            self.SubmittedOrders.task_done()

    def SendOrder(self, side, quantity, symbol, maturity, newOrderId, transactionTime):

        self.Logger.info('Submitting Validated order %s %s %s %s' % (side, quantity, symbol, maturity))
        if side.upper() == gain.OrderSide.Buy.upper():
            order = gain.BuyFutureMarketOrder(symbol, maturity, quantity)
        elif side.upper() == gain.OrderSide.Sell.upper():
            order = gain.SellFutureMarketOrder(symbol, maturity, quantity)
        trade = self.FixClient.send(order)
        orderId, status, price = self.SubmittedOrders.get(True, 5)
        while trade.OrderId != orderId:
            self.Logger.error('requests do not match orderId: %s, trade.OrderId: %s' % (orderId, trade.OrderId))
            orderId, status, price = self.SubmittedOrders.get(True, 5)
        self.Logger.info('Confirmed orderId %s. Status: %s. Price: %s. Symbol: %s' % (orderId, status, price, symbol))
        self.UpdateStatus('Confirmed newOrderId: %s. ClientOrderId: %s. Status: %s. Side: %s. Qty: %s. Symbol: %s. '
                        'Maturity: %s. Price: %s'
                        % (newOrderId, orderId, status, side, quantity, symbol, maturity, price),
                          newOrderId, transactionTime, orderId, status)

    def UpdateStatus(self, text, newOrderId, transactionTime, clientOrderId, status):
        try:
            response = self.__Orders.update_item(
                Key={
                    'NewOrderId': newOrderId['S'],
                    'TransactionTime': transactionTime['S'],
                },
                UpdateExpression="set #s = :s, ClientOrderId = :c",
                ConditionExpression="#s = :p and NewOrderId = :n",
                ExpressionAttributeNames={
                    '#s': 'Status'
                },
                ExpressionAttributeValues={
                    ':s': status,
                    ':c': clientOrderId,
                    ':n': newOrderId['S'],
                    ':p': 'PENDING'
                },
                ReturnValues="UPDATED_NEW")
            text += '. %s' % response['Attributes']

        except ClientError as e:
            self.Logger.error(e.response['Error']['Message'])
            text += '%s. %s' % ('', e.response['Error']['Message'])
        except Exception as e:
            self.Logger.error(e)
            text += '%s. %s' % ('', e)
        else:
            text += ". UpdateItem succeeded."
            self.Logger.info(json.dumps(response, indent=4, cls=DecimalEncoder))

        self.Logger.info('To Send Email: %s', text)
        self.Messages.append(text)


    def SendReport(self, text):
        try:
            self.Logger.info('Send Email: %s', text)

            def hash_smtp_pass_from_secret_key(key):
                message = "SendRawEmail"
                version = '\x02'
                h = hmac.new(key, message, digestmod=hashlib.sha256)
                return base64.b64encode("{0}{1}".format(version, h.digest()))

            msg = MIMEMultipart('alternative')
            msg['Subject'] = 'Lambda FIX Trader report'
            msg['From'] = os.environ['email_address']
            msg['To'] = os.environ['email_address']
            mime_text = MIMEText(text, 'html')
            msg.attach(mime_text)

            server = smtplib.SMTP('email-smtp.us-east-1.amazonaws.com', 587, timeout=10)
            server.set_debuglevel(10)
            server.starttls()
            server.ehlo()
            server.login(os.environ['aws_access_key_id'],
                         hash_smtp_pass_from_secret_key(os.environ['aws_secret_access_key']))
            server.sendmail(os.environ['email_address'], os.environ['email_address'], msg.as_string())
            res = server.quit()
            self.Logger.info(res)
        except Exception as e:
            self.Logger.error(e)

    def Run(self):
        if not self.FixClient.SocketInitiator.application.connected:
            self.FixClient.start()

        if not self.PendingOrders.empty():
            self.validate()

            report = reduce(lambda x, y: x + y, map(lambda x, y: '<br><b>%s</b>. %s\n' % (x + 1, y),
                                                    range(len(self.Messages)), self.Messages))
            self.SendReport(report)
            self.Messages = []

    def validate_order(self, order, security):
        try:
            side = str(order['Details']['M']['Side']['S'])
            ordType = str(order['Details']['M']['OrdType']['S'])
            riskFactor = float(security['Risk']['RiskFactor'])
            margin = int(security['Risk']['Margin']['Amount'])
            marginCcy = str(security['Risk']['Margin']['Currency'])
            colReqId = self.FixClient.collateralInquiry()
            receiveColReqId, balance, ccy = self.CurrentBalance.get(True, 5)
            while colReqId != receiveColReqId:
                self.Logger.error('requests do not match colReqId: %s, receiveColReqId: %s' % (colReqId, receiveColReqId))
                receiveColReqId, balance, ccy = self.CurrentBalance.get(True, 5)
            if marginCcy != ccy:
                raise Exception('Margin Currency does not match Balance Currency for %s' % security['Symbol'])
            if balance * riskFactor < margin:
                raise Exception('Margin exceeded for %s. Balance: %s, RF: %s, Margin: %s'
                                % (security['Symbol'], balance, riskFactor, margin))
        except Exception as e:
            self.Logger.error(e)
            self.UpdateStatus('Error validate_order NewOrderId: %s. %s' % (order['NewOrderId'], e),
                              order['NewOrderId'], order['TransactionTime'], 0, 'INVALID')
            return False, None
        else:
            if ordType.upper() != gain.OrderType.Market.upper():
                supported = 'Only MARKET Orders are supported'
                self.Logger.error(supported)
                self.UpdateStatus('Error validate_order NewOrderId: %s. %s' % (order['NewOrderId'], supported),
                                  order['NewOrderId'],order['TransactionTime'], 0, 'INVALID')
                return False, None
            if side.upper() == gain.OrderSide.Buy.upper() or side.upper() == gain.OrderSide.Sell.upper():
                return True, side
            else:
                error = 'Unknown side received. Side: %s' % side
                self.Logger.error(error)
                self.UpdateStatus('Error validate_order NewOrderId: %s. %s' % (order['NewOrderId'], error),
                                  order['NewOrderId'],order['TransactionTime'], 0, 'INVALID')
                return False, None

    def validate_quantity(self, order, security):
        otherPositionsInSecurity = False
        try:
            quantity = int(order['Details']['M']['Quantity']['N'])
            side = order['Details']['M']['Side']['S']
            symbol = order['Details']['M']['Symbol']['S']
            maturity = order['Details']['M']['Maturity']['S']
            maxPosition = security['Risk']['MaxPosition']
            reqId = self.FixClient.requestForPositions()
            receiveReqId, receivedSymbol, receivedMaturity, position = self.CurrentPositions.get(True, 5)
            while reqId != receiveReqId or symbol != receivedSymbol or maturity != receivedMaturity:
                otherPositionsInSecurity = True
                self.Logger.error('requests do not match reqId: %s, receivedId: %s, maturity: %s, receivedMaturity: %s'
                                  % (reqId, receiveReqId, maturity, receivedMaturity))
                receiveReqId, receivedSymbol, receivedMaturity, position = self.CurrentPositions.get(True, 5)

            if side.upper() == gain.OrderSide.Buy.upper() and  maxPosition < position + quantity:
                raise Exception('MaxPosition exceeded for %s' % security['Symbol'])
            if side.upper()== gain.OrderSide.Sell.upper() and  maxPosition < abs(position - quantity):
                raise Exception('MaxPosition exceeded for %s' % security['Symbol'])
        except Empty:
            error = 'No reply to requestForPositions'
            self.Logger.error(error)
            if otherPositionsInSecurity:
                self.Logger.error('Gain Futures does not send a reply to requestForPositions if position is 0 and there is'
                                  'a position in other maturity in this contract')
                if maxPosition < quantity:
                    self.UpdateStatus('Error validate_quantity NewOrderId: %s. %s' % (order['NewOrderId'], error+
                                                                                      '. MaxPosition exceeded for %s' %
                                                                                      security['Symbol']),
                                      order['NewOrderId'], order['TransactionTime'], 0, 'INVALID')
                    return 0
                else:
                    return quantity

            else:
                self.UpdateStatus('Error validate_quantity NewOrderId: %s. %s' % (order['NewOrderId'], error),
                              order['NewOrderId'],order['TransactionTime'], 0, 'INVALID')
                return 0
        except Exception as e:
            self.Logger.error(e)
            self.UpdateStatus('Error validate_quantity NewOrderId: %s. %s' % (order['NewOrderId'], e),
                              order['NewOrderId'],order['TransactionTime'], 0, 'INVALID')
            return 0
        else:
            return quantity

    def validate_maturity(self, order):
        try:
            maturity = order['Details']['M']['Maturity']['S']
            year = int(maturity[:4])
            month = int(maturity[-2:])
            date = datetime.date(year, month, 1)
            expiry = self.get_expiry_date(date)
            if expiry <= datetime.date.today() + timedelta(days=1):
                raise Exception('%s maturity date has expired' % expiry)

        except Exception as e:
            self.Logger.error(e)
            self.UpdateStatus('Error validate_maturity NewOrderId: %s. %s' % (order['NewOrderId'], e),
                              order['NewOrderId'],order['TransactionTime'], 0, 'INVALID')
            return None
        else:
            return maturity

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
            self.UpdateStatus('ClientError validate_symbol NewOrderId: %s. %s' % (order['NewOrderId'], e),
                              order['NewOrderId'],order['TransactionTime'], 0, 'INVALID')
            return False, None
        except Exception as e:
            self.Logger.error(e)
            self.UpdateStatus('Error validate_symbol NewOrderId: %s. %s' % (order['NewOrderId'], e),
                              order['NewOrderId'],order['TransactionTime'], 0, 'INVALID')
            return False, None
        else:
            # self.Logger.info(json.dumps(security, indent=4, cls=DecimalEncoder))
            if response.has_key('Item') and response['Item']['Symbol'] == symbol and response['Item']['TradingEnabled']:
                return True, response['Item']
            self.UpdateStatus('Symbol is unknown or not enabled for trading %s' % symbol,
                              order['NewOrderId'], order['TransactionTime'], 0, 'INVALID')
            return False, None

    def validate(self):
        while not self.PendingOrders.empty():

            order = self.PendingOrders.get()
            found, security = self.validate_symbol(order)
            if not found: continue

            maturity = self.validate_maturity(order)
            if not maturity: continue

            quantity = self.validate_quantity(order, security)
            if quantity < 1: continue

            good, side = self.validate_order(order, security)
            if not good: continue

            self.SendOrder(str(side), int(quantity), str(security['Symbol']), str(maturity),
                               order['NewOrderId'], order['TransactionTime'])


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

trader = None
@atexit.register
def lambda_exit():
    if trader is not None:
        trader.Logger.info('lambda_exit is called')
        trader.FixClient.stop()


def main(event, context):
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s')

    logger.info('event %s' % event)
    logger.info('context %s' % context)

    response = {'State':'OK'}
    try:
        logger.info('Start fix trader')
        global trader
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
    re = main(test_event, None)
    print(json.dumps(re))