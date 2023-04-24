//
// parameters
//

// must parameters
@description('LINE token for LINE messaging API')
@secure()
param lineToken string

@description('LINE secret for LINE messaging API')
@secure()
param lineSecret string

// optional parameters
@description('resource deploy region (without OpenAI)')
param location string = resourceGroup().location

@description('resouce base name')
param baseName string = 'chatbot'

@description('chat log store table name for table storage')
param tableName string = 'chatlog'

// Please select the region where your OpenAI Service preview request has been approved.
@description('OpenAI service deploy region')
@allowed([
  'eastus'
  'southcentralus'
  'westeurope'
])
param openAiLocation string = 'eastus'

//
// variables
//
var openAiName = 'openai-${baseName}-${uniqueString(resourceGroup().id)}'
var omsName = 'log-${baseName}'
var appinsName = 'appins-${baseName}'
var planName = 'plan-${baseName}'
var funcName = 'func-${baseName}-${uniqueString(resourceGroup().id)}'
var funcStName = 'st${take(baseName, 9)}${uniqueString(resourceGroup().id)}'
var kvName = 'kv-${baseName}-${uniqueString(resourceGroup().id)}'

var openAiDeploymentsName = 'gpt35'
var openAiModel = {
  format: 'OpenAI'
  name: 'gpt-35-turbo'
  version: '0301'
}

var funcAppSettings = [
  // Azure Functions basic settings
  {
    name: 'FUNCTIONS_WORKER_RUNTIME'
    value: 'python'
  }
  {
    name: 'APPINSIGHTS_INSTRUMENTATIONKEY'
    value: appInsights.properties.InstrumentationKey
  }
  {
    name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
    value: appInsights.properties.ConnectionString
  }
  {
    name: 'FUNCTIONS_EXTENSION_VERSION'
    value: '~4'
  }
  {
    name: 'AzureWebJobsStorage'
    value: 'DefaultEndpointsProtocol=https;AccountName=${funcStorage.name};EndpointSuffix=${environment().suffixes.storage};AccountKey=${funcStorage.listKeys().keys[0].value}'
  }
  {
    name: 'WEBSITE_CONTENTAZUREFILECONNECTIONSTRING'
    value: 'DefaultEndpointsProtocol=https;AccountName=${funcStorage.name};EndpointSuffix=${environment().suffixes.storage};AccountKey=${funcStorage.listKeys().keys[0].value}'
  }
  {
    name: 'WEBSITE_CONTENTSHARE'
    value: '${funcStName}000'
  }
  // ChatBot function settings
  {
    name: 'OPENAI_API_ENDPOINT'
    value: openAi.properties.endpoint
  }
  {
    name: 'OPENAI_ENGINE'
    value: openAiDeploymentsName
  }
  {
    name: 'TABLE_ENDPOINT'
    value: funcStorage.properties.primaryEndpoints.table
  }
  {
    name: 'KEY_VAULT_ENDPOINT'
    value: keyVault.properties.vaultUri
  }
  {
    name: 'TABLE_NAME'
    value: tableName
  }
]

resource openAi 'Microsoft.CognitiveServices/accounts@2022-12-01' = {
  name: openAiName
  location: openAiLocation
  sku: {
    name: 'S0'
  }
  kind: 'OpenAI'
  properties: {
    publicNetworkAccess: 'Enabled'
    customSubDomainName: openAiName
  }
}

resource openAiDeployments 'Microsoft.CognitiveServices/accounts/deployments@2022-12-01' = {
  name: openAiDeploymentsName
  parent: openAi
  properties: {
    model: openAiModel
    scaleSettings: {
      scaleType: 'Standard'
    }
  }
}

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: omsName
  location: location
  properties: {
    retentionInDays: 30
    sku: {
      name: 'PerGB2018'
    }
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appinsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalyticsWorkspace.id
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

resource appServicePlan 'Microsoft.Web/serverfarms@2022-09-01' = {
  name: planName
  location: location
  kind: 'functionapp'
  properties: {
    elasticScaleEnabled: false
    reserved: true
    zoneRedundant: false
  }
  sku: {
    family: 'B'
    tier: 'Basic'
    name: 'B1'
    size: 'B1'
    capacity: 1
  }
}

resource funcStorage 'Microsoft.Storage/storageAccounts@2022-09-01' = {
  name: funcStName
  location: location
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
    allowSharedKeyAccess: true // Since access through shared key is used from Functions, it cannot be set to false.
  }
}

resource functions 'Microsoft.Web/sites@2022-03-01' = {
  name: funcName
  kind: 'functionapp,linux'
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    siteConfig: {
      appSettings: funcAppSettings
      linuxFxVersion: 'PYTHON|3.10'
      functionAppScaleLimit: 200
      numberOfWorkers: 1
      minimumElasticInstanceCount: 0
      alwaysOn: true
    }
    serverFarmId: appServicePlan.id
  }
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-02-01' = {
  name: kvName
  location: location
  properties: {
    tenantId: tenant().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
    publicNetworkAccess: 'Enabled'
    enableSoftDelete: false
  }
}

resource keyVaultSecretsLINETOKEN 'Microsoft.KeyVault/vaults/secrets@2023-02-01' = {
  name: 'LINETOKEN'
  parent: keyVault
  properties: {
    attributes: {
      enabled: true
    }
    value: lineToken
  }
}

resource keyVaultSecretsLINESECRET 'Microsoft.KeyVault/vaults/secrets@2023-02-01' = {
  name: 'LINESECRET'
  parent: keyVault
  properties: {
    attributes: {
      enabled: true
    }
    value: lineSecret
  }
}

resource keyContainerSecretUserRoleDefinition 'Microsoft.Authorization/roleDefinitions@2022-04-01' existing = {
  scope: subscription()
  name: '4633458b-17de-408a-b874-0445c86b69e6'
}

resource keyVaultRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: keyVault
  name: guid(subscription().id, keyVault.id, keyContainerSecretUserRoleDefinition.id)
  properties: {
    roleDefinitionId: keyContainerSecretUserRoleDefinition.id
    principalId: functions.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource storageTableDataContributorRoleDefinition 'Microsoft.Authorization/roleDefinitions@2022-04-01' existing = {
  scope: subscription()
  name: '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'
}

resource storageRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: funcStorage
  name: guid(subscription().id, funcStorage.id, storageTableDataContributorRoleDefinition.id)
  properties: {
    roleDefinitionId: storageTableDataContributorRoleDefinition.id
    principalId: functions.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource cognitiveServicesOpenAiUserRoleDefinition 'Microsoft.Authorization/roleDefinitions@2022-04-01' existing = {
  scope: subscription()
  name: '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
}

resource cognitiveServicesRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: openAi
  name: guid(subscription().id, openAi.id, cognitiveServicesOpenAiUserRoleDefinition.id)
  properties: {
    roleDefinitionId: cognitiveServicesOpenAiUserRoleDefinition.id
    principalId: functions.identity.principalId
    principalType: 'ServicePrincipal'
  }
}
