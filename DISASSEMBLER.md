# Disassembly and Code Flow Analysis

## Matt's notes

[CodeUnit.java](Ghidra/Framework/SoftwareModeling/src/main/java/ghidra/program/model/listing/CodeUnit.java) - is the interface common to both Instructions and Data. It has labels, symbols, symbols, comments, mnemonic, start/end address, register references, operand addresses.
[Instruction] - Code
[Data] - Data


## The Entry Point: `EntryPointAnalyzer`

[EntryPointAnalyzer.java](Ghidra/Features/Base/src/main/java/ghidra/app/plugin/core/disassembler/EntryPointAnalyzer.java)

- **Type**: `BYTE_ANALYZER`
- **Priority**: `BLOCK_ANALYSIS`
- **Name**: "Disassemble Entry Points"

The analyzer that starts everything. Its `added()` method:

1. Disassembles addresses marked as code by the binary importer ("CodeMap" markers)
2. Processes dummy/placeholder functions
3. Disassembles external entry points and creates functions at them

It calls `Disassembler.disassemble(startSet, restrictedSet, followFlow=true)` then notifies
`AutoAnalysisManager.codeDefined()` with newly disassembled addresses, which cascades to
downstream analyzers.

## The Core Engine: `Disassembler`

[Disassembler.java](Ghidra/Framework/SoftwareModeling/src/main/java/ghidra/program/disassemble/Disassembler.java)

The main flow-following engine. Runs a `while` loop driven by a `DisassemblerQueue`:

```
Main Loop (continueProducingInstructionSets):
  ↓
  getNextBlockToBeDisassembled()     ← pop from queue
  ↓
  disassembleInstructionBlock()      ← parse bytes until flow terminates
    ├─ Language.parse() → InstructionPrototype (via SLEIGH)
    └─ processInstruction()
         └─ processInstructionFlows()
              ├─ BRANCH   → currentBranchQueue  (process immediately)
              ├─ CALL     → orderedSeedQueue     (defer until later)
              ├─ FALLTHRU → returned as next addr (loop continues inline)
              └─ copyToFutureFlowState()         (propagate context regs)
```

## The Three Queues in `DisassemblerQueue`

[DisassemblerQueue.java](Ghidra/Framework/SoftwareModeling/src/main/java/ghidra/program/disassemble/DisassemblerQueue.java)

| Queue | What goes in | Priority |
|-------|-------------|----------|
| `orderedSeedQueue` | Initial entry points + CALL targets | Lowest (deferred) |
| `priorityQueue` | Branch flows from last `InstructionSet` | Highest |
| `currentBranchQueue` | Branch flows within current `InstructionSet` | Mid |

Overall order: `priorityQueue` → `currentBranchQueue` → next seed from `orderedSeedQueue`.
This gives **depth-first within a straight-line block**, then **breadth across branches**,
with **calls deferred** until the local call site region is exhausted.

## How Each Flow Type Is Handled

`FlowType` properties (from [FlowType.java](Ghidra/Framework/SoftwareModeling/src/main/java/ghidra/program/model/symbol/FlowType.java)):
- `hasFall` — has fallthrough to next sequential instruction
- `isCall` — CALL instruction
- `isJump` — branch
- `isTerminal` — stops execution (RET, HALT)
- `isConditional` — both branch and fallthrough possible
- `isComputed` — indirect/computed target

| Instruction | FlowType | Fallthrough? | What happens |
|-------------|----------|-------------|--------------|
| `jz label` | `CONDITIONAL_JUMP` | Yes | Both target AND fallthrough queued as branches |
| `jmp label` | `UNCONDITIONAL_JUMP` | No | Target queued as branch, block ends |
| `call foo` | `CALL` | Yes | `foo` → `orderedSeedQueue`; fallthrough → `CALL_FALLTHROUGH` (deferred) |
| `ret` | `TERMINATOR` | No | No flows queued; block ends cleanly |
| `call [eax]` | `COMPUTED_CALL` | No static target | No target queued; block ends after fallthrough |

For **computed/indirect jumps** with no static target the disassembler cannot follow the flow —
it stops. Jump table recovery is a separate later step handled by `OperandReferenceAnalyzer`
and `ConstantPropagationAnalyzer`.

## Context Register Propagation

`DisassemblerContextImpl` tracks processor mode state (e.g., ARM Thumb/ARM toggle, MIPS ISA
mode) across flow edges. Every time a flow is queued, `copyToFutureFlowState(flowAddr)` saves
the current context so when that address is eventually disassembled it uses the correct
processor state.

## Function Creation

`EntryPointAnalyzer` creates functions only at **external entry points** via `CreateFunctionCmd`.

For **call targets**, function creation is handled by **`FunctionAnalyzer`** — a separate
`INSTRUCTION_ANALYZER` at `CODE_ANALYSIS.before()` priority — which watches for call references
and creates functions at their targets after disassembly completes.

## Instruction Representation: Assembly View vs. PCode

### Two Views, One Source of Truth: SLEIGH

Every instruction has **both** representations simultaneously — but neither is stored
redundantly. They both derive from the same SLEIGH specification on demand.

### What's Actually in the Database

Surprisingly little. The DB schema for an instruction is just:

```
address → (ProtoID, Flags)
```

- **ProtoID**: reference to an `InstructionPrototype` (the parsed SLEIGH constructor)
- **Flags**: FlowOverride, LengthOverride, FallThroughOverride bits

No raw bytes (read from memory on demand), no mnemonic strings, no PCode ops.

### The `InstructionPrototype` — Both Views in One Object

[InstructionPrototype.java](Ghidra/Framework/SoftwareModeling/src/main/java/ghidra/program/model/lang/InstructionPrototype.java)
[SleighInstructionPrototype.java](Ghidra/Framework/SoftwareModeling/src/main/java/ghidra/app/plugin/processors/sleigh/SleighInstructionPrototype.java)

`SleighInstructionPrototype` gets built once when an instruction is first parsed, then reused
for every identical instruction in the program:

```
SleighInstructionPrototype
├─ Assembly view (from SLEIGH parsing):
│   ├─ length
│   ├─ mnemonic constructors
│   └─ operand info (registers, scalars, addresses)
│
├─ Flow info (cached at construction from SLEIGH templates):
│   ├─ flowStateList  (list of FlowRecord)
│   └─ flowType       (UNCONDITIONAL_JUMP, CALL, TERMINATOR, etc.)
│
└─ PCode generation (on demand, never stored):
    └─ getPcode() → walks SLEIGH templates → emits PcodeOp[]
```

### FlowType and `getFlows()` Come from SLEIGH, NOT PCode

When the disassembler calls `inst.getFlowType()` to decide if something is a call, jump, or
terminator — it is **not analyzing PCode**. It reads flow directives baked into the prototype
at parse time.

SLEIGH instructions declare their flow behavior explicitly in the spec. During prototype
construction, `cacheTreeInfo()` walks those templates and computes a `FlowType` enum value.
That value is cached and returned directly — no PCode evaluation needed.

```java
// InstructionDB.getFlowType()
public FlowType getFlowType() {
    return FlowOverride.getModifiedFlowType(proto.getFlowType(this), flowOverride);
    //                                       ^ from SLEIGH cache, not PCode
}
```

Similarly, `getFlows()` (the actual target addresses of jumps/calls) comes from parsing the
SLEIGH constructor's operand handles — the address is extracted directly from the decoded
instruction fields, not from executing PCode.

### PCode Is Lazy — Generated On Demand, Never Stored

When you call `instruction.getPcode()`, it re-walks the SLEIGH template for that instruction
and emits a fresh `PcodeOp[]` array. It is **not stored anywhere**. Every call regenerates it
from the prototype's template. The decompiler calls this constantly as it lifts functions to
PCode IR.

### Example: `MOV AX, 10h`

| Query | Where it comes from | Stored? |
|-------|---------------------|---------|
| `getMnemonicString()` → `"MOV"` | SLEIGH constructor | No |
| `getOperandRepresentation(0)` → `"AX"` | Decoded from bytes via SLEIGH | No |
| `getOperandRepresentation(1)` → `"10h"` | Decoded from bytes via SLEIGH | No |
| `getFlowType()` → `FALL_THROUGH` | SLEIGH prototype cache | No |
| `getPcode()` → `[COPY AX, 0x10]` | Generated fresh from SLEIGH template | No |

Only `address → (ProtoID, flags)` lives in the database.

### Summary

| Question | Answer |
|----------|--------|
| Are there two representations? | Yes — assembly and PCode — but both derive from the same SLEIGH prototype |
| Is assembly always converted to PCode? | No. PCode is generated lazily on demand only |
| Does flow analysis use PCode? | No. FlowType and flow targets come from SLEIGH's cached metadata |
| What's stored in the DB? | Only (ProtoID, flags) per address — everything else is recomputed |
| Where does `getFlowType()` come from? | SLEIGH flow directives, parsed once at prototype construction |
| Where does `getPcode()` come from? | Walking SLEIGH templates at call time, never cached |

## The Full Pipeline

```
EntryPointAnalyzer.added()
  → Disassembler.disassemble(entries, followFlow=true)
      → DisassemblerQueue drives traversal
      → SLEIGH parses each instruction → FlowType + flows
      → Branches: immediate; Calls: deferred
  → AutoAnalysisManager.codeDefined(newAddresses)

Triggered by codeDefined event (in priority order):
  → FunctionAnalyzer              creates functions at call targets
  → FindNoReturnFunctionsAnalyzer marks non-returning functions
  → CallFixupAnalyzer             installs compiler spec fixups
  → ConstantPropagationAnalyzer   resolves computed jumps/calls
  → OperandReferenceAnalyzer      creates data refs, finds switch tables
```
