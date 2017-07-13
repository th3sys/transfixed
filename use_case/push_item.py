from __future__ import print_function # Python 2/3 compatibility
import boto3
import json
import uuid
import time
import decimal

#dynamodb = boto3.resource('dynamodb', region_name='us-east-1', endpoint_url="http://localhost:8000")
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

table = dynamodb.Table('Orders')

with open("orders.json") as json_file:
    orders = json.load(json_file, parse_float = decimal.Decimal)
    for order in orders:
        NewOrderId = str(uuid.uuid4().hex) #int(order['NewOrderId'])
        TransactionTime = str(time.time()) #order['TransactionTime']
        ClientOrderId = int(order['ClientOrderId'])
        Status = order['Status']
        Details = order['Details']

        print("Adding order:", NewOrderId, TransactionTime)

        table.put_item(
           Item={
               'NewOrderId': NewOrderId,
               'TransactionTime': TransactionTime,
               'ClientOrderId': ClientOrderId,
               'Status':Status,
               'Details':Details
            }
        )