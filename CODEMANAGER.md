# CodeManager — How Code, Data, and Undefined Are Classified

Source: [CodeManager.java](Ghidra/Framework/SoftwareModeling/src/main/java/ghidra/program/database/code/CodeManager.java)

## The Type Hierarchy

```
CodeUnit (interface)
├── Instruction  → InstructionDB
└── Data         → DataDB
```

Both live under the `CodeUnit` abstraction. `CodeManager` is the implementation backing
the `Listing` interface for all code unit queries.

Key interfaces and implementations:
- [CodeUnit.java](Ghidra/Framework/SoftwareModeling/src/main/java/ghidra/program/model/listing/CodeUnit.java) — base interface: labels, symbols, comments, mnemonic, start/end address, register references, operand addresses
- [Instruction.java](Ghidra/Framework/SoftwareModeling/src/main/java/ghidra/program/model/listing/Instruction.java) — extends CodeUnit; adds flow, PCode, operand info
- [Data.java](Ghidra/Framework/SoftwareModeling/src/main/java/ghidra/program/model/listing/Data.java) — extends CodeUnit; adds data type, value, components
- [InstructionDB.java](Ghidra/Framework/SoftwareModeling/src/main/java/ghidra/program/database/code/InstructionDB.java)
- [DataDB.java](Ghidra/Framework/SoftwareModeling/src/main/java/ghidra/program/database/code/DataDB.java)
- [CodeManager.java](Ghidra/Framework/SoftwareModeling/src/main/java/ghidra/program/database/code/CodeManager.java) - Class to manage database tables for data and instructions. Contains CommentsDBAdapter, DataDBAdapter, InstDBAdapter, CommentHistoryAdapter, ProgramDB, PrototypeManager, DBObjectCache<CodeUnitDB>, ProgramDataTypeManager, EquateTable, SymbolManager, ProgramContext, ReferenceManager, PropertyMapManager, IntPropertyMapDB

## Two DB Tables, One Synthesized Type

`CodeManager` maintains two separate B-Tree tables keyed by address:
- **`instAdapter`** — defined instructions: `address → (ProtoID, flags)`
- **`dataAdapter`** — defined data: `address → (DataType ID, length info)`

**"Undefined" is not stored anywhere.** It is synthesized on-the-fly as a `DataDB` instance
backed by the `DefaultDataType` singleton. The `??` mnemonic (`db ??` in the listing) comes
from `DefaultDataType.getMnemonic()` returning `"??"`.

```java
// DataDB.isDefined()
public boolean isDefined() {
    return !(dataType instanceof DefaultDataType);  // false = undefined
}
```

## `getCodeUnitAt()` — The Full Lookup

```java
// CodeManager.java lines 857-889
CodeUnit getCodeUnitAt(long addr) {
    // 1. Shared LRU object cache (1000 entries) — avoids DB hit if recently accessed
    CodeUnitDB cu = cache.get(addr);
    if (cu != null) return cu;

    // 2. Query instAdapter B-Tree
    InstructionDB inst = getInstructionDB(addr);   // instAdapter.getRecord(addr)
    if (inst != null) return inst;

    // 3. Query dataAdapter B-Tree
    DataDB data = getDataDB(addr);                  // dataAdapter.getRecord(addr)
    if (data != null) return data;

    // 4. Not in either table → synthesize undefined on-the-fly
    return getUndefinedAt(addrMap.decodeAddress(addr), addr);
}
```

There is no array, no bitmap, no unified index. The classification is entirely implicit:
- Instructions win (checked first)
- Defined data wins over undefined (checked second)
- Undefined is the fallback for anything not found in either table

The `DBObjectCache<CodeUnitDB>` (1000 entry LRU) sits in front of both tables as a single
unified cache. A cache hit short-circuits both B-Tree lookups.

`isUndefined()` makes the two-table structure explicit:

```java
// CodeManager.java lines 2640-2648
protected boolean isUndefined(Address address, long addr) {
    DBRecord rec = dataAdapter.getRecord(addr);
    if (rec == null) {
        rec = instAdapter.getRecord(addr);
    }
    if (rec != null) {
        return false;
    }
    // ...
}
```

Two lookups, absence in both = undefined.

## The Query API

| Method | Returns |
|--------|---------|
| `getCodeUnitAt(addr)` | Instruction → defined Data → synthesized undefined Data → `null` if not in memory |
| `getCodeUnitContaining(addr)` | Same, but also matches if a multi-byte unit *spans* the address |
| `getInstructionAt(addr)` | `Instruction` or `null` — never returns Data |
| `getDataAt(addr)` | Defined `Data`, synthesized undefined `Data`, or `null` if not in memory |
| `getUndefinedDataAt(addr)` | Only returns if truly undefined; `null` otherwise |
| `isUndefined(start, end)` | `true` only if no instructions and no defined data exist in the range |

Key distinctions:
- `getDataAt()` always returns something for in-memory addresses (even if undefined)
- `getInstructionAt()` returns `null` for anything that isn't an instruction
- `getCodeUnitAt()` never returns `null` for a valid in-memory address

## Initialized vs. Uninitialized Memory — A Separate Axis

"Undefined" (no DataType applied) and "uninitialized" (no backing bytes) are **orthogonal
concepts** from different layers of the model.

**Initialized** (`MemoryBlock.isInitialized() == true`): actual bytes exist in storage;
`getByte()` works. Examples: `.text`, `.data` segments.

**Uninitialized** (`MemoryBlock.isInitialized() == false`): no byte storage at all;
`getByte()` throws `MemoryAccessException("Attempted to read from uninitialized block")`.
Examples: `.bss`, stack reservation regions.

`CodeManager` **does not check** whether a memory block is initialized. It only checks the
two DB tables. Both initialized and uninitialized in-memory addresses return a synthesized
undefined `DataDB` when nothing is defined.

The full matrix:

| | Initialized (bytes exist) | Uninitialized (no bytes) |
|--|--|--|
| **Undefined** (no DataType) | `db ??` — bytes readable | `db ??` — `getByte()` throws |
| **Defined** (DataType applied) | `int 0x1234`, `struct Foo`, etc. | Theoretically possible; type defined, bytes unreadable |

`db ??` in the listing is **ambiguous** — you cannot tell from display alone whether bytes
are readable. To distinguish:

```java
// Is the byte readable?
MemoryBlock block = program.getMemory().getBlock(address);
boolean readable = block != null && block.isInitialized();

// Is a data type applied?
Data data = listing.getDataAt(address);
boolean typed = data != null && data.isDefined();
```

BSS segments are the canonical example: every address looks like `db ??` in the listing,
but `getByte()` throws on every one.

## Storage: B-Trees for CodeUnits, Flat Buffers for Bytes

These are two completely separate storage systems:

**B-Trees (`instAdapter` / `dataAdapter`)** — sparse, structured:
- Only addresses where something has been explicitly defined have a record
- Keyed on encoded address longs; lookups, range scans, and get-next/get-previous are O(log n)
- A 64-bit binary may have an enormous address space but only a few megabytes of records

**Flat buffers (`MemoryBlock` storage)** — dense, contiguous:
- `DBBuffer` (chunked buffer in the embedded DB) or `FileBytes` (original binary file contents)
- Accessed by offset; `getByte(addr)` translates address → buffer offset → direct read
- Closer to a flat byte array for the initialized regions

```
CodeUnit lookup (sparse):
  instAdapter / dataAdapter → B-Tree → "what is defined at this address"

Byte access (dense):
  MemoryBlock → DBBuffer / FileBytes → raw bytes at offset
```

When disassembling, both layers are used together: the B-Tree record provides the
`InstructionPrototype`, and the flat buffer provides the raw bytes that SLEIGH re-decodes on
demand to produce operand values, mnemonic text, and PCode.

The B-Tree design is necessary because a 64-bit binary has a 16 exabyte theoretical address
space. A flat array over that space would be impossible; the B-Tree is always sparse regardless
of address space size.


## Iteration: B-Tree Cursor, Not Repeated Point Lookups

Iterating through consecutive instructions (e.g., all instructions in a function) does **not**
perform N separate O(log n) point lookups. It uses a **B-Tree range scan with a cursor**.

`getCodeUnits(start, forward)` and `getInstructions(address, forward)` call
`instAdapter.getRecords(address, forward)` which opens a `RecordIterator` — a cursor
positioned at the start address that walks the B-Tree leaf nodes in order:

```java
// CodeManager.java line 2464-2467
public InstructionIterator getInstructions(Address address, boolean forward) {
    RecordIterator recIt = instAdapter.getRecords(address, forward);
    return new InstructionRecordIterator(this, recIt, forward);
}
```

`getCodeUnits()` merges **two** such cursors (one on `instAdapter`, one on `dataAdapter`)
via `CodeUnitRecordIterator`, picking whichever has the lower next address at each step to
yield a unified ordered stream.

Cost breakdown for iterating 500 consecutive instructions:
- **1 B-Tree seek** to position the cursor at the start address — O(log n)
- **500 cursor advances** through leaf nodes — O(1) amortized each (sequential leaf traversal)

This is meaningfully different from 500 independent point lookups, but still slower than a
raw array iteration — each step follows node pointers rather than incrementing an index, and
the LRU `cache.get(addr)` check still runs per record.

# DataDB and the DataType System

## DataDB — Instance vs. DataType — Specification

`DataDB` is the database-backed `CodeUnit` at a specific address. It holds:
- `DataType dataType` — the type specification (what bytes mean here)
- `DataType baseDataType` — the typedef-unwrapped base type (cached for efficiency) - this is for unwrapping datatypes which are typedef'd
- `Address` + `int length` — where it lives and how many bytes it covers (`length = -1` initially, computed lazily)

Multiple `DataDB` instances at different addresses can share the same `DataType` object.
DataType knows *how* to interpret bytes; DataDB knows *which* bytes.

`DataDB` also implements `MemBuffer` (inherited from `CodeUnitDB`), so when DataType methods
like `getValue(MemBuffer, settings, length)` are called, the DataDB passes itself — the DataType
reads bytes directly from program memory through it.

**Lazy length**: `DataDB` initializes `length = -1` and computes it on first `getLength()` —
constrained by the next defined code unit and the end of the containing memory block.

## DataType Sizing

| Category | How size is determined |
|---|---|
| Scalar (`int16`, `int32`, etc.) | Fixed constant from `getLength()` |
| Language-dependent (`long`, `pointer`) | Queried from `DataOrganization` (from CompilerSpec) at runtime |
| Structure/Union | Sum of component sizes (packed) or max(offset+length) across components |
| Array | `elementLength × count` |
| Dynamic (strings) | Returns `-1`; actual length specified at the instance level |
| Undefined | Always 1 byte |

## Scalar Types (int16, int32)

`AbstractIntegerDataType.getValue(MemBuffer buf, Settings settings, int length)`:

```java
byte[] bytes = new byte[size];
buf.getBytes(bytes, 0);                         // read from memory at this address
DataConverter dc = DataConverter.getInstance(
    ENDIAN.isBigEndian(settings, buf));         // endianness from settings or language
long val = dc.getValue(bytes, size);            // apply byte order
return new Scalar(size * 8, val, isSigned());   // wrap in Scalar with bit-width
```

`Scalar` is a value type — `long` plus bit-width and signedness metadata. For types wider than
8 bytes, `BigInteger` is returned instead.

`getRepresentation()` formats the `Scalar` as hex, decimal, octal, or binary depending on
`FormatSettingsDefinition` on the data instance.

## Structures

A `Structure` is a `Composite` holding an ordered list of `DataTypeComponent` objects:

```
struct MyStruct {
    int32 x;    // component: ordinal=0, offset=0, length=4
    int16 y;    // component: ordinal=1, offset=4, length=2
    int8  z;    // component: ordinal=2, offset=6, length=1
    // + 1 byte padding if alignment requires it
}               // total size = 8
```

`DataTypeComponent` fields: `getOrdinal()`, `getOffset()`, `getLength()`, `getDataType()`,
`getFieldName()`.

Size = offset of last component + its length, adjusted for alignment/packing. `StructureDB`
stores components in a DB table keyed by ordinal; offset is a stored column, not recomputed.

Lookup methods:
- `getComponentAt(offset)` — component whose start == offset
- `getComponentContaining(offset)` — component overlapping offset
- `getComponentsContaining(offset)` — list (needed for bitfields, where multiple components share the same byte)

## Enums

Enums store bidirectional name↔value mappings:

```java
long getValue(String name)      // "RED" → 1
String getName(long value)      // 1 → "RED"
String[] getNames(long value)   // multiple names for same value
void add(String name, long value)
```

Size is 1, 2, 4, or 8 bytes (`getMinimumPossibleLength()` computes the smallest power-of-2
that fits all values). Signedness is derived from stored values — if any value is negative,
`isSigned()` returns true. `getRepresentation()` returns the name string if found, otherwise
falls back to the numeric value.

## Pointers and Address Types

`PointerDataType` stores:
- `DataType referencedDataType` — what it points to (`null` = `void*`)
- `int length` — pointer size in bytes, or `-1` for "use DataOrganization"

When `length == -1`, the actual size is resolved from
`dataTypeManager.getDataOrganization().getPointerSize()` — so the same pointer type adapts to
16/32/64-bit depending on the program's architecture.

Specialized fixed-size variants: `Pointer16DataType`, `Pointer32DataType`, `Pointer64DataType`,
plus `Pointer24DataType` etc. for exotic architectures, and `SegmentedCodePointerDataType` for
x86 real-mode far pointers (encodes both segment and offset).

`getValue()` reads pointer bytes, applies endianness, and constructs an `Address` object.
Which address space it resolves into is controlled by `AddressSpaceSettingsDefinition` on the
pointer's settings — default is the program's default address space (`ram`).

## DataTypeManager

The registry that owns all type definitions:

| Manager | Backed by | Mutable? |
|---|---|---|
| `BuiltInDataTypeManager` | static singleton | no |
| `ProgramDataTypeManager` | program DB | yes |
| `ArchiveDataTypeManager` | `.gdt` file | yes |

Types are organized in a category hierarchy (like folders). Each type has a `UniversalID` for
cross-archive identity. `resolve(DataType, ConflictHandler)` ensures a type is owned by this
manager, copying and deduplicating as needed. `getDataOrganization()` returns the
compiler/arch-specific sizing rules (pointer size, int size, alignment) that language-dependent
types consult.

## End-to-End: getValue() on a DataDB

```
user calls data.getValue()
  DataDB.getValue()
    → dataType.getValue(this, settings, length)   // DataDB passes itself as MemBuffer
        → buf.getBytes(bytes, 0)                  // reads from program memory
        → DataConverter applies endianness
        → returns Scalar / BigInteger / Address / String depending on type
```

---
