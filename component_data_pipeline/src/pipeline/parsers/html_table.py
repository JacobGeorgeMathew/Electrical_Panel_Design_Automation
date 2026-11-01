from bs4 import BeautifulSoup

def parse_tables(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for table in soup.find_all("table"):
        headers = [cell.get_text(" ", strip=True) for cell in table.select("tr th")]
        for tr in table.select("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in tr.find_all(["td", "th"], recursive=False)]
            if cells and not all(c in headers for c in cells):
                rows.append({"headers": headers, "cells": cells})
    return rows
