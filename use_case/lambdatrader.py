import logging
import json
import datetime
import decimal
import boto3
import trollius as asyncio
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
        self.Loop = asyncio.get_event_loop()
        self.PendingOrders = asyncio.Queue(loop=self.Loop)
        db = boto3.resource('dynamodb', region_name='us-east-1')
        self.__Securities = db.Table('Securities')

    def SendOrder(self, future):
        self.Logger.info('Submitting Validated order %s' % future.result())

    def SendReport(self, message):
        self.Logger.info('Send Email: %s', message)

    def Run(self):
        if not self.PendingOrders.empty():
            validate = asyncio.ensure_future(self.validate(), loop=self.Loop)
            tasks = asyncio.gather(*[validate])
            self.Loop.run_until_complete(tasks)
        self.Loop.close()

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
            self.SendReport('ClientError processing NewOrderId: %s. %s' % (order['NewOrderId'], e))
            raise Return(False)
        except Exception as e:
            self.Logger.error(e)
            self.SendReport('Error processing NewOrderId: %s. %s' % (order['NewOrderId'], e))
            raise Return(False)
        else:
            # self.Logger.info(json.dumps(security, indent=4, cls=DecimalEncoder))
            if response.has_key('Item') and response['Item']['Symbol'] == symbol and response['Item']['TradingEnabled']:
                raise Return(True)
            self.SendReport('Symbol is unknown or not enabled for trading %s' % symbol)
            raise Return(False)

    @asyncio.coroutine
    def validate(self):
        while not self.PendingOrders.empty():
            future = asyncio.Future()
            future.add_done_callback(self.SendOrder)
            order = yield From(self.PendingOrders.get())
            security = yield From(self.validate_symbol(order))

            if security:
                future.set_result('sendme')


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