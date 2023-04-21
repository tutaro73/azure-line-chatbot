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

## 構成方法

### Line Developers

### Azure

## 環境変数

|環境変数名|説明|例|
|--|--|--|
OPENAI_API_ENDPOINT|Azure OpenAI Serviceのエンドポイント|https://\<YourResourceName\>.openai.azure.com/
OPENAI_ENGINE|Azure OpenAI Serviceのモデルデプロイ名(gpt-35-turbo)|line-gpt35
TABLE_ENDPOINT|Azure Table Storageのエンドポイント|https://\<YourResourceName\>.table.core.windows.net
TABLE_NAME|Chat Logを保存するTable名|chatlog
KEY_VAULT_ENDPOINT|Key Vaultのエンドポイント|https://\<YoutResourceName\>.vault.azure.net/

## Key Vault Secret

|シークレット名|説明|例|
|--|--|--|
LINESECRET|LINEチャンネルシークレット|xxxx...(32 Bytes)
LINETOKEN|LINEチャンネルアクセストークン|xxxx...xxx=



## 利用方法

