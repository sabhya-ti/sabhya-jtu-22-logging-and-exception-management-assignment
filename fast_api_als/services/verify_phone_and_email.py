import time
import httpx
import asyncio
import logging

logging.basicConfig(
    level = logging.INFO,
    format = "{asctime} {levelname:<8} {message}",
    style= '{',
    filename = 'fast_api_als.log',
    filemode = 'a'
)
try:

    from fast_api_als.constants import (
        ALS_DATA_TOOL_EMAIL_VERIFY_METHOD,
        ALS_DATA_TOOL_PHONE_VERIFY_METHOD,
        ALS_DATA_TOOL_SERVICE_URL,
        ALS_DATA_TOOL_REQUEST_KEY)
except ImportError as e:
    logging.error("Import Error occurred:", exc_info=True)

"""
How can you write log to understand what's happening in the code?
You also trying to undderstand the execution time factor.
"""

async def call_validation_service(url: str, topic: str, value: str, data: dict) -> None:  # 2
    if value == '':
        logging.info("Empty string passed for value for call_validation_service")
        return
    async with httpx.AsyncClient() as client: # 3
        logging.info("Awaiting URL response from clinet for phone/email validation")
        response = await client.get(url)
        logging.info("Awaiting URL response from clinet for phone/email validation")

    r = response.json()
    data[topic] = r
    

async def verify_phone_and_email(email: str, phone_number: str) -> bool:
    email_validation_url = '{}?Method={}&RequestKey={}&EmailAddress={}&OutputFormat=json'.format(
        ALS_DATA_TOOL_SERVICE_URL,
        ALS_DATA_TOOL_EMAIL_VERIFY_METHOD,
        ALS_DATA_TOOL_REQUEST_KEY,
        email)
    phone_validation_url = '{}?Method={}&RequestKey={}&PhoneNumber={}&OutputFormat=json'.format(
        ALS_DATA_TOOL_SERVICE_URL,
        ALS_DATA_TOOL_PHONE_VERIFY_METHOD,
        ALS_DATA_TOOL_REQUEST_KEY,
        phone_number)
    email_valid = False
    phone_valid = False
    data = {}

    await asyncio.gather(
        call_validation_service(email_validation_url, "email", email, data),
        call_validation_service(phone_validation_url, "phone", phone_number, data),
    )
    if "email" in data:
        if data["email"]["DtResponse"]["Result"][0]["StatusCode"] in ("0", "1"):
            logging.info("A valid Email has been received")
            email_valid = True
    if "phone" in data:
        if data["phone"]["DtResponse"]["Result"][0]["IsValid"] == "True":
            logging.info("A valid phone number has been received")
            phone_valid = True
    return email_valid | phone_valid
