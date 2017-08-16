from __future__ import print_function # Python 2/3 compatibility
import boto3
import json
import uuid
import time
import decimal

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

orders_table = dynamodb.Table('Orders')


NewOrderId = str(uuid.uuid4().hex) #int(order['NewOrderId'])
TransactionTime = str(time.time()) #order['TransactionTime']
ClientOrderId = 0
Status = 'PENDING'
Details = {
        "Side" : "BUY",
        "ProductType" : "FUTURE",
        "Symbol" : "6E",
        "Maturity" : "201709",
        "Quantity" : 1,
        "OrdType" : "MARKET",
        "Price" : 0
    }

print("Adding order:", NewOrderId, TransactionTime)

orders_table.put_item(
           Item={
               'NewOrderId': NewOrderId,
               'TransactionTime': TransactionTime,
               'ClientOrderId': ClientOrderId,
               'Status':Status,
               'Details':Details
            }
        )
