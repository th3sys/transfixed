import logging
import json
import datetime
import decimal
import trollius as asyncio
from trollius import Return, From

class LambdaTrader:
    def __init__(self, logger):
        self.Logger = logger
        self.Loop = asyncio.get_event_loop()
        self.PendingOrders = asyncio.Queue(loop=self.Loop)

    def Run(self):
        if not self.PendingOrders.empty():
            tasks = [self.validate_symbol()]
            self.Loop.run_until_complete(asyncio.wait(tasks))
        self.Loop.close()

    @asyncio.coroutine
    def validate_symbol(self):
        while not self.PendingOrders.empty():
            queue_item = yield From(self.PendingOrders.get())
            self.Logger.info(queue_item)

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
                trader.PendingOrders.put_nowait(record)
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