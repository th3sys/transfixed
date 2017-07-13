import logging
import json
import decimal


def main(event, context):
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s')

    logger.info('event %s' % event)
    logger.info('context %s' % context)

    response = {'State':'OK'}
    try:
        logger.info('Start fix trader')
        for record in event['Records']:
            if record['eventName'] == 'INSERT':
                logger.info('New Order received NewOrderId: %s', record['dynamodb']['Keys']['NewOrderId'])
            else:
                logger.info('Not INSERT event is ignored')
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