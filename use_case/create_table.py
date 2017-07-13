from __future__ import print_function # Python 2/3 compatibility
import boto3

#client = boto3.resource('dynamodb', region_name='us-east-1', endpoint_url="http://localhost:8000")
client = boto3.client('dynamodb', region_name='us-east-1')

try:
    if 'Orders' in client.list_tables()['TableNames']:
        client.delete_table(TableName='Orders')
        waiter = client.get_waiter('table_not_exists')
        waiter.wait(TableName='Orders')
        print ("table Orders deleted")

except Exception as e:
    print(e)

table = client.create_table(
    TableName='Orders',
    KeySchema=[
        {
            'AttributeName': 'NewOrderId',
            'KeyType': 'HASH'  #Partition key
        },
        {
            'AttributeName': 'TransactionTime',
            'KeyType': 'RANGE'  #Sort key
        }
    ],
    AttributeDefinitions=[
        {
            'AttributeName': 'NewOrderId',
            'AttributeType': 'S'
        },
        {
            'AttributeName': 'TransactionTime',
            'AttributeType': 'S'
        },

    ],
    ProvisionedThroughput={
        'ReadCapacityUnits': 10,
        'WriteCapacityUnits': 10
    }
)

waiter = client.get_waiter('table_exists')
waiter.wait(TableName='Orders')
print("table Orders created")
print("Table status:", table)
