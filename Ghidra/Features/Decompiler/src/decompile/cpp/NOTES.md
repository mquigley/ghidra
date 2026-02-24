# Ghidra Decompiler C++ Core — Analysis Notes

> Generated: 2026-02-23. Re-read this file at the start of any session involving the decompiler C++ source.
> Location: `Ghidra/Features/Decompiler/src/decompile/cpp/`
> Scale: ~186K lines, 115 .cc + 114 .hh files

---

## Overview

The C++ decompiler core is a standalone analysis engine. It runs as a **child subprocess** of Ghidra's JVM and communicates via binary-encoded stdin/stdout pipes. It implements the complete transformation pipeline from raw PCode → C source code, with no dependency on Ghidra's Java code at compile time.

**Two executables are built:**
- `decompile` — the main decompiler process (74 .cc files)
- `sleigh` — the SLEIGH spec compiler (.slaspec → .sla)

---

## File Groups at a Glance

| Group | Key Files | Purpose |
|-------|-----------|---------|
| **Infrastructure** | address, space, marshal, xml | Address spaces, binary protocol, XML |
| **Core IR** | varnode, op, block, cover | Varnode/PcodeOp/CFG data structures |
| **SSA** | heritage, merge | Phi-node insertion, renaming, merging |
| **High-level IR** | variable, funcdata | HighVariable, per-function container |
| **Analysis** | heritage, rangeutil, flow, jumptable | SSA, value ranges, control flow, switch recovery |
| **Action pipeline** | action, coreaction, ruleaction, blockaction | Transformation framework, 58+ actions, 136+ rules |
| **Type system** | type, typeop, cast | Datatype hierarchy, op semantics, cast decisions |
| **ABI / params** | fspec, varmap, modelrules | Calling conventions, parameter recovery, local vars |
| **Output** | printc, prettyprint, printlanguage | C code generation |
| **Ghidra integration** | ghidra_arch, ghidra_process, ghidra_translate, database_ghidra, loadimage_ghidra, inject_ghidra | Pipe protocol, symbol/byte/pcode queries |
| **Special analysis** | double, subflow, condexe, transform, dynamic | Double-precision, subvar, conditions, lane splitting, dynamic hashing |
| **Misc** | signature, paramid, pcodeinject, userop, override | BSim features, injection, user ops, overrides |

---

## Core Data Structures

### Varnode (varnode.hh/cc)

The fundamental SSA value — a contiguous set of bytes at a storage location.

**Key fields:**
```cpp
Address loc;           // Storage location (space + offset)
int4 size;             // Size in bytes
PcodeOp *def;          // Defining operation (nullptr = input or free)
list<PcodeOp*> descend;// All uses of this varnode
HighVariable *high;    // Owning high-level variable
SymbolEntry *mapentry; // Associated symbol
Datatype *type;        // Data type
Cover *cover;          // Liveness info
uintb consumed;        // Bits actually read (dead-code mask)
uintb nzm;             // Known-zero bits mask
uint4 flags;           // Boolean attributes
uint4 addlflags;       // Additional attributes
```

**Varnode flags (`varnode_flags`):**
- SSA: `written`, `input`, `insert`
- Type: `typelock`, `namelock`, `constant`, `annotation`
- Memory: `readonly`, `volatil`, `persist`, `externref`
- Address: `addrtied`, `addrforce`, `spacebase`
- Analysis: `indirect_creation`, `return_address`, `coverdirty`, `precislo`, `precishi`

**Free vs non-free:**
- Free: `!(written|input)` — identified by (Address, size) alone
- Non-free: part of SSA — identified by (Address, size, def_op, time)

**Join concept:** `isJoin()` returns true if address is in `IPTR_JOIN` space. Join varnodes represent logically unified values split across non-contiguous physical locations. `overlapJoin()` handles overlap calculation across pieces.

**VarnodeBank:** Container for all Varnodes. Dual sorted sets: `loc_tree` (by address) and `def_tree` (by definition). Allocates unique-space temporaries with auto-incrementing offsets.

---

### PcodeOp (op.hh/cc)

One PCode operation.

**Key fields:**
```cpp
TypeOp *opcode;          // Behavioral descriptor (type semantics)
SeqNum start;            // Address + unique time + order within block
BlockBasic *parent;      // Containing block
Varnode *output;         // Single output (may be null)
vector<Varnode*> inrefs; // Input varnodes (ordered)
list<PcodeOp*>::iterator basiciter;  // Position in block
list<PcodeOp*>::iterator insertiter; // Position in alive/dead list
uint4 flags, addlflags;
```

**SeqNum:** `(Address pc, uintm uniq, uintm order)`. `uniq` = creation time for uniqueness; `order` = execution order within block.

**Op flags:** `branch`, `call`, `returns`, `startbasic`, `startmark`, `booloutput`, `marker` (MULTIEQUAL/INDIRECT), `dead`, `commutative`, `halt`, `noreturn`, `indirect_creation`, etc.

**IopSpace:** Special address space encoding PcodeOp* as offset — used by branch targets to store pointers to target ops.

**PcodeOpBank:** All ops indexed by SeqNum (main), plus sub-lists: `alivelist`, `deadlist`, `storelist`, `loadlist`, `returnlist`, `useroplist`. Provides iteration by address, opcode, and alive/dead status.

---

### Address Spaces (address.hh, space.hh)

**AddrSpace types:**
| Constant | Role |
|----------|------|
| `IPTR_CONSTANT` | Constant values as offsets |
| `IPTR_PROCESSOR` | Normal RAM/register spaces |
| `IPTR_SPACEBASE` | Virtual: offsets from base register |
| `IPTR_INTERNAL` | UniqueSpace: temporaries |
| `IPTR_FSPEC` | FuncCallSpecs references |
| `IPTR_IOP` | PcodeOp pointers (branch targets) |
| `IPTR_JOIN` | Logically joined split variables |

**Address:** `(AddrSpace*, uintb offset)`. No size field — identifies one byte. Arithmetic wraps per-space word size.

---

### FlowBlock / CFG (block.hh/cc)

**Block type hierarchy:**
```
FlowBlock (base)
├── BlockBasic        — t_basic: holds list of PcodeOps, single entry, 1+ exits
├── BlockGraph        — t_graph: container (function level or structured region)
├── BlockCopy         — t_copy: duplicate of basic block
├── BlockIf           — t_if: if-then-else
├── BlockWhileDo      — t_whiledo
├── BlockDoWhile      — t_dowhile
├── BlockSwitch       — t_switch
├── BlockInfLoop      — t_infloop
└── BlockGoto / BlockMultiGoto — unstructured jumps
```

**FlowBlock fields:** `flags`, `index`, `parent`, `immed_dom` (dominator), `intothis`/`outofthis` edge lists, `visitcount`.

**BlockEdge:** `label` (flags), `point` (target block), `reverse_index`. Enables O(1) bidirectional traversal.

**Block flags:** Loop edges (`f_loop_edge`, `f_back_edge`), unstructured jumps (`f_goto_edge`), exit types (`f_goto_goto`, `f_break_goto`, `f_continue_goto`, `f_switch_out`), structural (`f_joined_block`, `f_duplicate_block`).

**Funcdata owns two block graphs:**
- `bblocks` — unstructured basic blocks (built from flow analysis)
- `sblocks` — structured hierarchy (built by ActionBlockStructure)

---

### HighVariable (variable.hh/cc)

Aggregates multiple Varnodes into one abstract variable.

**Key invariant:** Member Varnodes must NOT have intersecting Covers — a HighVariable holds one value at a time.

```cpp
vector<Varnode*> inst;       // Member Varnodes
Cover internalCover;         // Union of member covers
Datatype *type;              // Derived from members
Symbol *symbol;              // Associated symbol
VariablePiece *piece;        // If part of overlapping group
```

**Dirtiness flags:** `flagsdirty`, `typedirty`, `coverdirty`, `symboldirty`, `namerepdirty`, `type_finalized`. Lazy update via `getType()`, `getCover()`, `getSymbol()`.

**VariableGroup / VariablePiece:** Groups overlapping HighVariables. Tracks offsets within group for multi-entry symbols.

**Concrete subclasses:** `HighSingle` (one Varnode), `HighMultiAssign` (multiple), `HighOther` (non-local).

---

### Cover (cover.hh/cc)

Topological scope of a Varnode — the code ranges where it holds a value.

- Maps `block_index → CoverBlock` (range of ops within block)
- `CoverBlock`: `start`, `stop` pointers (nullptr = block boundary)
- Operations: `rebuild(varnode)`, `intersect(cover)`, `merge(cover)`, `contain(op)`
- **Intersection drives merge decisions**: intersecting covers → cannot merge into same HighVariable.

---

## Funcdata (funcdata.hh + funcdata_*.cc)

The per-function analysis hub. Owns everything for one function.

**Major fields:**
```cpp
VarnodeBank vbank;          // All Varnodes
PcodeOpBank obank;          // All PcodeOps
BlockGraph bblocks, sblocks;// Unstructured + structured CFG
Heritage heritage;           // SSA construction
Merge covermerge;            // Varnode merging
FuncProto funcp;             // Function prototype
ScopeLocal *localmap;        // Local variable scope
vector<FuncCallSpecs*> qlst; // All call sites
vector<JumpTable*> jumpvec;  // Switch jump tables
Override localoverride;      // User overrides
```

**State flags:** `highlevel_on`, `blocks_generated`, `processing_started/complete`, `typerecovery_on`, `jumptablerecovery_on`, `double_precis_on`.

**funcdata_varnode.cc:** Varnode creation, deletion, split, concatenate.
**funcdata_op.cc:** Op creation, insertion, `setOpcode()`, `setInput()`, mutation.
**funcdata_block.cc:** Block manipulation: `splitBasic()`, `mergeBasic()`, dead block removal.

---

## SSA Construction: Heritage (heritage.hh/cc, 2872 lines)

Multi-pass SSA construction. Different address spaces get different delays (registers early, stack later).

### Algorithm

**Phase 1 — Phi-node placement** (`placeMultiequals()`):
- Iterated dominance frontier (Bilardi/Pingali / Cytron et al.)
- Augmented Dominator Tree (ADT) for unstructured jumps
- Priority queue ordered by dominator tree depth
- Inserts `CPUI_MULTIEQUAL` ops at merge points

**Phase 2 — Renaming** (`rename()`):
- Stack-based renaming per address
- Post-order CFG traversal
- Links all reads to their unique defining writes

### HeritageInfo (per address space)

```cpp
int4 delay;           // Passes before heritaging this space
int4 deadcodedelay;   // Passes before deadcode removal
bool warningissued;
bool hasCallPlaceholders;
```

### LocationMap

Tracks which address ranges were heritaged and in which pass. Enables incremental SSA updates when new Varnodes are discovered late.

### Guard Mechanisms (aliasing)

| Guard | Trigger | Purpose |
|-------|---------|---------|
| `guardCalls()` | CALL ops | Stack/register effects of function calls |
| `guardStores()` | STORE with pointer | Memory may alias stack |
| `guardLoads()` | LOAD with dynamic index | Stack slot may be read indirectly |
| `guardReturns()` | RETURN | Return value overlap |
| `guardInputs()` | Function entry | Parameter ranges |

`LoadGuard`/`StoreGuard` track `minimumOffset`, `maximumOffset`, `step` and `analysisState` (0=unanalyzed, 1=partial, 2=complete).

---

## Variable Merging: Merge (merge.hh/cc, 1695 lines)

Unifies Varnodes into HighVariables.

**Forced merges** (must happen): MULTIEQUAL inputs/outputs, global (`persist`) locations, mapped stack locations.

**Speculative merges** (attempted): same datatype, non-intersecting covers, compatible address-tied status.

**Blocking conditions:** Cover intersection, address-tied conflicts, stack alias uncertainty, type incompatibility.

**Key methods:** `mergeOpcode()`, `mergeByDatatype()`, `mergeAddrTied()`, `mergeMarker()`, `mergeAdjacent()`, `mergeMultiEntry()`, `mergeTest()`.

---

## Action/Rule Transformation Pipeline

### Framework (action.hh/cc)

**Action** — large-scale transformation applied to entire Funcdata:
- `apply(Funcdata &data)` — increments `count` to signal changes
- `lcount` tracks previous count; loops while `lcount < count` if `rule_repeatapply` set
- `ActionGroup` — sequential list; `ActionPool` — pool of Rules applied to every op; `ActionRestartGroup` — handles restart signals; `ActionDatabase` — root registry

**Rule** — micro-transformation targeting specific PcodeOps:
- `getOpList(vector<uint4>&)` — register for opcodes
- `applyOp(PcodeOp*, Funcdata&)` — return 1 if applied, 0 otherwise
- Pooled in `ActionPool.perop[OPCODE]` vector
- When a rule changes an op's opcode, rule iteration restarts for that op

### Universal Action Pipeline (coreaction.cc, ~5758 lines)

```
ActionRestartGroup "universal"
├── ActionStart, ActionConstbase
├── ActionNormalizeSetup, ActionDefaultParams
├── ActionExtraPopSetup, ActionPrototypeTypes
├── ActionFuncLink / ActionFuncLinkOutOnly
└── ActionRestartGroup "fullloop"  [repeats until stable]
    ├── ActionGroup "mainloop"  [repeats]
    │   ├── ActionUnreachable, ActionVarnodeProps
    │   ├── ActionHeritage (SSA)
    │   ├── ActionParamDouble, ActionSegmentize
    │   ├── ActionActiveParam, ActionReturnRecovery
    │   ├── ActionRestrictLocal, ActionDeadCode
    │   ├── ActionDynamicMapping, ActionRestructureVarnode
    │   ├── ActionSpacebase, ActionNonzeroMask
    │   ├── ActionInferTypes
    │   ├── ActionGroup "stackstall"  [repeats]
    │   │   ├── ActionPool "oppool1"  (~100 rules)
    │   │   ├── ActionLaneDivide, ActionMultiCse
    │   │   ├── ActionShadowVar, ActionDeindirect
    │   │   └── ActionStackPtrFlow
    │   ├── ActionRedundBranch, ActionBlockStructure
    │   ├── ActionConstantPtr
    │   ├── ActionPool "oppool2"  (pointer/stack rules)
    │   ├── ActionDeterminedBranch, ActionUnreachable
    │   └── ActionConditionalExe, ActionConditionalConst
    ├── ActionLikelyTrash, ActionDeadCode
    ├── ActionDoNothing, ActionSwitchNorm, ActionReturnSplit
    └── ActionUnjustifiedParams, ActionActiveReturn
├── ActionMappedLocalSync
├── ActionStartCleanUp
├── ActionPool "cleanup"  (~15 cleanup rules)
└── ActionStop
```

**Pipeline variants** (configured by `SetAction` command):
- `"decompile"` — full analysis (default)
- `"jumptable"` — only jump table recovery
- `"normalize"` — no full type recovery
- `"paramid"` — parameter identification
- `"register"` — register analysis only

### Key Actions (coreaction.hh: 58+ classes)

| Action | Purpose |
|--------|---------|
| `ActionHeritage` | SSA construction (calls Heritage::heritage()) |
| `ActionDeadCode` | Bit-precise dead code via `consumed` masks |
| `ActionInferTypes` | Type propagation loop |
| `ActionBlockStructure` | CFG structuring (loops, if/else, switch) |
| `ActionActiveParam` | Determine which putative params are used |
| `ActionReturnRecovery` | Build return value data-flow |
| `ActionFuncLink` | Link subfunction parameter data-flow |
| `ActionMergeRequired` | Merge address-tied + marker Varnodes |
| `ActionMergeType` | Speculative merge by type |
| `ActionAssignHigh` | Create initial HighVariable objects |
| `ActionMarkExplicit` | Mark Varnodes needing output tokens |
| `ActionNameVars` | Choose final variable names |
| `ActionSetCasts` | Insert CAST PCode ops |
| `ActionSwitchNorm` | Normalize jump table construction |
| `ActionConstantPtr` | Map constants to global symbols |
| `ActionDeindirect` | Resolve indirect calls to direct |

### Rules (ruleaction.hh/cc: ~136 Rule classes, 11017 lines)

Organized by category (representative sample):

**Arithmetic/Algebraic (~40):**
`RuleCollectTerms` (`V*c + V*d → V*(c+d)`), `RuleAddMultCollapse`, `RuleTermOrder`, `RuleTrivialArith`, `RuleIdentityEl`, `RuleNegateNegate`

**Boolean/Comparison (~25):**
`RuleBoolNegate`, `RuleBoolZext`, `RuleBxor2NotEqual`, `RuleLessEqual`, `RuleLess2Zero`, `RuleEqual2Zero`, `RuleTestSign`, `RuleThreeWayCompare`

**Bitwise (~30):**
`RuleOrMask`, `RuleAndMask`, `RuleAndDistribute`, `RuleXorCollapse`, `RuleXorSwap`, `RuleNotDistribute`, `RuleHighOrderAnd`, `RuleShiftBitops`

**Extension/Piece (~15):**
`RuleZextEliminate`, `RulePiece2Zext`, `RuleConcatZext`, `RuleConcatCommute`, `RuleExtensionPush`, `RulePieceStructure`

**Shifts (~12):**
`RuleDoubleShift` (`(x<<a)<<b → x<<(a+b)`), `RuleShift2Mult`, `RuleSignShift`, `RuleTrivialShift`, `RuleConcatShift`

**Multiplication/Division (~15):**
`RuleSignDiv2`, `RuleDivOpt`, `RuleDivChain`, `RuleModOpt`, `RuleSignMod2nOpt`, `Rule2Comp2Mult`, `RuleMultNegOne`

**Pointer/Memory (~8):**
`RulePtrArith`, `RuleStructOffset0`, `RulePushPtr`, `RulePtraddUndo`, `RulePtrsubUndo`

**Double-precision (~4):**
`RuleDoubleLoad`, `RuleDoubleStore`, `RuleDoubleIn`, `RuleDoubleOut`

**Subvariable/Bitfield (~8):**
`RuleSubvarAnd`, `RuleSubvarSubpiece`, `RuleSubvarCompZero`, `RuleBitFieldStore`, `RuleBitFieldLoad`

**Float (~7):**
`RuleUnsigned2Float`, `RuleFloatCast`, `RuleFloatSign`, `RuleIgnoreNan`

**Conditional/Control-flow (~6):**
`RuleIndirectCollapse`, `RuleMultiCollapse`, `RuleSwitchSingle`, `RulePropagateCopy`

**Cleanup-only (~10):**
`Rule2Comp2Sub`, `RuleExpandLoad`, `RuleSplitCopy`, `RuleSplitLoad`, `RuleStringCopy`

### Block Structuring (blockaction.hh/cc, 2366 lines)

**LoopBody:** Detects natural loops; `findBase()` via dominance; `findExit()` selects exit; `setExitMarks()` marks exit edges.

**TraceDAG:** DAG-based unstructured edge detection. Traces single-entry/exit paths; remaining edges become gotos.

**ActionBlockStructure:** Iteratively applies structuring. Handles irreducible control flow.

### Special Analyses

**ConditionalExecution (condexe.hh/cc):** Two sequential conditionals on same boolean → merge. Handles `directsplit` (assignment followed by branch → fold into condition).

**SubvariableFlow (subflow.hh/cc, 4131 lines):** Detects logical values carried in smaller portions of larger Varnodes. Traces subgraph through container, replaces extractions with direct references.

**DoublePrecision (double.hh/cc, 3647 lines):** `SplitVarnode` represents 64-bit value as two 32-bit pieces. Forms: `AddForm`, `SubForm`, `LogicalForm`, `Equal1Form`, `Equal2Form`, `ShiftForm`.

---

## Type System (type.hh/cc, typeop.hh/cc)

### Datatype Metatypes (18 values)

```
TYPE_VOID=17, TYPE_SPACEBASE=16, TYPE_UNKNOWN=15, TYPE_INT=14,
TYPE_UINT=13, TYPE_BOOL=12, TYPE_CODE=11, TYPE_FLOAT=10,
TYPE_PTR=9, TYPE_PTRREL=8, TYPE_ARRAY=7,
TYPE_ENUM_UINT=6, TYPE_ENUM_INT=5,
TYPE_STRUCT=4, TYPE_UNION=3,
TYPE_PARTIALENUM=2, TYPE_PARTIALSTRUCT=1, TYPE_PARTIALUNION=0
```

Plus 24 sub-metatypes (e.g., `SUB_INT_CHAR`, `SUB_UINT_ENUM`, `SUB_PTR_STRUCT`).

### Datatype Hierarchy

```
Datatype (base: id, size, metatype, submeta, flags)
├── TypeVoid, TypeChar, TypeUnicode, TypeBase
├── TypePointer       — ptrto + wordsize
├── TypePointerRel    — pointer offset into parent struct
├── TypeArray         — arraysize + arrayof element
├── TypeStruct        — fields vector + bitfields
├── TypeUnion         — overlapping fields
├── TypeEnum          — name→value map
├── TypeCode          — function pointer + FuncProto
├── TypeSpacebase     — stack/RAM treated as struct
└── Partial types: TypePartialStruct, TypePartialEnum, TypePartialUnion
```

**TypeFactory:** Singleton manager. `DatatypeSet tree` (all types), `DatatypeNameSet nametree` (by name), `Datatype *typecache[9][8]` (cached atomics). Key ops: `getBase()`, `getTypePointer()`, `getTypeStruct()`, `concretize()`, `dependentOrder()`.

### TypeOp — PCode Operation Semantics (100+ subclasses)

Associates each PCode opcode with type behavior:
- `getOutputLocal()` / `getInputLocal()` — minimal input/output types
- `getOutputToken()` / `getInputCast()` — compiler-assigned types with cast decisions
- `propagateType()` — bidirectional type inference

**Key TypeOps:**
- `TypeOpLoad` — pointer-to type flows into load output
- `TypeOpStore` — stores into pointer
- `TypeOpCall` / `TypeOpCallind` — infer from FuncProto
- `TypeOpPiece` / `TypeOpSubpiece` — INT_PIECE / INT_SUBPIECE
- `TypeOpPtradd` / `TypeOpPtrsub` — pointer arithmetic + field access

**Type propagation:** Bidirectional. Forward (input→output) and backward (output→input). Iterate to fixed-point. `compare()` resolves conflicts: higher specificity (struct > unknown) wins.

### Cast Strategy (cast.hh/cc)

`CastStrategy` decides when explicit C casts are needed:
- Integer promotions (char/short → int): `UNSIGNED_EXTENSION`, `SIGNED_EXTENSION`, `EITHER_EXTENSION`, `NO_PROMOTION`
- `isExtensionCastImplied()` — checks if INT_ZEXT/INT_SEXT matches C rules (if so, hide the op)
- `castStandard()` — basic signed/unsigned, size, pointer-integer compatibility
- `checkIntPromotionForCompare()` — comparison operand extension checks

---

## ABI and Parameter Recovery (fspec.hh/cc, 5976 lines)

### ParamEntry — One Storage Location in the Model

```cpp
AddrSpace *spaceid;  // Register, stack, etc.
uintb addressbase;   // Start offset
int4 size, minsize;  // Range size, minimum logical value size
int4 alignment;      // Slot size (0 = exclusive, one param only)
int4 numslots;       // Max slots available
type_class type;     // GENERAL, FLOAT, PTR, HIDDENRET, VECTOR
JoinRecord *joinrec; // Multi-register support
```

**Flags:** `force_left_justify`, `reverse_stack`, `smallsize_zext/sext/inttype/floatext`, `is_grouped`, `overlapping`.

### ParamTrial — Candidate During Analysis

State: `checked`, `used`, `defnouse` (definitely NOT a param), `active`, `unref`, `killedbycall`, `ancestor_realistic/solid`.

### ParamActive — Trial Container

Holds all parameter trials during recovery. `numpasses`, `maxpass`, `isfullychecked`, `needsfinalcheck`. Methods: `registerTrial()`, `sortTrials()`, `deleteUnusedTrials()`, `splitTrial()`, `joinTrial()`.

### ProtoModel — Complete Calling Convention

```cpp
string name;                    // "cdecl", "stdcall", "gcc", etc.
int4 extrapop;                  // Stack change across call
ParamList *input, *output;      // Input/return models
vector<EffectRecord> effectlist;// Side effects
vector<VarnodeData> likelytrash;// Registers likely garbage after call
RangeList localrange, paramrange;// Stack zones
bool stackgrowsnegative, hasThis, isConstruct;
```

**EffectRecord types:** `unaffected` (preserved), `killedbycall` (destroyed), `return_address`, `unknown_effect`.

**ParamList subclasses:**
- `ParamListStandard` — ordered ABI (x86-64, ARM, etc.); resource groups (general, float, vector); no-holes rule
- `ParamListStandardOut` — return value model with fallback to hidden pointer
- `ParamListRegister` — unstructured register model (no hole enforcement)
- `ParamListMerged` — union of models during analysis before ABI is known

### Parameter Recovery Process

1. Collect candidates from input Varnodes as `ParamTrial`s
2. Iterate `maxpass` times: TypeOp propagates types; `fillinMap()` marks used/unused
3. `sortTrials()` — arrange in formal parameter order
4. `assignParameterStorage()` — map types to addresses

### Local Variable Recovery (varmap.hh/cc, 1620 lines)

**ScopeLocal:** Local variable scope for a function.
- `restructureVarnode(aliasyes)` — layout from Varnode info
- `recoverNameRecommendationsForSymbols()` — recover names from DWARF/Ghidra
- `applyTypeRecommendations()` — apply type hints

**AliasChecker:** Detects stack locations possibly aliased via pointers.
- `gatherAdditiveBase()` — finds `(sp + constant)` and `(sp + index)` expressions
- `hasLocalAlias()` — test if Varnode overlaps with pointer reference

**MapState / RangeHint:** Collect type-recovery hints (from symbols, Varnodes, pointer references). `RangeHint.rangeType`: `fixed`, `open` (array unknown length), `endpoint`.

**ModelRules (modelrules.hh/cc):** Alignment and extension rules per ProtoModel. Handles architecture-specific parameter layout customization.

---

## C Code Output (printc.hh/cc, prettyprint.hh/cc)

### PrintC (3536 lines)

108 static `OpToken` objects for all C operators, with precedence and associativity.

**Configuration:** `option_NULL`, `option_inplace_ops` (+=, -=), `option_convention`, `option_nocasts`, `option_hide_exts`, `option_brace_*`.

**Core output:**
- Type declarations: `pushTypeStart()` / `pushTypeEnd()` / `buildTypeStack()`
- Statements: `emitStatement()`, `emitForLoop()`, `emitSwitchCase()`, `emitLabel()`
- Block emission: `emitBlockBasic()`, `emitBlockIf()`, `emitBlockWhileDo()`, `emitBlockSwitch()`
- Expressions: `opBinary()`, `opUnary()`, `opTypeCast()`
- Special: `emitBitFieldStore()`, `checkArrayDeref()`, `checkBitFieldMember()`, `pushSymbolScope()`

**Expression building:** Reverse Polish Notation (RPN) stack. Operands pushed before operators. Precedence rules automatically add/suppress parentheses.

### Emit Interface (prettyprint.hh/cc, 1167 lines)

**Token types:** `tagtype` (start_element), `tagend` (end_element), `spaces`, `string`, `funcname`, `varname`, `param`, `comment`, `type`, `keyword`, `label`, `syntax`.

**Implementations:**
- `EmitMarkup` — emits tokens with highlight metadata (for Ghidra UI rendering)
- `EmitNoMarkup` — plain text output
- `TokenSplit` / `GroupToken` — pretty-printing break decisions

---

## Architecture and Ghidra Integration

### Architecture Class (architecture.hh/cc)

The master coordinator. Extends `AddrSpaceManager`.

**Key fields:**
```cpp
Database *symboltab;          // Global symbols/scopes/functions
ContextDatabase *context;     // Register values at addresses
TypeFactory *types;           // Data-type definitions
Translate *translate;         // Disassembly → PCode
LoadImage *loader;            // Program memory access
PcodeInjectLibrary *pcodeinjectlib; // PCode injections
PrintLanguage *print;         // Output formatter
map<string,ProtoModel*> protoModels; // Calling conventions
ProtoModel *defaultfp;        // Default calling convention
ActionDatabase allacts;       // Transformation rules
vector<TypeOp*> inst;         // PCode operation behaviors
UserOpManage userops;         // User-defined ops
```

**Initialization:** `init(DocumentStorage&)` calls virtual `buildDatabase()`, `buildTranslator()`, `buildLoader()`, `buildTypegrp()`, `buildContext()`, `buildPcodeInjectLibrary()`, `buildAction()`.

### ArchitectureGhidra (ghidra_arch.hh/cc)

Overrides all factory methods to use Ghidra-specific implementations.

**Protocol markers** (alignment bursts):
- Open codes (even): `2`=cmd, `4`=query, `6`=response, `8`=query_resp, `A`=exception
- Close codes (odd): `3`, `5`, `7`, `9`, `B`

**Queries C++ can send to Java:**
`GETBYTES`, `GETPCODE`, `GETMAPPEDSYMBOLS`, `GETCALLFIXUP`, `GETCALLMECH`, `GETCODELABEL`, `GETCOMMENTS`, `GETCPOOLREF`, `GETDATATYPE`, `GETEXTERNALREF`, `GETNAMESPACEPATH`, `GETPCODEEXECUTABLE`, `GETREGISTER`, `GETREGISTERNAME`, `GETSTRINGDATA`, `GETTRACKEDREGISTERS`, `GETUSEROPNAME`, `ISNAMEUSED`, `GETCALLOTHERFIXUP`

### Process Lifecycle (ghidra_process.hh/cc)

**Commands dispatched via `GhidraCapability::readCommand()`:**

| Command | Purpose |
|---------|---------|
| `RegisterProgram` | Create ArchitectureGhidra, receive pspec/cspec/tspec |
| `DeregisterProgram` | Release Architecture |
| `FlushNative` | Clear cached symbols |
| `DecompileAt` | Main decompilation (address → C code) |
| `StructureGraph` | Structure a given CFG |
| `SetAction` | Switch pipeline variant |
| `SetOptions` | Configure options |

### Binary Protocol (marshal.hh/cc, 1273 lines)

**ElementId / AttributeId:** String names mapped to unique uint4 IDs at startup via `initialize()`.

**Decoder types:**
- `XmlDecode` — parses XML documents; stacks element/iterator pairs for navigation
- `PackedDecode` — binary packed format (variable-length encoding)

**Encoder types:** Parallel Encode/PackedEncode for output.

### Integration Layer Components

| C++ Class | Java Query | Caches |
|-----------|-----------|--------|
| `GhidraTranslate` | `GETPCODE`, `GETREGISTER`, `GETREGISTERNAME` | `nm2addr`, `addr2nm` register maps |
| `LoadImageGhidra` | `GETBYTES` | None |
| `ScopeGhidra` | `GETMAPPEDSYMBOLS`, function lookup | `ScopeInternal` cache + `holes` RangeList |
| `PcodeInjectLibraryGhidra` | `GETPCODEEXECUTABLE`, `GETCALLFIXUP`, `GETCALLOTHERFIXUP` | Payload registrations |

### Symbol System (database.hh/cc, 3430 lines)

**Scope hierarchy:** `Scope` (abstract) → `ScopeInternal` (local cache) → `ScopeGhidra` (queries Java) → `ScopeGhidraNamespace`.

**SymbolEntry:** Maps `Symbol → (Address, size, use_limit, flags)`. `rangemap<SymbolEntry>` for spatial lookups. Dynamic entries use hash instead of address.

**Symbol types:** `FunctionSymbol`, `LabSymbol`, `EquateSymbol`, `ExternRefSymbol`, `FacetSymbol`.

---

## Control Flow Analysis

### FlowInfo (flow.hh/cc, 1460 lines)

**Phases:**
1. `generateOps()` — traces control flow; for each instruction, queries `GETPCODE`; follows branches, queues targets, detects BRANCHIND
2. `generateBlocks()` — splits ops into `BlockBasic`s at entry points and after branches
3. `injectPcode()` — performs callfixup injections
4. `recoverJumpTables()` — BRANCHIND recovery

**Algorithm:** worklist of addresses to process; `visited` map prevents infinite loops; error flags for out-of-bounds, unimplemented, too-many-instructions.

### JumpTable Recovery (jumptable.hh/cc, 2882 lines)

**RecoveryMode:** `Unrecovered`, `Disassembled`, `ModelPattern`, `Modeled`, `Truncated`.

**JumpModel subclasses:**
- `JumpBasic` — simple array: `switch_var → table[switch_var]`
- `JumpBasic2` — two-level: normalize → index
- `JumpAssisted` — helper-function assisted

**PathMeld:** Intersects paths from switch variable to BRANCHIND. `commonVn` = Varnodes on ALL paths; `opMeld` = all ops across paths.

**Recovery heuristics:**
1. Pattern matching — detect common switch constructs
2. Emulation (`EmulateFunction`) — trace data flow with switch variable, record loads
3. Guard analysis — CBRANCH conditions narrow value range

---

## Analysis Algorithms

### Value Range Analysis (rangeutil.hh/cc, 2605 lines)

**CircleRange:** Half-open interval `[left, right)` mod 2^n with step. Operations:
- `pullBackUnary()`, `pullBackBinary()`, `pullBackTernary()` — compute input range from output range + operation
- `pushForwardUnary()` / `Binary()` — compute output range from input
- `translate2Op()` — derive range from comparison condition

**ValueSet:** Associates CircleRange with Varnode during analysis. `typeCode`: 0=absolute, 1=spacebase-relative.

**Widening strategies:** `WidenerFull` (widen at iteration 2, full range at 5), `WidenerUpDown` (separate bounds). Landmarks prevent over-widening.

**Partition:** Groups of ValueSets iterated together for fixed-point analysis.

### DynamicHash (dynamic.hh/cc)

Uniquely identifies a Varnode by hashing its local data-flow subgraph. 4 methods with increasing context depth. `uniqueHash()` selects simplest method giving unique result.

### Transform Manager (transform.hh/cc)

Splits large Varnodes into logical lanes (SIMD/vector elements). Placeholder-based: build `TransformVar`/`TransformOp` graph → create actual Varnodes/ops → link → remove obsolete.

### PCode Injection (pcodeinject.hh/cc)

**InjectPayload types:** `CALLFIXUP_TYPE`, `CALLOTHERFIXUP_TYPE`, `CALLMECHANISM_TYPE`, `EXECUTABLEPCODE_TYPE`.

**InjectContext:** Holds concrete `inst_start`, `inst_next`, `inst_dest` addresses and input/output Varnodes.

### UserPcodeOp (userop.hh/cc)

CALLOTHER operations. Display types: `annotation_assignment`, `no_operator`, `display_string`. Subclasses: `InjectedUserOp`, `VolatileReadOp`, `VolatileWriteOp`, `SegmentOp`, `JumpAssistOp`, `InternalStringOp`.

### Override (override.hh/cc)

User-specified analysis overrides: `forcegoto`, `deadcodedelay`, `indirectover` (indirect→direct call), `protoover` (prototype at call site), `multistagejump`, `flowoverride` (CALL↔BRANCH).

### Signature / BSim (signature.hh/cc, 1148 lines)

Feature vectors for binary function similarity. `VarnodeSignature` (data-flow depth-limited hash), `BlockSignature` (control-flow), `CopySignature` (standalone COPYs). Noise reduction removes COPY shadows and non-contributing nodes.

---

## Developer Tips

- **Adding a new Rule**: Subclass `Rule`, implement `getOpList()` (register opcodes) and `applyOp()` (return 1 if applied). Register in the appropriate action pool in `coreaction.cc`.
- **Adding a new Action**: Subclass `Action`, implement `apply(Funcdata&)`. Insert into the universal pipeline in `coreaction.cc::buildDefaultGroups()`.
- **New data type**: Subclass `Datatype` and `TypeFactory::getTypeXxx()`. Override `compare()` for type ordering.
- **New calling convention**: Subclass `ParamList` (`assignMap()`, `fillinMap()`), instantiate `ProtoModel`, register in Architecture.
- **New output language**: Subclass `PrintLanguage`, override `emitBlock*()` and `op*()` methods.
- **Debugging the pipeline**: Set `rule_debug` flag on an Action/Rule. `checkActionBreak()` supports interactive breakpoints.
- **Java side callback**: Add a new ELEM_COMMAND_* in `ghidra_arch.hh` and implement the query response in `ArchitectureGhidra` + the Java-side `DecompileCallback`.
- **Understanding a decompilation failure**: Check `FlowInfo` flags for out-of-bounds/unimplemented. Check `Heritage` warnings for aliasing issues. Check ProtoModel's `effectlist` for missed register effects.
- **SSA invariant**: Every non-input Varnode must have exactly one defining `PcodeOp`. MULTIEQUAL is the only op that can have multiple inputs at the same address.
- **The consumed mask**: `Varnode.consumed` tracks which bits are actually read by any use. Dead code elimination propagates this backward from uses to definitions.
