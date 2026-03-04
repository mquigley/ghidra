# Register Context and CPU Register Storage

Source: [ProgramRegisterContextDB.java](Ghidra/Framework/SoftwareModeling/src/main/java/ghidra/program/database/register/ProgramRegisterContextDB.java)

## What Is Stored Here

`ProgramRegisterContextDB` stores **any register value at any address range** — both
processor context registers (e.g., ARM `TMode`, MIPS `ISAModeSwitch`) and regular CPU
registers (e.g., x86 `DS`, `CS`, `SS`, `SP`, `AX`). It is the same mechanism for both.

This is the persistent store returned by `program.getProgramContext()`. It backs the
`Listing` and analysis layer's register queries.

## Two Maps, Two Storage Backends

`AbstractStoredProgramContext` (the parent class) maintains two maps:

```java
protected Map<Register, RegisterValueStore> registerValueMap;        // instance-specific values
protected Map<Register, RegisterValueStore> defaultRegisterValueMap; // language/compiler defaults
```

| Map | Source | Storage Backend | Persistence |
|-----|--------|-----------------|-------------|
| `registerValueMap` | Loaders, analyzers, user code | `DatabaseRangeMapAdapter` → `AddressRangeMapDB` (DB table) | Yes — survives sessions |
| `defaultRegisterValueMap` | Language `.pspec` + CompilerSpec `.cspec` | `InMemoryRangeMapAdapter` | No — rebuilt each load |

`getValue()` checks `registerValueMap` first. If no value, falls back to `defaultRegisterValueMap`.

## Storage: AddressRangeMapDB

Each register gets its own `AddressRangeMapDB` table, named `"Range Map - Register_[name]"`.
Records are `(start_address, end_address, value_bytes)` — a sparse set of address ranges,
each annotated with a register value.

A write cache in `RegisterValueStore` merges contiguous writes with the same value into a
single range before flushing to the DB — important during disassembly when context register
values flow unchanged across thousands of instructions.

## setValue() — Writing Register Values

```java
// ProgramRegisterContextDB.java lines 251-271
@Override
public void setValue(Register register, Address start, Address end, BigInteger value)
        throws ContextChangeException {
    lock.acquire();
    try {
        checkContextWrite(register, start, end);
        super.setValue(register, start, end, value);
        if (program != null) {
            program.setRegisterValuesChanged(register, start, end);  // notify listeners
        }
    } finally {
        lock.release();
    }
}
```

A `null` value means delete (remove the range). Non-null values are stored as a
`RegisterValue` (a bitmask + value pair so partial register writes can be tracked).

## MzLoader — Setting Segment Registers at Load Time

[MzLoader.java](Ghidra/Features/Base/src/main/java/ghidra/app/util/opinion/MzLoader.java)
sets DS, CS, SS, SP for 16-bit DOS MZ executables via `ProgramContext.setValue()` at load
time:

```java
// MzLoader.java ~lines 376-443 (processRegisters method)
ProgramContext context = program.getProgramContext();
Register ss = context.getRegister("ss");
Register sp = context.getRegister("sp");
Register ds = context.getRegister("ds");
Register cs = context.getRegister("cs");

// SP and SS at entry point only
context.setValue(sp, entry.getAddress(), entry.getAddress(), BigInteger.valueOf(header.e_sp()));
context.setValue(ss, entry.getAddress(), entry.getAddress(), BigInteger.valueOf(ssValue));

// CS and DS for each entire memory block
for (MemoryBlock block : program.getMemory().getBlocks()) {
    BigInteger csValue = BigInteger.valueOf(((SegmentedAddress) block.getStart()).getSegment());
    context.setValue(cs, block.getStart(), block.getEnd(), csValue);
    if (shouldSetDS) {
        context.setValue(ds, block.getStart(), block.getEnd(), BigInteger.valueOf(dsValue));
    }
}
```

These values are written once and persist in the program DB. They are visible to analyzers
and scripts that call `context.getValue(register, address)`.

## SymbolicPropagator — Ephemeral, Not Persistent

[SymbolicPropogator.java](Ghidra/Framework/SoftwareModeling/src/main/java/ghidra/program/util/SymbolicPropogator.java)
does **not** write discovered register values back to the persistent `ProgramRegisterContextDB`.
It creates two private in-memory `ProgramContextImpl` instances:

```java
// SymbolicPropogator constructor
programContext = new ProgramContextImpl(language);   // ephemeral
spaceContext = new ProgramContextImpl(language);     // ephemeral
context = new VarnodeContext(program, programContext, spaceContext, ...);
```

`ProgramContextImpl` uses `InMemoryRangeMapAdapter` exclusively — no DB tables, no
persistence. All symbolic state (e.g., "AX = 0x21 at address 0x1234") is computed during
analysis and discarded when the analysis task completes.

**The implication**: even if `ConstantPropagationAnalyzer` discovers that `AX = 0x21`
before an interrupt call, that value is never written to `ProgramRegisterContextDB`. It
is used only within the propagation pass to resolve computed jumps/calls and create
cross-references.

## Summary

| Question | Answer |
|----------|--------|
| Where does Ghidra store DS/CS/SS/SP? | `ProgramRegisterContextDB`, backed by `AddressRangeMapDB` tables in the embedded DB |
| Who writes those values for MZ files? | `MzLoader.processRegisters()` at load time via `ProgramContext.setValue()` |
| Do analyzers persist discovered register values? | No — `SymbolicPropogator` uses ephemeral in-memory contexts only |
| Can scripts query register values at an address? | Yes — `program.getProgramContext().getValue(register, address)` |
| Are context registers and CPU registers stored the same way? | Yes — same `AddressRangeMapDB` mechanism for both |
| What is `defaultRegisterValueMap` for? | Language `.pspec` and compiler `.cspec` defaults; fallback when no explicit value set |
