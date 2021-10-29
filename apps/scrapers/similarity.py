import re
from itertools import product


def get_similarity(s1, s2):
    s1_numeric_values = set(map(str.lower, re.findall(r"\w*[\d]+\w*", s1)))
    s2_numeric_values = set(map(str.lower, re.findall(r"\w*[\d]+\w*", s2)))
    s1_words = set(map(str.lower, re.findall(r"\w+", s1)))
    s2_words = set(map(str.lower, re.findall(r"\w+", s2)))
    # s1_numeric_values = set(map(str.lower, re.findall(r'(\w*[:,.%-/]*[\d]+[:,.%-/]*\w*[:,.%-.]*)+', s1)))
    # s2_numeric_values = set(map(str.lower, re.findall(r'(\w*[:,.%-/]*[\d]+[:,.%-/]*\w*[:,.%-.]*)+', s2)))
    s1_words = s1_words - s1_numeric_values
    s2_words = s2_words - s2_numeric_values
    total_words = len(s1_words | s2_words)
    match_words = len(s1_words & s2_words)
    total_numeric_values = len(s1_numeric_values | s2_numeric_values)
    match_numeric_values = len(s1_numeric_values & s2_numeric_values)
    percentage = 0.3 * match_words / total_words + 0.7 * match_numeric_values / total_numeric_values
    return percentage


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

    similarities = []
    for net32_product, henry_product in product(net32_products, henry_products):
        similarity = get_similarity(net32_product, henry_product)
        similarities.append((f"{similarity:.2f}", net32_product, henry_product))

    for i in sorted(similarities, key=lambda x: x[0], reverse=True)[:10]:
        print(i)
