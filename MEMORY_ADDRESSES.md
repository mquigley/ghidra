# Memory, Addresses, and Loading in Ghidra

## Ownership Chain

Everything starts at `ProgramDB`, which owns a `MemoryMapDB` as manager index 0:

```
ProgramDB
  └─ managers[MEMORY_MGR=0]  →  MemoryMapDB
                                    └─ List<MemoryBlockDB> blocks  (sorted by start address)
                                         └─ List<SubMemoryBlock> subBlocks
                                              └─ FileBytesSubMemoryBlock
                                                   └─ FileBytes
                                                        ├─ DBBuffer[] originalBuffers  (unmodified bytes)
                                                        └─ DBBuffer[] layeredBuffers   (shadow/patch layer)
```

`MemoryMapDB` implements both the public `Memory` interface (used by the rest of Ghidra) and
`ManagerDB` (so `ProgramDB` can lifecycle-manage it).

---

## Address Spaces

An `AddressSpace` is the coordinate system in which addresses live. All addresses carry a
reference to their owning space. The default space for a program comes from the language
definition.

### SegmentedAddressSpace (x86 Real Mode)

For DOS programs, the language `x86:LE:16:Real Mode` provides a `SegmentedAddressSpace` — a
21-bit address space (`REALMODE_SIZE = 21`, max address `0x10FFEF`).

Real-mode address arithmetic:
```
flat_address = segment * 16 + offset
```

Multiple segment:offset pairs alias the same flat address — e.g. `1234:0005` and `1000:2345`
both map to flat `0x12345`. Internally Ghidra stores and compares by flat offset; the segment
value is carried in `SegmentedAddress.segment` for display and segment-relative arithmetic.

Key classes:
- [`SegmentedAddressSpace`](Ghidra/Framework/SoftwareModeling/src/main/java/ghidra/program/model/address/SegmentedAddressSpace.java)
  — 21-bit real-mode space; `getFlatOffset(seg, off)`, `getAddress(seg, off)`,
  `getAddressInSegment(flat, preferredSeg)`
- [`SegmentedAddress`](Ghidra/Framework/SoftwareModeling/src/main/java/ghidra/program/model/address/SegmentedAddress.java)
  — extends `GenericAddress`, adds `int segment`; `getSegment()`, `getSegmentOffset()`

The segment operation is defined as p-code in
[`x86-16-real.pspec`](Ghidra/Processors/x86/data/languages/x86-16-real.pspec):
```xml
<segmentop space="ram" userop="segment" farpointer="yes">
  <body>
    res = (zext(base) << 4) + zext(inner);
  </body>
</segmentop>
```

---

## MzLoader — Loading a DOS MZ Executable

**File:** [`MzLoader.java`](Ghidra/Features/Base/src/main/java/ghidra/app/util/opinion/MzLoader.java)
extends `AbstractLibrarySupportLoader`.

**Constants:**
- `INITIAL_SEGMENT_VAL = 0x1000` — load address for the program's first segment
- `FAR_RETURN_OPCODE = 0xCB` — used to detect segment boundaries
- `MOVW_DS_OPCODE = 0xBA` — used to detect DS initialization at entry point

### Loading Process

1. **Validate address space** — enforces that the language has a `SegmentedAddressSpace`:
   ```java
   if (!(af.getDefaultAddressSpace() instanceof SegmentedAddressSpace))
       throw new IOException("Selected Language must have a segmented address space.");
   ```

2. **Parse MZ relocations** — discovers which segments the program references

3. **Create `FileBytes`** — reads the raw file bytes into the database:
   ```java
   FileBytes fileBytes = memory.createFileBytes(filename, 0, size, inputStream, monitor);
   ```

4. **Create memory blocks** — one initialized block per segment from file data, plus
   uninitialized (BSS) blocks as needed:
   - Names: `CODE_0`, `CODE_1`, `CODE_0u`, …
   - `DATA` block sized to `e_minalloc * 16` bytes (minimum allocation from MZ header)
   - DOS header dumped into `OTHER_SPACE` (non-addressable auxiliary space) as `HEADER`

5. **Apply relocations** — fixup segment values in the loaded image (go into layered buffers,
   originals preserved)

6. **Detect segment boundaries** — `adjustSegmentStarts()` scans first 16 bytes of each block
   for `FAR_RETURN_OPCODE`; splits/merges blocks for compiler stack-switching thunks

7. **Set entry point** — label `"entry"` created at `CS:IP`

8. **Initialize registers:**
   - `CS = (INITIAL_SEGMENT_VAL + e_cs) & 0xFFFF`
   - `SS = (INITIAL_SEGMENT_VAL + e_ss) & 0xFFFF`
   - `SP = e_sp`
   - `DS` — detected by scanning entry point for `mov dx, <imm16>` (opcode `0xBA`)

### Typical Memory Map After Load

```
Segment:Offset    Flat Addr    Block Name    Content
1000:0000         0x10000      CODE_0        Initialized (file bytes)
1100:0000         0x11000      CODE_1        Initialized (additional segment, if any)
12xx:0000         ...          CODE_0u       Uninitialized (BSS)
1280:0000         ...          DATA          Uninitialized (stack/heap, e_minalloc)

OTHER_SPACE:      (not addressable by program)
                               HEADER        MZ header + relocation table
```

---

## Memory Block Byte Storage

### FileBytes

**File:** [`FileBytes.java`](Ghidra/Framework/SoftwareModeling/src/main/java/ghidra/program/database/mem/FileBytes.java)

The primary container for raw loaded bytes. Key fields:

| Field | Type | Purpose |
|---|---|---|
| `originalBuffers` | `DBBuffer[]` | Unmodified bytes from the file (read-only) |
| `layeredBuffers` | `DBBuffer[]` | Shadow/copy-on-write layer for patches |
| `fileOffset` | `long` | Offset in source file (nonzero for embedded files) |
| `size` | `long` | Total byte count |
| `filename` | `String` | Source file name |

The dual-buffer design preserves original bytes permanently. `getOriginalByte()` always returns
the file byte; `getModifiedByte()` returns the patched value (or the original if unpatched).
Relocations applied during load go into the layered buffers.

### DBBuffer / ChainedBuffer

Each `DBBuffer` wraps a `ChainedBuffer` (in `Ghidra/Framework/DB`) that spreads bytes across
fixed-size database pages. Max buffer size is **1 GB** (`MAX_BUF_SIZE = 1_000_000_000`); larger
files get multiple `DBBuffer` entries. Byte lookup:

```java
dbBufferIndex = (int)(offset / maxBufferSize);
localOffset   = (int)(offset % maxBufferSize);
byte = buffers[dbBufferIndex].getByte(localOffset);
```

### Database Tables

Managed by `FileBytesAdapterV0` — table name `"File Bytes"`:

| Column | Type | Content |
|---|---|---|
| `FILENAME_COL` | String | Original filename |
| `OFFSET_COL` | Long | Offset in source file |
| `SIZE_COL` | Long | Byte count |
| `BUF_IDS_COL` | Binary | int[] of original DBBuffer IDs |
| `LAYERED_BUF_IDS_COL` | Binary | int[] of layered DBBuffer IDs |

### FileBytesSubMemoryBlock

**File:** [`FileBytesSubMemoryBlock.java`](Ghidra/Framework/SoftwareModeling/src/main/java/ghidra/program/database/mem/FileBytesSubMemoryBlock.java)

Bridges a `MemoryBlock` to its `FileBytes`. Stores:
- `FileBytes fileBytes` — reference to the owning FileBytes object
- `long fileBytesOffset` — byte offset within FileBytes where this block's data starts

Byte access:
```java
getByte(offsetInMemBlock):
    return fileBytes.getModifiedByte(fileBytesOffset + (offsetInMemBlock - subBlockOffset));
```

### How createInitializedBlock() Wires It Together

```
loader calls memory.createInitializedBlock(name, startAddr, fileBytes, offset, length)
  └─ MemoryMapDB
      └─ MemoryMapDBAdapter.createFileBytesBlock()
          ├─ Creates record in "Memory Blocks" table  (name, start addr, length, flags)
          └─ Creates SUB_TYPE_FILE_BYTES record in "Sub Memory Blocks" table
               ├─ SUB_INT_DATA1  = fileBytes.getId()    ← links to FileBytes row
               └─ SUB_LONG_DATA2 = offset               ← byte offset within FileBytes
                    └─ FileBytesSubMemoryBlock instantiated, caches FileBytes reference
```

---

## What is an Address?

`Address` is an interface with exactly two logical pieces of information:

```
Address = (AddressSpace, long offset)
```

- **`AddressSpace`** — which coordinate system the address lives in (RAM, register, stack,
  constant, unique, external, other, …). Two addresses with offset `0` in different spaces are
  completely unrelated.
- **`long offset`** — a byte position within that space (the "flat offset"). For a normal RAM
  space this is a simple linear integer from `0` to `2^size - 1`.

There is **no size** stored in an `Address`. It identifies a single byte location, not a range.

### Flat offset

The flat offset is `Address.getOffset()` — the raw `long` in the `Address` object. "Flat" means
a single linear number with no encoding. For `SegmentedAddressSpace`, the flat offset encodes
`segment * 16 + segmentOffset`. The `SegmentedAddress` subclass stores an additional `int segment`
field only for display and segment-relative arithmetic — the underlying `offset` is always flat.

### What MemoryBlock knows about its position

`MemoryBlockDB` stores:
```java
private Address startAddress;  // absolute position in the address space
private long    length;        // byte count
```

From these it can answer `getStart()`, `getEnd()`, `getSize()`, and `contains(addr)`. It does
**not** know about neighboring blocks — that knowledge lives in `MemoryMapDB.blocks` (the sorted
list), which is what you binary-search when looking up an address.

---

## Address Space Types

`AddressSpace` defines type constants covering all spaces a program can have:

| Constant | Value | Purpose |
|---|---|---|
| `TYPE_RAM` | 1 | Normal memory (default for most programs) |
| `TYPE_REGISTER` | 4 | Processor registers |
| `TYPE_STACK` | 5 | Stack-relative offsets (signed) |
| `TYPE_UNIQUE` | 3 | Decompiler temporaries |
| `TYPE_CONSTANT` | 0 | Constants (signed offset space) |
| `TYPE_OTHER` | 7 | Non-loaded data (debug info, DOS header, etc.) |
| `TYPE_EXTERNAL` | 10 | External library locations |
| `TYPE_VARIABLE` | 11 | Function variables/parameters |

Well-known singleton spaces defined on `AddressSpace`:
- `OTHER_SPACE` — 64-bit, `TYPE_OTHER`; where loaders dump non-addressable file data
- `EXTERNAL_SPACE` — 32-bit; external library function references
- `VARIABLE_SPACE` — 32-bit; function-scoped variables
- `HASH_SPACE` — 60-bit; decompiler dynamic hash identification

---

## MemoryBlock Overlap Rules

**Normal blocks cannot overlap.** `MemoryMapDB.checkRange()` is called before every
`createInitializedBlock`, `createUninitializedBlock`, etc., and throws `MemoryConflictException`
if any part of the new range already exists in `allAddrSet`:

```java
if (allAddrSet.intersects(start, end)) {
    throw new MemoryConflictException(
        "Part of range (" + start + ", " + end + ") already exists in memory.");
}
```

**Overlay blocks are the deliberate exception.** An overlay block gets its own
`OverlayAddressSpace` — a distinct space that wraps the same base space. Addresses in the overlay
space and the base space have the same numeric offset but are different `Address` objects in
different spaces, so they do not conflict. This is how Ghidra models bank-switched memory,
DOS code overlays, etc. — same physical address range, different content depending on context.

---

## Relationship Between SegmentedAddressSpace and MemoryBlock

They are **orthogonal** — they meet only at the `Address` object.

- `SegmentedAddressSpace` — pure address arithmetic; knows nothing about bytes or blocks
- `MemoryBlock` — a flat byte range with a decorated start address; knows nothing about segments

When `memory.getByte(addr)` is called:
1. `MemoryMapDB` finds the block by **flat offset** (`addr.getOffset()`)
2. Computes `offsetIntoBlock = addr.getOffset() - block.getStart().getOffset()`
3. Delegates to `FileBytesSubMemoryBlock` → `FileBytes` → `DBBuffer`

The segment portion of a `SegmentedAddress` is **discarded** for block lookup. Addresses
`1234:0005` and `1000:2345` (both flat `0x12345`) access the identical byte. The segment value
is preserved only for display and segment-relative arithmetic — it has no effect on which bytes
you get.

---

## Unique Address Keys — AddressMapDB

Every `Address` in Ghidra has a unique `long` database key, managed by `AddressMapDB`. This key
is used in **all** program database tables (code, symbols, references, comments, etc.) to
cross-reference locations.

### Encoding

```
bits 63–60  (4 bits):  type tag
bits 59–32  (28 bits): base segment index  (into a table of 32-bit base addresses)
bits 31–0   (32 bits): offset within that 4 GB segment
```

Type tags:

| Tag | Name | Meaning |
|---|---|---|
| `0x0` | `OLD_ADDRESS_KEY_TYPE` | Legacy encoding (backwards compat) |
| `0x1` | `ABSOLUTE_ADDR_TYPE` | Ignores image base; used by memory map |
| `0x2` | `RELOCATABLE_ADDR_TYPE` | Most common; moves with image base |
| `0x3` | `REGISTER_ADDR_TYPE` | Register space |
| `0x4` | `STACK_ADDR_TYPE` | Stack space (includes namespace for uniqueness) |
| `0x5` | `EXTERNAL_ADDR_TYPE` | External space |
| `0x6` | `VARIABLE_ADDR_TYPE` | Variable space |
| `0x7` | `HASH_ADDR_TYPE` | 60-bit hash space (no base segment) |
| `0xF` | `NO_ADDR_TYPE` | Null / invalid address |

For RAM addresses: the base segment covers the top 32 bits of the flat offset; the low 32 bits
are the within-segment offset. Every address in a 64-bit space maps to a unique `long`.

This encoded `long` is the single canonical identity used across the entire program database —
not a pointer into `FileBytes`, but the cross-reference key for every instruction, data item,
symbol, reference, and comment.
