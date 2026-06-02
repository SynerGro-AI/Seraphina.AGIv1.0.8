// Azure Trusted Signing - SynerGroSigning account
// DR / redeployment template capturing the current production setup.
//
// Deploy with:
//   az deployment group create \
//     --resource-group rg-synergro-signing \
//     --template-file infra/signing.bicep \
//     --parameters accountName=SynerGroSigning
//
// Notes:
// - Identity Validation is portal-only (cannot be provisioned via Bicep/ARM as of 2026-05-15-preview API).
// - Certificate Profiles depend on a completed Identity Validation; create via portal or post-deployment script.
// - This template is idempotent for the account resource itself.

targetScope = 'resourceGroup'

@description('Name of the Trusted Signing (Code Signing) account.')
param accountName string = 'SynerGroSigning'

@description('Azure region. Trusted Signing is available in: eastus, westcentralus, westus2, westus3, northeurope, westeurope.')
@allowed([
  'eastus'
  'westcentralus'
  'westus2'
  'westus3'
  'northeurope'
  'westeurope'
])
param location string = 'eastus'

@description('SKU tier. Basic = $9.99/mo, 5,000 signatures/day. Premium = higher limits.')
@allowed([
  'Basic'
  'Premium'
])
param skuName string = 'Basic'

resource codeSigningAccount 'Microsoft.CodeSigning/codeSigningAccounts@2024-09-30-preview' = {
  name: accountName
  location: location
  properties: {
    sku: {
      name: skuName
    }
  }
}

// Example certificate profile (commented — requires completed Identity Validation).
// Uncomment and set identityValidationId after validation is approved.
//
// resource certProfile 'Microsoft.CodeSigning/codeSigningAccounts/certificateProfiles@2024-09-30-preview' = {
//   parent: codeSigningAccount
//   name: 'synergroai-prod'
//   properties: {
//     profileType: 'PublicTrust'
//     identityValidationId: '<GUID from completed identity validation>'
//     includeStreetAddress: false
//     includePostalCode: true
//   }
// }

output accountId string = codeSigningAccount.id
output accountUri string = codeSigningAccount.properties.accountUri
output skuName string = codeSigningAccount.properties.sku.name
