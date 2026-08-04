# Product intelligence

Product matching is evidence-first and household-scoped. A receipt description,
a specific product, its semantic family, and its reporting category are separate
concepts. For example, `JA H-MILCH 3.5 1L` can identify a specific Ja! product,
belong to the family `Milk`, and use category `Dairy`.

## Identification paths

- Confirmed aliases provide reusable household knowledge.
- Open Food Facts provides exact barcode evidence.
- Search-a-licious provides text candidates from the Open Food Facts index.
- GitHub Models can optionally rank supplied candidates and propose a family. It
  does not browse retailer sites.

Every candidate response includes its provider, source URL when available,
evidence level, score explanation, semantic family, category, and an audit flag
showing whether AI or retailer-site search was used.

## Barcode photographs

Barcode photographs are processed only in memory by ZXing-C++. The application
does not store the photograph, image hash, or object-storage key. When decoding
works, only the detected 8–14 digit barcode is passed to product lookup and may
be stored on a product after confirmation.

## Batch recognition after OCR

The OCR draft form offers `Recognize all OCR product items automatically`. When
selected, the browser runs enrichment sequentially for every unmatched product
after the draft opens and displays evidence cards below each item. Leaving it
unchecked preserves manual `Identify` buttons.

## Migration

Apply migration `018_product_family` to add the semantic `family_name` field:

```cmd
cd apps\api
python -m alembic upgrade head
```
