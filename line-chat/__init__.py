import logging
import os
from datetime import datetime, timedelta

from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, StickerMessage, TextSendMessage
from linebot import LineBotApi, WebhookHandler

from azure.identity import DefaultAzureCredential
from azure.data.tables import TableServiceClient
import azure.functions as func
from azure.keyvault.secrets import SecretClient

import openai

# Azure Credential
azure_credential = DefaultAzureCredential()
azure_token = azure_credential.get_token(
    "https://cognitiveservices.azure.com/.default")

# OpenAI
openai.api_type = 'azure_ad'
openai.api_version = "2023-03-15-preview"

openai.api_base = os.getenv('OPENAI_API_ENDPOINT')
openai.api_key = azure_token.token
openai_engine = os.getenv('OPENAI_ENGINE')

system_prompt = os.getenv('OPENAI_API_SYSTEM_PROMPT',
                          u'あなたの名前は「みぃちゃん」です。必ず日本語で返答してください。返答は猫っぽくお願いします。絵文字も付けて。結果は1つだけで短めでお願いします。')
unknown_sticker_message = os.getenv(
    'UNKNOWN_STICKER_MESSAGE', u'そのスタンプはよくわからないにゃ。ごめんにゃ。')

# Azure table storage
table_endpoint = os.getenv('TABLE_ENDPOINT')
table_name = os.getenv('TABLE_NAME', 'chatlog')

table_service = TableServiceClient(
    endpoint=table_endpoint, credential=azure_credential)
table_client = table_service.create_table_if_not_exists(table_name=table_name)

# Azure Key Vault
key_vault_endpoint = os.getenv('KEY_VAULT_ENDPOINT')
key_vault_client = SecretClient(
    vault_url=key_vault_endpoint, credential=azure_credential)

# LINE
channel_secret = key_vault_client.get_secret('LINESECRET').value
channel_access_token = key_vault_client.get_secret('LINETOKEN').value

line_bot_api = LineBotApi(channel_access_token)
handler = WebhookHandler(channel_secret)


def put_table(user_id, unique_id, user_message, assistant_message):
    """
    Add conversation content to Table Storage
    """
    task = {'PartitionKey': user_id, 'RowKey': unique_id,
            'UserMessage': user_message, 'AssistantMessage': assistant_message}
    # Insert an entity into the table
    table_client.create_entity(entity=task)


def get_table(user_id):
    """
    Retrieve past conversation history from Table Storage
    """
    logging.info("start:get_table()")
    current_time = datetime.utcnow()
    past_time = current_time - timedelta(minutes=10)

    logging.info("current time:{}".format(current_time))
    logging.info("past time:{}".format(past_time))

    partition_key = user_id
    filter_condition = f"PartitionKey eq '{partition_key}' and Timestamp ge datetime'{past_time.isoformat()}'"

    select_col = [
        "RowKey",
        "PartitionKey",
        "UserMessage",
        "AssistantMessage"
    ]
    return_obj = []
    try:
        entities = table_client.query_entities(
            select=select_col, query_filter=filter_condition)
    except Exception as e:
        logging.error(f'Unhandled exception: {e}')
        return return_obj

    for wk in entities:
        return_obj.append(
            {
                "role": "user",
                "content": wk.get('UserMessage')
            }
        )
        return_obj.append(
            {
                "role": "assistant",
                "content": wk.get('AssistantMessage')
            }
        )

    logging.info("end:get_table()")
    return return_obj[-10:]


def chat_with_gpt3(messages):
    """
    Calling process of OpenAI API
    """
    try:
        response = openai.ChatCompletion.create(
            engine=openai_engine,
            messages=messages,
            temperature=0.7,
            max_tokens=800,
            top_p=0.95,
            frequency_penalty=0,
            presence_penalty=0,
            stop=None)
        return response.choices[0]["message"]["content"].strip()

    except (openai.error.AuthenticationError, openai.error.InvalidRequestError) as e:
        logging.error(f"OpenAI API error: {e}")
        return None

    except IndexError:
        logging.error("No response returned from GPT-3.")
        return None


def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    Main processing for a webhook
    """
    logging.info('Python HTTP trigger function processed a request.')

    signature = req.headers['x-line-signature']

    body = req.get_body().decode("utf-8")
    logging.info("Request body: " + body)

    try:
        handler.handle(body, signature)
        return func.HttpResponse(status_code=200)

    except InvalidSignatureError:
        logging.error('Invalid signature')
        return func.HttpResponse(status_code=400)

    except Exception as e:
        logging.error(f'Unhandled exception: {e}')
        return func.HttpResponse(status_code=500)


def reply_message(message_text, user_id, message_id, reply_token):
    """
    Create a response to the received message and send it back to LINE.
    """
    msg = [
        {
            "role": "system",
            "content": system_prompt
        }
    ]

    res = get_table(user_id)

    for wk in res:
        msg.append(wk)

    msg.append(
        {
            "role": "user",
            "content": message_text
        }
    )

    try:
        res_message = chat_with_gpt3(msg)
        reply_message = f'{res_message}'
        put_table(user_id, message_id, message_text, reply_message)

    except Exception as e:
        logging.error(f"Error while calling chat_with_gpt3: {e}")
        reply_message = "Sorry, I couldn't process your message."

    line_bot_api.reply_message(
        reply_token,
        TextSendMessage(text=reply_message)
    )


@handler.add(MessageEvent, message=StickerMessage)
def message_sticker(event):
    """
    Handler for receiving Sticker (Stamp)
    """
    profile = line_bot_api.get_profile(event.source.user_id)
    user_id = profile.user_id
    message_id = event.message.id
    reply_token = event.reply_token

    try:
        # Set the first keyword in the ticker message as the message
        message_text = event.message.keywords[0]
        reply_message(message_text=message_text, user_id=user_id,
                      message_id=message_id, reply_token=reply_token)
    except Exception as e:
        logging.error(f'Sticker: Unhandled exception: {e}')
        # There are no keywords in the sticker message
        line_bot_api.reply_message(
            reply_token,
            TextSendMessage(text=unknown_sticker_message)
        )


@handler.add(MessageEvent, message=TextMessage)
def message_text(event):
    """
    Handler for receiving text message
    """
    profile = line_bot_api.get_profile(event.source.user_id)
    user_id = profile.user_id
    message_id = event.message.id
    message_text = event.message.text
    reply_token = event.reply_token

    reply_message(message_text=message_text, user_id=user_id,
                  message_id=message_id, reply_token=reply_token)
