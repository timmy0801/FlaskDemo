MAX_PER_PAGE = 100


def clamp_per_page(per_page, max_per_page=MAX_PER_PAGE):
    """Clamp the per_page value to a maximum limit."""
    return max(1, min(per_page, max_per_page))
