# Ghidra Framework — Analysis Notes

> Generated: 2026-02-23. Re-read this file at the start of any session involving the Framework directory.
> For deep dives into a specific submodule, the key facts are all here; ask for more detail only if needed.

---

## Submodule Overview

The Framework layer is the foundation of Ghidra. All features, plugins, and processors sit above it.
Dependency order (bottom → top): **Utility → Generic → DB → FileSystem → SoftwareModeling → Emulation → Graph → Gui → Docking → Help → Project**. Pty is a lateral dependency used by the debug subsystem.

| Submodule | Purpose (one line) |
|-----------|-------------------|
| **Utility** | Bootstrap only — zero external deps; launches JVM, discovers modules, builds classpath |
| **Generic** | Core data structures, concurrency, classfinder, options, async utilities — [deep dive notes](Generic/NOTES.md) |
| **DB** | Embedded B-Tree database with transactions, undo/redo, and schema versioning |
| **FileSystem** | Versioned hierarchical project file storage (local disk + RMI remote) |
| **SoftwareModeling** | PCode IR, SLEIGH language engine, HighFunction decompiler model, assembler — [deep dive notes](SoftwareModeling/NOTES.md) |
| **Emulation** | PCode interpreter + JIT emulator (7-phase compilation to JVM bytecode) |
| **Graph** | Graph algebra, layout algorithms, interactive visualization (JUNG/JGraphT) |
| **Gui** | Theme system (colors/fonts/icons), LAF management, background task framework |
| **Docking** | Window docking, action framework, context sensitivity, GTable/GTree widgets |
| **Help** | JavaHelp integration, cross-module help merging, help validator/builder |
| **Project** | Project lifecycle, DomainObject/DomainFile, PluginTool, GTaskManager |
| **Pty** | Pseudo-terminal abstraction (Linux/macOS/Windows ConPty) for debugger I/O |

---

## Utility

**Role**: True bootstrap layer. The JVM entry point. Zero external deps (enforced).

**Key classes**:
- `GhidraLauncher` — discovers modules, builds classpath, launches target class via reflection
- `GhidraClassLoader` — custom URLClassLoader allowing runtime classpath mutation
- `GhidraApplicationLayout` — discovers directory structure, modules, extensions (XDG-aware on Linux)
- `GModule` — represents a single module with its manifest, libs, and build outputs
- `ResourceFile` — unified abstraction over filesystem files and JAR-embedded resources
- `ApplicationLayout` — abstract base; customizable directory structure
- `TaskMonitor` — interface for cancellable progress reporting (defined here, used everywhere)
- `ServiceProvider` — interface for dynamic service lookup
- `Msg` — centralized logging facade with pluggable error display backend
- `GThreadPool` — shared/private thread pool factory

**Design notes**:
- Two-phase boot: `GhidraClassLoader` installed first (JVM property), then `GhidraLauncher` runs
- Module types loaded in priority order: Framework → Configurations → Features → Processors → Extensions
- Dev mode vs release mode detection (`SystemUtilities.isInDevelopmentMode()`) changes classpath strategy

---

## Generic

**Role**: Foundational utility library. Nearly every other module depends on it.

**Key classes**:
- `ConcurrentQ<I,R>` — thread pool queue for parallel work with callbacks and throttling
- `Worker` / `PriorityWorker` — FIFO/priority background job executors
- `ClassSearcher` — reflective class discovery enabling plugin/extension point loading
- `CachingPool<T>` — thread-safe object pool with factory-based creation
- `RedBlackTree<K,V>` — balanced BST (C++ STL-inspired)
- `DependencyGraph<T>` — directed graph with topological ordering for dependency resolution
- `AsyncUtils` — CompletableFuture helpers for async/await patterns
- `GProperties` — options/preferences persistence (XML/JSON/binary backends)
- `ExtensionUtils` — extension discovery, installation, lifecycle

**Key packages**:
- `generic.*` — pure utility (no Ghidra deps): algorithms, cache, concurrent, hash, lsh, stl, timer
- `ghidra.util.classfinder` — plugin discovery
- `ghidra.util.datastruct` — specialized data structures
- `ghidra.util.worker` — background job execution
- `ghidra.net` / `ghidra.security` — SSL, HTTP, PKI, keystore management

**External deps**: Apache Commons, Guava, Log4j2, JDOM2, Bouncy Castle, GSON

---

## DB

**Role**: Embedded B-Tree database. Ghidra's persistence engine for all program data.

**Key classes**:
- `DBHandle` — main database access point; manages tables and transactions
- `Table` — CRUD, B-Tree storage, record iteration, secondary indexes
- `Schema` — defines table structure (column names, types, sparse columns, key type)
- `DBRecord` — portable record container (key + typed fields)
- `Field` — abstract type system: ByteField, IntField, LongField, StringField, BinaryField, etc.
- `BufferMgr` — low-level buffer pool, LRU cache, checkpointing, undo/redo stack
- `Transaction` — AutoCloseable wrapper for try-with-resources syntax
- `RecordIterator` — bidirectional record iteration interface

**B-Tree variants**: LongKey (primitive long), FixedKey (fixed-length binary), VarKey (variable-length) — each with interior and leaf node implementations.

**Storage files**:
- `LocalBufferFile` — standard disk file
- `ManagedBufferFile` — adds versioning and change tracking
- `RecoveryMgr` / `RecoveryFile` — crash recovery

**Used by**: SoftwareModeling (symbols, memory, references, code units, data types), FileSystem

---

## FileSystem

**Role**: Hierarchical, versioned project file storage. Abstracts local disk vs remote (RMI) storage.

**Key classes**:
- `FileSystem` (interface) — root abstraction; versioning, online/offline states
- `FolderItem` (interface) — a file; typed as DATABASE, DATAFILE, or LINK
- `DatabaseItem` (interface) — versioned read/update access via `ManagedBufferFile`
- `LocalFileSystem` — disk-based implementation; versioning support
- `IndexedLocalFileSystem` — MD5-indexed shallow storage for fast metadata lookups
- `RemoteFileSystem` — wraps RMI `RepositoryAdapter` for server-based access
- `RepositoryAdapter` — manages connection lifecycle, reconnection, listener notification
- `VersionedDatabase` — multi-version database storage; checkout IDs, change data
- `PackedDatabase` — compressed single-version format; expands to temp dir on open
- `FileSystemEventManager` — sync/async listener notification for folder/file events

**Patterns**: Strategy (local vs remote), Adapter (RMI wrapping), Index-optimized local (avoids deep directory nesting), Checkout/copy-on-write versioning.

**Depends on**: DB (BufferFile, Database), Docking (auth dialogs). Used by: Project.

---

## SoftwareModeling

**Role**: The heart of analysis. PCode IR, SLEIGH engine, decompiler's high-level model, assembler.

**Key classes**:
- `PcodeOp` — single PCode operation (opcode + input/output varnodes)
- `Varnode` — value location: register, memory address, or temporary
- `HighFunction` — decompiler output: PCode ops, variables, symbols, control flow
- `HighVariable` / subclasses — semantic variables: HighLocal, HighParam, HighGlobal, HighConstant
- `SleighLanguage` — core SLEIGH processor definition; instruction parsing, PCode generation
- `Assembler` / `SleighAssembler` — reverse assembly (mnemonic → bytes)
- `Encoder` / `Decoder` — streaming packed-binary serialization of PCode
- `FloatFormat` — variable-size IEEE 754 support via BigFloat
- `PcodeBlock` / `BlockGraph` — CFG nodes (basic blocks, if/while/switch structures)

**Build quirk**: ANTLR3 grammar generates `SleighParser`, `SleighCompiler`, `DisplayParser`, `SemanticParser` with custom package injection post-processing.

**SLEIGH grammar**: 3 distinct syntactic modes (base, display, semantic) with modal lexer switching. Language specs validated against XML schemas in `data/languages/`.

**External deps**: ANTLR 3.5.2 runtime, MSV (XML validation).

---

## Emulation

**Role**: PCode interpreter + JIT emulator for concrete and abstract/symbolic execution.

**Key classes**:
- `PcodeMachine<T>` — generic PCode machine interface (parametric on state type)
- `AbstractPcodeMachine<T>` — base with thread management, breakpoints, shared state
- `PcodeEmulator` — concrete bytes emulator (default implementation)
- `PcodeThread<T>` / `DefaultPcodeThread<T>` — per-thread execution, PC, decoding
- `PcodeArithmetic<T>` — pluggable arithmetic (bytes, abstract domains, taint pairs)
- `JitPcodeEmulator` — JIT-accelerated variant; compiles passages to JVM bytecode
- `JitCompiler` — 7-phase pipeline: CFG → data flow → variable scope → type inference → allocation → use modeling → codegen
- `OpBehaviorFactory` — factory for 60+ operation behavior implementations

**JIT pipeline phases**: (1) CFG analysis, (2) data flow, (3) variable scope, (4) type inference, (5) allocation, (6) use modeling, (7) JVM bytecode generation via ASM 9.7.1.

**Auxiliary/paired emulation**: `PcodeExecutorState` supports composing concrete + abstract state (e.g., taint tracking alongside byte values).

**External deps**: ASM 9.7.1 (5 libraries for JVM bytecode generation).

---

## Graph

**Role**: Graph algebra, algorithms, interactive visualization.

**Key classes**:
- `GDirectedGraph<V,E>` — core mutable explicit graph interface
- `GImplicitDirectedGraph<V,E>` — lazy/computed graphs; used by all algorithms
- `VisualGraph<V,E>` — rendering interface: selection, focus, events
- `GraphComponent<V,E,G>` — main UI container; primary + satellite viewers
- `VisualGraphLayout<V,E>` — layout interface; extends Jung; manages vertex positioning
- `GraphAlgorithms` — static utility: dominance, post-dominance, SCC, shortest paths, topo sort
- `AttributedGraph` — service-level graph with key-value attributes on vertices/edges
- `DefaultVisualGraph<V,E>` — base VisualGraph with selection/focus state management
- `JungLayoutProvider` — bridge to Jung layout algorithms (FR, ISOM, Spring, Tree)

**Algorithms**: Dominance (ChkDominanceAlgorithm), post-dominance, Tarjan SCC, Dijkstra shortest paths, topological sort, recursive/iterative path finding.

**External deps**: JUNG 2.1.1 (layout algorithms), JGraphT 1.5.1 (AttributedGraph backing).

**Used by**: Function Graph, Call Graph, Data Flow analysis tools.

---

## Gui

**Role**: Theme management, cross-platform LAF, background task coalescing.

**Key classes**:
- `ThemeManager` — singleton managing colors, fonts, icons, LAF state
- `ApplicationThemeManager` — concrete impl; loads from `*.theme.properties` files
- `GTheme` — a named theme: LAF type, dark mode flag, customized values
- `Gui` (static utility) — facade: `Gui.getColor(id)`, `Gui.getFont(id)`, etc.
- `Task` — base for background operations with cancellation and progress
- `SwingUpdateManager` — coalesces rapid UI update requests (min/max delay thresholds)
- `LookAndFeelManager` — installs platform-specific LAF (Windows, macOS, GTK, FlatLaf)
- `ResourceManager` — static icon/resource loader with classpath cache
- `Options` / `ToolOptions` — preferences storage with PropertyEditor support
- `HTMLUtilities` — HTML formatting helpers for Swing components

**Theme system**: ID-based indirection (string IDs like `"color.bg"`, `"font.body"`), discovered from `{module}.theme.properties` files via classpath scanning. Dark mode via `useDarkDefaults()`. `StubThemeManager` placeholder until full init.

**External deps**: FlatLaf 3.5.4.

---

## Docking

**Role**: Ghidra's GUI shell — window docking, actions, context sensitivity, rich widgets.

**Key classes**:
- `Tool` (interface) — service provider contract for window/action/options management
- `DockingWindowManager` — core orchestrator; window layout, persistence, docking
- `ComponentProvider` — base class for all dockable UI components
- `DockingActionIf` (interface) — action contract: name, owner, enablement, menu/toolbar/keybinding
- `DockingAction` — base implementation with context predicates, weak listeners
- `ActionBuilder` / `ToggleActionBuilder` / `MultiStateActionBuilder` — fluent action builders
- `GTable` — JTable with column filtering, multi-column sorting, constraints, export
- `GTree` — tree with filtering, threaded node loading, progress
- `FieldPanel` — complex attributed-text rendering; selections, highlights, cursor, hover
- `OptionsService` — pluggable options/preferences UI

**Window layout model**: Tree of nodes — `RootNode → WindowNode → SplitNode → ComponentNode → ComponentPlaceholder`. Serialized for session persistence.

**804 Java source files** across 20+ packages. Depends on Help (API). All other modules depend on this.

---

## Help

**Role**: Context-sensitive help delivery via JavaHelp; cross-module merging; help validation/build.

**Key classes**:
- `HelpService` (interface) — show help, register locations, manage state
- `Help` (static) — global singleton accessor; pluggable implementation
- `GHelpSet` — extends JavaHelp HelpSet; enables cross-module help resolution (key innovation)
- `GHelpBroker` — customized help window with zoom, theming integration
- `GHelpBuilder` — CLI utility orchestrating help build: collects, validates, generates map/TOC/index
- `JavaHelpValidator` — validates all links and images; detects broken refs, missing anchors
- `GHelpHTMLEditorKit` — intercepts HTML rendering for Ghidra link resolution and theming
- `LinkDatabase` — central registry of all help links; enables cross-module validation
- `OverlayHelpTree` — builds TOC tree from multiple modules' contributions

**Build artifacts per module**: `_map.xml`, `_TOC.xml`, Lucene search index, `.hs` HelpSet file.

**External deps**: JavaHelp 2.0.05, timing-framework 1.0 (animations).

---

## Project

**Role**: Project lifecycle, domain object management, plugin tool framework.

**Key classes**:
- `Project` (interface) — top-level container: data, tools, repository association
- `DomainObject` (interface) — persistent analysis data; transactions, undo/redo, events
- `DomainFile` (interface) — immutable reference to a project file; versioning, metadata
- `DomainFolder` (interface) — immutable reference to a project folder
- `ProjectData` (interface) — root accessor; path-based file/folder navigation
- `PluginTool` — plugin-based tool; manages plugins, actions, events, background commands
- `ToolManager` (interface) — manages tool templates, workspaces, inter-tool connections
- `GTaskManager` — async prioritized task execution in transaction scope; supports suspension
- `DefaultProject` — concrete Project; manages state, data, tool manager, config persistence
- `DomainObjectAdapterDB` — base for DB-backed domain objects; transactions, undo/redo, locking

**Key patterns**:
- Immutable file/folder refs for safe concurrent access
- Transaction-mandatory change model (ACID)
- Event batching to reduce UI thrashing
- Command pattern (`Command<T>`, `BackgroundCommand`) for domain object modifications
- `ServiceManager` for runtime service discovery within a tool

**394 Java classes (~77K LOC)**. API dep: FileSystem. External dep: xz-1.9 (compression).

---

## Pty

**Role**: Pseudo-terminal abstraction for debugger subprocess I/O.

**Key classes**:
- `Pty` (interface) — both ends of a pseudo-terminal; AutoCloseable
- `PtyFactory` — platform-detecting factory (Linux/macOS/Windows); static `local()` method
- `PtyParent` — master/control side; InputStream/OutputStream
- `PtyChild` — slave side; `session()` spawns subprocess, `nullSession()` for passive ptys
- `PtySession` — running subprocess: `waitExited()`, `destroyForcibly()`
- `UnixPty` — POSIX impl wrapping `openpty()` file descriptors via JNA
- `ConPty` — Windows Console Pseudoconsole API impl
- `LocalProcessPtySession` — wraps Java `Process`
- `ShellUtils` — shell command line parse/generate with quoting

**Platform notes**: Linux, macOS, and Windows have separate implementations. Unix uses a Java "leader" subprocess that `exec()`s the target to set session leader on the controlling tty. JNA (not JNI) used for all native bindings.

**Used by**: Debugger-rmi-trace, Debugger-importers.

---

## Dependency Graph (simplified)

```
Utility
  └─ Generic
       ├─ DB
       │    └─ FileSystem
       │         └─ Project ──────────────────────────────────┐
       ├─ SoftwareModeling ──────────────────────────────┐    │
       │    └─ Emulation                                  │    │
       ├─ Graph ──────────────────┐                       │    │
       ├─ Gui                     │                       │    │
       │    └─ Docking ───────────┤                       │    │
       │         └─ Help          │                       │    │
       └─ Pty (debug subsystem)   │                       │    │
                                  └── Features/Plugins ───┘────┘
```

---

## Developer Tips

- **Adding analysis**: Extend the `Action`/`Rule` system in the Decompiler's C++ core (built on SoftwareModeling's PCode). For Java-side analysis, use `DomainObject` transactions and `BackgroundCommand`.
- **New plugin/tool**: Subclass `ComponentProvider` (Docking) and `PluginTool` (Project). Register via `ClassSearcher` extension point discovery.
- **Custom theme values**: Add entries to your module's `{name}.theme.properties`; they are discovered automatically at runtime.
- **Background work**: Use `GTaskManager` (Project) for transaction-scoped tasks, `Worker`/`ConcurrentQ` (Generic) for general parallel work.
- **Accessing program data**: Go through `DomainObject` → `DBHandle` (DB) → `Table`; always inside a transaction.
- **Help authoring**: Add HTML to your module's `help/topics/` directory; the Help build system merges it automatically.
- **Emulation/symbolic exec**: Implement `PcodeArithmetic<T>` and plug into `AbstractPcodeMachine` for a new abstract domain.
- **Graph visualization**: Extend `VisualVertex`/`VisualEdge` and `DefaultVisualGraph`; provide a `LayoutProvider` for custom layout.
