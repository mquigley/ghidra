# Listing UI — Virtual Rendering and Scrollbar Architecture

## How the Listing Handles Millions of Lines

### Rendering: Only Visible Layouts Are Ever Allocated

`FieldPanel` maintains a `List<AnchoredLayout> layouts` — typically 5–20 objects — containing only the rows currently on screen. `paintComponent()` iterates only that list. `model.getLayout(index)` is **never called** for anything off-screen.

When the user scrolls, `AnchoredLayoutHandler.positionLayoutsAroundAnchor(index, offset)` rebuilds this list:
1. Fetches layouts forward from the anchor until the viewport is full
2. Fetches layouts backward to fill anything above
3. Trims anything that falls outside the viewport

Old layout objects are discarded; no 1M-object list is ever built.

### Index Space: `BigInteger`, Not `int`

The model uses `BigInteger` indices so row counts aren't limited to 2 billion. `ListingModelAdapter` bridges the address-based `ListingModel` to the index-based `LayoutModel`:

```
BigInteger index → AddressIndexMap.getAddress(index) → Address
                 → ListingModel.getLayout(address)   → AnchoredLayout
```

`AddressIndexMap` handles the sparse address space problem: it **compresses large gaps** (gaps larger than `totalAddresses / 100`) so a 64-bit binary with huge unmapped regions doesn't produce a trillion indices. Gaps that are compressed still show a visible divider line (`isGapAddress()` → the divider format in `ProgramBigListingModel`).

### The Scrollbar: Estimated Pixel Heights, Not Line Counts

`JScrollBar` internally uses `int` — it cannot represent millions of real positions directly. `IndexedScrollPane` solves this with a `ViewToIndexMapper` that maps the scrollbar's integer range to index space. Three implementations are chosen based on data size:

| Mapper | Used when | How |
|---|---|---|
| `PreMappedViewToIndexMapper` | < ~1000 items | Pre-builds `layoutStarts[]` array; binary search |
| `UniformViewToIndexMapper` | All layouts same height, fits in int | Exact arithmetic |
| `DefaultViewToIndexMapper` | Millions of items | **Estimates** total height = `indexCount × 20px (average)`; maps scrollbar range linearly |

For millions of lines, `DefaultViewToIndexMapper` computes:
```
xFactor = lastIndex / (estimatedTotalHeight - viewportHeight)
scroll(pixelPos) → index = pixelPos * xFactor
```

The JScrollBar never knows there are millions of rows — it only sees:
- **Total virtual height**: `indexMapper.getViewHeight()` (an estimate)
- **Viewport height**: current panel height in pixels
- These produce a ratio that positions the thumb

When the user drags the thumb, `IndexedScrollPane.viewportStateChanged()` converts:
```
JScrollBar position (0..MAX_VALUE)
  → ViewToIndexMapper.getIndex(pixelOffset)
  → BigInteger index
  → FieldPanel.showIndex(index, yOffset)
  → AnchoredLayoutHandler rebuilds visible layouts
```

### End-to-End for a Scrollbar Drag

```
User drags scrollbar to 73%
  → JScrollBar fires change event
  → IndexedScrollPane.viewportStateChanged()
      → pixelPos = (73% × estimatedTotalHeight)
      → DefaultViewToIndexMapper.getIndex(pixelPos)
          → index = pixelPos * xFactor          ← linear estimate
  → FieldPanel.showIndex(index, yOffset)
  → AnchoredLayoutHandler.positionLayoutsAroundAnchor(index, yOffset)
      → fillLayoutsForward(): calls model.getLayout() for ~10 visible rows
      → fillLayoutsBack():    calls model.getLayout() for ~5 rows above
  → FieldPanel.paintComponent(): paints those ~15 AnchoredLayouts
```

**Key properties:**
- Memory: always O(visible rows) — never O(total rows)
- Scrollbar position at large scales is an **estimate** — dragging to 73% doesn't guarantee landing on the exact same row every time, but it's close enough; keyboard navigation is always precise

## Key Source Files

| Component | File | Key Methods |
|---|---|---|
| `FieldPanel` | [Ghidra/Framework/Docking/src/main/java/docking/widgets/fieldpanel/FieldPanel.java](Ghidra/Framework/Docking/src/main/java/docking/widgets/fieldpanel/FieldPanel.java) | `layouts` list (line 82), `showIndex`, `paintComponent` |
| `AnchoredLayoutHandler` | [Ghidra/Framework/Docking/src/main/java/docking/widgets/fieldpanel/internal/AnchoredLayoutHandler.java](Ghidra/Framework/Docking/src/main/java/docking/widgets/fieldpanel/internal/AnchoredLayoutHandler.java) | `positionLayoutsAroundAnchor`, `fillLayoutsForward`, `fillLayoutsBack`, `trimLayouts` |
| `ListingModel` | [Ghidra/Features/Base/src/main/java/ghidra/app/util/viewer/listingpanel/ListingModel.java](Ghidra/Features/Base/src/main/java/ghidra/app/util/viewer/listingpanel/ListingModel.java) | `getLayout(Address, isGap)`, `getAddressAfter`, `getAddressBefore` |
| `ListingModelAdapter` | [Ghidra/Features/Base/src/main/java/ghidra/app/util/viewer/listingpanel/ListingModelAdapter.java](Ghidra/Features/Base/src/main/java/ghidra/app/util/viewer/listingpanel/ListingModelAdapter.java) | `AddressIndexMap`, `getLayout(BigInteger)` |
| `DefaultViewToIndexMapper` | [Ghidra/Framework/Docking/src/main/java/docking/widgets/indexedscrollpane/DefaultViewToIndexMapper.java](Ghidra/Framework/Docking/src/main/java/docking/widgets/indexedscrollpane/DefaultViewToIndexMapper.java) | Height estimate, `xFactor`, `getIndex` |
| `IndexedScrollPane` | [Ghidra/Framework/Docking/src/main/java/docking/widgets/indexedscrollpane/IndexedScrollPane.java](Ghidra/Framework/Docking/src/main/java/docking/widgets/indexedscrollpane/IndexedScrollPane.java) | `createIndexMapper`, `viewportStateChanged`, `indexRangeChanged` |
| `AddressIndexMap` | [Ghidra/Features/Base/src/main/java/ghidra/app/util/viewer/util/AddressIndexMap.java](Ghidra/Features/Base/src/main/java/ghidra/app/util/viewer/util/AddressIndexMap.java) | Gap compression, `isGapIndex`, `getAddress` |
| `ProgramBigListingModel` | [Ghidra/Features/Base/src/main/java/ghidra/app/util/viewer/listingpanel/ProgramBigListingModel.java](Ghidra/Features/Base/src/main/java/ghidra/app/util/viewer/listingpanel/ProgramBigListingModel.java) | `getLayout`, `getAddressAfter`, `getAddressBefore` |
