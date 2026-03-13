# SymbolManager — How Symbols Work

Source: [SymbolManager.java](Ghidra/Framework/SoftwareModeling/src/main/java/ghidra/program/database/symbol/SymbolManager.java)

`SymbolManager` is the sole owner of all symbol data in the program. It implements `SymbolTable` and is backed by a `SymbolDatabaseAdapter` (a B-Tree keyed by address). It handles every named or nameable thing in the program.

## Symbol Types

`SymbolType` is a set of singleton constants:

| Type | Stored | What it is |
|------|--------|------------|
| `LABEL` (was `CODE`) | DB or dynamic | Named address in memory or external |
| `FUNCTION` | DB | Function entry point |
| `NAMESPACE` | DB | Organizational scope (no address) |
| `CLASS` | DB | C++ class namespace |
| `LIBRARY` | DB | External library reference |
| `PARAMETER` | DB | Function parameter |
| `LOCAL_VAR` | DB | Local variable |
| `GLOBAL_VAR` | DB | Global register variable |

`LABEL` and `FUNCTION` both `allowsDuplicates()` — multiple symbols can share an address.

## Source Type — The Trust Hierarchy

Every stored symbol has a `SourceType` that determines its "trust level", ordered by priority:

```
USER_DEFINED   (4) — user explicitly named it
IMPORTED       (3) — came from the binary (ELF symbol table, DWARF, etc.)
ANALYSIS / AI  (2) — created by an analyzer
DEFAULT        (1) — auto-generated; lowest trust
```

This priority is used to protect higher-quality names from being overwritten by lower-quality analysis.

## Dynamic Symbols — Auto-Generated Labels

**Dynamic symbols are not stored in the database at all.** They are synthesized on demand.

The rule: any memory address that has **at least one incoming reference** but **no stored symbol record** gets a dynamic symbol.

`getPrimarySymbol(addr)`:
```java
DBRecord record = adapter.getPrimarySymbol(addr);
if (record != null) {
    return getSymbol(record);           // stored symbol
}
if (refManager.hasReferencesTo(addr)) {
    return getDynamicSymbol(addr);      // synthesized on the fly
}
return null;                            // no symbol at all
```

`getDynamicSymbol(addr)` constructs a `CodeSymbol` with a **derived ID** (not a DB row key): `dynamicSymbolAddressMap.getKey(addr)` encodes the address into a long with the high-order `0x40` byte set, so dynamic IDs never collide with stored IDs.

### Dynamic Name Generation

The symbol's display name is computed by `SymbolUtilities.getDynamicName(program, addr)` based on what's at the address and how many/what type of references point there (`ReferenceManager.getReferenceLevel()`):

| Prefix | Level | When used |
|--------|-------|-----------|
| `FUN_` | 6 | Address is a call target → function entry |
| `LAB_` | 2 | Address is a jump/fall-through target |
| `DAT_` | 1 | Address contains defined data |
| `EXT_` | 5 | External entry point |

The address portion is formatted by `SymbolUtilities.getAddressString(addr)` — for segmented addresses this produces `seg:off` encoding.

DataTypes can contribute their own prefix via `DataType.getDefaultLabelPrefix()` — for example a string DataType emits `s_` giving `s_HelloWorld_00401234`.

When a dynamic symbol is **renamed**, `convertDynamicToNamedSymbol()` writes a real record to the DB with the specified `SourceType` and the dynamic symbol ceases to exist.

## Function Symbols

A `FUNCTION` symbol always coexists with its function entry point address. When `FunctionAnalyzer` creates a function, `FunctionManagerDB` creates both the `FunctionDB` object and a `FunctionSymbol` record in `SymbolManager` — this is the `FUN_` name visible in the Listing.

Function symbols start at `SourceType.DEFAULT`; they become `IMPORTED` when loaded from ELF `.dynsym` / DWARF, and `USER_DEFINED` when renamed manually.

`FunctionSymbol` at an address takes precedence over `CodeSymbol` — `CodeSymbol.isPrimary()` returns `false` if a `FunctionSymbol` already exists at the same address.

## Multiple Symbols at One Address

Multiple symbols can exist at the same address. `getSymbols(addr)` returns an array with the **primary** symbol at index 0. For memory addresses, exactly one symbol is designated primary (the `isPrimary` flag is stored in the DB record). For dynamic symbols, `isPrimary()` always returns `true` (there is only one, and it has no record).

## Label History

Every time a symbol is added, renamed, or removed at an address, `SymbolManager` writes a `LabelHistory` record to `historyAdapter`. This is the "Symbol History" window in the UI — a permanent audit log per address.

## Key Source Files

- [SymbolManager.java](Ghidra/Framework/SoftwareModeling/src/main/java/ghidra/program/database/symbol/SymbolManager.java) — main implementation
- [SymbolType.java](Ghidra/Framework/SoftwareModeling/src/main/java/ghidra/program/model/symbol/SymbolType.java) — symbol type constants and validation rules
- [SourceType.java](Ghidra/Framework/SoftwareModeling/src/main/java/ghidra/program/model/symbol/SourceType.java) — trust hierarchy enum
- [CodeSymbol.java](Ghidra/Framework/SoftwareModeling/src/main/java/ghidra/program/database/symbol/CodeSymbol.java) — LABEL symbol implementation (both stored and dynamic)
- [SymbolUtilities.java](Ghidra/Framework/SoftwareModeling/src/main/java/ghidra/program/model/symbol/SymbolUtilities.java) — dynamic name generation (`FUN_`, `LAB_`, `DAT_`, `EXT_` prefixes)

## Summary

| Question | Answer |
|----------|--------|
| Are `FUN_`, `LAB_`, `DAT_` labels stored in the DB? | No — synthesized on demand from reference presence |
| What triggers a dynamic symbol? | Any address with ≥1 incoming reference and no stored symbol |
| What decides `FUN_` vs `LAB_` vs `DAT_`? | `ReferenceManager.getReferenceLevel()` — count/type of refs pointing there |
| When does a dynamic symbol become real? | When renamed — written to DB with the specified `SourceType` |
| Can multiple symbols share an address? | Yes — one is `isPrimary`; `FunctionSymbol` always wins primary |
| Does `SymbolType.LABEL` allow duplicate names? | Yes — same name can appear multiple times at different addresses |
