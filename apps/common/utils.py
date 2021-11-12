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
        product_words -= {"of", "and", "with"}
        total_words.update(product_words)
        total_numeric_values.update(product_numeric_values)
        if product_i == 0:
            matched_words = product_words
            matched_numeric_values = product_numeric_values
        else:
            matched_words &= product_words
            matched_numeric_values &= product_numeric_values

    if len(total_numeric_values):
        percentage = 0.4 * len(matched_words) / len(total_words) + 0.6 * len(matched_numeric_values) / len(
            total_numeric_values
        )
    else:
        percentage = len(matched_words) / len(total_words)
    return percentage


def group_products(vendors_search_result_products, model=False):
    search_result_vendors_count = len(vendors_search_result_products)
    matched_products = set()
    well_matching_pairs = set()
    # a list of candidate products which are similar
    similar_candidate_products = []
    products = []
    n_similarity = 2
    threshold = 0.6
    while n_similarity <= search_result_vendors_count:
        vendors_products_combinations = itertools.combinations(vendors_search_result_products, n_similarity)
        for vendors_products_combination in vendors_products_combinations:
            for vendor_products in itertools.product(*vendors_products_combination):
                # when finding more than 3-length similar products we need to check that
                # sub-set of products belongs to well matching pairs. If well matching set contains subset of products
                # it is worth to check similarity but otherwise, we don't have to calculate it.
                if n_similarity > 2:
                    contains_well_matching_pair = any(
                        [
                            set(well_matching_pair).issubset(vendor_products)
                            for well_matching_pair in well_matching_pairs
                        ]
                    )
                    if not contains_well_matching_pair:
                        continue

                similarity = get_similarity(*vendor_products, key="name")
                if similarity > threshold:
                    similar_candidate_products.append((f"{similarity:.2f}", *vendor_products))
                    well_matching_pairs.add(vendor_products)

        n_similarity += 1

    for similar_candidate_product in sorted(similar_candidate_products, key=lambda x: (len(x), x[0]), reverse=True):
        similar_candidate_product_without_similarity = similar_candidate_product[1:]
        for product in similar_candidate_product_without_similarity:
            if product in matched_products:
                break
        else:
            matched_products.update(similar_candidate_product_without_similarity)
            parent_product = similar_candidate_product_without_similarity[0]
            if model:
                parent_product.children.set(similar_candidate_product_without_similarity[1:])
            else:
                parent_product = parent_product.to_dict()
                products.append(
                    {
                        "price": parent_product.pop("price"),
                        "product": parent_product,
                    }
                )
                parent_product["children"] = [
                    {"price": (p_ := p.to_dict()).pop("price"), "product": p_}
                    for p in similar_candidate_product_without_similarity[1:]
                ]

    if not model:
        for vendor_search_result_products in vendors_search_result_products:
            for vendor_product in vendor_search_result_products:
                if vendor_product not in matched_products:
                    products.append(
                        {
                            "price": (p := vendor_product.to_dict()).pop("price"),
                            "product": p,
                        }
                    )

        return products


def group_products_from_search_result(search_results):
    meta = {
        "total_size": 0,
        "vendors": [],
    }

    vendors_search_result_products = []
    for search_result in search_results:
        if not isinstance(search_result, dict):
            continue
        meta["total_size"] += search_result["total_size"]
        meta["vendors"].append(
            {
                "vendor": search_result["vendor_slug"],
                "page": search_result["page"],
                "last_page": search_result["last_page"],
            }
        )
        if len(search_result["products"]):
            vendors_search_result_products.append(search_result["products"])

    meta["last_page"] = all([vendor_search["last_page"] for vendor_search in meta["vendors"]])

    products = group_products(vendors_search_result_products)
    return meta, products


def group_products_by_str():
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
    for products in itertools.product(*net32_products, henry_products, benco_products):
        similarity = get_similarity(*products)
        similarities.append((f"{similarity:.2f}", *products))

    for i in sorted(similarities, key=lambda x: x[0], reverse=True)[:10]:
        print(i)


if __name__ == "__main__":
    group_products_by_str()
