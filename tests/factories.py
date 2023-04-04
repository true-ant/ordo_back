import factory
from factory import fuzzy

from services.api_client.vendor_api_types import DentalCityProduct


class DentalCityProductFactory(factory.Factory):
    class Meta:
        model = DentalCityProduct

    product_sku = fuzzy.FuzzyText()
    list_price = fuzzy.FuzzyDecimal(low=0)
    partner_price = fuzzy.FuzzyDecimal(low=0)
    web_price = fuzzy.FuzzyDecimal(low=0)
    partner_code = fuzzy.FuzzyText()
    product_desc = fuzzy.FuzzyText()
    available_quantity = fuzzy.FuzzyText()
    manufacturer = fuzzy.FuzzyText()
    manufacturer_part_number = fuzzy.FuzzyText()
    manufacturer_special = fuzzy.FuzzyText()
    flyer_special = fuzzy.FuzzyText()
    eta_date = fuzzy.FuzzyText()
    update_date = fuzzy.FuzzyText()
