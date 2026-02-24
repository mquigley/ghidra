# Ghidra Codebase — Claude Analysis Index

This file is the master index for Claude's module-by-module analysis of this codebase.
At the start of any session, tell Claude which module you're working on and ask it to read
the corresponding NOTES.md file listed below.

---

## Analyzed Modules

| Module | Notes File | Summary |
|--------|-----------|---------|
| Decompiler | [Ghidra/Features/Decompiler/NOTES.md](Ghidra/Features/Decompiler/NOTES.md) | Hybrid Java/C++ decompiler. C++ core runs as subprocess communicating via binary pipe protocol. Action-based transformation pipeline on PCode IR. |
| Framework (all 12 submodules) | [Ghidra/Framework/NOTES.md](Ghidra/Framework/NOTES.md) | Foundation layer: Utility (bootstrap), Generic (data structures/concurrency), DB (embedded B-Tree), FileSystem (versioned storage), SoftwareModeling (PCode/SLEIGH), Emulation (JIT PCode engine), Graph (visualization), Gui (themes/LAF), Docking (window/action framework), Help (JavaHelp), Project (domain objects/plugins), Pty (pseudo-terminal). |
| Framework/Generic (deep dive) | [Ghidra/Framework/Generic/NOTES.md](Ghidra/Framework/Generic/NOTES.md) | Deep dive: ConcurrentQ (parallel task queue), ClassSearcher (extension point discovery), Worker/PriorityWorker (sequential jobs), GProperties (typed options persistence), async CF helpers, primitive data structures, LSH binary similarity, PKI/SSL utilities. |
| Processors (all 38 modules) | [Ghidra/Processors/NOTES.md](Ghidra/Processors/NOTES.md) | 38 processor families, each containing SLEIGH specs (.slaspec/.sinc), language defs (.ldefs), processor/compiler specs (.pspec/.cspec), binary format opinions (.opinion), and optional Java for relocation handlers and analyzers. ~277K lines of SLEIGH total. |
| Features/Base | [Ghidra/Features/Base/NOTES.md](Ghidra/Features/Base/NOTES.md) | Ghidra's core application module (3,493 Java files): binary loaders, GFileSystem/FSRL, CodeBrowser/Listing viewer (100+ field factories), auto-analysis framework (Analyzer interface, AutoAnalysisManager), scripting (GhidraScript, FlatProgramAPI, headless, OSGi), data type manager, symbol/reference/memory UI, merge system, search (memory, byte, text, instruction, trie), bookmarks/equates/highlights/quick-fix. |
| Framework/SoftwareModeling (deep dive) | [Ghidra/Framework/SoftwareModeling/NOTES.md](Ghidra/Framework/SoftwareModeling/NOTES.md) | Deep dive: Program model API (Address/Listing/Memory/Language/PCode/Symbol/DataType interfaces), ProgramDB (15 managers, DB v32, versioned adapter pattern, DBObjectCache), SLEIGH runtime (SleighLanguage, DecisionNode tree, Constructor/ConstructTpl/VarnodeTpl, PcodeEmit), pcodeCPort compiler port (.slaspec→.sla), SLEIGH assembler (LALR(1) parser, constraint solving, MaskedLong, context graph/Dijkstra), Disassembler, ProgramEvent system, FieldLocation classes, graph service (AttributedGraph/GraphDisplay). |
| Decompiler C++ core (deep dive) | [Ghidra/Features/Decompiler/src/decompile/cpp/NOTES.md](Ghidra/Features/Decompiler/src/decompile/cpp/NOTES.md) | Deep dive: Varnode/PcodeOp/FlowBlock core IR, SSA construction (Heritage: phi-node insertion, renaming, guard mechanisms), HighVariable/Cover/Merge, Funcdata hub, Action/Rule pipeline (58+ Actions, 136+ Rules, universal pipeline order), type system (18 metatypes, TypeOp semantics, cast strategy), ABI/parameter recovery (ParamEntry, ProtoModel, ParamList variants), C code output (PrintC, EmitMarkup), Ghidra integration (ArchitectureGhidra, binary protocol, ScopeGhidra, FlowInfo, JumpTable recovery), value range analysis (CircleRange), DynamicHash, PCode injection, user ops. |

---

## How to Use

Start a session by saying:
> "Read the notes for the Decompiler module, then help me with X."

Claude will read the relevant NOTES.md and have immediate context without re-exploring the codebase.

---

## Project Overview

**Ghidra** is NSA's open-source software reverse engineering (SRE) framework.

- **Language**: Primarily Java (framework, UI, plugins) + C++ (decompiler core) + Sleigh (processor specs)
- **Build**: Gradle (Java), Gradle native (C++ cross-platform), Bison/Flex (parsers)
- **Structure**: Modular — `Ghidra/Features/`, `Ghidra/Framework/`, `Ghidra/Processors/`, etc.
- **Key concept**: Sleigh is Ghidra's domain-specific language for describing processor instruction sets; it drives both disassembly and PCode lifting.
