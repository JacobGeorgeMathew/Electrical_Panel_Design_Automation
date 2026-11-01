"""Explicitly disabled official-channel placeholders. No implicit network access."""

class SchneiderProductCatalogApi:
    enabled = False

    def import_products(self, *args, **kwargs):
        raise RuntimeError("Schneider Product Catalog API connector is disabled. Obtain written authorization, API onboarding/credentials, and API-specific terms before implementation.")

class ABBProductDataImport:
    """ABB BMEcat and Excel use the offline manual-import parser."""
    enabled = True

    @staticmethod
    def import_file(path):
        from .manual_import import import_file
        return import_file(path, "abb")
