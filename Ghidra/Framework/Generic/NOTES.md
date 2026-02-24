# Ghidra Framework/Generic — Analysis Notes

> Generated: 2026-02-23. Re-read this file at the start of any session involving Framework/Generic.

---

## Purpose

Framework/Generic is Ghidra's **foundational utility and infrastructure library**. It sits just above Utility in the dependency chain and is depended on by nearly every other module. It provides:
- Parallel task execution (ConcurrentQ, Worker)
- Dynamic class/extension point discovery (ClassSearcher)
- Options/state persistence (GProperties)
- CompletableFuture async helpers (ghidra.async)
- Specialized data structures (primitives, weak refs, LRU caches, STL-like containers)
- Binary similarity search (LSH)
- Network / SSL / PKI utilities
- Application bootstrap context (Application singleton)

**431 Java source files.** External deps: Apache Commons, Guava, Log4j2, JDOM2, Bouncy Castle, GSON.

---

## Package Map

| Package | Content |
|---------|---------|
| `generic.algorithms` | CRC64, LCS (Longest Common Subsequence) |
| `generic.cache` | `CachingPool`, `BasicFactory`, `FixedSizeMRUCachingFactory` |
| `generic.concurrent` | `ConcurrentQ`, `ConcurrentQBuilder`, `QCallback`, `QResult`, `QProgressListener`, `ReentryGuard`, `ConcurrentListenerSet` |
| `generic.concurrent.io` | `ProcessConsumer`, `IOResult` — process I/O handling |
| `generic.constraint` | Decision trees / constraint solving: `DecisionTree`, `DecisionNode`, `Constraint` |
| `generic.expressions` | Math expression evaluator: `ExpressionEvaluator`, `ExpressionElement` |
| `generic.hash` | `FNV1a` (32/64-bit), `CRC32`, MessageDigest abstractions |
| `generic.io` | `JarWriter`, `NullPrintWriter` |
| `generic.json` | Simple JSON parser: `Json`, `JSONParser`, `JSONToken` |
| `generic.lsh` | Locality-Sensitive Hashing: `Partition`, `KandL`, `LSHMemoryModel` |
| `generic.lsh.vector` | LSH vectors: `LSHVector`, `LSHCosineVector`, `LSHCosineVectorAccum`, `HashEntry`, `VectorCompare`, `WeightFactory`, `IDFLookup` |
| `generic.random` | `SecureRandomFactory` |
| `generic.stl` | C++ STL-like containers (28 classes): `ListSTL`, `VectorSTL`, `MapSTL`, `SetSTL`, `MultiMapSTL`, `RedBlackTree`, iterators, `Pair`, `Quad` |
| `generic.test` | Test base classes: `AbstractGenericTest`, `TestUtils`, `ConcurrentTestExceptionHandler`, `TestExceptionTracker`, `TestThread` |
| `generic.test.category` | JUnit categories: `@NightlyCategory`, `@PortSensitiveCategory` |
| `generic.test.rule` | JUnit rules: `@Repeated`, `@IgnoreUnfinished` |
| `generic.timer` | Swing timers: `GhidraSwingTimer`, `ExpiringSwingTimer`, `GhidraTimerFactory` |
| `generic.util` | Misc utilities: iterators, action bindings, path handling, archive access |
| `generic.util.action` | Swing text actions: `BeginningOfLineAction`, `EndOfLineAction`, `DeleteToEndOfWord` |
| `ghidra.app.util.importer` | `MessageLog` — structured import log |
| `ghidra.async` | Async/CF helpers: `AsyncDebouncer`, `AsyncFence`, `AsyncLazyMap`, `AsyncLazyValue`, `AsyncPairingQueue`, `AsyncReference`, `AsyncTimer`, `AsyncUtils`, `SwingExecutorService` |
| `ghidra.framework` | `Application` singleton, `ApplicationConfiguration`, `Architecture`, `Platform`, logging init, `ShutdownHookRegistry` |
| `ghidra.framework.options` | `GProperties`, `SaveState`, `XmlProperties`, `JSonProperties`, `AttributedSaveState` |
| `ghidra.generic.util.datastruct` | `RestrictedValueSortedMap`, `SortedList`, `TreeValueSortedMap`, `ValueSortedMap` |
| `ghidra.lifecycle` | API lifecycle annotations: `@Experimental`, `@Internal`, `@Transitional`, `@Unfinished` |
| `ghidra.net` | PKI/SSL: `PKIUtils`, `HttpClients`, `DefaultSSLContextInitializer`, `DefaultTrustManagerFactory`, `DefaultKeyManagerFactory`, `SignedToken` |
| `ghidra.net.http` | `HttpUtil` |
| `ghidra.security` | `KeyStorePasswordProvider` |
| `ghidra.util` | Core utilities: `DataConverter`, `NumericUtilities`, `StringUtilities`, `Msg`, `Swing`, `UniversalID`, `Saveable`, `MathUtilities`, `DateUtils` |
| `ghidra.util.classfinder` | Extension point discovery: `ClassSearcher`, `ExtensionPoint`, `ExtensionPointProperties`, `ClassFileInfo`, `ClassDir`, `ClassJar`, `ClassLocation`, `ClassTranslator` |
| `ghidra.util.datastruct` | 80+ data structure classes (arrays, hashtables, weak maps, LRU, ranges, stacks) |
| `ghidra.util.exception` | Domain exceptions: `ClosedException`, `DuplicateNameException`, `MultipleCauses`, `NotYetImplementedException`, etc. |
| `ghidra.util.extensions` | Extension manager: `Extensions`, `ExtensionDetails`, `ExtensionUtils`, `ExtensionModuleClassLoader` |
| `ghidra.util.graph` | Graph algorithms: `DirectedGraph`, `WeightedDigraph`, `DependencyGraph`, `DepthFirstSearch`, `Dominator` |
| `ghidra.util.graph.attributes` | Vertex/edge attributes: `Attribute`, `IntegerAttribute`, `DoubleAttribute`, `StringAttribute`, `AttributeManager` |
| `ghidra.util.map` | `ValueMap`, `IntValueMap`, `ObjectValueMap` |
| `ghidra.util.task` | Task monitoring: `TaskMonitor`, `TaskMonitorAdapter`, `WrappingTaskMonitor`, `TaskMonitorSplitter`, `TimeoutTaskMonitor`, `MonitoredRunnable` |
| `ghidra.util.timer` | `GTimer`, `GTimerCache`, `Watchdog` |
| `ghidra.util.worker` | `Worker`, `PriorityWorker`, `AbstractWorker`, `Job`, `PriorityJob` |
| `ghidra.util.xml` | `XmlWriter`, `XmlUtilities`, `SpecXmlUtils` |
| `ghidra.xml` | XML pull parser: `XmlPullParserFactory`, `ThreadedXmlPullParserImpl`, `XmlTreeNode` |

---

## ConcurrentQ — Full Reference

The primary abstraction for parallel item processing.

### Flow
```
add(items) → fillOpenSlots() → submit FutureTaskMonitor to threadPool
    ↓
background thread: QCallback.process(item, monitor) → result
    ↓
QResult (success / exception / cancelled) → notify listener / collect
    ↓
signal waiters
```

### Key API

| Method | Blocks | Purpose |
|--------|--------|---------|
| `add(I)` / `add(Collection)` / `add(Iterator)` | No | Submit items |
| `offer(Iterator)` | Yes (when queue full) | Submit with backpressure |
| `waitForResults()` | Yes | All done; return all QResults (success + errors) |
| `waitForResults(long, TimeUnit)` | Yes | Timed variant |
| `waitForNextResult()` | Yes | Block until next single result |
| `waitUntilDone()` | Yes | Block; throw first exception; cancel rest (fail-fast) |
| `waitUntilDone(long, TimeUnit)` | Yes | Timed fail-fast |
| `isEmpty()` | No | All items processed? |
| `cancelAllTasks(boolean interrupt)` | No | Cancel pending + running |
| `cancelAllTasks(Predicate, boolean)` | No | Cancel matching items |
| `cancelScheduledJobs()` | No | Cancel only pending (not running) |
| `removeUnscheduledJobs()` | No | Remove pending; return list |
| `addProgressListener(QProgressListener)` | No | Progress events |
| `setMonitor(TaskMonitor, boolean)` | No | Attach TaskMonitor |
| `dispose()` | No | Shutdown private pool, cancel all |

**Error handling**:
- `waitForResults()` — returns all results including errors; use for fault-tolerant bulk processing
- `waitUntilDone()` — throws first exception, cancels remaining; use for fail-fast pipelines

**Throttling**: `ConcurrentQBuilder.setMaxInProgress(N)` limits concurrent items. With `N=1` and a FIFO queue, gives sequential processing. With a `PriorityBlockingQueue(capacity)`, `offer()` blocks when full (backpressure).

### QProgressListener events
- `taskStarted(id, item)` — new task begins
- `taskEnded(id, item, totalCount, completedCount)` — task done
- `progressChanged(id, item, current)` — job reports progress
- `progressModeChanged(id, item, indeterminate)` — determinate/indeterminate toggle
- `progressMessageChanged(id, item, msg)` — message update
- `maxProgressChanged(id, item, max)` — max bound change

### Builder

```java
ConcurrentQ<File, Result> q = new ConcurrentQBuilder<File, Result>()
    .setThreadPoolName("MyWorkers")        // or .setThreadPool(pool)
    .setMaxInProgress(4)                   // throttle to 4 concurrent
    .setCollectResults(true)               // buffer results
    .setJobsReportProgress(true)           // jobs call monitor.setProgress()
    .setListener((item, result) -> {})     // per-item callback
    .build((item, monitor) -> process(item));  // QCallback lambda
```

---

## ClassSearcher — Extension Point Discovery

### Discovery Pipeline

1. Read `data/ExtensionPoint.manifest` from each module root (one regex per line, e.g., `.*Plugin$`)
2. Build master suffix regex pattern from all manifests
3. Walk classpath dirs + JARs for `.class` files whose simple name matches the pattern
4. Load class; reject: abstract, non-public, inner, no no-arg constructor, `@ExtensionPointProperties(exclude=true)`
5. Sort by `@ExtensionPointProperties.priority()` descending (default priority = 1)
6. Cache results; track false positives (matched suffix but failed validation)

### Making an Extension Point

```java
// 1. In data/ExtensionPoint.manifest:
.*MyAnalyzer$

// 2. Java class:
@ExtensionPointProperties(priority = 2)        // optional, default priority=1
public class ConcreteMyAnalyzer
        implements MyInterface, ExtensionPoint { // both required
    public ConcreteMyAnalyzer() {}              // no-arg constructor mandatory
    @Override public void analyze() { ... }
}

// 3. Runtime:
ClassSearcher.search(monitor);                  // call once at startup
List<MyInterface> analyzers =
    ClassSearcher.getInstances(MyInterface.class);
// ConcreteMyAnalyzer automatically found and instantiated
```

### Key Methods

| Method | Purpose |
|--------|---------|
| `search(TaskMonitor)` | One-time disk scan; fires ChangeListeners when done |
| `getClasses(Class<T>)` | All loaded classes assignable to T, priority-sorted |
| `getClasses(Class<T>, Predicate)` | Same with filter |
| `getInstances(Class<T>)` | Instantiate all via no-arg constructor |
| `getExtensionPointInfo()` | `Set<ClassFileInfo>` of discovered classes |
| `getLoaded()` / `getFalsePositives()` | Introspection |
| `logStatistics()` | Debug output |
| `addChangeListener(ChangeListener)` | Notify when scan completes |

**Pitfalls**: No static initializers calling ClassSearcher (circular). Manifest suffix required. Keep listener references strong (weak internally).

---

## Worker / PriorityWorker

Both use `ConcurrentQ` internally with `maxInProgress=1` → sequential execution.

| Aspect | Worker | PriorityWorker |
|--------|--------|----------------|
| Queue | `LinkedBlockingQueue` | `PriorityBlockingQueue` |
| Ordering | FIFO | `Job.getPriority()` ascending (lower = higher priority) |
| Submit | `schedule(Job)` | `schedule(PriorityJob)` |
| Lifecycle | `IDLE → BUSY → IDLE` via `BusyListener` | same |

### Job API

```java
class MyJob extends Job {
    @Override
    public void run(TaskMonitor monitor) throws CancelledException {
        monitor.checkCancelled();
        // ... do work ...
    }
}

Worker worker = Worker.createGuiWorker();   // uses shared Swing pool
worker.schedule(new MyJob());
```

**Job states**: pending → running → completed | cancelled | error
**Error access**: `job.getError()` after completion (exceptions not thrown from `schedule()`).
**BusyListener**: fires `isBusy(true/false)` when worker transitions between idle/active.

---

## GProperties — Options / State Persistence

### Type-Safe Key-Value Store

```java
GProperties props = new GProperties("config");
props.putString("version", "1.0");
props.putInt("maxSize", 100);
props.putColor("background", Color.BLUE);
props.putEnum("mode", MyEnum.VALUE);
props.putSaveable("userData", myObj);   // custom Saveable
props.putPropertySet("nested", child);  // hierarchical

String v = props.getString("version", "0.0");  // with default
int n = props.getInt("maxSize", 50);
```

### Supported Types
`int`, `long`, `double`, `float`, `boolean`, `byte`, `short`, `String`, `Color`, `Font`, `KeyStroke`, `File`, `Date`, `Enum`, arrays of all primitives/String, `Saveable` (custom), nested `GProperties`.

### Backends

| Class | Behavior |
|-------|---------|
| `GProperties` | In-memory; manual `toXml()` / `fromXml()` |
| `XmlProperties(File)` | File-backed XML; loads on construction |
| `JSonProperties(File)` | File-backed JSON; loads on construction |
| `SaveState` | Legacy wrapper over GProperties |
| `AttributedSaveState` | GProperties + version/source metadata |

### XML format (reference)
```xml
<GPROPERTIES NAME="config">
  <STATE KEY="version" TYPE="string" VALUE="1.0"/>
  <STATE KEY="maxSize" TYPE="int" VALUE="100"/>
  <STATE KEY="nested" TYPE="GProperties">
    <GPROPERTIES NAME="child">...</GPROPERTIES>
  </STATE>
</GPROPERTIES>
```

---

## Async Utilities (ghidra.async)

| Class | Purpose | Example |
|-------|---------|---------|
| `AsyncUtils.nil()` | Pre-completed CF with null | `return AsyncUtils.nil();` |
| `AsyncUtils.unwrapThrowable(t)` | Strip CompletionException wrappers | Unwrap for error handling |
| `AsyncUtils.copyTo(dest)` | BiFunction: copy CF result to another CF | `src.handle(copyTo(dest))` |
| `AsyncUtils.FRAMEWORK_EXECUTOR` | ForkJoinPool for background work | `supplyAsync(fn, FRAMEWORK_EXECUTOR)` |
| `AsyncUtils.SWING_EXECUTOR` | Swing EDT executor | `supplyAsync(fn, SWING_EXECUTOR)` |
| `AsyncFence` | Barrier: wait for multiple futures | `fence.include(cf); fence.ready()` |
| `AsyncDebouncer` | Rate-limit calls in time window | Suppress rapid repeat events |
| `AsyncLazyValue<T>` | Compute once on demand | `lazy.get()` returns CF |
| `AsyncLazyMap<K,V>` | Per-key lazy computation | `map.get(key)` |
| `AsyncPairingQueue` | Match two async event streams | Pair request/response |
| `AsyncReference<T>` | Observable async reference | Value changes fire listeners |
| `AsyncTimer` | Periodic async callback | Scheduled repeat |
| `SwingExecutorService` | Executor on Swing EDT | Use with CompletableFuture |

---

## Data Structures

### Primitives (avoid boxing)
- `IntArray`, `LongArray`, `ByteArray`, `FloatArray`, `DoubleArray`, `ShortArray`, `BooleanArray`
- 2D variants: `IntArrayArray`, etc.
- `IntIntHashtable`, `LongObjectHashtable`, `StringIntHashtable` (and many more combinations)

### Weak-Reference Collections (listener safety, GC-friendly caches)
- `WeakSet<T>` — GC-able elements; variants: `ThreadUnsafeWeakSet`, `CopyOnReadWeakSet`, `CopyOnWriteWeakSet`
- `WeakValueHashMap<K,V>` — keys held, values GC-able
- `WeakValueTreeMap<K,V>` — sorted keys, GC-able values

### Bounded Caches
- `LRUMap<K,V>(capacity)` — evicts least-recently-used
- `LRUSet<T>(capacity)` — set version
- `SoftCacheMap` — uses `SoftReference` (allows GC under pressure)
- `ObjectCache` — object reuse pool

### Accumulator Pattern
```java
// Decouple search from result collection
Accumulator<Symbol> acc = new ListAccumulator<>();
symbolTable.search(criteria, acc);         // result added during search
List<Symbol> symbols = acc.get();
```
Implementations: `ListAccumulator`, `SetAccumulator`, `CallbackAccumulator` (fires `Consumer<T>` per item).

### Range / Index Structures
- `IndexRange` — contiguous index span
- `SortedRangeList` — non-overlapping sorted ranges
- `RangeMap<T>` — map ranges to values

### STL-like (generic.stl)
- `ListSTL<T>`, `VectorSTL<T>`, `MapSTL<K,V>`, `SetSTL<T>`, `MultiMapSTL<K,V>`, `MultiSetSTL<T>`
- `RedBlackTree<K,V>` — balanced BST
- `Pair<A,B>`, `Quad<A,B,C,D>` — tuples
- C++-style iterators (`IteratorSTL`)

---

## LSH — Binary Similarity

Locality-Sensitive Hashing enables fast approximate function/code similarity matching without exhaustive comparison.

### How it works
1. Extract features from a function (instruction sequences, CFG patterns, etc.) → weighted hash entries
2. Apply FNV-1a hash per entry to build `LSHCosineVector`
3. Hash vector into buckets via `Partition` (K hash functions per table, L tables)
4. Candidate lookup: query same buckets, compare cosine similarity of candidates
5. Similarity score ∈ [0,1]: 1.0 = identical, 0.0 = completely different

### Key Classes

| Class | Purpose |
|-------|---------|
| `LSHCosineVector` | Weighted feature vector; supports cosine similarity |
| `LSHCosineVectorAccum` | Accumulator for building a vector incrementally |
| `HashEntry` | Single (hash, coefficient) pair in a vector |
| `VectorCompare` | Comparison result: similarity score + match counts |
| `Partition` | FNV-1a hash family for bucketing |
| `KandL` | Parameters: K (hashes/table) and L (table count) |
| `WeightFactory` | Pluggable weight functions (default: TF-IDF) |
| `IDFLookup` | Pre-computed inverse document frequencies |

### Usage
```java
LSHCosineVectorAccum accum = new LSHCosineVectorAccum();
for (Feature f : features) {
    accum.addHash(f.hash(), f.weight());
}
LSHCosineVector vec = accum.finish(idfLookup);

VectorCompare cmp = new VectorCompare();
vec.compare(otherVec, cmp);
double similarity = cmp.similarity;  // 0.0–1.0
```

---

## Network / Security (ghidra.net)

| Class | Purpose |
|-------|---------|
| `PKIUtils` | X.509 cert generation (RSA 4096, SHA512), PKCS#12 keystore create/load, DN manipulation. Uses BouncyCastle. |
| `DefaultSSLContextInitializer` | Configure `SSLContext` for HTTPS connections |
| `DefaultTrustManagerFactory` | Trust store (which CAs to accept) |
| `DefaultKeyManagerFactory` | Client certificate selection for mutual TLS |
| `ApplicationKeyManagerFactory` | App-specific key material |
| `HttpClients` | Factory for configured `HttpClient` instances |
| `SignedToken` | Digitally-signed authentication tokens |
| `KeyStorePasswordProvider` | Callback for keystore password entry |

Used primarily for Ghidra Server ↔ Client mutual TLS authentication.

---

## Application Bootstrap (ghidra.framework)

`Application` is a singleton accessed statically after `initializeApplication()`:

```java
// At startup (once):
Application.initializeApplication(new GhidraApplicationLayout(), new ApplicationConfiguration());

// Anywhere thereafter:
ResourceFile root = Application.getApplicationRootDirectory();
ResourceFile dataFile = Application.getFile("languages/x86.sla");
ClassLoader cl = Application.getClassLoader();
boolean headless = Application.isHeadlessMode();
```

`ShutdownHookRegistry` — registers ordered cleanup hooks on JVM shutdown.
`Architecture` / `Platform` — detect OS, CPU architecture, Java version at runtime.

---

## TaskMonitor

The universal interface for cancellation + progress reporting in long-running operations.

```java
// In a long operation:
public void analyze(TaskMonitor monitor) throws CancelledException {
    monitor.setMaximum(items.size());
    monitor.setMessage("Analyzing...");
    for (int i = 0; i < items.size(); i++) {
        monitor.checkCancelled();         // throws CancelledException if user cancelled
        monitor.setProgress(i);
        processItem(items.get(i), monitor);
    }
}
```

**Implementations**:
- `TaskMonitorAdapter` — no-op base (override only what you need)
- `ConsoleTaskMonitor` — prints to stdout
- `WrappingTaskMonitor` — delegates to another monitor
- `CancelOnlyWrappingTaskMonitor` — proxies only cancel signal
- `TaskMonitorSplitter` — splits one monitor into sub-monitors for sub-tasks
- `TimeoutTaskMonitor` — auto-cancels after elapsed time
- `NullTaskMonitor` — ignores everything (never cancels)

---

## Extension System (ghidra.util.extensions)

Manages third-party Ghidra extensions (downloadable modules):

| Class | Purpose |
|-------|---------|
| `ExtensionUtils` | Discover, install, uninstall extensions from extension dirs |
| `ExtensionDetails` | Metadata: name, version, description, author, path |
| `Extensions` | Active extension inventory; duplicate detection |
| `ExtensionModuleClassLoader` | Isolated class loader for extension deps |

Extensions are ZIP files placed in `<ghidra_home>/Extensions/Ghidra/` or user extension dir. `ExtensionUtils` unpacks and registers them on next launch. `ExtensionModuleClassLoader` isolates extension class loading from the main classloader.

---

## Key Design Patterns

| Pattern | Where | Purpose |
|---------|-------|---------|
| **Builder** | `ConcurrentQBuilder` | Complex ConcurrentQ config |
| **Factory** | `GThreadPool.getSharedThreadPool()`, `BasicFactory`, `FixedSizeMRUCachingFactory` | Object creation abstraction |
| **Singleton** | `Application`, `ClassSearcher` statics | Global coordination |
| **Adapter** | `TaskMonitorAdapter`, `WrappingTaskMonitor` | Interface bridging |
| **Observer** | `QProgressListener`, `ChangeListener`, `BusyListener` | Event notification |
| **Strategy** | `QCallback`, `Accumulator`, `Factory<K,V>`, `WeightFactory` | Pluggable algorithms |
| **Template Method** | `AbstractWorker`, `AbstractGenericTest` | Common structure, custom steps |
| **Weak Reference** | `WeakSet`, `WeakValueHashMap`, `ConcurrentListenerSet` | GC-safe listener lists |
| **Barrier** | `AsyncFence` | Synchronize futures |
| **Debounce** | `AsyncDebouncer` | Rate-limit rapid events |
| **Object Pool** | `CachingPool`, `ObjectCache` | Reduce allocation |
| **Command** | `Job`, `QCallback` | Encapsulate work |
| **State Machine** | `Job` (pending → running → done/cancelled) | Lifecycle |

---

## External Dependencies

| Artifact | Version | Used For |
|----------|---------|---------|
| `guava` | 32.1.3-jre | Collections, caching, utilities |
| `commons-codec` | 1.18.0 | Base64, Hex encoding |
| `commons-collections4` | 4.1 | Extended collections |
| `commons-compress` | 1.27.1 | ZIP, TAR, GZIP archive handling |
| `commons-lang3` | 3.20.0 | String, enum, reflection utilities |
| `commons-text` | 1.10.0 | Advanced string operations |
| `commons-io` | 2.19.0 | File I/O utilities |
| `log4j-api` / `log4j-core` | 2.25.3 | Logging |
| `jdom2` | 2.0.6.1 | XML parsing/generation |
| `gson` | 2.9.0 | JSON serialization |
| `bcprov-jdk18on` + `bcpkix` + `bcutil` | 1.80 | BouncyCastle crypto (PKI/SSL) |

---

## Developer Tips

- **Parallel work**: Use `ConcurrentQ` with `waitForResults()` for fault-tolerant bulk processing; use `waitUntilDone()` for fail-fast pipelines.
- **New extension point**: Implement `ExtensionPoint`, add no-arg constructor, add suffix regex to `data/ExtensionPoint.manifest`.
- **Listener lists**: Always use `WeakSet` or `ConcurrentListenerSet` — never a strong `List` — to avoid memory leaks.
- **State persistence**: Use `GProperties` + `XmlProperties` for file-backed config; prefer `JSonProperties` for new code.
- **Async composition**: Prefer `AsyncFence` over manual `CompletableFuture.allOf()` for clarity; use `SwingExecutorService` for EDT scheduling.
- **Primitive perf**: When maps/arrays involve primitive int/long keys, use the primitive hashtable classes to avoid boxing overhead.
- **Binary similarity**: `LSHCosineVector` + `Partition` is the mechanism; it's used by BSim (Binary Similarity) feature — look there for complete examples.
- **Cancellation**: Always thread `TaskMonitor` through long operations and call `monitor.checkCancelled()` at loop boundaries.
