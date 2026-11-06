"""Scrapers open pages in a real browser and read the JSON the page itself loads.

Parsing (parse.py, shopee_parse.py, tiktok_parse.py) is kept apart from the browser so it can be
tested with sample responses. The parsers look for records by their keys anywhere in a response,
not by a fixed path, so a site moving a field one level deeper does not break them.
"""
