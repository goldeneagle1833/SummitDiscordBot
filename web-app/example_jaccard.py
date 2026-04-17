def compute_jaccard_from_diff(diff: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
    """
    Computes Jaccard similarities (unique and total) for Spells and Sites
    from the given diff structure.

    Returns:
        {
            "Spells": {"unique": float, "total": float},
            "Sites": {"unique": float, "total": float}
        }
    """
    # Categories to consider as Sites vs Spells
    site_categories = {"Site"}
    spell_categories = set(diff.keys()) - site_categories

    def compute_for_categories(categories):
        unique_a, unique_b, shared, total_a, total_b, shared_total = 0, 0, 0, 0, 0, 0

        for category in categories:
            if category not in diff:
                continue
            section = diff[category]

            # Unique card counts
            unique_a += len(section.get("unique_a", []))
            unique_b += len(section.get("unique_b", []))
            shared += len(section.get("shared", []))

            # Total quantities
            total_a += sum(c.get("quantity", 0) for c in section.get("unique_a", []))
            total_b += sum(c.get("quantity", 0) for c in section.get("unique_b", []))
            for c in section.get("shared", []):
                total_a += c.get("quantity_a", 0)
                total_b += c.get("quantity_b", 0)
                shared_total += min(c.get("quantity_a", 0), c.get("quantity_b", 0))

        # Jaccard (unique)
        union_unique = unique_a + unique_b + shared
        unique_jaccard = shared / union_unique if union_unique > 0 else 1.0

        # Jaccard (total)
        union_total = total_a + total_b - shared_total
        total_jaccard = shared_total / union_total if union_total > 0 else 1.0

        return unique_jaccard, total_jaccard

    spells_unique, spells_total = compute_for_categories(spell_categories)
    sites_unique, sites_total = compute_for_categories(site_categories)

    return {
        "Spells": {"unique": spells_unique, "total": spells_total},
        "Sites": {"unique": sites_unique, "total": sites_total},
    }
