import logging
import os
from datetime import datetime, timezone, timedelta
import openai

import azure.functions as func
from linebot import (
    LineBotApi, WebhookHandler
)
from linebot.exceptions import (
    InvalidSignatureError
)
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
)
from azure.identity import DefaultAzureCredential
from azure.data.tables import TableServiceClient

# LINE
channel_secret = os.getenv('LINE_CHANNEL_SECRET', None)
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', None)

line_bot_api = LineBotApi(channel_access_token)
handler = WebhookHandler(channel_secret)

# OpenAI
openai.api_type = "azure"
openai.api_base = os.getenv('OPENAI_API_BASE', None)
openai.api_version = "2023-03-15-preview"
openai.api_key = os.getenv('OPENAI_SECRET', None)

system_prompt = u'あなたの名前は「みぃちゃん」です。必ず日本語で返答してください。返答は猫っぽくお願いします。絵文字も付けて。結果は1つだけで良いです。'

# Azure table storage
table_endpoint = os.getenv('TABLE_ENDPOINT', None)
table_name = os.getenv('TABLE_NAME', None)

credential = DefaultAzureCredential()
table_service = TableServiceClient(
    endpoint=table_endpoint, credential=credential)
table_client = table_service.get_table_client(table_name=table_name)


def put_table(user_id, user_message, assistant_message):
    task = {'PartitionKey': user_id, 'RowKey': format(datetime.now(timezone.utc).isoformat(
    )), 'UserMessage': user_message, 'AssistantMessage': assistant_message}
    # Insert an entity into the table
    table_client.create_entity(entity=task)

def get_table(user_id):
    logging.info("start:get_table()")
    current_time = datetime.utcnow()
    past_time = current_time - timedelta(minutes=10)

    logging.info("current time:{}".format(current_time))
    logging.info("past time:{}".format(past_time))

    partition_key = user_id
    filter_condition = "PartitionKey eq '{0}' and Timestamp ge datetime'{1}'".format(
        partition_key, past_time.isoformat())
    # print(filter_condition)
    entities = table_client.query_entities(select=["RowKey","PartitionKey","UserMessage","AssistantMessage"] ,query_filter=filter_condition)
    # entities_sorted = sorted(entities, key=lambda x: x.RowKey)
    entities_sorted = entities
    return_obj = []
    # for hor in entities_sorted:
    #     print('{}'.format(hor.get('UserMessage')))

    # return(return_obj)
    for hor in entities_sorted:
        return_obj.append(
            {
                "role": "user",
                "content": hor.get('UserMessage')
            }
        )
        return_obj.append(
            {
                "role": "assistant",
                "content": hor.get('AssistantMessage')
            }
        )
    logging.info("end:get_table()")
    return (return_obj[-10:])

def chat_with_gpt3(messages):
    # print(messages)
    # GPT-3 での応答を取得するためのリクエストを作成する
    response = openai.ChatCompletion.create(
        engine='test-gpt35',
        messages=messages,
        temperature=0.7,
        max_tokens=800,
        top_p=0.95,
        frequency_penalty=0,
        presence_penalty=0,
        stop=None)

    # GPT-3 からの応答を取得する
    return response.choices[0]["message"]["content"].strip()


# Azure function webhook triggerd module


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    # get x-line-signature header value
    signature = req.headers['x-line-signature']

    body = req.get_body().decode("utf-8")
    logging.info("Request body: " + body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        func.HttpResponse(status_code=400)

    return func.HttpResponse(status_code=200)

# LINE text message handler


@handler.add(MessageEvent, message=TextMessage)
def message_text(event):
    profile = line_bot_api.get_profile(event.source.user_id)

    msg = []
    msg.append(
        {
            "role": "system",
            "content": system_prompt
        }
    )
    res = get_table(profile.user_id)
    for hoe in res:
        msg.append(hoe)
    msg.append(
        {
            "role": "user",
            "content": event.message.text
        }
    )
    res_message=chat_with_gpt3(msg)
    # message_history= get_table(profile.user_id)
    # logging.info("message_history: " + message_history)
    reply_message = '{}'.format(
        res_message)
    # reply_message = '{}さん、{}だよね'.format(
    #     profile.display_name, event.message.text)
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_message)
    )
    logging.info("user_id: " + profile.user_id)

    put_table(profile.user_id, event.message.text, reply_message)
