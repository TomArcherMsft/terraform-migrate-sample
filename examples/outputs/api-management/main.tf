resource "random_pet" "rg_name" {
  prefix = var.resource_group_name_prefix
}

resource "azurerm_resource_group" "rg" {
  location = var.resource_group_location
  name     = random_pet.rg_name.id
}

resource "random_pet" "api_management" {
}

resource "azurerm_api_management" "apim_service" {
  name                = "${random_pet.api_management.id}-apim-service"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  publisher_name      = "Example Publisher"
  publisher_email     = "publisher@example.com"
  sku_name            = "Developer_1"
  tags = {
    Environment = "Example"
  }
  policy {
    xml_content = <<XML
    <policies>
      <inbound />
      <backend />
      <outbound />
      <on-error />
    </policies>
XML
  }
}

resource "azurerm_api_management_api" "api" {
  name                = "${random_pet.api_management.id}-api"
  resource_group_name = azurerm_resource_group.rg.name
  api_management_name = azurerm_api_management.apim_service.name
  revision            = "1"
  display_name        = "${random_pet.api_management.id}-api"
  path                = "example"
  protocols           = ["https", "http"]
  description         = "An example API"
  import {
    content_format = var.open_api_spec_content_format
    content_value  = var.open_api_spec_content_value
  }
}

resource "azurerm_api_management_product" "product" {
  product_id            = "${random_pet.api_management.id}-product"
  resource_group_name   = azurerm_resource_group.rg.name
  api_management_name   = azurerm_api_management.apim_service.name
  display_name          = "${random_pet.api_management.id}-product"
  subscription_required = true
  approval_required     = false
  published             = true
  description           = "An example Product"
}

resource "azurerm_api_management_group" "group" {
  name                = "${random_pet.api_management.id}-group"
  resource_group_name = azurerm_resource_group.rg.name
  api_management_name = azurerm_api_management.apim_service.name
  display_name        = "${random_pet.api_management.id}-group"
  description         = "An example group"
}

resource "azurerm_api_management_product_api" "product_api" {
  resource_group_name = azurerm_resource_group.rg.name
  api_management_name = azurerm_api_management.apim_service.name
  product_id          = azurerm_api_management_product.product.product_id
  api_name            = azurerm_api_management_api.api.name
}

resource "azurerm_api_management_product_group" "product_group" {
  resource_group_name = azurerm_resource_group.rg.name
  api_management_name = azurerm_api_management.apim_service.name
  product_id          = azurerm_api_management_product.product.product_id
  group_name          = azurerm_api_management_group.group.name
}
