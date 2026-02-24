# Ghidra Framework/SoftwareModeling — Analysis Notes

> Generated: 2026-02-23. Re-read this file at the start of any session involving Framework/SoftwareModeling.

---

## Overview

**SoftwareModeling** is the heart of Ghidra's analysis infrastructure. It defines the **Program model** (the canonical API for all program data), the **DB-backed implementation** of that model, the **SLEIGH runtime engine** (disassembly and PCode lifting), and the **SLEIGH assembler** (mnemonic → bytes). Everything above it (Features, Decompiler, Processors) speaks the language defined here.

- **1,614 Java files** across ~80 packages
- **DB version**: 32 (as of Sep 2025); upgrades required from version 19+

### Major Subsystems

| Subsystem | Packages | Purpose |
|-----------|----------|---------|
| **Program Model (API)** | `ghidra/program/model/**` | Interfaces for all program data — the public contract |
| **Program Database** | `ghidra/program/database/**` | DB-backed implementations of the model |
| **SLEIGH Runtime** | `ghidra/app/plugin/processors/sleigh/**` | Loads `.sla`, disassembles bytes → Instructions → PCode |
| **SLEIGH Compiler** | `ghidra/pcodeCPort/**` | Java port of C++ compiler: `.slaspec` → `.sla` |
| **SLEIGH Grammar** | `ghidra/sleigh/grammar/**` | ANTLR3 lexer/parser + preprocessor for `.slaspec` |
| **Assembler** | `ghidra/app/plugin/assembler/**` | Reverse SLEIGH: mnemonic string → machine bytes |
| **Disassembler** | `ghidra/program/disassemble/**` | High-level disassembly coordinator |
| **Program Utilities** | `ghidra/program/util/**` | ProgramDiff, language translation, field locations, context |
| **PCode Formatting** | `ghidra/app/util/pcode/**` | Display formatting for PCode operations |
| **Graph Service** | `ghidra/service/graph/**` | AttributedGraph, GraphDisplay service interface |

---

## Program Model API (`ghidra/program/model/`)

The model packages define **interfaces only** — no database code. They are the universal language of all Ghidra code.

### Address Layer (`model/address/`)

| Class | Role |
|-------|------|
| `Address` | Immutable location in a program; arithmetic ops (`add`, `subtract`); `getOffset()`, `getAddressSpace()` |
| `AddressSpace` | Named typed space: RAM, register, stack, unique, external, constant. Types: `TYPE_RAM`, `TYPE_REGISTER`, `TYPE_STACK`, `TYPE_UNIQUE`, `TYPE_EXTERNAL`, `TYPE_VARIABLE`, `TYPE_OTHER`. Static instances: `EXTERNAL_SPACE`, `DEFAULT_REGISTER_SPACE` |
| `AddressFactory` | Creates addresses from strings or longs; `getDefaultAddressSpace()`, `getConstantSpace()`, `getUniqueSpace()`, `getStackSpace()` |
| `AddressSet` | Mutable collection of `AddressRange`s; red-black tree backing; `union()`, `intersect()`, `subtract()`, forward/backward iteration |
| `AddressRange` | Inclusive `[min, max]` in a single space; `contains(Address)`, `getLength()` |
| `AddressSetView` | Read-only view of an AddressSet (implemented by Memory, CodeBlock, etc.) |

**Non-obvious**: `AddressSet` selects linear vs. binary search algorithm at runtime based on set characteristics.

### Listing Layer (`model/listing/`)

The central program-level API.

| Interface | Role |
|-----------|------|
| `Program` | Root of everything: `getListing()`, `getMemory()`, `getSymbolTable()`, `getReferenceManager()`, `getDataTypeManager()`, `getFunctionManager()`, `getAddressFactory()`, `getLanguage()`, `getCompilerSpec()` |
| `Listing` | Code unit repository: `getCodeUnitAt(Address)`, `getCodeUnitContaining(Address)`, iterators with property filters |
| `CodeUnit` | Common base for Instruction and Data: `getMinAddress()`, `getMaxAddress()`, `getMnemonicString()`, comment access (EOL/PRE/POST/PLATE/REPEATABLE), `getSymbols()`, `getReferences()` |
| `Instruction` | Extends `CodeUnit` + `ProcessorContext`; `getPrototype()`, `getPcode()`, `getOpObjects(int)`, flow info, fallthrough address |
| `Data` | Extends `CodeUnit` + `Settings`; `getValue()`, `getDataType()`, `isDefined()`, `isConstant()`, `isVolatile()`, `hasStringValue()` |
| `Function` | Extends `Namespace`; `getEntryPoint()`, `getBody()`, `getSignature()`, `getStackFrame()`, calling convention, inline/thunk flags, function tags |
| `FunctionSignature` | Return type + parameters (no storage info; see `PrototypeModel` for that) |
| `Variable` | Named storage: `getName()`, `getDataType()`, `getVariableStorage()` |
| `Parameter` | Extends Variable; `getOrdinal()`, `isAutoParameter()`, `isForcedIndirect()`. Auto-params include `this` and `__return_storage_ptr__` |
| `StackFrame` | `GROWS_NEGATIVE`/`GROWS_POSITIVE`; `getFrameSize()`, `getLocalSize()`, `getParameterSize()` |

### Memory Layer (`model/mem/`)

| Interface | Role |
|-----------|------|
| `Memory` | Extends `AddressSetView`; `getByte(Address)`, `getBytes(...)`, `getBlock(Address)`, `getAllInitializedAddressSet()`, `getLoadedAndInitializedAddressSet()`, `getExecuteSet()`. Max block/binary: 16 GB |
| `MemoryBlock` | Named contiguous region; permissions (RWX); types: RAM, UNINITIALIZED, BIT_MAPPED, BYTE_MAPPED |
| `MemoryAccessException` | Thrown on read of uninitialized/unmapped memory |

### Language Layer (`model/lang/`)

| Interface | Role |
|-----------|------|
| `Language` | Processor definition: `getLanguageID()`, `isBigEndian()`, `parse(MemBuffer, ProcessorContext, inDelaySlot)` → `InstructionPrototype`, `getAddressFactory()`, `getRegister(String)` |
| `Register` | Named register with address + size; `getParentRegister()`, `getChildRegisters()`, overlap support |
| `RegisterManager` | `getRegister(String)`, `getRegister(Address)`, context register |
| `CompilerSpec` | Calling conventions, stack pointer, pointer size, data organization; `getDefaultCallingConvention()`, `getCallingConvention(String)` |
| `PrototypeModel` | Calling convention: parameter locations, return location, `getName()` |
| `PrototypeModelMerged` | Union of multiple calling conventions |
| `InstructionPrototype` | Decoded instruction: mnemonic, operand count/types, PCode ops, flow type, delay slots |

### PCode Layer (`model/pcode/`)

| Class | Role |
|-------|------|
| `Varnode` | Operand: `(address, size)` pair; `getSpace()`, `getOffset()`, `getSize()` |
| `PcodeOp` | One PCode operation: `getOpcode()`, `getNumInputs()`, `getInput(i)`, `getOutput()`, `getSeqnum()`. ~150 opcodes: LOAD, STORE, BRANCH, CBRANCH, BRANCHIND, CALL, CALLIND, RETURN, INT_ADD, INT_SUB, FLOAT_ADD, SUBPIECE, PIECE, etc. |
| `HighFunction` | Decompiler output per function: extends `PcodeSyntaxTree`; `getFunction()`, `getLocalSymbolMap()`, `getJumpTables()`, `getFunctionPrototype()` |
| `HighVariable` | Abstract SSA variable (union of Varnodes) |
| `HighLocal` / `HighParam` / `HighGlobal` / `HighConstant` | Concrete variable categories |
| `PcodeBlock` / `BlockGraph` | CFG: basic blocks, if/else/loop structures, `AddressSetView` |
| `Encoder` / `Decoder` | Streaming packed-binary serialization (used for decompiler communication) |

### Symbol Layer (`model/symbol/`)

| Interface | Role |
|-----------|------|
| `Symbol` | Name+address binding: `getAddress()`, `getName()`, `getPath()`, `getParentNamespace()`, `getSymbolType()`, `hasReferences()`, `getSource()` (DEFAULT/USER_DEFINED/IMPORTED/ANALYSIS) |
| `SymbolTable` | `createLabel()`, `createClass()`, `createNamespace()`, `getSymbol(Address)`, `getGlobalSymbols()`, `getLabelOrFunctionSymbol()`, dynamic symbol support |
| `Namespace` | Hierarchical container; types: GLOBAL, NAMESPACE, LIBRARY, CLASS, FUNCTION |
| `Reference` | From-address → to-address: `getFromAddress()`, `getToAddress()`, `getReferenceType()`, `getOperandIndex()`, `isPrimary()` |
| `ReferenceManager` | `addMemoryReference()`, `removeReference()`, `getReferencesFrom(Address)`, `getReferencesTo(Address)` |
| `RefType` | Rich enum: FLOW, JUMP, CALL, DATA, THUNK, PARAM, RETURN, READ, WRITE, etc. |
| `ExternalLocation` | External symbol with library name, location name, optional address |

### Data Type Layer (`model/data/`)

| Interface/Class | Role |
|-----------------|------|
| `DataType` | `getSize()`, `getAlignment()`, `getCategory()`, `isEquivalent(DataType)`, `clone(DTM)`, `copy(DTM)` |
| `DataTypeManager` | Repository: `getDataType(String)`, `resolve(DataType)`, `findDataTypes(String, List)`, category management, UniversalID for cross-archive refs |
| `Structure` | Fields at offsets: `add(DataType, name, comment)`, `insert(ordinal, ...)`, `replace(ordinal, ...)`, `getComponent(ordinal)`, flexible array support |
| `Union` | Overlapping fields |
| `Array` | `getDataType()`, `getNumElements()`, `getElementLength()` |
| `Pointer` | `getDataType()`, `getLength()` |
| `TypeDef` | Named alias; `getDataType()` |
| `Enum` | Name→value map; `getValue(String name)`, `getName(long value)`, `getNames()` |
| `FunctionDefinition` | Function prototype as a type |
| `DataOrganization` | Alignment, sizes of primitives for a compiler |
| `BuiltInDataType` | Marker for built-in types (void, bool, byte, word, char, etc.) |

### Other Model Packages

| Package | Key Content |
|---------|-------------|
| `model/block/` | `CodeBlock` (extends `AddressSetView`), `CodeBlockModel`, `BasicBlockModel`, `PartitionCodeSubModel`, `CallGraph` |
| `model/scalar/` | `Scalar` — 1–64 bit integer with signed/unsigned choice |
| `model/reloc/` | `Relocation` (status: UNKNOWN/SKIPPED/UNSUPPORTED/FAILURE/PARTIAL/APPLIED/APPLIED_OTHER), `RelocationTable` |
| `model/sourcemap/` | `SourceFile`, `SourceMapEntry`, `SourceMapManager` — source-level address mapping (added v29) |
| `model/correlate/` | Address correlation utilities for diff/merge |
| `model/gclass/` | GhidraClass support |

---

## Program Database (`ghidra/program/database/`)

DB-backed implementations of the model interfaces. Every manager is a `ManagerDB` that participates in `ProgramDB`'s lifecycle.

### ProgramDB — The Root

`ProgramDB` is version 32. Manages **15 subsystem managers** in a fixed order:

| Index | Manager | Role |
|-------|---------|------|
| 0 | `MemoryMapDB` | Memory blocks, file bytes |
| 1 | `CodeManager` | Instructions and data code units |
| 2 | `SymbolManager` | All symbol types |
| 3 | `NamespaceManager` | Namespace hierarchy |
| 4 | `FunctionManagerDB` | Functions, parameters, locals |
| 5 | `ExternalManagerDB` | External library locations |
| 6 | `ReferenceDBManager` | Code/data references |
| 7 | `ProgramDataTypeManager` | Data types (extends `DataTypeManagerDB`) |
| 8 | `EquateManager` | Equates (constant substitutions) |
| 9 | `BookmarkDBManager` | Bookmarks |
| 10 | `ProgramRegisterContextDB` | Processor register context values |
| 11 | `DBPropertyMapManager` | Generic property maps |
| 12 | `TreeManager` | Program organization trees |
| 13 | `RelocationManager` | Relocation records |
| 14 | `SourceFileManagerDB` | Source file/line mappings |

**Critical ordering rule**: Managers notify in **forward order** for `setProgram()`/`programReady()`, but **reverse order** for `deleteAddressRange()`/`moveAddressRange()`. Symbol/namespace managers must see function extents before code deletion.

### DBObjectCache Pattern

Used by every manager for memory-efficient caching:

```java
// Soft references (GC-able under memory pressure) + hard-cache (size-limited)
DBObjectCache<T> cache = new DBObjectCache<>(hardCacheSize);
// Objects stale-detect via global invalidateCount
// Thread-safe: synchronized put/get
```

Hard cache sizes: 1000 for CodeUnit, 100 for Symbol.

### Address Key Encoding (`AddressMapDB`)

Address spaces are encoded into long keys:

```
Upper 4 bits:   space type (RELOCATABLE=0x2, REGISTER=0x3, STACK=0x4, EXTERNAL=0x5, ...)
Next 28 bits:   space/segment ID
Lower 32 bits:  offset within space
```

Keys are **not sequential within a space** — never use key ordering for address ordering.

### Adapter Pattern (Schema Versioning)

Every subsystem uses versioned adapter classes:

```java
static XyzAdapter getAdapter(DBHandle handle, OpenMode mode, TaskMonitor monitor) {
    if (mode == CREATE) return new XyzAdapterVLatest(handle, true);
    try { return new XyzAdapterVLatest(handle, false); }
    catch (VersionException e) {
        XyzAdapter old = findReadOnlyAdapter(handle);
        if (mode == UPGRADE) return upgrade(handle, old);
        return old;
    }
}
```

Upgrade: iterate old records → transform → write to new table schema.

### Key DB Schemas

**Instructions** table: `[Address Key, ProtoID (int), Flags (byte)]`
- Flags: FALLTHROUGH_SET (0x01), FLOW_OVERRIDE (0x0e), LENGTH_OVERRIDE (0x70)

**Data** table: `[Address Key, DataType ID (long)]`
- DataType ID high byte = table ID, rest = primary key

**Functions**: versioned V0→V3; V3 adds auto-parameters + forced-indirect

**Symbols**: versioned V0→V4; V4 adds external symbol data indexing

**Relocations**: versioned V1→V6; V6 adds status, byte-length, original FileBytes

**Comments**: `[Address Key, Pre, Post, EOL, Plate]` strings

**Source map**: added at DB version 29 (`SourceMapAdapterV0`, `SourceFileAdapterV0`)

### Transaction & Locking

- Single shared `Lock` object across all managers
- `DomainObjectAdapterDB` base: `startTransaction()` / `endTransaction(commit)` / `rollback()`
- `recordChanges` flag gates `ProgramDBChangeSet` updates (for multi-user merge)
- Event flow: `manager detects change → updateChangeSet() → fireEvent(ProgramChangeRecord) → listeners`

### Object Refresh Pattern

Cached objects can become stale after undo/redo or external changes:
- Global `invalidateCount` counter increments on cache invalidation
- Each object caches `invalidateCount` at creation; `validate(Lock)` detects mismatch
- `refresh()` / `refresh(DBRecord)` reload state from DB

---

## SLEIGH Runtime Engine

### SleighLanguage — Loader and Runtime

`SleighLanguage` loads `.sla` binary format and provides the instruction parsing entry point.

**Initialization sequence:**
1. `readInitialDescription()` — parse `.pspec` XML
2. `decode(slaFile)` — load binary `.sla`:
   - `parseSpaces()` → build `spacetable` (LinkedHashMap)
   - `symtab.decode()` → load symbol table
   - `root = symtab.getGlobalScope().findSymbol("instruction").getDecisionNode()`
3. `loadRegisters()` — register all register symbols
4. `readRemainingSpecification()` — parse full `.pspec`
5. `initParallelHelper()` — load VLIW support if present

**Just-in-time recompilation**: If `.sla` is absent or stale (vs `.slaspec`), `SleighCompileLauncher` recompiles automatically.

**Instruction parsing entry point:**
```java
InstructionPrototype parse(MemBuffer buf, ProcessorContext context, boolean inDelaySlot)
// Creates SleighInstructionPrototype, caches by hashcode in ConcurrentHashMap
```

### DecisionNode — Pattern Matching Tree

Binary decision tree compiled from SLEIGH patterns:

```java
// Each node tests either instruction bits or context bits
int val = contextdecision
    ? walker.getContextBits(startbit, bitsize)
    : walker.getInstructionBits(startbit, bitsize);
return children[val].resolve(walker);  // descend

// At leaf (bitsize == 0): linear scan of DisjointPattern array
for (int i = 0; i < patternlist.length; i++)
    if (patternlist[i].isMatch(walker)) return constructlist[i];
throw new UnknownInstructionException();
```

### Constructor — Semantic Unit

One SLEIGH instruction pattern + semantics:
- `parent` — owning `SubtableSymbol`
- `operands[]` — `OperandSymbol` array
- `templ` — `ConstructTpl` (PCode template)
- `context[]` — `ContextChange` array (applied during resolution)
- `minimumlength` — minimum instruction bytes

### SleighInstructionPrototype — Decoded Instruction

Caches the matched Constructor tree for one instruction encoding:

**Resolution** (`resolve()`): recursive tree walk
1. `ParserWalker.baseState()` → start at root `ConstructState`
2. `root.resolve(walker)` → returns Constructor via DecisionNode
3. `ct.applyContext(walker)` → apply context changes
4. Recurse into each operand's subtable

**PCode generation** (`getPcode()`):
1. `ParserWalker` at root
2. `PcodeEmitObjects.build(constructor.getTempl())` → resolve `VarnodeTpl`s, emit `PcodeOp`s
3. `resolveRelatives()` → convert label indices to offsets
4. `resolveFinalFallthrough()`

**Flow analysis** (`walkTemplates()`): scans `OpTpl` tree detecting BRANCH/CALL/RETURN → produces `FlowType`

### PCode Template System

Three-layer template hierarchy (compile-time; resolved at decode time):

```
ConstructTpl  →  OpTpl[]  +  HandleTpl (result location)
                  ↓
OpTpl         →  opcode + VarnodeTpl output + VarnodeTpl[] inputs
                  ↓
VarnodeTpl    →  ConstTpl space + ConstTpl offset + ConstTpl size
```

`ConstTpl` types: `REAL` (constant), `HANDLE` (operand reference), `J_START`/`J_NEXT`/`J_NEXT2`/`J_RELATIVE` (label references).

### Context System

**`ContextCache`**: Converts between `RegisterValue` (BigInteger) and `int[]` words. LRU cache for conversion.

**`SleighParserContext`**: Per-instruction parse state:
- `addr` (inst_start), `nextInstrAddr` (inst_next), `next2InstAddr` (inst_next2)
- `context[]` — packed context bits
- `contextcommit` — list of pending future context changes
- `handleMap` — ConstructState → FixedHandle (resolved operand address)

**`ContextOp`**: Applies during Constructor resolution — evaluates a `PatternExpression` and writes bits into `context[num]` masked by `mask`.

### PCode Emission

Two `PcodeEmit` implementations:
- `PcodeEmitObjects` — produces `PcodeOp[]` array
- `PcodeEmitPacked` — encodes directly to binary (for decompiler protocol)

### pcodeCPort — Java Port of C++ SLEIGH Compiler

Java translation of the C++ compiler used to compile `.slaspec` → `.sla`. Key packages:

| Package | Content |
|---------|---------|
| `slgh_compile` | `SleighCompile` (1897 lines, main orchestrator), `PcodeCompile` (PCode generation from AST), `ConsistencyChecker` |
| `slghsymbol` | Compiler-time symbol table: `SymbolTable`, `Constructor`, `DecisionNode`, symbol types |
| `slghpattern` | `PatternBlock` (mask+value byte arrays), `DisjointPattern`, `CombinePattern`, `OrPattern`, `ContextPattern`, `InstructionPattern` |
| `slghpatexpress` | `TokenPattern` (variable-length field patterns), pattern expression evaluation |
| `semantics` | Compiler-time `ConstructTpl`, `OpTpl`, `VarnodeTpl` (serialized to `.sla`) |
| `space` | `AddrSpace`, `Translate` (abstract interface) |
| `address` | Compiler-time `Address` representation |

### ANTLR3 Grammar (`ghidra/sleigh/grammar/`)

| File | Role |
|------|------|
| `SleighPreprocessor` | Handles `#define`, `#include`, detects staleness by file timestamps |
| `SleighLexer` | ANTLR3-generated tokenizer |
| `AbstractSleighParser` | ANTLR3-generated parser base |
| `SleighParserRun` | Entry point |
| `Location` | Source file + line tracking for error reporting |

### Disassembler (`ghidra/program/disassemble/`)

`Disassembler` — high-level coordinator:
1. Get seed `DisassemblerContext`
2. For each address: `language.parse(memBuffer, context)` → `SleighInstructionPrototype`
3. Extract mnemonic, operands, flow → create `Instruction` DB object
4. Follow branches; update context
5. Commit context changes at transaction boundaries

`DisassemblerContextImpl` — proxy caching context changes, preventing conflicts between parallel flows.

---

## SLEIGH Assembler (`ghidra/app/plugin/assembler/`)

The assembler runs SLEIGH **backwards**: mnemonic string → machine bytes. This is a four-phase pipeline.

### Public API

```java
// Entry point
Assembler asm = Assemblers.getAssembler(program);  // cached by LanguageID
byte[] bytes = asm.assembleLine(address, "ADD R0, #0x10");
```

`Assemblers` factory caches `AssemblerBuilder` by `LanguageID`. `AssemblySelector` pluggable strategy for disambiguation.

### Four Build Phases (in `SleighAssemblerBuilder`)

**Phase 1 — Grammar Building** (`buildGrammar()`):
- Convert SLEIGH constructors into a context-free grammar
- Each production maps to one or more SLEIGH constructors

**Phase 2 — LALR(1) Parser** (`buildParser()`):
- LR(0) states → extended grammar → action/goto table
- Supports ambiguous grammars (multiple parse trees allowed)

**Phase 3 — Prototype Generation** (`AssemblyConstructStateGenerator`):
- Match parse tree against constructor semantics
- Prune constructors with conflicting operand patterns
- Handle hidden operands (in machine code but not mnemonic)

**Phase 4 — Machine Code Generation** (post-order tree walk):
- `AssemblyConstructState.resolve()` — leaves-up pattern building
- `RecursiveDescentSolver` — constraint solving per field
- `AssemblyContextGraph` — Dijkstra shortest path for context prefix sequences
- Re-disassemble result to validate (roundtrip check)

### Key Classes

| Class | Role |
|-------|------|
| `AssemblyGrammar` | CFG with SLEIGH constructor semantics per production |
| `AssemblyParser` | LALR(1); `parse(String)` → `Collection<AssemblyParseResult>` |
| `AssemblyPatternBlock` | `byte[] mask` + `byte[] vals` + offset; `combine()`, `fillMask()`, `shift()` |
| `AssemblyResolvedPatterns` | Successful encoding: instruction + context pattern blocks |
| `AssemblyResolutionResults` | Set of all possible encodings (errors + successes) |
| `AssemblyResolvedBackfill` | Forward reference (e.g., forward branch target) |
| `RecursiveDescentSolver` | Dispatches to 18 expression-type-specific solvers |
| `MaskedLong` | 64-bit value with undefined bits (mask+value pair); propagates through arithmetic |
| `AssemblyContextGraph` | Dijkstra over context transition graph for pure-recursive productions |
| `AssemblySelector` | Disambiguation: `filterParse()` (pre-semantic) + `select()` (post-semantic) |

### Constraint Solving (`sleigh/expr/`)

`RecursiveDescentSolver` registers solvers for each expression type:
- Arithmetic: `PlusExpressionSolver`, `MinusExpressionSolver`, `MultExpressionSolver`, `DivExpressionSolver`
- Bitwise: `AndExpressionSolver`, `OrExpressionSolver`, `XorExpressionSolver`
- Shift: `LeftShiftExpressionSolver`, `RightShiftExpressionSolver`
- Terminal: `TokenFieldSolver`, `ContextFieldSolver`, `OperandValueSolver`, `ConstantValueSolver`

`MaskedLong` tracks defined vs undefined bits through operations — critical for encoding fields of variable length.

### Assembly Pipeline

```
"ADD R0, #0x10"
     ↓
AssemblyParser.parse() → Collection<AssemblyParseResult>
     ↓
AssemblySelector.filterParse() → filtered parse trees
     ↓
AssemblyTreeResolver.resolve():
  ├─ AssemblyConstructStateGenerator → prototype states
  ├─ AssemblyConstructState.resolve() → per-constructor patterns
  │   └─ RecursiveDescentSolver.solve() → MaskedLong field values
  ├─ resolveRootRecursion() via AssemblyContextGraph (Dijkstra)
  ├─ selectContext() → match generated context
  ├─ resolvePendingBackfills() → resolve forward refs
  ├─ filterForbidden() → remove invalid patterns
  └─ filterByDisassembly() → roundtrip validation
     ↓
AssemblyResolutionResults
     ↓
AssemblySelector.select() → single chosen encoding
     ↓
byte[] machine code
```

---

## Program Utilities (`ghidra/program/util/`)

~111 files. Key content:

| Class/Package | Purpose |
|---------------|---------|
| `ProgramEvent` | Enum of all events fired by Program (MEMORY_BLOCK_ADDED, CODE_ADDED, SYMBOL_ADDED, DATA_TYPE_CHANGED, PROGRAM_TREE_CREATED, etc.) |
| `ProgramDiff` / `ProgramMerge` | Program differencing and merging infrastructure |
| `LanguageTranslator` / `LanguageTranslatorFactory` | Language migration (register remapping on language upgrade) |
| `ProgramContextImpl` / `RegisterValueStore` | Context register value storage |
| `*FieldLocation` classes | GUI-level location types: `AddressFieldLocation`, `MnemonicFieldLocation`, `OperandFieldLocation`, `LabelFieldLocation`, `FunctionSignatureFieldLocation`, etc. |
| `InstructionUtils` | Instruction-level utilities |
| `CyclomaticComplexity` | Compute cyclomatic complexity for a function |
| `DefinedDataIterator` / `DefinedStringIterator` | Efficient iteration over defined data / strings |
| `AddressCorrelator` / `LinearDataAddressCorrelation` | Address mapping across program versions |
| `SimpleDiffUtility` | Diff utility helpers |

### Field Location Classes

Used by the Listing and Decompiler to represent cursor position:
- Each field type has its own `*FieldLocation` subclass
- Includes: address field, mnemonic, operands, labels, function signatures, variables, comments, separators

---

## PCode Formatting (`ghidra/app/util/pcode/`)

| Class | Role |
|-------|------|
| `AbstractAppender<T>` | Template for formatting PCode: `appendMnemonic()`, `appendRegister()`, `appendScalar()`, `appendSpace()`, `appendUnique()`, `appendUserop()` |
| `PcodeFormatter` | Extends `AbstractAppender` for full PCode operation display |
| `Appender` | Interface variant for different output sinks |

Convention: hex for large values, decimal for small; unique temps displayed as `$U<offset>`.

---

## Graph Service (`ghidra/service/graph/`)

| Interface/Class | Role |
|-----------------|------|
| `GraphDisplay` | Service interface for visualization: `setFocusedVertex()`, `selectVertices()`, `getGraph()`, `setGraphDisplayListener()` |
| `AttributedGraph` | Graph with key-value attributes on vertices and edges; backed by JGraphT |
| `AttributedVertex` / `AttributedEdge` | Vertex/edge with `getAttribute(key)`, `setAttribute(key, val)` |
| `GraphType` | Named graph type with vertex/edge categories |
| `GraphDisplayOptions` | Colors, icons, layout for graph display |
| `GraphDisplayProvider` | Extension point: provides `GraphDisplay` instances; discovered by `ClassSearcher` |

---

## Design Patterns Summary

| Pattern | Where | Purpose |
|---------|-------|---------|
| **Facade** | `ProgramDB` | Single access point for 15 subsystems |
| **Interface segregation** | `model/**` | Pure API layer; no DB code |
| **Adapter + versioning** | All DB adapters | Schema evolution without data loss |
| **DBObjectCache** | All managers | Soft-reference cache with hard-cache layer |
| **Decorator** | `AddressSetView` | Read-only view of AddressSet |
| **Factory** | `Assemblers`, `LanguageService` | Cached factory with key-based lookup |
| **Template method** | `AbstractAppender`, `AbstractSleighAssemblerBuilder` | Customizable formatting/building |
| **Strategy** | `AssemblySelector`, `PrototypeModel` | Pluggable disambiguation and calling conventions |
| **Visitor** | `PcodeEmit`, `walkTemplates()` | Tree traversal without modifying nodes |
| **Chain of responsibility** | `RecursiveDescentSolver` | Dispatch expression solving by type |
| **Observer** | `ProgramEvent` + listeners | Change notification throughout |

---

## Developer Tips

- **Adding a new DB-backed property**: Add a `PropertyMapDB` via `DBPropertyMapManager`; use `IntPropertyMapDB`, `LongPropertyMapDB`, `StringPropertyMapDB`, or `ObjectPropertyMapDB`. All changes must be inside a transaction.
- **Extending Program model**: Implement the interface from `model/**`, add a manager to `ProgramDB`'s manager array, add a `ProgramEvent` entry.
- **Schema upgrade**: Add a new versioned `Adapter` class; increment DB_VERSION; implement `upgrade()` factory path.
- **Reading PCode**: Call `Instruction.getPcode()` (raw) or use `HighFunction` (SSA decompiler output). The two are different representations.
- **Custom assembly**: Implement `AssemblySelector` to control which encoding is chosen; useful for patching tools.
- **Language migration**: Implement `LanguageTranslator` and register via `LanguageTranslatorFactory` for register remapping.
- **Understanding disassembly failures**: `UnknownInstructionException` = no matching SLEIGH pattern; check context register values via `DisassemblerContextImpl`.
- **New data type**: Use `DataTypeManager.resolve(DataType)` to add; creates a copy in the program archive. Cross-archive references use UniversalID.
- **SourceMap**: New in DB v29; `SourceFileManagerDB` maps `Address → (sourceFile, line, column)`.
