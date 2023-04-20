"""
This program is a bot that integrates LINE Messaging API with OpenAI Chat API where a Japanese AI assistant named 'Mii-chan' responds to the user's text message. This program also includes functionality to store and aggregate the user's conversation history using Azure Table Storage and Azure Functions.

Usage:
1. Create a Messaging API account from the LINE Developers console and obtain your Channel Access Token and Channel Secret.
2. Add a Table Storage account to your subscription from the Azure Portal and get the endpoint URL and table name.
3. Also get the authentication information for the OpenAI API. Set them as environment variables and run this program.
4. Create a Functions app using Azure Portal or Azure CLI, and upload this code.
5. Add the necessary keys and values ​​to the application settings in the Functions app settings.
6. Add the LINE account as a friend, send a text message, and receive a reply!
7. Check the status of the processing in "Function Logs" within the Functions app.

Note:
This program contains an HTTP trigger, which means that the system automatically enables the function when it is called for the first time.
If you want to access this function on your own simple website before hosting it, you may need to modify the function slightly.
"""

import logging
import os
from datetime import datetime, timezone, timedelta
import openai
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from azure.identity import DefaultAzureCredential
from azure.data.tables import TableServiceClient
import azure.functions as func
from linebot import LineBotApi, WebhookHandler

# LINE
channel_secret = os.getenv('LINE_CHANNEL_SECRET')
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')

line_bot_api = LineBotApi(channel_access_token)
handler = WebhookHandler(channel_secret)

# OpenAI
openai.api_type = os.getenv('OPENAI_API_TYPE', 'azure')
openai.api_base = os.getenv('OPENAI_API_BASE', None)
openai.api_version = "2023-03-15-preview"
openai.api_key = os.getenv('OPENAI_SECRET', None)
openai_engine = os.getenv('OPENAI_ENGINE', 'test-gpt35')

system_prompt = u'あなたの名前は「みぃちゃん」です。必ず日本語で返答してください。返答は猫っぽくお願いします。絵文字も付けて。結果は1つだけで短めでお願いします。'

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
    filter_condition = f"PartitionKey eq '{partition_key}' and Timestamp ge datetime'{past_time.isoformat()}'"

    select_col = ["RowKey", "PartitionKey", "UserMessage", "AssistantMessage"]
    entities = table_client.query_entities(
        select=select_col, query_filter=filter_condition)
    return_obj = []
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


@handler.add(MessageEvent, message=TextMessage)
def message_text(event):
    profile = line_bot_api.get_profile(event.source.user_id)

    msg = [
        {
            "role": "system",
            "content": system_prompt
        }
    ]

    res = get_table(profile.user_id)

    for wk in res:
        msg.append(wk)

    msg.append(
        {
            "role": "user",
            "content": event.message.text
        }
    )

    try:
        res_message = chat_with_gpt3(msg)

        # ここは将来返信メッセージを加工する時のためにこのようにしている
        reply_message = f'{res_message}'

        put_table(profile.user_id, event.message.text, reply_message)

    except Exception as e:
        logging.error(f"Error while calling chat_with_gpt3: {e}")
        reply_message = "Sorry, I couldn't process your message."

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_message)
    )

    logging.info("user_id: " + profile.user_id)
