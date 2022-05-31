import logging

logging.basicConfig(
    level = logging.INFO,
    format = "{asctime} {levelname:<8} {message}",
    style= '{',
    filename = 'fast_api_als.log',
    filemode = 'a'
)
try:
    import uuid
    import time
    import boto3
    import botocore
    from boto3.dynamodb.conditions import Key
    import dynamodbgeo
    from datetime import datetime, timedelta

    from fast_api_als import constants
    from fast_api_als.utils.boto3_utils import get_boto3_session
except ImportError as e:
    logging.error("Import Error occured", exc_info=True)

"""
    the self.table.some_operation(), return a json object and you can find the http code of the executed operation as this :
    res['ResponseMetadata']['HTTPStatusCode']
    
    write a commong function that logs this response code with appropriate context data
"""
def loggerFunction(res, context):
    rec_sta_code = res['ResponseMetadata']['HTTPStatusCode']
    logging.info("Context: {context_pla}, HTTP Code Received: {code_pla}".format(context_pla = context, code_pla = rec_sta_code))

class DBHelper:
    def __init__(self, session: boto3.session.Session):
        self.session = session
        self.ddb_resource = session.resource('dynamodb', config=botocore.client.Config(max_pool_connections=99))
        self.table = self.ddb_resource.Table(constants.DB_TABLE_NAME)
        self.geo_data_manager = self.get_geo_data_manager()
        self.dealer_table = self.ddb_resource.Table(constants.DEALER_DB_TABLE)
        self.get_api_key_author("Initialize_Connection")

    def get_geo_data_manager(self):
        config = dynamodbgeo.GeoDataManagerConfiguration(self.session.client('dynamodb', config=botocore.client.Config(max_pool_connections=99)), constants.DEALER_DB_TABLE)
        geo_data_manager = dynamodbgeo.GeoDataManager(config)
        return geo_data_manager

    def insert_lead(self, lead_hash: str, lead_provider: str, response: str):
        item = {
            'pk': f'LEAD#{lead_hash}',
            'sk': lead_provider,
            'response': response,
            'ttl': datetime.fromtimestamp(int(time.time())) + timedelta(days=constants.LEAD_ITEM_TTL)
        }
        res = self.table.put_item(Item=item)
        loggerFunction(res, "Inserting Lead in table")
    def insert_oem_lead(self, uuid: str, make: str, model: str, date: str, email: str, phone: str, last_name: str,
                        timestamp: str, make_model_filter_status: str, lead_hash: str, dealer: str, provider: str,
                        postalcode: str):

        item = {
            'pk': f"{make}#{uuid}",
            'sk': f"{make}#{model}",
            'gsipk': f"{make}#{date}",
            'gsisk': "0#0",
            'make': make,
            'model': model,
            'email': email,
            'phone': phone,
            'last_name': last_name,
            'timestamp': timestamp,
            'conversion': "0",
            "make_model_filter_status": make_model_filter_status,
            "lead_hash": lead_hash,
            "dealer": dealer,
            "3pl": provider,
            "postalcode": postalcode,
            'ttl': datetime.fromtimestamp(int(time.time())) + timedelta(days=constants.OEM_ITEM_TTL)
        }

        res = self.table.put_item(Item=item)
        loggerFunction(res, "inserting OEM Lead in table")
    def check_duplicate_api_call(self, lead_hash: str, lead_provider: str):
        res = self.table.get_item(
            Key={
                'pk': f"LEAD#{lead_hash}",
                'sk': lead_provider
            }
        )
        loggerFunction(res, "Getting item from table for checking for dup API call")
        item = res.get('Item')
        if not item:
            logger.info("No Duplicate API Call")
            return {
                "Duplicate_Api_Call": {
                    "status": False,
                    "response": "No_Duplicate_Api_Call"
                }
            }
        else:
            logger.warning("Duplicate API Call")
            return {
                "Duplicate_Api_Call": {
                    "status": True,
                    "response": item['response']
                }
            }

    def accepted_lead_not_sent_for_oem(self, oem: str, date: str):
        res = self.table.query(
            IndexName='gsi-index',
            KeyConditionExpression=Key('gsipk').eq(f"{oem}#{date}")
                                   & Key('gsisk').begins_with("0#0")
        )
        loggerFunction(res, "Querying table for accepted lead not sent for OEM")
        return res.get('Items', [])

    def update_lead_sent_status(self, uuid: str, oem: str, make: str, model: str):
        res = self.table.get_item(
            Key={
                'pk': f"{uuid}#{oem}"
            }
        )
        loggerFunction(res, "Getting item from table for updating lead sent status")
        item = res['Item']
        if not item:
            return False
        item['gsisk'] = "1#0"
        res = self.table.put_item(Item=item)
        loggerFunction(res, "Putting item in table after updating gsisk")
        return True

    def get_make_model_filter_status(self, oem: str):
        res = self.table.get_item(
            Key={
                'pk': f"OEM#{oem}",
                'sk': 'METADATA'
            }
        )
        loggerFunction(res, "Getting item from table for making model filter status")
        if res['Item'].get('settings', {}).get('make_model', "False") == 'True':
            return True
        return False

    def verify_api_key(self, apikey: str):
        res = self.table.query(
            IndexName='gsi-index',
            KeyConditionExpression=Key('gsipk').eq(apikey)
        )
        loggerFunction(res, "Querying the table for verification of API Key")
        item = res.get('Items', [])
        if len(item) == 0:
            return False
        return True

    def get_auth_key(self, username: str):
        res = self.table.query(
            KeyConditionExpression=Key('pk').eq(username)
        )
        loggerFunction(res, "Querying the table for getting auth key")
        item = res['Items']
        if len(item) == 0:
            return None
        return item[0]['sk']

    def set_auth_key(self, username: str):
        self.delete_3PL(username)
        apikey = str(uuid.uuid4())
        res = self.table.put_item(
            Item={
                'pk': username,
                'sk': apikey,
                'gsipk': apikey
            }
        )
        loggerFunction(res, "Putting item in table after setting auth key")
        return apikey

    def register_3PL(self, username: str):
        res = self.table.query(
            KeyConditionExpression=Key('pk').eq(username)
        )
        loggerFunction(res, "Querying the table for registration of 3PL")
        item = res.get('Items', [])
        if len(item):
            return None
        return self.set_auth_key(username)

    def set_make_model_oem(self, oem: str, make_model: str):
        item = self.fetch_oem_data(oem)
        item['settings']['make_model'] = make_model
        res = self.table.put_item(Item=item)
        loggerFunction(res, "Putting item in table after setting make model oem")

    def fetch_oem_data(self, oem, parallel=False):
        res = self.table.get_item(
            Key={
                'pk': f"OEM#{oem}",
                'sk': "METADATA"
            }
        )
        loggerFunction(res, "Getting OEM data from the table")
        if 'Item' not in res:
            return {}
        if parallel:
            return {
                "fetch_oem_data": res['Item']
            }
        else:
            return res['Item']

    def create_new_oem(self, oem: str, make_model: str, threshold: str):
        res = self.table.put_item(
            Item={
                'pk': f"OEM#{oem}",
                'sk': "METADATA",
                'settings': {
                    'make_model': make_model
                },
                'threshold': threshold
            }
        )
        loggerFunction(res, "Putting item in table after creating new OEM")

    def delete_oem(self, oem: str):
        res = self.table.delete_item(
            Key={
                'pk': f"OEM#{oem}",
                'sk': "METADATA"
            }
        )
        loggerFunction(res, "Deleting OEM from table")

    def delete_3PL(self, username: str):
        authkey = self.get_auth_key(username)
        if authkey:
            res = self.table.delete_item(
                Key={
                    'pk': username,
                    'sk': authkey
                }
            )
        loggerFunction(res, "Deleting 3PL from table")

    def set_oem_threshold(self, oem: str, threshold: str):
        item = self.fetch_oem_data(oem)
        if item == {}:
            return {
                "error": f"OEM {oem} not found"
            }
        item['threshold'] = threshold
        res = self.table.put_item(Item=item)
        return {
            "success": f"OEM {oem} threshold set to {threshold}"
        }
        loggerFunction(res, "Putting item in table after setting OEM threshold")

    def fetch_nearest_dealer(self, oem: str, lat: str, lon: str):
        query_input = {
            "FilterExpression": "oem = :val1",
            "ExpressionAttributeValues": {
                ":val1": {"S": oem},
            }
        }
        res = self.geo_data_manager.queryRadius(
            dynamodbgeo.QueryRadiusRequest(
                dynamodbgeo.GeoPoint(lat, lon),
                50000,  # radius = 50km
                query_input,
                sort=True
            )
        )
        if len(res) == 0:
            return {}
        res = res[0]
        dealer = {
            'id': {
                '#text': res['dealerCode']['S']
            },
            'vendorname': res['dealerName']['S'],
            'contact': {
                'address': {
                    'postalcode': res['dealerZip']['S']
                }
            }
        }
        return dealer

    def get_dealer_data(self, dealer_code: str, oem: str):
        if not dealer_code:
            return {}
        res = self.dealer_table.query(
            IndexName='dealercode-index',
            KeyConditionExpression=Key('dealerCode').eq(dealer_code) & Key('oem').eq(oem)
        )
        res = res['Items']
        if len(res) == 0:
            return {}
        res = res[0]
        return {
            'postalcode': res['dealerZip'],
            'rating': res['Rating'],
            'recommended': res['Recommended'],
            'reviews': res['LifeTimeReviews']
        }

    def insert_customer_lead(self, uuid: str, email: str, phone: str, last_name: str, make: str, model: str):
        item = {
            'pk': uuid,
            'sk': 'CUSTOMER_LEAD',
            'gsipk': email,
            'gsisk': uuid,
            'gsipk1': f"{phone}#{last_name}",
            'gsisk1': uuid,
            'oem': make,
            'make': make,
            'model': model,
            'ttl': datetime.fromtimestamp(int(time.time())) + timedelta(days=constants.OEM_ITEM_TTL)
        }
        res = self.table.put_item(Item=item)
        loggerFunction(res, "Inserting customer lead in the table")

    def lead_exists(self, uuid: str, make: str, model: str):
        lead_exist = False
        if self.get_make_model_filter_status(make):
            res = self.table.query(
                KeyConditionExpression=Key('pk').eq(f"{make}#{uuid}") & Key('sk').eq(f"{make}#{model}")
            )
            if len(res['Items']):
                lead_exist = True
        else:
            res = self.table.query(
                KeyConditionExpression=Key('pk').eq(f"{make}#{uuid}")
            )
            loggerFunction(res, "Querying the table for lead")

            if len(res['Items']):
                lead_exist = True
        return lead_exist

    def check_duplicate_lead(self, email: str, phone: str, last_name: str, make: str, model: str):
        email_attached_leads = self.table.query(
            IndexName='gsi-index',
            KeyConditionExpression=Key('gsipk').eq(email)
        )
        phone_attached_leads = self.table.query(
            IndexName='gsi1-index',
            KeyConditionExpression=Key('gsipk1').eq(f"{phone}#{last_name}")
        )
        customer_leads = email_attached_leads['Items'] + phone_attached_leads['Items']

        for item in customer_leads:
            if self.lead_exists(item['pk'], make, model):
                return {"Duplicate_Lead": True}
        return {"Duplicate_Lead": False}

    def get_api_key_author(self, apikey):
        res = self.table.query(
            IndexName='gsi-index',
            KeyConditionExpression=Key('gsipk').eq(apikey)
        )
        loggerFunction(res, "Querying the table for getting API key author")
        item = res.get('Items', [])
        if len(item) == 0:
            return "unknown"
        return item[0].get("pk", "unknown")

    def update_lead_conversion(self, lead_uuid: str, oem: str, converted: int):
        res = self.table.query(
            KeyConditionExpression=Key('pk').eq(f"{oem}#{lead_uuid}")
        )
        loggerFunction(res, "Querying the table for updating lead conversion")
        items = res.get('Items')
        if len(items) == 0:
            return False, {}
        item = items[0]
        item['oem_responded'] = 1
        item['conversion'] = converted
        item['gsisk'] = f"1#{converted}"
        res = self.table.put_item(Item=item)
        return True, item


def verify_response(response_code):
    if not response_code == 200:
        pass
    else:
        pass


session = get_boto3_session()
db_helper_session = DBHelper(session)
