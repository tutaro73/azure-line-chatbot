import logging
import os
import base64
import openai
import requests

from datetime import datetime, timedelta

from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, StickerMessage, TextSendMessage, ImageMessage
from linebot import LineBotApi, WebhookHandler

from azure.identity import DefaultAzureCredential
from azure.data.tables import TableServiceClient
import azure.functions as func
from azure.keyvault.secrets import SecretClient

class TokenManager:
    def __init__(self):
        self.credential = DefaultAzureCredential()
        self.token = None
        self.expiry = datetime.utcnow()

    def get_token(self, url='https://management.azure.com/.default'):
        if not self.token or self.expiry <= datetime.utcnow() + timedelta(minutes=5):
            token_response = self.credential.get_token(url)
            self.token = token_response.token
            self.expiry = datetime.utcfromtimestamp(token_response.expires_on)
        return self.token

token_manager = TokenManager()
token_manager.__init__()
azure_credential = DefaultAzureCredential()

# OpenAI
openai.api_key = os.getenv('API_KEY')
openai_model = "gpt-4-1106-preview"
openai_vision_model = "gpt-4-vision-preview"

system_prompt = os.getenv('OPENAI_API_SYSTEM_PROMPT',
                          u'あなたの名前は「らいざっぴ」です。食事のカロリー計算をしてダイエットの手助けをします。必ず日本語で簡潔に返答してください。親しみやすい口調で話し、語尾に「ッピ」をつけてください。')
unknown_sticker_message = os.getenv(
    'UNKNOWN_STICKER_MESSAGE', u'そのスタンプはよくわからないッピ。ごめんッピ。')

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


def chat_with_gpt4(messages):
    """
    Calling process of OpenAI API
    """
    logging.info("start:get_token()\n")
    openai.api_key = os.getenv('API_KEY')
    logging.info("APIKEY")#debug
    logging.info(openai.api_key)#debug
    logging.info("messages")#debug
    logging.info(messages)#debug
    logging.info("end:get_token()\n")
    try:
        response = openai.chat.completions.create(
            model=openai_model,
           messages=messages
           )
        #responsev = "テストメッセージ"
        logging.info(response)#debug
        logging.info(type(response))#debug
        #return responsev
        return response.choices[0].message.content

    except IndexError:
        logging.error("No response returned from GPT-4-turbo.")
        return None

def chat_with_gpt4_vision(messages):
    """
    Calling process of OpenAI vision API
    """
    logging.info("start:get_token()\n")
    openai.api_key = os.getenv('API_KEY')
    logging.info("messages")#debug
    logging.info(messages)#debug
    logging.info("end:get_token()\n")
    
    try:
        response = openai.chat.completions.create(
            model="gpt-4-vision-preview",
            messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "あなたの名前は「らいざっぴ」です。食事のカロリー計算をしてダイエットの手助けをします。必ず日本語で簡潔に返答してください。親しみやすい口調で話し、語尾に「ッピ」をつけてください。画像を説明してください。また、食べ物の場合は、カロリー計算もして簡潔に提示してください。"},
                {
                    "type": "image_url",
                    "image_url":  {"url": f"data:image/jpeg;base64,{messages}"},
                },
            ],
        }
    ],
    max_tokens=300,
    )
        logging.info(response)
        return response.choices[0].message.content


    except IndexError:
        logging.error("No response returned from GPT-4-vision.")
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
    
    logging.info(msg)#debug

    try:
        res_message = chat_with_gpt4(msg)
        reply_message = f'{res_message}'
        logging.info(reply_message) #debug
        put_table(user_id, message_id, message_text, reply_message)

    except Exception as e:
        logging.error(f"Error while calling chat_with_gpt4: {e}")
        reply_message = "すみません、メッセージを処理できませんでした"

    line_bot_api.reply_message(
        reply_token,
        TextSendMessage(text=reply_message)
    )

def handle_image_message(image_data, user_id, message_id, reply_token):
    """
    Process the received image and create a response.
    """
    
    try:
        # 画像データを処理して説明を取得
        image_description = chat_with_gpt4_vision(image_data)
        logging.info("ハンドル関数に戻ってきた")#debug
        put_table(user_id, message_id, "[Image data]", image_description)
        reply_vision_message = f'{image_description}'
        
    except Exception as e:
        logging.error(f"Error while processing image: {e}")
        return "申し訳ありませんが、画像を分析できませんでした。"
    
    line_bot_api.reply_message(
        reply_token,
        TextSendMessage(text=reply_vision_message)
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

    logging.info(message_text) #debug

    reply_message(message_text=message_text, user_id=user_id,
                  message_id=message_id, reply_token=reply_token)

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    profile = line_bot_api.get_profile(event.source.user_id)
    user_id = profile.user_id
    message_id = event.message.id
    reply_token = event.reply_token

    logging.info("image_file") #debug

    # message_idから画像のバイナリデータを取得
    image_data = line_bot_api.get_message_content(message_id)
    
    logging.info("image_dataのデータ型")
    logging.info(type(image_data))


    # 画像データをBase64エンコードする
    encoded_image = base64.b64encode(image_data.content).decode("utf-8")
    
    logging.info("encoded_imageのデータ型")
    logging.info(type(encoded_image))

    handle_image_message(image_data=encoded_image, user_id=user_id,
                  message_id=message_id, reply_token=reply_token)

