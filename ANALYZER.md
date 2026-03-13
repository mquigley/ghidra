# Auto-Analysis Framework

## The `Analyzer` Interface

Every analyzer implements `Analyzer` (or extends `AbstractAnalyzer`) and is discovered automatically by `ClassSearcher` — the only requirement is that the class name ends in `Analyzer`.

The core method is `added(Program, AddressSetView, TaskMonitor, MessageLog)` — called with the set of addresses that triggered the analysis event.

## Trigger Model: AnalyzerType

Analyzers don't poll; they subscribe to specific types of program events:

| Type | Triggered when... |
|------|-------------------|
| `BYTE_ANALYZER` | Memory blocks are added |
| `INSTRUCTION_ANALYZER` | Instructions are defined |
| `FUNCTION_ANALYZER` | Functions are created |
| `FUNCTION_MODIFIERS_ANALYZER` | Function modifiers change (inline, thunk, no-return) |
| `FUNCTION_SIGNATURES_ANALYZER` | Function signatures change |
| `DATA_ANALYZER` | Data is defined |

## Execution Order: AnalysisPriority

Analyzers declare a priority that determines when they run relative to each other:

```
FORMAT_ANALYSIS (100)    → header markup (ELF, PE, DWARF)
BLOCK_ANALYSIS  (200)    → entry points
DISASSEMBLY     (300)    → code recovery / flow analysis
CODE_ANALYSIS   (400)    → non-returning functions, flow fixes
FUNCTION_ANALYSIS (500)  → boundary detection
REFERENCE_ANALYSIS (600) → operands, strings, pointers
DATA_ANALYSIS   (700)    → string/struct creation
FUNCTION_ID_ANALYSIS (800) → function identification
DATA_TYPE_PROPOGATION (900) → late type propagation
```

Fine-grained control: `priority.before()` (-1), `priority.after()` (+1), `priority.getNext()` (+100).

## Analyzers by Priority

### FORMAT_ANALYSIS (96–102) — Binary format markup

| Analyzer | Type | Priority | Purpose |
|---|---|---|---|
| `MingwRelocationAnalyzer` | BYTE | 95 | Identify and apply MinGW pseudo-relocations |
| `ArmSymbolAnalyzer` | BYTE | 96 | Detect Thumb symbols and shift addresses by -1 as needed |
| `NoReturnFunctionAnalyzer` | BYTE | 97 | Mark known non-returning functions by name (exit, abort, etc.) |
| `ElfAnalyzer` | BYTE | 100 | Parse ELF headers, segments, sections, and symbols |
| `MachoAnalyzer` | BYTE | 100 | Parse Mach-O headers, load commands, and symbols |
| `PortableExecutableAnalyzer` | BYTE | 100 | Parse PE headers, sections, imports, exports, and relocations |
| `CoffAnalyzer` | BYTE | 100 | Parse COFF binary format |
| `PefAnalyzer` (format) | BYTE | 100 | Parse PEF (Classic Mac OS) binary format |
| `ObjcTypeMetadataAnalyzer` | BYTE | 100 | Discover Objective-C type metadata records |
| `SwiftTypeMetadataAnalyzer` | BYTE | 100 | Discover Swift type metadata records |
| `DWARFAnalyzer` | BYTE | 101 | Extract DWARF debug info (types, functions, line numbers) from ELF/Mach-O/PE |
| `Objc2MessageAnalyzer` | FUNCTION | 101 | Extract Objective-C 2.0 message dispatch information |
| `GolangSymbolAnalyzer` | BYTE | 102 | Analyze Go binaries for RTTI and function symbols |
| `AbstractDemanglerAnalyzer` | BYTE | 897 (DATA_TYPE_PROPOGATION-3) | Demangle Microsoft/GNU/Rust symbol names |

---

### BLOCK_ANALYSIS (200–202) — Initial disassembly seeds

| Analyzer | Type | Priority | Purpose |
|---|---|---|---|
| `EmbeddedMediaAnalyzer` | BYTE | 200 | Find embedded PNG, GIF, JPEG, WAV, MIDI data and mark it |
| `EntryPointAnalyzer` | BYTE | 200 | Disassemble entry points from symbol table, CodeMap markers, and language-defined vectors; seeds all subsequent flow-following |
| `CreateThunkAnalyzer` | INSTRUCTION | 202 | Create thunk functions early, before function boundary analysis runs |

---

### DISASSEMBLY (300–302) — Code recovery and flow

| Analyzer | Type | Priority | Purpose |
|---|---|---|---|
| `FindNoReturnFunctionsAnalyzer` | INSTRUCTION | 301 | Detect that calls to certain functions never return; marks them so flow analysis stops at those call sites |
| `CallFixupAnalyzer` | FUNCTION | 302 | Install compiler-spec call-fixups (inline PCode substitutions for compiler intrinsics like `__alloca`) |
| `CallFixupChangeAnalyzer` | FUNCTION_MODIFIERS | 302 | Re-apply call-fixups when a function's modifiers change |

---

### CODE_ANALYSIS (398–400) — Function creation and flow fixups

| Analyzer | Type | Priority | Purpose |
|---|---|---|---|
| `ExternalEntryFunctionAnalyzer` | BYTE | 398 | Create function stubs at external entry points (exports, entry symbols) |
| `SharedReturnJumpAnalyzer` | INSTRUCTION | 398 | Convert tail-call branches into CALL+RETURN pairs so function boundaries are correct |
| `SharedReturnAnalyzer` | FUNCTION | 398 | Same as above, but triggered when a function is created rather than when an instruction is defined |
| `FunctionAnalyzer` | INSTRUCTION | 399 | Create `Function` objects at call targets discovered during disassembly |
| `CliMetadataTokenAnalyzer` | INSTRUCTION | 400 | Decode CLI (.NET) metadata tokens embedded in instructions into human-readable names |
| `DecompilerSwitchAnalyzer` | INSTRUCTION | 400 | Use the decompiler to recover switch statement targets that the flow-follower couldn't resolve |

---

### FUNCTION_ANALYSIS (500) — Function boundary detection

| Analyzer | Type | Priority | Purpose |
|---|---|---|---|
| `X86FunctionPurgeAnalyzer` | FUNCTION | 500 | Determine the stack-purge value (bytes popped by callee) for stdcall functions on x86 |
| `SegmentedCallingConventionAnalyzer` | FUNCTION | 500 | Detect calling conventions in x86 segmented (real-mode) programs |

---

### REFERENCE_ANALYSIS (596–602) — Operands, strings, pointers

| Analyzer | Type | Priority | Purpose |
|---|---|---|---|
| `ConstantPropagationAnalyzer` | INSTRUCTION | 596 | Symbolic execution via `SymbolicPropogator` to resolve computed addresses, indirect calls, and register-based memory references; creates references and data at resolved targets |
| `ScalarOperandAnalyzer` | INSTRUCTION | 598 | Scan scalar immediate operands and create data references when they look like valid addresses |
| `ElfScalarOperandAnalyzer` | INSTRUCTION | 598 | For ELF shared libraries: suppress false references created by `ScalarOperandAnalyzer` for position-independent code |
| `OperandReferenceAnalyzer` | INSTRUCTION | 600 | For every instruction operand reference: validate code targets, create ASCII/Unicode strings, detect pointer tables and switch tables via `AddressTable` |
| `GolangStringAnalyzer` | BYTE | 604 | Find and label Go string structures (Go stores strings as {ptr, len} pairs, not null-terminated) |
| `DataOperandReferenceAnalyzer` | DATA | 602 | Same operand-reference analysis applied to Data items (pointer arrays, vtables, etc.) |

---

### DATA_ANALYSIS (698–700) — Data structure creation

| Analyzer | Type | Priority | Purpose |
|---|---|---|---|
| `PefAnalyzer` (functions) | FUNCTION | 698 | Create references to symbols indirectly addressed via the R2 (TOC) register in PEF binaries |
| `AddressTableAnalyzer` | BYTE | 699 | Scan undefined data regions for address tables (jump tables, vtables, pointer arrays) and create pointer data |

---

### FUNCTION_ID_ANALYSIS (800–803) — Function identification

| Analyzer | Type | Priority | Purpose |
|---|---|---|---|
| `ApplyDataArchiveAnalyzer` | BYTE | 801 | Apply known data type archives (.gdt files) based on compiler/library identification |
| `MachoFunctionStartsAnalyzer` | BYTE | 801 | Create functions at addresses listed in Mach-O `LC_FUNCTION_STARTS` load command |
| `DecompilerCallConventionAnalyzer` | FUNCTION_SIGNATURES | 803 | Use the decompiler to infer calling conventions for functions with unknown conventions |

---

### DATA_TYPE_PROPOGATION (896–905) — Late type propagation and cleanup

| Analyzer | Type | Priority | Purpose |
|---|---|---|---|
| `ExternalSymbolResolverAnalyzer` | BYTE | 896 | Link unresolved external symbols to the first matching symbol in required libraries |
| `AbstractDemanglerAnalyzer` | BYTE | 897 | Demangle C++/Rust/Swift mangled symbol names and apply recovered type information |
| `DecompilerFunctionAnalyzer` | FUNCTION | 902 | Use the decompiler to recover parameter and local variable types for each function |
| `StackVariableAnalyzer` | FUNCTION | 903 | Create stack variable definitions for a function based on stack accesses found during analysis |
| `StringsAnalyzer` | BYTE | 905 | Sweep all initialized memory with a probabilistic n-gram model to find and define ASCII/Unicode strings not referenced by any instruction |
| `CondenseFillerBytesAnalyzer` | BYTE | 905 | Find runs of filler bytes between functions (0x00, 0x90, 0xCC) and mark them as `AlignmentDataType` |
| `RustStringAnalyzer` | BYTE | 10000 (LOW) | Split non-null-terminated Rust static strings into separate string Data items |

---

### Special / Language-Specific (10000+)

| Analyzer | Type | Priority | Purpose |
|---|---|---|---|
| `Objc1MessageAnalyzer` | FUNCTION | 10000000 | Extract `_objc_msgSend` dispatch targets (Objective-C 1.x runtime) |
| `ObjectiveC2_DecompilerMessageAnalyzer` | FUNCTION | 10000000 | Extract Objective-C 2.0 message dispatch targets using decompiler output |

## AutoAnalysisManager — The Scheduler

There is a **single dedicated analysis thread**. Events are batched (500ms default) before analyzers are invoked.

Key source files:
- [AutoAnalysisManager.java](Ghidra/Features/Base/src/main/java/ghidra/app/plugin/core/analysis/AutoAnalysisManager.java)
- [AnalysisScheduler.java](Ghidra/Features/Base/src/main/java/ghidra/app/plugin/core/analysis/AnalysisScheduler.java)
- [AnalysisTaskList.java](Ghidra/Features/Base/src/main/java/ghidra/app/plugin/core/analysis/AnalysisTaskList.java)

### The Main Loop

`startAnalysis()` runs a `while(true)` loop on the single analysis thread:

```
loop:
  1. Run activeTask to completion   ← one full analyzer.added() call
  2. synchronized { dequeue next from PriorityQueue }
  3. If queue empty → break
```

**One analyzer runs to completion before the next starts.** There is no mid-task interruption. A higher-priority task arriving during execution just sits in the queue and is picked up on the next iteration.

### Address Batching

Addresses are **not dispatched one-by-one**. When a program event fires (e.g., 100 instructions defined):

1. `AnalysisTaskList.notifyAdded(addressSet)` broadcasts to all analyzers of that `AnalyzerType`
2. Each analyzer's `AnalysisScheduler` accumulates those addresses into its own `addSet`
3. When scheduled, the entire accumulated `addSet` is passed as one `AddressSetView` to `analyzer.added()`

All 100 addresses go to the analyzer in one call — not 100 separate tasks.

### Priority Queue

The queue is a min-heap `PriorityQueue<BackgroundCommand<Program>>`. Lower numeric value = higher priority (hence `FORMAT_ANALYSIS=100` runs before `DATA_ANALYSIS=700`). `getNextTask()` calls `queue.removeFirst()` each loop iteration.

### Yield — Recursive Nesting

`yield(limitPriority)` is the only way to get interleaving. It works by **recursively calling `startAnalysis()`**:

```
Analyzer A (priority 500) is running
  → calls yield(400)
    → current task paused (timer paused), pushed onto yieldedTasks stack
    → inner startAnalysis() runs, drains all tasks with priority < 400
    → inner loop exits
  → Analyzer A's task is popped from yieldedTasks stack, timer resumed
  → Analyzer A continues
```

It is a call-stack–based nested loop, not a preemption mechanism. The yielded analyzer voluntarily hands control back.

External threads can call `waitForAnalysis(limitPriority)` to block until analysis up to a given priority completes.

### Summary

| Question | Answer |
|----------|--------|
| Run order | Highest priority task runs first, fully to completion |
| Granularity | Per-task (one full `added()` call), not per-address |
| Address delivery | Whole accumulated `AddressSet` in one call |
| Higher-priority preemption | None — queued and picked up next iteration |
| Interleaving mechanism | Only via `yield()` (recursive loop on same thread) |
| Threading | Single dedicated analysis thread; synchronized queue access |

## Writing a New Analyzer

```java
@ExtensionPointProperties(priority = 1)
public class MyAnalyzer extends AbstractAnalyzer {
    public MyAnalyzer() {
        super("My Analyzer", "Description", AnalyzerType.FUNCTION_ANALYZER);
        setPriority(AnalysisPriority.FUNCTION_ANALYSIS);
        setDefaultEnablement(true);
    }

    @Override
    public boolean canAnalyze(Program program) {
        return program.getLanguage().getProcessor().toString().equals("x86");
    }

    @Override
    public boolean added(Program program, AddressSetView set,
                         TaskMonitor monitor, MessageLog log) throws CancelledException {
        // process addresses in `set`
        monitor.checkCancelled();
        return true;  // true = changes made
    }
}
```

Key rules:
- Class name must end in `Analyzer` for `ClassSearcher` auto-discovery
- Always call `monitor.checkCancelled()` in loops
- All analyzers run on a single thread; use `AbstractAnalyzer.runParallelAddressAnalysis()` for parallel sub-tasks
- Never mutate the program outside a transaction

Source: [Ghidra/Features/Base/src/main/java/ghidra/app/plugin/core/analysis/](Ghidra/Features/Base/src/main/java/ghidra/app/plugin/core/analysis/)
