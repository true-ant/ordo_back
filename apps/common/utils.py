import itertools
import re
import uuid


def generate_token():
    return uuid.uuid4().hex + uuid.uuid4().hex


def get_similarity(*products, key=None):
    total_words = set()
    matched_words = set()
    total_numeric_values = set()
    matched_numeric_values = set()

    for product_i, product in enumerate(products):
        product_name = product if isinstance(product, str) else getattr(product, key)
        product_numeric_values = set(map(str.lower, re.findall(r"\w*[\d]+\w*", product_name)))
        product_words = set(map(str.lower, re.findall(r"\w+", product_name)))
        product_words = product_words - product_numeric_values
        total_words.update(product_words)
        total_numeric_values.update(product_numeric_values)
        if product_i == 0:
            matched_words = product_words
            matched_numeric_values = product_numeric_values
        else:
            matched_words &= product_words
            matched_numeric_values &= product_numeric_values

    percentage = 0.3 * len(matched_words) / len(total_words) + 0.7 * len(matched_numeric_values) / len(
        total_numeric_values
    )
    return percentage


def group_products(search_results):
    meta = {
        "total_size": 0,
        "vendors": [],
    }

    vendors_search_result_products = []
    vendors_matched_products = {}
    for search_result in search_results:
        if not isinstance(search_result, dict):
            continue
        vendor_slug = search_result["vendor_slug"]
        meta["total_size"] += search_result["total_size"]
        meta["vendors"].append(
            {
                "vendor": search_result["vendor_slug"],
                "page": search_result["page"],
                "last_page": search_result["last_page"],
            }
        )
        vendors_search_result_products.append(search_result["products"])
        vendors_matched_products[vendor_slug] = set()

    meta["last_page"] = all([vendor_search["last_page"] for vendor_search in meta["vendors"]])

    # group by similar products
    search_result_vendors_count = len(vendors_search_result_products)
    mismatching_pairs = set()
    longest_mismatching_pair_length = 2
    products = []
    similar_candidate_products = []
    n_similarity = 2
    while n_similarity <= search_result_vendors_count:
        threshold = 0.6 ** (n_similarity - 1)
        vendors_products_combinations = itertools.combinations(vendors_search_result_products, n_similarity)
        for vendors_products_combination in vendors_products_combinations:
            for vendor_products in itertools.product(*vendors_products_combination):
                # when finding more than 3-length similar products we need to check that
                # sub-set of products belongs to mismatching pairs. If mismatching set contains subset of products
                # we don't need to calculate the similarity
                if n_similarity > longest_mismatching_pair_length:
                    contains_mismatching_pair = any(
                        [set(mismatching_pair) & set(vendor_products) for mismatching_pair in mismatching_pairs]
                    )
                    if contains_mismatching_pair:
                        continue

                similarity = get_similarity(*vendor_products, key="name")
                if similarity < threshold:
                    mismatching_pairs.add(vendor_products)
                    longest_mismatching_pair_length = len(vendor_products)
                else:
                    similar_candidate_products.append([f"{similarity:.2f}", *vendor_products])

        n_similarity += 1

    # remove duplicates in candidate list
    if similar_candidate_products:
        for similar_candidate_product in sorted(similar_candidate_products, key=lambda x: x[0], reverse=True):
            similar_candidate_product_without_similarity = similar_candidate_product[1:]
            for vendor_matched_products, product in zip(
                vendors_matched_products, similar_candidate_product_without_similarity
            ):
                if product not in vendor_matched_products:
                    vendor_matched_products.add(product)
                else:
                    break
            else:
                products.append([p.to_dict() for p in similar_candidate_product_without_similarity])

    for vendor_search_result_products, vendor_matched_products in zip(
        vendors_search_result_products, vendors_matched_products
    ):
        for vendor_product in vendor_search_result_products:
            if vendor_product not in vendor_matched_products:
                products.append(vendor_product.to_dict())

    return meta, products


if __name__ == "__main__":
    net32_products = [
        "Septocaine Articaine 4% with Epinephrine 1:100,000. Box of 50 - 1.7 mL",
        "Septocaine Articaine HCl 4% with Epinephrine 1:200,000. Box of 50 - 1.7 mL",
        "Orabloc Articaine HCl 4% with Epinephrine 1:100,000 Injection Cartridges, 1.8",
        "House Brand Articaine HCl 4% with Epinephrine 1:100,000 Injection Cartridges",
        "Orabloc Articaine HCl 4% with Epinephrine 1:200,000 Injection Cartridges, 1.8",
        "Cook-Waite Zorcaine (Articaine Hydrochloride 4%) Local Anesthetic",
        "House Brand Articaine HCl 4% with Epinephrine 1:200,000 Injection Cartridges",
    ]
    henry_products = [
        "Septocaine Articaine HCl 4% Epinephrine 1:200,000 50/Bx",
        "Articadent Articaine HCl 4% Epinephrine 1:100,000 50/Bx",
        "Articaine HCl 4% Epinephrine 1:100,000 50/Bx",
        "Orabloc Articaine HCl 4% Epinephrine 1:200,000 50/Bx",
        "Articaine HCl 4% Epinephrine 1:200,000 50/Bx",
    ]
    benco_products = [
        "Septocaine® Articaine HCl 4% and Epinephrine 1:200,000 Silver Box of 50",
        "Septocaine® Articaine HCl 4% and Epinephrine 1:100,000 Gold Box of 50",
        "SNAP Liquid Monomer 4oz.",
        "Hemodent® Liquid 10cc",
        "IRM Ivory Powder Immediate Restorative Material 38gm",
        "Wizard Wedges® Matrix Small Wedges Pack of 500",
        "Benco Dental™ Non-Skid Base Mix Pads 3” x 3” Pad of 50 Sheets",
        "Dr. Thompson's Applicator Pack of 100",
        'Econoback™ Patient Bib 13" x 19" Blue 3-Ply Case of 500',
        'Benco Dental™ Cotton Tip Applicators 6" Box of 1000',
        "Cook-Waite Lidocaine 1:100,000 Red Box of 50",
        "Jeltrate® Alginate Impression Material Fast Set Pink 1 pound package",
        "IRM COMB P&L IVORY",
        "Dental Floss Waxed Mint 200yd Refill",
    ]

    similarities = []
    products_list = [net32_products, henry_products, benco_products]
    for products in itertools.product(*products_list):
        similarity = get_similarity(*products)
        similarities.append((f"{similarity:.2f}", *products))

    for i in sorted(similarities, key=lambda x: x[0], reverse=True)[:10]:
        print(i)
