# azure-line-chatbot

## はじめに

これは、Azure OpenAI serviceをベースとして、ChatGPTと会話するプログラムです。

## 必要なもの

- Azure Subscription
  - 加えてOpenAI Serviceのプレビュー申請でChatGPT 3.5の利用が可能になっていること
- LINE Developerアカウント

## 構成説明

- LINEでフレンド追加されたChatBotがWeb HookにてAzure Functionsを呼び出します
- 本プログラムが実行され以下の処理を行います
  - LINEユーザ識別子を元に過去の会話履歴をAzure Table Storageから取得します
  - 過去の会話履歴(直近10分かつ5件以内)を含め、ChatGPTに送信します
  - ChatGPTから受けた返信メッセージをLINEに返却します
  - 最新のチャットメッセージ(ユーザ、アシスタント)をAzure Table Storageに追加します

![img](/images/infrastructure.png)

## 利用方法

### ツールの事前準備

クライアントPCに以下のツールをインストールしておきます

- Azure CLI  
  https://learn.microsoft.com/ja-jp/cli/azure/install-azure-cli
- Azure Functions Core Tools  
  https://learn.microsoft.com/ja-jp/azure/azure-functions/functions-run-local

### LINE DevelopersにてMessaging APIの準備

以下を控えておく

- チャネルシークレット
- チャネルアクセストークン（長期）

### GitHubリポジトリのclone

```sh
git clone https://github.com/katakura/azure-line-chatbot.git
```

### Azureリソースのデプロイ

```sh
# 環境変数の設定
rg_name="rg-chatbot"
location="japaneast"
openai_location="eastus"
line_token="???"
line_secret="???"

# Azure Subscriptionへログイン
az login

# リソースグループの作成
az group create -g $rg_name -l $location

# リソースデプロイ
az deployment group create -g $rg_name --template-file templates/deploy.bicep --parameters location=$location openAiLocation=$openai_location lineToken=$line_token lineSecret=$line_secret
```

### Functionsアプリのデプロイ

```sh
# 作成されたFunctiosnのリソース名取得
func_name=$(az functionapp list -g $rg_name --query "[0].name" -o tsv)

# アプリデプロイ
func azure functionapp publish $func_name --python
```

### LINE messaging APIのWeb Hook登録

```sh
func azure functionapp list-functions $func_name --show-keys
```

```text:実行例
$ func azure functionapp list-functions $func_name --show-keys

Functions in func-chatbot-xxxxxxxxxxxxx:
    line-chat - [httpTrigger]
        Invoke url: https://func-chatbot-xxxxxxxxxxxxx.azurewebsites.net/api/line-chat?code=xxx...xxx==
```

Invoke urlに表示されている内容をLINE DevelopersのWebhook URLに設定する

## 環境変数

|環境変数名|説明|例 or デフォルト値|
|--|--|--|
OPENAI_API_ENDPOINT|Azure OpenAI Serviceのエンドポイント|https://\<YourResourceName\>.openai.azure.com/
OPENAI_ENGINE|Azure OpenAI Serviceのモデルデプロイ名(gpt-35-turbo)|line-gpt35
TABLE_ENDPOINT|Azure Table Storageのエンドポイント|https://\<YourResourceName\>.table.core.windows.net
TABLE_NAME|Chat Logを保存するTable名|chatlog
KEY_VAULT_ENDPOINT|Key Vaultのエンドポイント|https://\<YoutResourceName\>.vault.azure.net/
OPENAI_API_SYSTEM_PROMPT|ChatGPTのSystem Prompt|あなたの名前は「みぃちゃん」です。必ず日本語で返答してください。返答は猫っぽくお願いします。絵文字も付けて。結果は1つだけで短めでお願いします。
UNKNOWN_STICKER_MESSAGE|スタンプを受けて返信に困ったときのメッセージ|そのスタンプはよくわからないにゃ。ごめんにゃ。

## Key Vault Secret

|シークレット名|説明|例|
|--|--|--|
LINESECRET|LINEチャンネルシークレット|xxxx...(32 Bytes)
LINETOKEN|LINEチャンネルアクセストークン|xxxx...xxx=
