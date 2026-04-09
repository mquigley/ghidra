# Decompiler ruleaction: trivial arithmetic and register-clear idioms

This note documents how Ghidra handles x86-style **same-register** logical ops for SSA and use–def reasoning. The decompiler core lives under `Ghidra/Features/Decompiler/src/decompile/cpp/`; the main rule implementations are in `ruleaction.cc`.

## `OR` vs `XOR` (terminology)

- **`OR reg, reg`** is **not** a zero idiom. Bitwise `x | x` equals `x` (identity). It is often used to set flags while leaving the register value unchanged.
- **`XOR reg, reg`** (and sometimes **`SUB reg, reg`**) is the usual compact encoding for **clearing** the register (`reg = 0`).

## `RuleTrivialArith` — decompiler fold

**Class:** `RuleTrivialArith` in `ruleaction.cc`.

**Purpose:** Simplify binary ops when **both inputs hold the same value** (same `Varnode`, or two inputs whose defining ops **CSE-match** via `isCseMatch`).

Documented equivalences include:

| Form | Result |
|------|--------|
| `V == V`, `V <= V`, … | constants / booleans as appropriate |
| `V & V` | `V` |
| `V \| V` | `V` |
| `V ^ V` | `#0` (constant zero) |

**Implementation sketch:** For `CPUI_INT_XOR` with identical inputs, the rule sets the op to **`CPUI_COPY`** with a **new constant 0** input, removing the second input. That turns `XOR AX, AX`–style p-code into “assign 0” without keeping a misleading **read** of the prior register value for data-flow.

For `CPUI_INT_OR` / `CPUI_INT_AND` with identical inputs, the rule becomes **`COPY`** of **one** operand only (`vn == nullptr` branch), so **`OR reg, reg`** still carries a **use** of `reg`, which matches real semantics.

**File reference:** `Ghidra/Features/Decompiler/src/decompile/cpp/ruleaction.cc` — search for `RuleTrivialArith` (class comment lists `V | V => V`, `V ^ V => #0`, etc.).

## Java-side constant / symbolic handling (not the main SSA rule pass)

- **`SymbolicPropogator`** — for `PcodeOp.INT_XOR`, if both inputs are the **same register** `Varnode`, the result is folded to constant **0** without treating it like a general two-operand XOR.  
  **File:** `Ghidra/Features/Base/src/main/java/ghidra/program/util/SymbolicPropogator.java` (`case PcodeOp.INT_XOR`).

- **`ResultsState`** — constant folding for `INT_XOR` includes the case where the two abstract values are **equal** → result **0**.  
  **File:** `Ghidra/Features/Base/src/main/java/ghidra/util/state/ResultsState.java` (`case PcodeOp.INT_XOR`).

- **Taint / emulation** — e.g. `TaintPcodeArithmetic` documents **`XOR RAX, RAX`** as a **`MOV`-to-zero** idiom and reasons from **input varnodes**, not only runtime values.  
  **File:** `Ghidra/Debug/TaintAnalysis/src/main/java/ghidra/pcode/emu/taint/TaintPcodeArithmetic.java`.

## Summary

- **`XOR reg, reg`** is accommodated in the **decompiler** primarily by **`RuleTrivialArith`**: **`V ^ V` → `COPY #0`**, which aligns SSA/use–def behavior with “definition only from constant,” not a real dependency on the old register value.
- **`OR reg, reg`** is **`V | V` → `COPY V`** (identity), not zero; a use of `reg` remains appropriate for analysis.
