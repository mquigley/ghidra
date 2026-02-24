# Ghidra Features/Base — Analysis Notes

> Generated: 2026-02-23. Re-read this file at the start of any session involving Features/Base.

---

## Overview

`Features/Base` is Ghidra's **largest and most central feature module** — the collection of core plugins, services, and infrastructure that make up the Ghidra application itself. It is not a library; it is the application.

**Size**: 3,493 Java source files across ~180 packages.

**Key areas**:
- Binary loading (Loader system, GFileSystem/FSRL, batch importer)
- Code display (CodeBrowser, Listing panel, 100+ field factories)
- Auto-analysis framework (Analyzer interface, AutoAnalysisManager, scheduling)
- Scripting (GhidraScript, FlatProgramAPI, headless analyzer, OSGi)
- Data type management (composite editor, type archives, sync)
- Symbol/reference/memory UI (symbol tree, symbol table, refs, memory map)
- Search (memory search, text search, instruction search, byte trie, strings)
- Annotations (bookmarks, equates, highlights, quick-fix, search-and-replace)
- Merge/version control conflict resolution

---

## Package Map (by functional area)

| Area | Key Packages |
|------|-------------|
| Loaders / Opinions | `ghidra/app/util/opinion/`, `ghidra/plugin/importer/`, `ghidra/plugins/importer/` |
| GFileSystem | `ghidra/formats/gfilesystem/` + subpackages |
| File System Browser | `ghidra/plugins/fsbrowser/` |
| CodeBrowser / Listing | `ghidra/app/plugin/core/codebrowser/`, `ghidra/app/util/viewer/` |
| Field Factories | `ghidra/app/util/viewer/field/` (100+ files) |
| Navigation | `ghidra/app/plugin/core/navigation/`, `ghidra/app/nav/` |
| Markers | `ghidra/app/plugin/core/marker/` |
| Auto-Analysis | `ghidra/app/plugin/core/analysis/`, `ghidra/app/analyzers/` |
| Services | `ghidra/app/services/` |
| Function Commands | `ghidra/app/cmd/function/` |
| Disassembly Commands | `ghidra/app/cmd/disassemble/` |
| Scripts | `ghidra/app/script/`, `ghidra/program/flatapi/` |
| Headless | `ghidra/app/util/headless/` |
| OSGi | `ghidra/app/plugin/core/osgi/` |
| Data Type Manager | `ghidra/app/plugin/core/datamgr/` |
| Composite Editor | `ghidra/app/plugin/core/compositeeditor/` |
| Symbol Tree | `ghidra/app/plugin/core/symboltree/` |
| Symbol Table | `ghidra/app/plugin/core/symtable/` |
| References | `ghidra/app/plugin/core/references/` |
| Data Plugin | `ghidra/app/plugin/core/data/` |
| Label Plugin | `ghidra/app/plugin/core/label/` |
| Memory Map | `ghidra/app/plugin/core/memory/` |
| Merge | `ghidra/app/merge/` |
| Memory Search | `ghidra/features/base/memsearch/` |
| Byte Search | `ghidra/util/bytesearch/` |
| Text Search | `ghidra/app/plugin/core/searchtext/` |
| Strings | `ghidra/app/plugin/core/string/`, `ghidra/app/plugin/core/strings/` |
| Instruction Search | `ghidra/app/plugin/core/instructionsearch/` |
| Byte Trie | `ghidra/util/search/trie/` |
| Bookmarks | `ghidra/app/plugin/core/bookmark/` |
| Highlight | `ghidra/app/plugin/core/highlight/` |
| Equates | `ghidra/app/plugin/core/equate/`, `ghidra/app/cmd/equate/` |
| Quick Fix | `ghidra/features/base/quickfix/` |
| Search & Replace | `ghidra/features/base/replace/` |

---

## 1. Loader / Opinion System

### Core interfaces

**`Loader`** (interface, `ghidra/app/util/opinion/`) — extension point; class names must end in `Loader`.
- `findSupportedLoadSpecs(ByteProvider)` → `Collection<LoadSpec>` — probe method; called on every file to discover what formats this loader handles
- `load(ImporterSettings)` → `LoadResults<DomainObject>` — creates new program(s) from bytes
- `loadInto(Program, ImporterSettings)` — adds bytes to existing program (overlay)
- `getTier()` + `getTierPriority()` — priority for loader selection when multiple match

**`LoadSpec`** — immutable config: loader + image base + `LanguageCompilerSpecPair` + preferred flag.

**`LoadResults<T>`** — container for loaded objects; `getPrimary()` + `getNonPrimary()`. Manages consumer refs and has `save(TaskMonitor)`. Implements `AutoCloseable`.

**`AbstractProgramLoader`** — template base; subclasses implement `loadProgram()` → `List<Loaded<Program>>`. Handles post-load fixups and label application.

### Opinion system

`.opinion` XML files (in processor modules) map binary format machine codes (ELF `e_machine`, PE machine type) → language/compiler spec pairs. `QueryOpinionService` scans all opinions to drive auto-detection.

```
Binary opened → QueryOpinionService queries all opinions
   → Matched LoadSpecs ranked by tier/priority
   → User picks (or auto-selects) language + compiler
   → Loader.load() called
```

### Importer

**`ProgramLoader`** — fluent builder:
```java
ProgramLoader.builder()
    .source(fsrl)
    .project(project)
    .projectFolderPath("/")
    .name("myBinary")
    .language(langId)          // optional override
    .log(messageLog)
    .monitor(monitor)
    .load(consumer)            // returns LoadResults<Program>
```

**`LoadSpecChooser`** hierarchy — interactive disambiguation when multiple loaders match.

**Batch Importer** (`ghidra/plugins/importer/batch/`):
- `BatchInfo` — state for batch operation; recursive container scan up to `maxDepth` (default 2)
- `BatchGroup` — groups of related `LoadSpec`s by format/language
- `BatchImportDialog` — tree UI; user enables/disables groups before import

---

## 2. GFileSystem / FSRL

A unified interface for navigating nested binary container formats (ZIP, TAR, disk images, etc.).

### FSRL

**`FSRL`** — immutable, thread-safe path to a resource in potentially nested filesystems.
- Format: `fstype://path?MD5=hash` optionally chained with `|` for nesting
- Example: `file:///archive.zip|zip://inner/file.txt` = `file.txt` inside `archive.zip`
- Parse: `FSRL.fromString(str)` — splits on `|`
- Extend: `fsrl.appendPath("subdir/file.bin")`
- Retrieve from program: `FSRL.fromProgram(program)`

### GFileSystem

**`GFileSystem`** (interface) — `Closeable`, reference-counted.
- `lookup(String path)` → `GFile`
- `Iterable<GFile>` — iterate contents
- `getRefManager()` — tracks active refs; prevents premature closure

**`GFile`** — a file or directory in a GFileSystem (valid only while owning FS is open).
- `getFSRL()`, `getName()`, `getPath()`, `getLength()`, `isDirectory()`

### FileSystemService (singleton)

Central factory for all GFileSystem access.
- `getLocalFS()` — root OS filesystem
- `openFileSystemRef(FSRL, monitor)` → `FileSystemRef` — mounts and pins filesystem
- `getFileAsByteProvider(FSRL, monitor)` → `ByteProvider`
- `getDerivedByteProvider(sourceFSRL, derivedName, producer, monitor)` — synthetic files (decompressed, decrypted)
- `isFilesystemMountedAt(FSRL)` — cache check
- `getFullyQualifiedFSRL(FSRL, monitor)` — compute MD5 for content addressing

**`FileSystemRef`** — pinning handle; keeps filesystem open while held. Release to allow cleanup.

**FileCache** — MD5-keyed, 2MB in-memory threshold, LRU eviction. Cached files are obfuscated to avoid antivirus interference.

### Factory system

- `@FileSystemInfo(type="zip", description="...", factory=ZipFileSystemFactory.class)` — annotates GFileSystem implementations for auto-registration
- `FileSystemFactoryMgr` — discovers all `@FileSystemInfo`-annotated classes; probes on `openFileSystem(ByteProvider)`
- `GFileSystemProbe` — format detection interface; priority-ordered

### File System Browser UI

`FileSystemBrowserPlugin` (`ghidra/plugins/fsbrowser/`) — UI for exploring container files:
- `FSBComponentProvider` — per-window `GTree` of filesystem hierarchy
- `FSBRootNode / FSBDirNode / FSBFileNode` — tree node hierarchy with lazy loading
- `FSBFileHandler` — pluggable context-menu actions per file type (import, export, hex view, etc.); discovered via `ClassSearcher`

---

## 3. CodeBrowser & Listing Viewer

### Architecture

```
CodeBrowserPlugin
  └─ CodeViewerProvider (Navigatable dockable)
       └─ ListingPanel (JPanel)
            ├─ FieldPanel (docking framework — low-level pixel rendering)
            ├─ ListingModelAdapter (bridges ListingModel → LayoutModel)
            │   └─ ProgramBigListingModel (what to display; adapts Program)
            │       └─ FormatManager (how to format it)
            │           └─ FieldFormatModel[7] (layout categories)
            │               └─ FieldFactory[] (100+ field types)
            ├─ ListingMarginProvider[] (left margin renderers)
            └─ ListingOverviewProvider[] (right overview map renderers)
```

### Key classes

**`CodeBrowserPlugin`** — main plugin. Services: `CodeViewerService`, `CodeFormatService`, `FieldMouseHandlerService`. Manages connected provider (primary window) and disconnected providers (secondary windows).

**`CodeViewerProvider`** — dockable UI; implements `Navigatable`. Broadcasts location changes via `broadcastLocationChanged()`.

**`ListingPanel`** — JPanel container. Key methods:
- `goTo(Address)` / `goTo(ProgramLocation)` — scroll to location
- `setLocation(ProgramLocation)` / `getLocation()`
- `setSelection(FieldSelection)` / `getSelection()`
- `addMarginProvider()` / `addOverviewProvider()` — extension points
- `getFieldPanel()` — direct access to low-level renderer

**`ListingModel`** (interface) — what to display:
- `getLayout(Address, boolean)` — formatted display for one address
- `getAddressAfter(Address)` / `getAddressBefore(Address)` — navigation (skips gaps)
- Open/close controls for data structures and function variables

**`ProgramBigListingModel`** — main `ListingModel` implementation. Adapts `Program` → listing. Uses `LayoutCache` for performance. Listens to `DomainObjectListener`.

**`ListingModelAdapter`** — bridges `ListingModel` → docking's `LayoutModel`. Maintains `AddressIndexMap` (address ↔ BigInteger index). Uses `SwingUpdateManager` (500ms debounce, 5s max) for async invalidation.

**`FormatManager`** — manages 7 `FieldFormatModel` instances (Address Break, Plate, Function, Variable, Instruction/Data, Open Data, Array). Discovers `FieldFactory` implementations via `ClassSearcher`.

### Field factories

100+ `FieldFactory` implementations in `ghidra/app/util/viewer/field/`. Class names must end in `FieldFactory`.

Categories:
- **Address**: `AddressFieldFactory`, `ImagebaseOffsetFieldFactory`, `FileOffsetFieldFactory`, `MemoryBlockStartFieldFactory`
- **Code unit**: `MnemonicFieldFactory`, `OperandFieldFactory`, `BytesFieldFactory`, `ParallelInstructionFieldFactory`
- **Data structure**: `ArrayValuesFieldFactory`, `SubDataFieldFactory`, `AssignedVariableFieldFactory`
- **Comments**: `PreCommentFieldFactory`, `PostCommentFieldFactory`, `EolCommentFieldFactory`, `FunctionRepeatableCommentFieldFactory`
- **Metadata**: `LabelFieldFactory`, `FunctionSignatureFieldFactory`, `XRefFieldFactory`, `XRefHeaderFieldFactory`, `RegisterTransitionFieldFactory`
- **Structure**: `PlateFieldFactory`, `FunctionOpenCloseFieldFactory`, `SeparatorFieldFactory`, `SpaceFieldFactory`

Extension: subclass `FieldFactory`, implement `getField(ProxyObj, FieldFormatModel, ...)`, name it `*FieldFactory`.

---

## 4. Navigation & Markers

### Navigation

**`Navigatable`** (interface) — components that support location/selection tracking.
- `goTo(Program, ProgramLocation)`, `getLocation()`, `getProgram()`
- `setSelection()`, `setHighlight()`
- `getMemento()` / `setMemento()` — save/restore view state

**`NavigationHistoryPlugin`** — provides `NavigationHistoryService`. Maintains per-`Navigatable` `HistoryList` of `LocationMemento` snapshots. Configurable size (default 30, range 10–400).

**`GoToServiceImpl`** — implements `GoToService`. Key entry points:
- `goTo(Address)`, `goTo(ProgramLocation)` — navigate active view
- `goTo(Navigatable, Address)`, `goTo(Navigatable, ProgramLocation)` — target specific view
- `goToExternalLocation(ExternalLocation)` — external references
- `goToQuery(...)` — symbol search-based navigation

**`ProgramLocationTranslator`** — maps `ProgramLocation` between two versions of a program using `ListingAddressCorrelation`.

### Markers

**`MarkerService`** (provided by `MarkerManager`) — create/remove colored margin indicators.
- `createMarkerSet(Program, name, description, Color, priority)` → `MarkerSet`
- `addMarginProvider()` / `addOverviewProvider()`

**`MarkerSetImpl`** — stores `AddressSetCollection`; configurable: `showMarkers`, `showNavigation`, `colorBackground`, `priority`.

**`MarkerMarginProvider`** — renders left margin gutter. Maps Y pixel ↔ address via `VerticalPixelAddressMap`. Double-click fires navigation.

**`MarkerOverviewProvider`** — renders right-side overview map showing proportional marker density.

**Rendering pipeline**: On scroll/layout change → `screenDataChanged()` → providers re-render using `VerticalPixelAddressMap` for Y↔address mapping.

---

## 5. Auto-Analysis Framework

### Analyzer interface

```java
public interface Analyzer extends ExtensionPoint {
    String getName();
    AnalyzerType getAnalysisType();  // BYTE, INSTRUCTION, FUNCTION, FUNCTION_MODIFIERS,
                                     // FUNCTION_SIGNATURES, DATA
    boolean getDefaultEnablement(Program program);
    boolean canAnalyze(Program program);
    AnalysisPriority getPriority();
    boolean added(Program program, AddressSetView set, TaskMonitor monitor, MessageLog log);
    boolean removed(Program program, AddressSetView set, TaskMonitor monitor, MessageLog log);
    void registerOptions(Options options, Program program);
    void optionsChanged(Options options, Program program);
    void analysisEnded(Program program);
}
```

Class names must end in `Analyzer` for ClassSearcher discovery.

### AnalyzerType — event triggers

| Type | Triggered by |
|------|-------------|
| `BYTE_ANALYZER` | Memory blocks added |
| `INSTRUCTION_ANALYZER` | Instructions defined |
| `FUNCTION_ANALYZER` | Functions created |
| `FUNCTION_MODIFIERS_ANALYZER` | Function modifiers changed (inline, thunk, no-return, etc.) |
| `FUNCTION_SIGNATURES_ANALYZER` | Function signatures changed |
| `DATA_ANALYZER` | Data defined |

### AnalysisPriority — execution order

| Priority | Value | Phase |
|----------|-------|-------|
| `FORMAT_ANALYSIS` | 100 | Binary format header markup |
| `BLOCK_ANALYSIS` | 200 | Initial block markup, entry points |
| `DISASSEMBLY` | 300 | Code recovery via flow analysis |
| `CODE_ANALYSIS` | 400 | Non-returning functions, flow fixes |
| `FUNCTION_ANALYSIS` | 500 | Function boundary detection |
| `REFERENCE_ANALYSIS` | 600 | Operand references, strings, pointers |
| `DATA_ANALYSIS` | 700 | Data creation (strings, structures) |
| `FUNCTION_ID_ANALYSIS` | 800 | Function identification |
| `DATA_TYPE_PROPOGATION` | 900 | Late type propagation |

Fine-grained control: `priority.before()` (-1), `priority.after()` (+1), `priority.getNext()` (+100).

### AutoAnalysisManager

Single dedicated analysis thread. Batches program events (500ms default) before notifying analyzers.

**Flow**:
1. Program event (`codeDefined`, `functionAdded`, etc.) → `AnalysisTaskList` accumulates addresses
2. `AnalysisScheduler.schedule()` → queues `AnalysisTask` in `PriorityQueue<BackgroundCommand>`
3. Analysis thread picks up tasks in priority order → calls `Analyzer.added(program, addressSet, monitor, log)`
4. Analyzer may call `yield(limitPriority)` to pause and let higher-priority work run first

**`yield(limitPriority)`** — suspends current analyzer, processes queued tasks up to given priority, then resumes.

**`waitForAnalysis(limitPriority)`** — external thread blocks until analysis up to priority threshold completes.

### Key built-in analyzers

| Analyzer | Type | Priority | Purpose |
|---------|------|----------|---------|
| `OperandReferenceAnalyzer` | INSTRUCTION | REFERENCE_ANALYSIS | Creates refs from operands; finds strings, pointer tables, switch tables |
| `FindNoReturnFunctionsAnalyzer` | FUNCTION | CODE_ANALYSIS | Evidence-based detection of non-returning functions |
| `ConstantPropagationAnalyzer` | INSTRUCTION | DATA_TYPE_PROPOGATION | Symbolic execution for constant/pointer recovery |
| `DWARFAnalyzer` | BYTE | FORMAT_ANALYSIS | DWARF debug info extraction |
| Various format analyzers | BYTE | FORMAT_ANALYSIS | ELF, Mach-O, PE header markup |

### Writing a new analyzer

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

---

## 6. Service Interfaces

Key service interfaces defined in `ghidra/app/services/`:

| Service | Purpose |
|---------|---------|
| `GoToService` | Navigate to addresses, external symbols, query by name |
| `BlockModelService` | Provides basic block / subroutine models |
| `DataTypeManagerService` | Access/edit types, favorites, enum equates |
| `DataTypeArchiveService` | Load/manage type archives |
| `CodeViewerService` | Access listing panel content |
| `MarkerService` | Add/remove visual margin markers |
| `BookmarkService` | Bookmark management |
| `MemorySearchService` | Byte pattern search |
| `ConsoleService` | Script console output |
| `GhidraScriptService` | Execute scripts programmatically |
| `NavigationHistoryService` | Go-back/forward navigation |
| `ViewManagerService` | Manage dockable views |
| `DataService` | Access code/data units at addresses |

---

## 7. Commands (cmd/)

### Function commands (`ghidra/app/cmd/function/`)

| Command | Purpose |
|---------|---------|
| `CreateFunctionCmd` | Define function at entry point(s) |
| `CreateThunkFunctionCmd` | Create thunk (trampoline); handles indirection chains |
| `CreateExternalFunctionCmd` | External function references |
| `DeleteFunctionCmd` | Remove function |
| `ApplyFunctionSignatureCmd` | Apply prototype/calling convention |
| `ApplyFunctionDataTypesCmd` | Apply return type and parameter types |
| `NewFunctionStackAnalysisCmd` | Full stack frame analysis |
| `FunctionPurgeAnalysisCmd` | Determine stack cleanup on return |
| `SetFunctionNameCmd` | Rename function |
| `AddParameterCommand` / `AddRegisterParameterCommand` / `AddStackParameterCommand` | Add parameters |
| `AddMemoryVarCmd` / `AddStackVarCmd` / `AddRegisterVarCmd` | Add local variables |
| `SetVariableDataTypeCmd` / `SetVariableNameCmd` | Modify variable properties |

### Disassembly commands (`ghidra/app/cmd/disassemble/`)

**`DisassembleCommand`** — primary disassembly engine.
- `startSet` — entry points
- `restrictedSet` — bounds (null = all memory)
- `followFlow` — follow jumps/calls
- `enableAnalysis` — trigger auto-analysis after

Processor-specific variants: `ArmDisassembleCommand`, `MipsDisassembleCommand`, `X86_64DisassembleCommand`, `PowerPCDisassembleCommand` — initialize processor-specific context (Thumb mode, PIC, etc.).

`SetFlowOverrideCmd` — override computed flow (fallthrough, jump, call, return, conditional).

---

## 8. Scripting

### GhidraScript

`GhidraScript` extends `FlatProgramAPI`. Implement `run()`.

**Auto-populated state fields**:
- `currentProgram` — active program
- `currentAddress` — cursor address
- `currentLocation` — `ProgramLocation` (may be null)
- `currentSelection` — `ProgramSelection` (may be null)
- `currentHighlight` — highlight (may be null)

**Analysis mode**:
- `ENABLED` — auto-analysis runs concurrently
- `DISABLED` — auto-analysis paused; runs after script completes
- `SUSPENDED` — auto-analysis disabled; resumes responding to changes after

**User interaction** (dialog-based): `askChoice()`, `askString()`, `askInt()`, `askAddress()`, `askFile()`, etc. Caches previous choices.

**Discovery**: `ScriptInfo` parses header comments for `@author`, `@category`, `@keybinding`, `@menupath`, `@toolbar`, `@runtime`.

**Providers**: `GhidraScriptProvider` (interface) → `JavaScriptProvider` (OSGi-compiled), `PythonScriptProvider`, etc. Class names must end in `ScriptProvider`.

### FlatProgramAPI

Base class providing the full scripting API. **Never remove or change method signatures** (backward compatibility guarantee).

Key method groups:
- Memory: `createMemoryBlock`, `getMemoryBlock`, `setByte`, `setBytes`, `setInt`
- Listing: `clearListing(AddressSetView)`, `disassemble(Address)`
- Symbols: `createLabel`, `removeSymbol`, `setPlateComment`, `setEOLComment`
- Functions: `removeFunction`, `removeFunctionAt`
- Data types: `createDwords`, `removeData`, `openDataTypeArchive`
- Transactions: `start()`, `end(boolean commit)`

### GhidraState

Execution environment container:
- `tool: PluginTool` — null in headless
- `project: Project`
- `currentProgram`, `currentLocation`, `currentSelection`, `currentHighlight`
- `envmap: HashMap<String, Object>` — script environment variables
- When `isGlobalState=true` and tool exists: setting location/selection fires plugin events

### Headless Analyzer (`ghidra/app/util/headless/`)

**`HeadlessAnalyzer`** — singleton for headless execution.
```
processLocal(projectLoc, projectName, folderPath, filesToImport)
processURL(ghidraURL, filesToImport)
```

**Script execution pipeline**:
```
Pre-Scripts → Auto-Analysis (if enabled) → Post-Scripts → Save/Commit
```

**`HeadlessOptions`**: `readOnly`, `commit`, `analyze`, `perFileTimeout`, `overwrite`, `recursive`, `preScripts`, `postScripts`, `scriptPaths`.

**HeadlessScript** — `GhidraScript` subclass with `HeadlessContinuationOption`: `CONTINUE`, `ABORT`, `ABORT_AND_DELETE`, `CONTINUE_THEN_DELETE`.

### OSGi (`ghidra/app/plugin/core/osgi/`)

**`BundleHost`** — manages embedded Felix OSGi framework. Enables dynamic Java script compilation/reloading.
- `GhidraSourceBundle` — source directory compiled to JAR on demand
- `GhidraJarBundle` — JAR-based bundle
- `OSGiParallelLock` — thread-safe class loading
- `BundleHostListener` — bundle state change callbacks

---

## 9. Data Type Management

**`DataTypeManagerPlugin`** — implements `DataTypeManagerService` + `DataTypeQueryService`.
- Manages archives: `BuiltInArchive`, `FileArchive`, `ProjectArchive`
- 80+ actions for create/edit/delete/import/export/merge of types, categories, archives
- `DataTypeSynchronizer` — syncs type changes between source and destination archives

**`DataTypesProvider`** — tree view of types organized by archive and category. Uses `DataTypeArchiveGTree` with drag-and-drop.

**`CompositeEditorPlugin`** / **`StructureEditorProvider`** / **`UnionEditorProvider`**:
- MVC design; `CompositeEditorModel<T>` tracks editing state
- `CompositeEditorPanel<T, M>` — `GTable` of fields (offset, type, name, comment)
- `BitFieldEditorDialog` — specialized UI for bitfield configuration
- `CompositeEditorActionManager` — centralized actions (add, delete, duplicate, move, array expansion)

---

## 10. Symbol, Reference & Memory UI

**Symbol Tree** (`ghidra/app/plugin/core/symboltree/`):
- `SymbolGTree` — lazy-loading tree; `MoreNode` for pagination of large symbol groups
- Node types: `FunctionSymbolNode`, `CodeSymbolNode`, `ClassSymbolNode`, `LibrarySymbolNode`, `NamespaceCategoryNode`, etc.
- Drag-and-drop: `SymbolGTreeDragNDropHandler`

**Symbol Table** (`ghidra/app/plugin/core/symtable/`):
- `SymbolTableModel` — filterable, sortable; loads via `SymbolIterator`
- `ReferenceProvider` — shows incoming/outgoing references for selected symbol
- `SymbolFilter` — filter by type, scope, namespace

**References Plugin** (`ghidra/app/plugin/core/references/`):
- `EditReferencesProvider` — tabular view of all refs from current code unit
- Type-specific edit panels: `EditMemoryReferencePanel`, `EditStackReferencePanel`, `EditRegisterReferencePanel`, `EditExternalReferencePanel`

**Memory Map** (`ghidra/app/plugin/core/memory/`):
- `MemoryMapModel` — table columns: name, start, end, length, R/W/X, volatile, artificial, type, initialized, source, comment
- `MemoryMapManager` — operations: split, merge, expand, move, delete
- Dialogs: `AddBlockDialog`, `ExpandBlockDialog`, `MoveBlockDialog`, `SplitBlockDialog`, `ImageBaseDialog`

**Merge System** (`ghidra/app/merge/`):
Orchestrates multi-way program merge with 8 sequential phases:
1. `MemoryMergeManager` — block conflicts
2. `ProgramTreeMergeManager` — fragment tree conflicts
3. `DataTypeMergeManager` — type/archive conflicts
4. `ProgramContextMergeManager` — register value conflicts
5. `FunctionTagMerger` — tag conflicts
6. `ListingMergeManager` — code units, symbols, references, comments, equates, functions (delegates to ~8 sub-mergers)
7. `ExternalProgramMerger` — external library conflicts
8. `PropertyListMergeManager` — property conflicts

Resolution options: `ASK_USER`, `OPTION_LATEST`, `OPTION_MY`, `OPTION_ORIGINAL`, `CANCELED`.

---

## 11. Search Systems

### Memory Search (`ghidra/features/base/memsearch/`)

Pipeline: `SearchFormat` (parse user input) → `ByteMatcher` (pattern matching) → `MemorySearcher<T>` (address iteration) → `MemoryMatch` (results)

**`SearchFormat`** hierarchy: `HexSearchFormat`, `BinarySearchFormat`, `DecimalSearchFormat`, `StringSearchFormat`, `RegExSearchFormat`, `FloatSearchFormat`

**`MemorySearcher<T>`**: Chunk-based (16KB default), 100-byte overlap to catch patterns at block boundaries.

**`MemoryMatch`**: Address + matched bytes + pattern metadata.

### Byte Pattern Engine (`ghidra/util/bytesearch/`)

**`BulkPatternSearcher<T>`** — Aho-Corasick state machine for simultaneous multi-pattern search.
- Accepts byte array, stream, or `ExtendedByteSequence`
- Returns `Iterator<Match<T>>` (lazy) or `List<Match<T>>` (eager)

**`ExtendedByteSequence`** — wraps 3 buffers (pre/main/post) with configurable overlap for boundary-safe searching.

### Trie (`ghidra/util/search/trie/`)

**`ByteTrie<T>`** — Aho-Corasick trie.
- `search(byte[] text)` → `List<SearchResult<Integer, T>>`
- `search(Memory, AddressSetView)` → `List<SearchResult<Address, T>>`
- Lazy suffix pointer fixup; compact `ByteTrieNode<T>` with binary-search sorted children

### Text Search (`ghidra/app/plugin/core/searchtext/`)

Two modes: `ListingDisplaySearcher` (renders and searches — exact visual match) and `ProgramDatabaseSearcher` (queries DB directly — faster).

Field types: Mnemonic, Operand, Comment, Label, Function, Instruction, Data.

### Strings

- **`DefinedStringsPlugin`** — shows all user-created string definitions
- **`EncodedStringsPlugin`** — scans for strings using charset/Unicode script filters; trigram-based validation via `TrigramStringValidator`

### Instruction Search (`ghidra/app/plugin/core/instructionsearch/`)

Build generalized patterns from selected instructions by masking operands/mnemonics. Export to Yara format via `InstructionSearchApi_Yara`.

---

## 12. Annotations

### Bookmarks

**`BookmarkPlugin`** — implements `BookmarkService`. Integrates with `MarkerService` for visual indicators.
Types: Analysis, Error, Checksum, InfoBrowser, Notes + custom.

### Equates

Bind symbolic names to scalar operand values.
- Create: `CreateEquateCmd`, `CreateEnumEquateCommand`
- Convert format: `ConvertToUnsignedHexAction`, `ConvertToSignedHexAction`, `ConvertToBinaryAction`, `ConvertToCharAction`, `ConvertToFloatAction`, etc.
- View: `EquateTablePlugin` + `EquateReferenceTableModel`

### Highlights

**`SetHighlightPlugin`** — bidirectional highlight ↔ selection mapping.
Actions: set selection as highlight, clear highlight, add/subtract selection from highlight, set highlight as selection.

### Quick Fix Framework (`ghidra/features/base/quickfix/`)

Abstract base `QuickFix`:
- `getActionName()`, `getItemType()`, `getAddress()`, `getOriginal()`, `getCurrent()`, `getPreview()`
- `performAction()` — execute the fix
- `getStatus()` → `QuickFixStatus`: `NONE`, `WARNING`, `DONE`, `ERROR`, `CHANGED`, `DELETED`

Monitors program modification number to detect external changes after apply.

### Search and Replace (`ghidra/features/base/replace/`)

Extensible via `SearchAndReplaceHandler` implementations:
- `SymbolsSearchAndReplaceHandler` — functions, labels, namespaces
- `ListingCommentsSearchAndReplaceHandler` — code comments
- `DataTypesSearchAndReplaceHandler` / `DatatypeCategorySearchAndReplaceHandler` — type names/categories
- `MemoryBlockSearchAndReplaceHandler` — block names
- `ProgramTreeSearchAndReplaceHandler` — module/group names

Each handler generates `QuickFix` objects (e.g., `RenameSymbolQuickFix`, `UpdateCommentQuickFix`) displayed in `QuickFixTableModel`.

---

## Design Patterns Summary

| Pattern | Where used |
|---------|-----------|
| **Extension point** | Loader, Analyzer, FieldFactory, GFileSystem, FSBFileHandler, SearchAndReplaceHandler — all via ClassSearcher + suffix convention |
| **Command** | All mutating operations on Program (function, disassembly, label, equate, data commands) — enables undo/redo |
| **Service** | Inter-plugin communication via `GoToService`, `MarkerService`, `BookmarkService`, etc. |
| **Observer** | `DomainObjectListener` throughout for reactive UI updates on program changes |
| **Factory / Builder** | `ProgramLoader.builder()`, `ConcurrentQBuilder`, `FieldFactory` |
| **Adapter** | `ListingModelAdapter` (Program → LayoutModel), `ProgramBigListingModel` (Program → ListingModel) |
| **Caching** | `LayoutCache`, `FileCache` (MD5-keyed), `LRUMap` for field metadata |
| **Batching** | `SwingUpdateManager` throughout; analysis event batching (500ms) |
| **State machine** | `QuickFix` status, analysis task scheduling |
| **Template method** | `AbstractAnalyzer`, `AbstractProgramLoader`, `CompositeEditorModel` |

---

## Developer Tips

- **New analyzer**: Subclass `AbstractAnalyzer`, name ends in `Analyzer`, set `AnalyzerType` and `AnalysisPriority`, call `monitor.checkCancelled()` in loops.
- **New field factory**: Subclass `FieldFactory`, name ends in `FieldFactory`, auto-discovered by `FormatManager`.
- **New loader**: Implement `Loader`, name ends in `Loader`, provide `.opinion` file in processor module for auto-detection.
- **New GFileSystem**: Annotate with `@FileSystemInfo`, implement `GFileSystemProbe` for format detection.
- **New FSB action**: Implement `FSBFileHandler`, auto-discovered by `ClassSearcher`.
- **New search/replace target**: Implement `SearchAndReplaceHandler`, generates `QuickFix` objects.
- **Script API stability**: Never remove or change signatures in `FlatProgramAPI`.
- **Analysis thread**: All analyzers run on a single thread; use `AbstractAnalyzer.runParallelAddressAnalysis()` for parallel sub-tasks.
- **Program mutation**: Always use `Command`/`BackgroundCommand` subclasses for undo support; never mutate program directly outside a transaction.
