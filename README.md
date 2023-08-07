# azure-line-chatbot

## Introduction

This is a program to chat with ChatGPT based on Azure OpenAI service.

## Requirements

- Azure Subscription
  - In addition, the use of ChatGPT 3.5 should be possible with the preview application of OpenAI Service.
- LINE Developer Account

## Configuration details

- The ChatBot added in LINE calls Azure Functions via Webhook.
- This program executes the following processes:
  - Retrieve past conversation history from Azure Table Storage based on LINE user identifier.
  - Send past conversation history (up to 5 items within the last 10 minutes) to ChatGPT.
  - Returns the reply message received from ChatGPT to LINE.
  - Add the latest chat message (user and assistant) to Azure Table Storage.

![img](/images/infrastructure.png)

## Usage

### Preparing Tools

Install the following tools on your client PC:

- Azure CLI  
  https://learn.microsoft.com/en-us/cli/azure/install-azure-cli
- Azure Functions Core Tools  
  https://learn.microsoft.com/en-us/azure/azure-functions/functions-run-local

### Preparing Messaging API in LINE Developers

Note the following:

- Channel secret
- Channel access token (long-term)

### Clone GitHub Repository

```sh
git clone https://github.com/katakura/azure-line-chatbot.git
```

### Deploy Azure Resources

```sh
# Set environment variables
rg_name="rg-chatbot"
location="japaneast"
openai_location="eastus"
line_token="???"
line_secret="???"

# Login to Azure Subscription
az login

# Create resource group
az group create -g $rg_name -l $location

# Deploy resources
az deployment group create -g $rg_name --template-file templates/deploy.bicep --parameters location=$location openAiLocation=$openai_location lineToken=$line_token lineSecret=$line_secret
```

### Deploy Functions Application

```sh
# Get the name of the created Function's resource
func_name=$(az functionapp list -g $rg_name --query "[0].name" -o tsv)

# Deploy the app
func azure functionapp publish $func_name --python
```

### Register Web Hook for LINE messaging API

```sh
func azure functionapp list-functions $func_name --show-keys
```

```text:Execution example
$ func azure functionapp list-functions $func_name --show-keys

Functions in func-chatbot-xxxxxxxxxxxxx:
    line-chat - [httpTrigger]
        Invoke url: https://func-chatbot-xxxxxxxxxxxxx.azurewebsites.net/api/line-chat?code=xxx...xxx==
```

Set the contents displayed in the Invoke URL to the Webhook URL of LINE Developers

## Environment variables

|Environment variable name|Description|Example or default value|
|--|--|--|
OPENAI_API_ENDPOINT|Azure OpenAI Service endpoint|https://\<YourResourceName\>.openai.azure.com/
OPENAI_ENGINE|Model deployment name of Azure OpenAI Service (gpt-35-turbo)|line-gpt35
TABLE_ENDPOINT|Azure Table Storage endpoint|https://\<YourResourceName\>.table.core.windows.net
TABLE_NAME|Table name to save chat logs|chatlog
KEY_VAULT_ENDPOINT|Key Vault endpoint|https://\<YoutResourceName\>.vault.azure.net/
OPENAI_API_SYSTEM_PROMPT|ChatGPTのSystem Prompt|あなたの名前は「みぃちゃん」です。必ず日本語で返答してください。返答は猫っぽくお願いします。絵文字も付けて。結果は1つだけで短めでお願いします。
UNKNOWN_STICKER_MESSAGE|Message for when you have trouble replying after receiving a stamp|そのスタンプはよくわからないにゃ。ごめんにゃ。

## Key Vault Secret

|Secret name|Description|Example|
|--|--|--|
LINESECRET|LINE Channel Secret|xxxx...(32 Bytes)
LINETOKEN|LINE Channel Access Token|xxxx...xxx=
