# Source permission review

**Checked:** 2026-10-31 (Asia/Kolkata). **Scope:** discovery only; no product pages, catalog PDFs, or APIs were batch downloaded. No requests to product pages were made for this review.

## Status summary

| Source ID / owner | robots.txt checked | Terms / automated-use finding | Classification | Official data channels and access |
|---|---|---|---|---|
| `schneider_india` — Schneider Electric | **UNVERIFIED.** Attempted `GET https://www.se.com/robots.txt` on 2026-10-31; the available runtime failed DNS resolution (`No such host is known`). Research browser also could not open the URL. Therefore no rule text or path decision can be stated. | The official global Terms of Use says reproduction of site content is restricted except personal non-commercial use, and describes a limited right to consult. It does not give a clear grant for automated extraction for this pipeline. | **PERMISSION_REQUIRED** for automated product-data collection from the site/catalog. The API is a separate authorized path and requires onboarding; robots status still needs a direct check against its API host before API requests. | **Official Product Catalog API exists.** Product Catalog API v2 advertises technical data, dimensions, weight, ETIM, documentation/assets and product list/detail/delta operations. Requires OAuth and partner/distributor onboarding with supplier and customer identifiers; India is listed as a tested country. Not anonymous/open access; contact Schneider/partner contact to request onboarding and usage terms. Official product catalogs and product datasheets are also downloadable, but catalog copyright terms apply. |
| `abb` — ABB Electrification | **UNVERIFIED.** Attempted `GET https://www.abb.com/robots.txt` on 2026-10-31; DNS resolution failed. No rules can be quoted. The ABB Library host and EPLAN portal are separate hosts and need their own robots checks if used. | A first-party ABB portal Terms of Use expressly prohibits bots/data-mining on ABB Content for that portal. An ABB Library PDF notice says reproduction, disclosure, or use of document content is prohibited without prior written permission. I did not verify general terms applicable to every public ABB product page. | **PERMISSION_REQUIRED** for automated collection/reuse from ABB product data and catalog files unless a separate product-data licence/contract expressly authorizes it. | **Official data channels exist.** ABB's German low-voltage site publishes Excel, Datanorm/Eldanorm and BMEcat 5.0 with ETIM9/10 data; its page says Excel contains ordering/logistics attributes including weight, dimensions, loss power and catalog links. This download is market-specific; STRIEBEL & JOHN system-partner material requires login. ABB e-Configure provides product details/configuration and Excel/PDF BOM exports; some country price lists vary. ABB parts are also available through EPLAN Data Portal, which requires EPLAN account/login; EPLAN access/format rights apply. Contact ABB e-Business for data-exchange/API licensing. |
| `havells_india` — Havells India | **UNVERIFIED.** Attempted `GET https://www.havells.com/robots.txt` on 2026-10-31; DNS resolution failed. Havells PowerPlus is a distinct host and would need its own robots check. | I could not verify an applicable website Terms of Use page. Official Havells catalog PDFs carry a copyright notice; that notice addresses copying of trade dress/graphics and does not itself settle automated extraction of product facts. | **UNVERIFIED.** No verified web terms or robots result establishes whether automated extraction is permitted. Treat PDFs as copyrighted; request permission before automation or reuse beyond manual factual note-taking. | Official Havells product PDFs and catalogs are publicly indexed on Havells' own domains, including protection-device material for MCB/RCCB/RCBO and MCCB catalogs. A public structured product-data API or openly licensed product spreadsheet was not verified. Havells' online-vendor/Sampark portals are channel-partner systems and may require registration; do not use them without authorization. |
| `lt_india` — Larsen & Toubro / L&T Switchgear | **UNVERIFIED.** Attempted `GET https://www.larsentoubro.com/robots.txt` on 2026-10-31; DNS resolution failed. | The official L&T Copyright & Terms page permits personal, non-commercial use in accordance with IP law, and says other use/modification without prior written authorization is prohibited. It does not specifically describe automated access. | **UNVERIFIED.** The terms do not explicitly address automated extraction; robots could not be checked. Because the stated permission is narrow, obtain written permission before automated reuse. | Official L&T-hosted D-Sine and DU-series MCCB PDF catalogs are available and include product data, technical datasheets and dimensions. No official product-data API, BMEcat/ETIM bulk product file or open-data licence was verified in this review. L&T's current product/business domain mapping should be confirmed; some former L&T switchgear product lines may now use the Lauritz Knudsen brand. |
| `siemens` — Siemens Product Information Hub | **UNVERIFIED.** Attempted `GET https://product-information-hub.siemens.cloud/robots.txt` on 2026-10-31; DNS resolution failed. Siemens website/developer portal robots are separate hosts and were not verified in this request. | Siemens' current general Terms of Use explicitly prohibit text/data mining, including automated scraping, reproduction, or extraction from the Siemens Website. API-specific terms may supersede general terms for the API, but the API docs' applicable usage terms and a grant for this project were not verified. | **FORBIDDEN** for automated scraping/extraction from Siemens web pages under the reviewed general terms. **PERMISSION_REQUIRED** for Product Information API use until API-specific permission/terms are confirmed. | An official Product Information API exists, but its documented focus is product lifecycle/obsolescence, delivery, successor/substitute and API-key information—not a full electrical engineering specification catalog. Siemens says an API key must be purchased by contacting support. A separate EPLAN Data Portal may provide parts data under EPLAN's account/licence conditions. No open, anonymous manufacturer-data export was verified. |

## Quoted evidence (short excerpts)

These excerpts are copied verbatim from the linked official terms/material. Excerpts are limited to the clauses relevant to access and reuse; where a page or clause could not be verified, that is stated rather than inferred.

### Schneider Electric

> “You agree not to reproduce, other than for your own personal, non-commercial use as defined in the Code, all or part of this website or its content on any medium whatsoever without Schneider Electric's permission, given in writing.”

> “Schneider Electric does not grant any right or license for the personal and non-commercial use of the website or its content, except for a non-exclusive license to consult it on an ‘as is’ basis, at your own risk.”

Source: [Schneider Electric Terms of Use](https://www.se.com/ww/en/about-us/legal/terms-of-use/), paragraphs 2, lines 39–43 in the page view. The terms page is dated 2014; confirm current India/site-specific terms before seeking API onboarding.

### ABB

> “use any data mining, bots, spiders, automated tools, or similar data gathering and extraction methods on the contents of the ABB Content”

Source: [ABB MyBuildings Portal Terms of Use](https://eu.mybuildings.abb.com/en_GB/page/terms-of-use), restriction clause 6.5. This clause is for that portal; I do not extend it to all ABB public web pages.

> “Any reproduction, disclosure to third parties or utilization of its contents – in whole or in parts – is forbidden without prior written consent.”

Source: [ABB Library example data sheet](https://library.e.abb.com/public/ccca2eaf37fc476bae20a542a3a9a3f9/9AKK1074920598_Rev_A.pdf). It is document-specific evidence of a rights restriction, not a universal ABB website clause.

### Havells India

> “Copyright Subsists. Imitation of trade dress, graphics and color scheme of this document is a punishable offence.”

Source: an [official Havells protection-device PDF](https://havellspowerplus.havells.com/NotificationUpload/146_flashAttachment.pdf). The website terms page and robots file could not be verified; this document notice does not expressly address automated retrieval or extraction of individual technical facts.

### Larsen & Toubro

> “You may use this material for personal and non-commercial purposes in accordance with the principles governing intellectual property laws. Any other use or modification of the content of the Company’s web site without the Company’s prior written authorisation is prohibited.”

Source: [L&T Copyright & Terms](https://www.larsentoubro.com/heavy-engineering/copyright-terms), Intellectual Property section. It does not expressly mention bots or automated extraction.

### Siemens

> “Engage in text or data mining. This includes, but is not limited to, any automated scraping, reproduction, or extraction of content, information, or data from the Siemens Website for the purpose of analysis”

Source: [Siemens Terms of Use](https://www.siemens.com/en-us/terms-of-use/), section 6.2, Use Restrictions. The clause expressly prohibits website scraping/extraction absent a separately applicable licence.

## Official catalogs, APIs and licenses reviewed

| Manufacturer / system | Verified channel | Access/license notes and suitability |
|---|---|---|
| Schneider | [Product Catalog API v2](https://api-explorer.se.com/en/api/product-catalog-v2) | Partner/distributor API; OAuth; onboarding assigns supplier/customer IDs. It covers catalog offer data with product details, technical specs, dimensions, weights, ETIM, documentation and media URLs. Not publicly usable without credentials and API terms. Official [download center](https://www.se.com/ww/en/download/) also exposes catalogs/datasheets; no open-data licence was found. |
| ABB | [ABB low-voltage article master data](https://new.abb.com/low-voltage/de/artikelstammdaten/niederspannung), [ABB e-Configure](https://new.abb.com/low-voltage/support/e-configure) | Regional (Germany) downloadable Excel and BMEcat/ETIM9/10 files were confirmed. Some data is login-protected/for system partners. e-Configure supports product selection/configuration and BOM exports; not verified as an unrestricted API or reuse licence. ABB directs B2B product-data exchange inquiries to e-Business. |
| Havells | [Official product catalogs and datasheets](https://havellspowerplus.havells.com/) | PDF download channel confirmed. A public product API or open CSV/XLSX feed was not found. The observed Havells API endpoint relates to motor products, not switchgear, so it is not a suitable source for this project. |
| L&T | [Official D-Sine MCCB catalog](https://www.larsentoubro.com/media/29931/dsine-mccb-catalogue.pdf), [DU MCCB catalog](https://www.larsentoubro.com/media/29938/du-series-mccb-catalogue.pdf) | Official PDFs contain useful product/dimension tables. No official API, ETIM/BMEcat export, or permissive dataset was verified. |
| Siemens | [Product Information API overview](https://developer.siemens.com/product-information-api/overview.html), [Getting Started](https://developer.siemens.com/product-information-api/getting-started.html) | Siemens requires contacting its support team to **purchase an API key**. Documented endpoints focus on obsolescence and delivery data. API key purchase is not evidence of rights to bulk collect or retain product technical data; obtain applicable API terms/license. General website scraping is expressly prohibited. |
| EPLAN Data Portal | [Portal overview](https://www.eplan.com/gb-en/products/eplan-data-portal/), [FAQ/access](https://www.eplan.com/int/en/support/data-portal.html) | Manufacturer-supplied parts data includes commercial/technical data, connection patterns, 2D/3D graphics, documents and macros. Basic portal access requires an EPLAN Cloud account; EPLAN-format downloads may require a software service agreement, depending on use/version. Account access is not a general redistribution licence. Ask the college whether it has a licensed EPLAN account and review EPLAN's terms before exporting data to this separate catalog. |
| ETIM / BMEcat | [ETIM CMT and BMEcat overview](https://www.etim-uk-and-ie.org/the-standard/cmt-and-bmecat/) | ETIM's classification model is available for lookup and has CSV/Excel/IXF/JSON/API access as described by ETIM; BMEcat is an exchange format. ETIM classifications describe classes/features; they are not themselves a populated manufacturer product catalog. Terms/license for any product data still come from its provider. |

## Openly licensed dataset search

I did **not** verify an openly licensed dataset suitable as a real product catalog for MCCB/MCB/RCCB/SPD, enclosure, terminal, or busbar selection. The closest candidate found, [CircuitBase](https://circuitbase.tech/about), states CC BY 4.0 for its published data, but its stated coverage is electronic hobby components, development boards, connectors and schematics—not distribution-board protection devices or panel enclosures. A GitHub electronic-components collection mentions distributor-collected breaker data, but a suitable license and engineering-field coverage were not verified, so it is not recommended for import. ETIM/IEC dictionaries are vocabularies/characteristic models, not real product instances.

## What is usable now

- **No manufacturer website is cleared for automated scraping.** The robots checks could not be completed because DNS resolution was unavailable in the execution environment. Do not interpret this as robots allowing access.
- **Best route to request first:** Schneider Product Catalog API partner onboarding; ABB's regional BMEcat/Excel product data or e-Business data exchange; and the college's EPLAN Data Portal access. These are official data channels but their terms, regional availability and downstream reuse rights need confirmation.
- **Manual curation is still possible:** the source PDFs and product pages can be viewed by a person. Record the product URL, part code, exact source document/page, raw text, retrieval date, and only facts needed for the academic prototype. Do not copy/rehost protected PDFs or CAD files. When in doubt, ask the manufacturer/college for written permission.

## References

- [Schneider Product Catalog API](https://api-explorer.se.com/en/api/product-catalog-v2)
- [ABB product-data downloads](https://new.abb.com/low-voltage/de/artikelstammdaten/niederspannung) and [ABB e-Configure](https://new.abb.com/low-voltage/support/e-configure)
- [Havells official protection-device PDF](https://havellspowerplus.havells.com/NotificationUpload/146_flashAttachment.pdf)
- [L&T MCCB catalog](https://www.larsentoubro.com/media/29931/dsine-mccb-catalogue.pdf)
- [Siemens API Getting Started](https://developer.siemens.com/product-information-api/getting-started.html) and [Terms](https://www.siemens.com/en-us/terms-of-use/)
- [EPLAN Data Portal](https://www.eplan.com/gb-en/products/eplan-data-portal/) and [EPLAN FAQ](https://www.eplan.com/int/en/support/data-portal.html)
- [ETIM/BMEcat overview](https://www.etim-uk-and-ie.org/the-standard/cmt-and-bmecat/)
- [CircuitBase license and data description](https://circuitbase.tech/about)
