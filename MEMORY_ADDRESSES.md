# Memory, Addresses, and Loading in Ghidra

## Matt's Summary

A Sleigh definition defines AddressSpaces. AddressSpaces are coordinate systems. For example, in DOS environments, the RAM is a fixed 21-bit address space, in NES environments it is a 16-bit space.

When bytes are loaded, a MemoryBlock is created to hold the bytes and they placed in this coordinate system. So you could load code into offset 0x1000 and create a memory block in RAM at offset 0x1000 with size 0x300. You could then assign uninitialized data at 0x2000 of size 0x1000 based on the information in MZ loader.

You can create additional data outside of RAM. For example, you can create a new overlay space which maps to the RAM space, by creating a new AddressSpace with a unique key, then adding a MemoryBlock into that AddressSpace. 

There are other types of AddressSpaces such as stacks, DOS headers, etc.

IDA "linear addresses" or unique addresses are made by combining space and offset, e.g. (RAM, 0x1234) or (BANK1, 0x1000). This would be done by using the first 32-bits to define the address space and the second 32-bits to define the offset. Although technically this isn't how Ghidra does it; the top 32-bits refers to a "base ID" which is an "AddressMap" DB table:

```
Base ID 0  →  ("ram",   segment=0)  →  ram:0x0000_0000   .. ram:0xFFFF_FFFF
Base ID 1  →  ("ram",   segment=1)  →  ram:0x1_0000_0000 .. ram:0x1_FFFF_FFFF
Base ID 2  →  ("BANK0", segment=0)  →  BANK0:0x0000_0000 .. BANK0:0xFFFF_FFFF
Base ID 3  →  ("BANK1", segment=0)  →  BANK1:0x0000_0000 .. BANK1:0xFFFF_FFFF
```

A bit more about the AddressMapDB - it exists to map the combination of 64-bit addresses plus address space identifier to a 64-bit long used by the Database (`DBHandle`) using `long`s. It turns out you can't encode all possible 64-bit addresses to a database handle. If the btree used 80-bits, you probably wouldn't need the address map, although it does have another benefit by handling "image base rebasing".

Addresses may not need an underlying MemoryBlock. For example, Register addresses (e.g. RBX is at `register:0x08`), stack addresses, or external addresses like `printf` which aren't in the program. There are also valid Addresses that exist in gaps between blocks, so getByte() might throw an exception but the `Address` is legal. A valid `Address` just means "a well-formed coordinate"; backing bytes are optional.


## Class Ownership Diagram

```
ProgramDB
  ├─ addrMap: AddressMapDB          (private field; passed to every manager)
  │    └─ encodes Address → long key for all DB tables
  │
  ├─ managers[MEMORY_MGR=0]: MemoryMapDB   (implements Memory + ManagerDB)
  │    ├─ allAddrSet: AddressSet           (union of all block ranges; for overlap checks)
  │    └─ blocks: List<MemoryBlockDB>      (sorted by start address)
  │         └─ subBlocks: List<SubMemoryBlock>
  │              └─ FileBytesSubMemoryBlock
  │                   ├─ fileBytesOffset: long
  │                   └─ fileBytes: FileBytes
  │                        ├─ originalBuffers: DBBuffer[]   (unmodified file bytes)
  │                        └─ layeredBuffers:  DBBuffer[]   (shadow/patch layer)
  │
  ├─ managers[...]: CodeManager
  ├─ managers[...]: SymbolManager
  ├─ managers[...]: FunctionManagerDB
  └─ ...  (15 total managers, all receive addrMap at construction)

AddressFactory (ProgramAddressFactory)
  ├─ spaces from Language (defined in SLEIGH .ldefs / .sinc):
  │    ├─ ram    (TYPE_RAM, default)
  │    ├─ register  (TYPE_REGISTER)
  │    └─ unique    (TYPE_UNIQUE)
  └─ spaces added by ProgramAddressFactory:
       ├─ OTHER_SPACE     (TYPE_OTHER,    64-bit)
       ├─ EXTERNAL_SPACE  (TYPE_EXTERNAL, 32-bit)
       ├─ stack space     (TYPE_STACK,    from CompilerSpec)
       ├─ HASH_SPACE      (TYPE_HASH,     60-bit)
       ├─ VARIABLE_SPACE  (TYPE_VARIABLE, 32-bit)
       └─ ProgramOverlayAddressSpace  (one per overlay block, created dynamically)

Address  =  (AddressSpace, long offset)
  └─ SegmentedAddress  (subclass; adds int segment for display only)
```

---

## ProgramDB — The Root Owner

[`ProgramDB`](Ghidra/Framework/SoftwareModeling/src/main/java/ghidra/program/database/ProgramDB.java)
is the concrete implementation of the `Program` interface. It is the root of the entire in-memory
and on-disk model of a binary.

Two fields are central to the memory system:

**`AddressMapDB addrMap`** (private field, line 205) — created first, before any manager. It is
the single source of truth for converting `Address` objects to `long` database keys. Every manager
receives it at construction and uses it to store and look up addresses in DB tables.

**`MemoryMapDB`** (stored as `managers[MEMORY_MGR=0]`) — the implementation of the `Memory`
interface. It owns all memory blocks and their bytes. Being a `ManagerDB`, `ProgramDB` can
lifecycle-manage it (open, close, invalidate cache, upgrade schema).

---

## Address Spaces

An `AddressSpace` is a **fixed-size coordinate system** — a numbered range `[0, 2^size - 1]` in
which addresses live. It is **not** a container of bytes. Think of it as a grid: memory blocks
are placed at positions on the grid, but the grid itself has no content.

### How Address Spaces Are Defined

Address spaces originate in SLEIGH processor definitions, compiled at language build time:

```
# ia.sinc (x86 shared definitions)
define space ram      type=ram_space size=$(SIZE) default;
define space register type=register_space size=4;
```

- `size` is in **bytes** (so `size=4` → 32-bit address space, max offset `0xFFFFFFFF`)
- `default` marks the space instructions address by default
- The size is **fixed at compile time** — it never grows or shrinks

When a `Program` is created, [`ProgramAddressFactory`](Ghidra/Framework/SoftwareModeling/src/main/java/ghidra/program/database/ProgramAddressFactory.java)
takes the language's spaces and adds several more:

| Space | Type | Size | Source |
|---|---|---|---|
| `ram` | `TYPE_RAM` | language-defined | SLEIGH `.ldefs` |
| `register` | `TYPE_REGISTER` | language-defined | SLEIGH `.ldefs` |
| `unique` | `TYPE_UNIQUE` | language-defined | SLEIGH `.ldefs` |
| `OTHER_SPACE` | `TYPE_OTHER` | 64-bit | `ProgramAddressFactory` |
| `EXTERNAL_SPACE` | `TYPE_EXTERNAL` | 32-bit | `ProgramAddressFactory` |
| stack space | `TYPE_STACK` | from `CompilerSpec` | `ProgramAddressFactory` |
| `HASH_SPACE` | `TYPE_HASH` | 60-bit | `ProgramAddressFactory` |
| `VARIABLE_SPACE` | `TYPE_VARIABLE` | 32-bit | `ProgramAddressFactory` |

### Address Space Types

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

### Overlay Address Spaces

When bank-switched or otherwise overlapping memory regions exist, a new
`ProgramOverlayAddressSpace` is created **per overlay block**. Each overlay wraps a base space
(always a `TYPE_RAM` space) and covers the same numeric offset range, but is a completely
independent `AddressSpace` object with its own name.

```java
// ProgramAddressFactory.java:180
return new ProgramOverlayAddressSpace(key, overlayName, baseSpace, getNextUniqueID(),
    overlayRegionSupplier, this);
```

Result: `BANK0`, `BANK1`, etc. each become their own named spaces listed in
`ProgramAddressFactory.getAllAddressSpaces()`. There is no shared "overlay space" — there are N
independent overlay spaces, one per bank.

`OverlayAddressSpace` key methods:
- `getOverlayedSpace()` → the base space (`ram`)
- `getPhysicalSpace()` → the base space's physical space
- `translateAddress(addr)` → converts an overlay address to the equivalent base-space address

### Segmented Address Space (x86 Real Mode)

For DOS programs, `x86:LE:16:Real Mode` defines a `SegmentedAddressSpace` — a 21-bit space
(`REALMODE_SIZE = 21`, max flat offset `0x10FFEF`). 
Matt's note - maximum unique address is 0xFFFFF and it's a 20-bit physical address bus. 0xFFFF:FFFF is 0xFFFF0+0xFFFF=0x10FFEF which is 21-bits, but it wraps around modulo 1MB to 0x0FFEF.

Real-mode address arithmetic:
```
flat_offset = segment * 16 + segment_offset
```

Multiple `seg:off` pairs alias the same flat offset — e.g. `1234:0005` and `1000:2345` both map
to flat `0x12345`. Ghidra stores and compares by flat offset internally; the segment value is
carried in `SegmentedAddress.segment` for display and segment-relative arithmetic only.

Key classes:
- [`SegmentedAddressSpace`](Ghidra/Framework/SoftwareModeling/src/main/java/ghidra/program/model/address/SegmentedAddressSpace.java)
  — `getFlatOffset(seg, off)`, `getAddress(int seg, int off)`, `getAddressInSegment(flat, preferredSeg)`
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

## What Is an Address?

`Address` is an interface representing a single-byte location in a program:

```
Address = (AddressSpace, long offset)
```

- **`AddressSpace`** — which coordinate system the address lives in. Two addresses with the same
  numeric offset in different spaces are **completely unrelated**.
- **`long offset`** — the byte position within that space. Called the "flat offset" —
  `Address.getOffset()` always returns this single linear number with no encoding, regardless of
  whether the space is segmented, overlaid, etc.

There is **no size** in an `Address`. It identifies one byte location, not a range.

`SegmentedAddress` is the only notable subclass: it extends `GenericAddress` and adds an
`int segment` field purely for display and segment-relative arithmetic. The underlying `offset`
is still the flat value `segment * 16 + segmentOffset`.

### Address Equality

Two `Address` objects are equal when **both** their flat offset **and** their `AddressSpace` are
equal. For overlay spaces, `AddressSpace.equals()` uses the overlay's `orderedKey` (its name),
so `BANK0:0x8000` and `BANK1:0x8000` are distinct addresses even though their offsets are
identical.

### How Address Objects Are Constructed During Disassembly
The answer is: AddressSpace is the factory for Address objects, and the right AddressSpace is always already in hand — it was established at language load time and never changes.

The SLEIGH language defines the attributes of the address space. Most languages are Generic Address Spaces, while special attributes `"segmented"` and `"protected"` to created `SegmentedAddressSpace` and `ProtectedAddressSpace`. When the SLEIGH lanuage is being decoded inside `SleighLanguage.parseSpaces()`, the "ram" address space is constructed and put inside a `LinkedHashMap<String, AddressSpace> spacetable`. This is exposed to the entire Ghidra application through `currentProgram.getAddressFactory()` with methods like `.getDefaultAddressSpace()` and `getStackSpace()`. Within this list, `"ram"` maps to a SegmentedAddressSpace for x86 real-mode, or a GenericAddressSpace for everything else. This decision is made once at language load. After that, any code that needs to make an address in "ram" just does:

```java
spacetable.get("ram").getAddress(offset)
```

Two separate questions
1. The instruction's own address — this is trivial. The disassembler starts with an Address that the caller already provides (from a MemBuffer). blockMemBuffer.getAddress() returns the current address, and as the disassembler advances instruction-by-instruction it calls addr.add(inst.getLength()) — pure arithmetic on the existing Address, which preserves the space. No construction happens.

2. Operand addresses (e.g., the target of a jump, or a register reference) — this is where AddressSpace acts as a factory.

The factory pattern: `AddressSpace.getAddress(long)`
`Address` objects are never constructed directly by callers. The `AddressSpace` is the factory:

```java
// GenericAddressSpace.getAddress()
public Address getAddress(long offset) {
    return new GenericAddress(this, offset);   // → GenericAddress
}

// SegmentedAddressSpace.getAddress()
public SegmentedAddress getAddress(long byteOffset) {
    return new SegmentedAddress(this, byteOffset);  // → SegmentedAddress
}
```

The correct concrete class is produced automatically by whichever `AddressSpace` subclass you already hold. Callers never instanceof-check or pick a class — they just call `.getAddress(offset)` on the space they have.


---

## Absolute Address Keys — AddressMapDB

Every `Address` in Ghidra has a unique `long` database key, managed by
[`AddressMapDB`](Ghidra/Framework/SoftwareModeling/src/main/java/ghidra/program/database/map/AddressMapDB.java).
This key is used in **all** program database tables (code, symbols, references, comments, data
types, etc.) to cross-reference locations. It is the single canonical identity for any point in
a program.

The AddressMapDB long key is typically unused in most interfaces. That encoded long is strictly an internal database cross-reference key — it lives in DB table rows to link records together (e.g. "this symbol is at address key 0x100004000"). It is not used for byte lookup.

### Encoding

```
bits 63–60  (4 bits):  type tag
bits 59–32  (28 bits): base segment index  (into addrToIndexMap, keyed by Address)
bits 31–0   (32 bits): offset within that 4 GB segment
```

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

### How Overlay Addresses Get Distinct Keys

Overlay spaces reuse `ABSOLUTE_ADDR_TYPE` (tag `0x1`). What distinguishes them is the
**base segment index** in bits 59–32.

`encodeAbsolute()` calls `getBaseAddressIndex(space, normalizedBaseOffset)`, which does:

```java
Address tBase = space.getAddressInThisSpaceOnly(normalizedBaseOffset);
Integer tIndex = addrToIndexMap.get(tBase);  // HashMap<Address, Integer>
```

Because `Address.equals()` incorporates `AddressSpace` identity, `BANK0:0x0000` and
`BANK1:0x0000` produce different `tBase` objects → different map entries → different base
indexes → different encoded `long` values:

```
BANK0:0x8000  →  0x1000_0000_0000_0000 | (N << 32) | 0x8000
BANK1:0x8000  →  0x1000_0000_0000_0000 | (M << 32) | 0x8000   (M ≠ N)
```

---

## Memory Blocks

A memory block is a contiguous named range of bytes at a specific location in an address space.

### MemoryBlockDB

[`MemoryBlockDB`](Ghidra/Framework/SoftwareModeling/src/main/java/ghidra/program/database/mem/MemoryBlockDB.java)
is the concrete implementation. It stores:

```java
private Address startAddress;  // absolute position in the address space
private long    length;        // byte count
```

From these two fields it can answer `getStart()`, `getEnd()`, `getSize()`, and `contains(addr)`.
It does **not** know about neighboring blocks — that knowledge lives in `MemoryMapDB.blocks`
(the sorted list).

Byte addresses within a block are **never stored individually**. Given a block starting at
`startAddress` with `length` bytes, the address of byte at index `i` is simply:

```
address_of_byte_i = startAddress + i   (implicit arithmetic)
```

### Sub-Blocks and Byte Storage

Each `MemoryBlockDB` contains one or more `SubMemoryBlock` objects that back the actual bytes:

| Sub-block type | Content |
|---|---|
| `FileBytesSubMemoryBlock` | Bytes from a loaded file (`FileBytes`) |
| `ByteMappedSubMemoryBlock` | Redirects reads to another address range |
| `BitMappedSubMemoryBlock` | Bit-mapped projection |
| `UninitializedSubMemoryBlock` | No backing bytes (BSS-style) |
| `BufferSubMemoryBlock` | Raw `DBBuffer` bytes (patch/scratch) |

**`FileBytesSubMemoryBlock`** is by far the most common for loaded programs. It stores:
- `FileBytes fileBytes` — reference to the owning `FileBytes` object
- `long fileBytesOffset` — byte offset within `FileBytes` where this block's data starts

Byte access:
```java
getByte(offsetInMemBlock):
    return fileBytes.getModifiedByte(fileBytesOffset + (offsetInMemBlock - subBlockOffset));
```

### FileBytes

[`FileBytes`](Ghidra/Framework/SoftwareModeling/src/main/java/ghidra/program/database/mem/FileBytes.java)
is the primary container for raw loaded bytes. It uses a dual-buffer design:

| Field | Type | Purpose |
|---|---|---|
| `originalBuffers` | `DBBuffer[]` | Unmodified bytes from the file (read-only) |
| `layeredBuffers` | `DBBuffer[]` | Shadow/copy-on-write layer for patches |
| `fileOffset` | `long` | Offset in source file (nonzero for embedded files) |
| `size` | `long` | Total byte count |
| `filename` | `String` | Source file name |

`getOriginalByte()` always returns the original file byte. `getModifiedByte()` returns the
patched value if one exists, otherwise the original. Relocations applied during load go into
the layered buffers, preserving the original bytes permanently.

Each `DBBuffer` wraps a `ChainedBuffer` that spreads bytes across fixed-size database pages.
Max buffer size is **1 GB** (`MAX_BUF_SIZE = 1_000_000_000`); larger files get multiple
`DBBuffer` entries.

---

## Adding a Memory Block to a Program

When a loader calls `memory.createInitializedBlock(name, startAddr, fileBytes, offset, length)`,
the following chain executes:

```
memory.createInitializedBlock(name, startAddr, fileBytes, offset, length)
  └─ MemoryMapDB
       ├─ checkRange(startAddr, length)          ← throws MemoryConflictException if overlap
       ├─ [if overlay] createOverlaySpace()      ← creates new ProgramOverlayAddressSpace
       │                                            startAddr is rewritten into overlay space
       └─ MemoryMapDBAdapterV3.createFileBytesBlock()
            ├─ updateAddressMapForAllAddresses(startAddr, length)
            │    └─ addrMap.getKeyRanges(addrSet, true)   ← allocates DB key ranges for full span
            ├─ createMemoryBlockRecord(name, startAddr, length, flags)
            │    └─ stores addrMap.getKey(startAddr) and length  ← only start+length, not per-byte
            └─ creates SUB_TYPE_FILE_BYTES record
                 ├─ links to FileBytes row by ID
                 └─ stores fileBytesOffset
```

**The address space is chosen by the caller** — whatever space the `startAddr` lives in becomes
the block's space. For a normal block, the loader picks an address in `ram`. For an overlay
block, `MemoryMapDB` creates a new overlay space and rewrites `startAddr` into that space before
storing the record.

**Blocks cannot overlap.** `checkRange()` consults `allAddrSet` (a union of all existing block
ranges) and throws `MemoryConflictException` if the new range intersects any existing one.
Overlay blocks bypass this check because their addresses are in a distinct space — `BANK0:0x8000`
and `ram:0x8000` never intersect.

### Address Space vs. Memory Block — They Are Orthogonal

The address space is a fixed coordinate grid. The memory block is a byte range placed at a
position on that grid. The space does not grow when blocks are added; blocks are simply placed
at chosen positions within the existing fixed-size space.

When `memory.getByte(addr)` is called:
1. `MemoryMapDB` binary-searches `blocks` by address (via `Address.compareTo`, which includes space identity)
2. `block.contains(addr)` confirms the candidate block — this explicitly calls `addr.hasSameAddressSpace(block.getStart())`, returning false if the spaces differ
3. Computes `offsetIntoBlock = addr.subtract(block.getStart())` (validated to be in-range)
4. Delegates to `FileBytesSubMemoryBlock` → `FileBytes` → `DBBuffer`

`getByte` works with **any** memory space — RAM, overlay, OTHER, etc. The `Address` you pass
determines which block is found. `BANK0:0x8000` finds only the block in the `BANK0` overlay
space; `ram:0x8000` finds the block in `ram`. Two blocks at the same numeric offset in different
spaces are completely isolated from each other.

For `SegmentedAddressSpace`, the segment portion of a `SegmentedAddress` is **discarded** for
block lookup — only the flat offset matters. `1234:0005` and `1000:2345` (both flat `0x12345`)
access the identical byte.

---

## The Memory Map

`MemoryMapDB` maintains the complete picture of all memory in a program:

- **`List<MemoryBlockDB> blocks`** — sorted by start address; binary-searched for address lookup
- **`AddressSet allAddrSet`** — union of all block address ranges; used for fast overlap detection

Each block has:
- A name (e.g. `CODE_0`, `DATA`, `.text`)
- A start address (including its address space)
- A length
- Flags: read/write/execute, initialized/uninitialized, overlay
- Backing bytes (via sub-blocks)

The memory map is what the Ghidra Memory Map window shows — each row is one `MemoryBlockDB`.

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
   - DOS header dumped into `OTHER_SPACE` as block `HEADER` (non-addressable auxiliary space)

5. **Apply relocations** — fixup segment values in the loaded image; writes go into the layered
   buffers, preserving original bytes

6. **Detect segment boundaries** — `adjustSegmentStarts()` scans the first 16 bytes of each
   block for `FAR_RETURN_OPCODE`; splits/merges blocks for compiler stack-switching thunks

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

All blocks live in the 21-bit `ram` (SegmentedAddressSpace). No overlays are created by
`MzLoader` itself — if the DOS program uses bank-switched overlays, those would be added
separately. The flat offset is the only value used for block lookup; the segment portion of any
`SegmentedAddress` is strictly for display and segment-relative arithmetic.

---

## How ConstantPropagationAnalyzer Resolves Segmented References

This traces the exact path for code like:

```asm
MOV DS, 0xA000
MOV AX, DS:[0F00]    ← Ghidra should create a reference to A000:0F00 and a 2-byte Data there
```

### Phase 1: DS=0xA000 Enters the Analyzer

`MzLoader` writes `DS=0xA000` into `ProgramRegisterContextDB` at load time (persistent DB).
When `ConstantPropagationAnalyzer` runs, `SymbolicPropogator`'s constructor copies all
persisted register values from `program.getProgramContext()` into an ephemeral `regVals`
HashMap. If `MOV DS, 0xA000` also appears in code, the `PcodeOp.COPY` handler writes it in
the same way. From that point the symbolic executor treats DS as the constant 0xA000.

### Phase 2: Resolving the LOAD Operand

`SymbolicPropogator.applyPcode()` processes the `MOV AX, DS:[0F00]` instruction. SLEIGH
emits this as a `PcodeOp.LOAD` with a `SEGMENTOP`. The LOAD handler:

```java
val1 = vContext.getValue(DS_varnode)      // → Varnode(constant_space, 0xA000)
val2 = vContext.getValue(offset_varnode)  // → Varnode(constant_space, 0x0F00)
vt   = vContext.getVarnode(val1, val2, size=2, evaluator)  // → resolves flat address
```

Inside `VarnodeContext.getVarnode(Varnode space, Varnode offset, int size, ContextEvaluator)`:

```java
// Both DS (0xA000) and offset (0x0F00) are known constants:
spaceID = (int) space.getOffset()   // = 0xA000  ← segment register value used as spaceID
valbase = offset.getOffset()        // = 0x0F00
return getVarnode(spaceID, valbase, size)
```

Inside `VarnodeContext.getVarnode(int spaceID, long offset, int size)`:

```java
AddressSpace space = addrFactory.getAddressSpace(0xA000)  // → SegmentedAddressSpace "ram"
Address target = space.getTruncatedAddress(0x0F00, true)  // → SegmentedAddress(flat=0xA0F00)
return new Varnode(target, 2)
```

`SegmentedAddressSpace.getTruncatedAddress(0x0F00)` computes flat = `0xA000 * 16 + 0x0F00 =
0xA0F00` and returns a `SegmentedAddress` displayed as `A000:0F00`.

**Key non-obvious design**: the segment register's value (`0xA000`) is threaded through PCode
data flow as a **spaceID** integer. `addrFactory.getAddressSpace(0xA000)` returns the `ram`
`SegmentedAddressSpace`, whose `getAddress()` then applies the segment formula.

### Phase 3: Reference and Data Creation

After resolving the Varnode, `addLoadStoreReference()` calls `makeReference()`, which:

1. Extracts `spaceID=0xA000, wordOffset=0x0F00` from the Varnode
2. Reconstructs `Address target = space.getAddress(0x0F00)` → `SegmentedAddress A000:0F00`
3. Calls `evaluator.evaluateReference()` — `ConstantPropagationContextEvaluator` returns `true`
4. Calls `instruction.addOperandReference(opIndex, A000:0F00, READ, ANALYSIS)`

Inside `ConstantPropagationContextEvaluator.evaluateReference()`:

```java
if (refType.isData()) {
    createPointedToData(aMgr, program, address, refType, dataType, size)
}
```

Which calls `createData()`:

```java
DataUtilities.createData(program, A000:0F00, Undefined2, -1,
    ClearDataMode.CLEAR_ALL_UNDEFINED_CONFLICT_DATA)
// → 2-byte Data item created at SegmentedAddress A000:0F00
```

### Full Call Chain

```
ConstantPropagationAnalyzer.analyzeLocation()
  → SymbolicPropogator.flowConstants()
      [copies DS=0xA000 from ProgramRegisterContextDB into ephemeral regVals]
      → applyPcode() per instruction
          case LOAD:
            vContext.getValue(DS_varnode)        → Varnode(const, 0xA000)
            vContext.getValue(offset_varnode)    → Varnode(const, 0x0F00)
            vContext.getVarnode(0xA000, 0x0F00, 2)
              → addrFactory.getAddressSpace(0xA000) → SegmentedAddressSpace
              → space.getTruncatedAddress(0x0F00)   → SegmentedAddress A000:0F00
              → new Varnode(A000:0F00, size=2)
            addLoadStoreReference(...)
              → makeReference(vt=Varnode(A000:0F00,2), READ)
                  → instruction.addOperandReference(A000:0F00, READ, ANALYSIS)
                  → evaluator.evaluateReference()
                       → createData(program, A000:0F00, Undefined2)
                            → DataUtilities.createData(...)
                                 → 2-byte Data at A000:0F00  ✓
```

### Key Classes

| Class | File | Role |
|-------|------|------|
| `ConstantPropagationAnalyzer` | `ghidra/app/plugin/core/analysis/` | Entry point; creates SymbolicPropogator |
| `SymbolicPropogator` | `ghidra/program/util/` | PCode symbolic executor; loads register state |
| `VarnodeContext` | `ghidra/program/util/` | Tracks symbolic Varnode values; resolves addresses |
| `ConstantPropagationContextEvaluator` | `ghidra/app/plugin/core/analysis/` | Callback; creates references and Data items |
| `DataUtilities` | `ghidra/app/util/` | `createData()` — places typed Data at an address |
