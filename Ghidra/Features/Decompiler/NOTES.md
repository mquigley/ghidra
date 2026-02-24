# Ghidra Decompiler Module — Analysis Notes

> Generated: 2026-02-23. Re-read this file at the start of any session involving the Decompiler module.

---

## Directory Structure

```
Ghidra/Features/Decompiler/
├── build.gradle                    # Java build
├── buildNatives.gradle             # Native C++ build (cross-platform)
├── data/                           # Runtime data (theme properties)
├── ghidra_scripts/                 # Decompiler-related Ghidra scripts
├── src/
│   ├── decompile/
│   │   ├── cpp/                    # C++ decompiler core (~186K lines, 229 files)
│   │   │   ├── *.cc / *.hh         # Source files
│   │   │   ├── *.y / *.l           # Bison/Flex parser definitions
│   │   │   └── Makefile, Doxyfile
│   │   ├── unittests/              # C++ unit tests
│   │   ├── datatests/              # C++ data-driven tests
│   │   └── zlib/                   # Bundled zlib
│   ├── main/java/
│   │   ├── ghidra/app/decompiler/  # Core Java API (~47 files)
│   │   ├── ghidra/app/plugin/core/decompile/  # UI Plugin (10 files)
│   │   ├── ghidra/app/plugin/core/analysis/   # Analysis algorithms
│   │   └── ghidra/app/util/exporter/          # C code export
│   └── test.slow/java/             # Integration tests (~18 test classes)
└── Module.manifest
```

---

## Architecture

**Hybrid Java/C++ with process isolation.**

```
Ghidra Framework (Java)
        │
Java Integration Layer
  - DecompilePlugin        (UI plugin, entry point)
  - DecompilerProvider     (UI view / window)
  - DecompInterface        (main public API)
  - DecompileProcess       (spawns/manages C++ subprocess)
  - DecompileCallback      (responds to C++ data queries)
  - DecompileOptions       (100+ configuration knobs)
        │
        │  binary protocol over stdin/stdout pipes
        ▼
C++ Decompiler Core  (standalone native executable: `decompile`) — [deep dive notes](src/decompile/cpp/NOTES.md)
  - ArchitectureGhidra     (coordinator, query/response protocol)
  - Funcdata               (per-function analysis container)
  - Action framework       (modular transformation/optimization rules)
  - PCode IR               (platform-independent intermediate representation)
  - PrintC                 (C code generation)
```

---

## Java/C++ Communication Protocol

- **Transport**: stdin/stdout pipes between Java process and C++ subprocess
- **Encoding**: `PackedEncode`/`PackedDecode` (binary serialization, not plain XML)
- **Markers**:
  - Command start: `{0,0,1,2}` / end: `{0,0,1,3}`
  - Query start: `{0,0,1,8}` / end: `{0,0,1,9}`
- **Callback flow**: C++ can pause and query Java mid-decompilation (e.g., to fetch raw bytes, type info, comments); Java's `DecompileCallback` handles these.
- **Process lifecycle**: Subprocess is spawned on demand, cached, and auto-restarted on crash.

---

## Key Java Files

| File | Purpose |
|------|---------|
| `DecompInterface.java` | Main public API — opens program, triggers decompilation, parses results |
| `DecompileProcess.java` | Spawns native executable, manages I/O, enforces timeouts |
| `DecompileCallback.java` | Handles C++ callbacks — fetches bytes, types, symbols from Ghidra DB |
| `DecompileOptions.java` | 100+ options controlling analysis behavior and output style |
| `DecompilerProvider.java` | UI component — renders decompiled C code with highlighting |
| `DecompilePlugin.java` | Ghidra plugin registration and tool integration |
| `DecompileResults.java` | Result container — C code markup + optional CFG/data-flow info |
| `ClangToken*.java` | Token hierarchy — represents C code syntax tree for display |
| `PrettyPrinter.java` | Converts token tree to formatted C code string |
| `ParallelDecompiler.java` | Bulk decompilation via thread pool |

---

## Key C++ Files

| File | Purpose |
|------|---------|
| `ghidra_arch.hh/cc` | Ghidra-specific architecture — query/response protocol implementation |
| `ghidra_process.hh/cc` | Process lifecycle, main loop |
| `architecture.hh/cc` | Base architecture class, configuration |
| `funcdata.hh/cc` | Per-function container: CFG, SSA values, PCode ops |
| `action.hh/cc` | Action/Rule framework — transformation pipeline |
| `varnode.hh/cc` | SSA value (Varnode) representation |
| `op.hh/cc` | PCode operation representation |
| `block.hh/cc` | Basic block / control-flow graph structures |
| `heritage.hh/cc` | SSA form maintenance (phi insertion, liveness) |
| `type.hh/cc` | Data-type system |
| `printc.hh/cc` | C code generation |
| `grammar.y`, `xml.y` | Bison parsers |

---

## Data Flow: Raw Bytes → Decompiled C

```
1. User navigates to function in Ghidra UI
2. DecompilerProvider.setLocation(func)
3. DecompileRunnable → DecompInterface.decompileFunction(func, timeout, monitor)
4. Java encodes function address/metadata → sends to C++ subprocess
5. [C++] Disassembles bytes via Sleigh → builds PCode IR
6. [C++] Builds SSA form (Heritage)
7. [C++] Applies Action pipeline:
     - SSA form building
     - Data-flow analysis
     - Parameter/return value recovery
     - Type inference (iterative)
     - Jump-table recovery
     - Control-flow structuring (loops, if/else)
8. [C++] During analysis: sends query markers to Java to fetch bytes, types, etc.
9. [C++] PrintC generates C syntax tree → encodes response → sends to Java
10. Java: DecompileResults parses response
11. DecompilerProvider renders ClangTokenGroup (syntax-highlighted, interactive)
```

---

## Intermediate Representations

| Layer | Name | Description |
|-------|------|-------------|
| Low | PCode | Platform-independent stack-machine IR; ops like `load`, `store`, `int_add`, `branch` |
| Mid | Funcdata / CFG | Basic blocks, SSA varnodes, PCode ops, function prototype |
| High | ClangTokenGroup | C syntax tree for display: function → statement → token |

---

## Build System

- **Java**: Standard Gradle (`build.gradle`)
- **Native**: Gradle native build model (`buildNatives.gradle`)
  - Targets: `win_x86_64`, `win_arm_64`, `linux_x86_64`, `linux_arm_64`, `mac_x86_64`, `mac_arm_64`, `freebsd_x86_64`, `freebsd_arm_64`
  - Produces two executables: `decompile` (74 .cc files) and `sleigh` (processor spec compiler)
- **Parsers**: Bison/Flex; regenerate with `generateParsers` Gradle task (generated files checked in)
- **Docs**: XSL-FO → PDF (`sleigh.pdf`, `pcoderef.pdf`); requires `xsltproc` + `fop`

---

## Design Patterns

| Pattern | Where | Purpose |
|---------|-------|---------|
| **Action/Rule pipeline** | `action.hh`, `ActionGroup` | Composable, ordered transformations on Funcdata |
| **Object pool** | `VarnodeBank`, `PcodeOpBank` in Funcdata | Efficient allocation and tracking of analysis objects |
| **SSA maintenance** | `Heritage` class | Automatic phi insertion as graph mutates |
| **Callback/query** | `ArchitectureGhidra` overrides | Decouples C++ core from Ghidra DB |
| **Composite token tree** | `ClangTokenGroup` | Lightweight AST for display |
| **Thread pool** | `ParallelDecompiler` | Bulk analysis across many functions |

---

## Tests

| Location | Type |
|----------|------|
| `src/decompile/unittests/` | C++ unit tests |
| `src/decompile/datatests/` | C++ data-driven tests |
| `src/test.slow/java/` | Java integration tests (~18 classes) |

Notable test classes: `DecompilerTest`, `DecompilerClangTest`, `DecompilerNavigationTest`, `DecompilerSwitchAnalyzerTest`, `DecompilerHighSymbolTest`

---

## Developer Tips

- **Extending analysis**: Add a new `Action` or `Rule` subclass in C++; register it in the action sequence.
- **Extending the Java API**: Hook into `DecompileCallback` to intercept/augment data provided to C++.
- **Debugging communication**: The pipe protocol is binary — add logging in `DecompileProcess` or `ghidra_process.cc`.
- **Crash recovery**: `DecompileProcess` auto-restarts the subprocess; look here for timeout/error handling.
- **UI customization**: `ClangTokenGroup` and `ClangToken` subclasses control what's rendered; `DecompilerProvider` controls layout.
- **Options impact**: `DecompileOptions` maps directly to C++ action configuration — changing options can dramatically affect analysis quality and speed.
- **PCode is the pivot**: All architecture-specific work lives in Sleigh specs; the C++ core only sees PCode.
