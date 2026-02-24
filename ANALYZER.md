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

## Key Built-in Analyzers

| Analyzer | Type | Priority | Purpose |
|----------|------|----------|---------|
| `OperandReferenceAnalyzer` | INSTRUCTION | REFERENCE_ANALYSIS | Creates refs, finds strings, pointer tables, switch tables |
| `FindNoReturnFunctionsAnalyzer` | FUNCTION | CODE_ANALYSIS | Detects non-returning functions |
| `ConstantPropagationAnalyzer` | INSTRUCTION | DATA_TYPE_PROPOGATION | Symbolic execution for constant/pointer recovery |
| `DWARFAnalyzer` | BYTE | FORMAT_ANALYSIS | DWARF debug info extraction |

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
