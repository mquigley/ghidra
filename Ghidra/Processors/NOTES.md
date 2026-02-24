# Ghidra Processors — Analysis Notes

> Generated: 2026-02-23. Re-read this file at the start of any session involving Ghidra/Processors/.

---

## Overview

The `Ghidra/Processors/` directory contains **38 processor modules**, one per processor family. Each module is nearly identical in structure — the primary content is SLEIGH language specification files, with optional Java for format-specific analysis and relocation handling.

**Total SLEIGH source**: ~276,600 lines across 191 `.sinc` + 146 `.slaspec` files.

---

## Standard Module Structure

Every processor module follows this layout:

```
Ghidra/Processors/<NAME>/
├── data/
│   ├── languages/           # SLEIGH specs and supporting XML (the core content)
│   │   ├── *.slaspec        # Root SLEIGH spec (compiled to *.sla binary)
│   │   ├── *.sinc           # SLEIGH include files (shared/modular sub-specs)
│   │   ├── *.ldefs          # Language definitions (ties everything together)
│   │   ├── *.pspec          # Processor spec (PC register, context, register groups)
│   │   ├── *.cspec          # Compiler spec (calling conventions, stack, data sizes)
│   │   ├── *.opinion        # Binary format detection hints (ELF machine codes, etc.)
│   │   └── *.dwarf          # DWARF register number → Ghidra register name mapping
│   ├── patterns/            # Byte pattern files for function prologue/entry detection
│   └── manuals/             # Manual index files (*.idx) for instruction cross-refs
├── src/
│   ├── main/java/           # Optional Java (relocation handlers, analyzers, loaders)
│   ├── test.processors/     # Processor-level unit tests (instruction encoding/decoding)
│   └── test.slow/           # Slower integration tests
├── build.gradle
└── Module.manifest
```

---

## File Types Explained

| Extension | Purpose |
|-----------|---------|
| `.slaspec` | Root SLEIGH specification — `@include`s `.sinc` files; compiled by `sleigh` tool to `.sla` binary used at runtime |
| `.sinc` | SLEIGH include fragment — defines registers, context variables, instruction encodings, PCode semantics |
| `.ldefs` | Language definitions XML — declares available language variants (e.g., x86:LE:32, x86:LE:64), references `.sla`, `.pspec`, `.cspec`; maps external tool IDs (IDA-PRO, GNU, QEMU names) |
| `.pspec` | Processor spec XML — sets program counter register, initial context values, register display groups (DEBUG, CONTROL, etc.), tracked register initial values |
| `.cspec` | Compiler spec XML — calling convention (`<prototype>`), parameter passing (registers + stack), return value location, data type sizes (int, long, pointer, float, wchar), stack pointer register |
| `.opinion` | Binary format opinion XML — maps binary format machine codes (ELF `e_machine`, PE machine type) to language ID + compiler spec; drives auto-detection when loading a binary |
| `.dwarf` | DWARF register map — maps DWARF register numbers to Ghidra register names for debug info import |
| `.idx` | Manual index — maps instruction mnemonic → page number in vendor PDF; enables "Open Documentation" feature |
| `.gdis` | Disassembler options (rare) |

---

## SLEIGH Spec Structure (`.slaspec` / `.sinc`)

SLEIGH is Ghidra's DSL for specifying instruction encodings and their PCode semantics. A typical spec contains:

```sleigh
# 1. Global definitions
@define BITS "64"

# 2. Address spaces
define space ram type=ram_space size=8 default;
define space register type=register_space size=4;

# 3. Register definitions
define register offset=0 size=8 [RAX RCX RDX ...];

# 4. Context variables (mode bits that affect instruction decoding)
define context contextreg
    addrsize=(0,1)   # 0=16-bit, 1=32-bit, 2=64-bit
    opsize=(2,3)
    longMode=(4,4);

# 5. Token/field definitions (bit-level instruction field extraction)
define token instr(8)
    op8=(0,7);

# 6. Constructor tables (pattern matching + PCode semantics)
:MOV dest,src is op8=0x89 & dest & src {
    dest = src;    # PCode: copy src to dest
}
```

**The `sleigh` compiler** (built as part of the Decompiler module) compiles `.slaspec` → `.sla` binary at build time; the runtime `SleighLanguage` loads `.sla` files.

---

## All 38 Processor Modules

| Module | Processors | SLEIGH lines | Java files | Notes |
|--------|-----------|-------------|-----------|-------|
| **x86** | x86 (16/32/64-bit, Real/Protected/Long mode) | 38,309 | 16 | Most complex Java; ELF/COFF/Mach-O relocation for both 32 and 64-bit |
| **AARCH64** | AArch64 | 61,994 | 10 | Largest spec; covers SVE, SME, system regs; ELF/COFF/Mach-O relocation |
| **ARM** | ARM (v4–v8, Thumb, Thumb2) | 20,761 | 11 | 22 `.sinc` files covering many ARM variants and instruction sets |
| **PowerPC** | PowerPC (32/64-bit, BE/LE, AltiVec, VSX) | 21,416 | 12 | 42 `.sinc` files; ELF relocation; address analysis |
| **MIPS** | MIPS (32/64-bit, BE/LE, micro, nano) | 10,835 | 9 | ELF64 relocation; address/symbol analyzers |
| **RISCV** | RISC-V (32/64-bit, compressed) | 10,193 | 6 | 31 spec files; ELF relocation; address analyzer |
| **Dalvik** | Android Dalvik bytecode | 3,472 | 4 | 37 `.sinc` files (one per instruction group); loader-level Java |
| **JVM** | Java Virtual Machine bytecode | 2,158 | 96 | Special: massive Java for class file parsing/loading; inject payloads for virtual dispatch |
| **PIC** | PIC 12/16/17/18/24, dsPIC 30F/33C/33E/33F | varies | 11 | 9 processor families; 22 spec files |
| **Atmel** | AVR8, AVR32 | varies | 5 | Harvard architecture |
| **Dalvik** | Android DEX bytecode | 3,472 | 4 | |
| **eBPF** | Extended BPF (Linux kernel) | varies | 5 | |
| **BPF** | Classic BPF | varies | 0 | |
| **Loongarch** | LoongArch (Chinese RISC) | varies | 3 | |
| **RISCV** | RISC-V | 10,193 | 6 | |
| **Sparc** | SPARC V8/V9 (32/64-bit) | varies | 5 | |
| **tricore** | Infineon TriCore | varies | 3 | |
| **Xtensa** | Tensilica Xtensa | varies | 3 | |
| **68000** | Motorola 68000 | varies | 2 | |
| **HCS12** | Freescale HCS12/HCS12X | varies | 2 | |
| **NDS32** | Andes NDS32 | varies | 3 | |
| **SuperH4** | Hitachi/Renesas SuperH4 | varies | 5 | |
| **TI_MSP430** | TI MSP430/MSP430X | varies | 5 | |
| **6502** | MOS 6502, 65C02 | varies | 0 | Classic 8-bit |
| **8048** | Intel 8048 | varies | 0 | |
| **8051** | Intel 8051/8052/8031 variants | varies | 0 | |
| **8085** | Intel 8085 | varies | 0 | |
| **CP1600** | General Instrument CP1600 | varies | 0 | |
| **CR16** | National Semi CR16 | varies | 0 | |
| **HCS08** | Freescale HC05/HC08/HCS08 | varies | 0 | |
| **M16C** | Renesas M16C/60 and M16C/80 | varies | 0 | |
| **M8C** | Cypress M8C | varies | 0 | |
| **MC6800** | Motorola 6800/6805/6809 | varies | 0 | |
| **MCS96** | Intel MCS-96 | varies | 0 | |
| **PA-RISC** | HP PA-RISC 1.x/2.0 | varies | 0 | |
| **SuperH** | Hitachi SuperH (non-SH4) | varies | 0 | |
| **V850** | Renesas V850 | varies | 0 | |
| **Z80** | Zilog Z80, Z180 | varies | 0 | |
| **DATA** | Raw data (no instructions) | — | 1 | Special: used for data-only segments; no instruction semantics |
| **Toy** | Fake processor for testing | — | 1 | Used by Ghidra test infrastructure; multiple variants (BE/LE, 32/64, Harvard) |

---

## Java Content by Category

Most Java in processor modules falls into 4 categories:

### 1. ELF Relocation Handlers
`*_ElfRelocationHandler`, `*_ElfRelocationContext`, `*_ElfRelocationType`
- Process ELF relocation entries (`.rela` / `.rel` sections) during binary loading
- Apply architecture-specific relocation formulas to patch addresses
- Most processors with ELF support have these (x86, AARCH64, ARM, MIPS, PowerPC, RISCV, Sparc, etc.)

### 2. COFF/Mach-O Relocation Handlers
`*_CoffRelocationHandler`, `*_MachoRelocationHandler`, `*_MachoRelocationConstants`
- Same concept for Windows PE/COFF and macOS Mach-O formats
- x86, AARCH64, ARM, PowerPC, MIPS have these

### 3. ELF Extension / Format Customization
`*_ElfExtension`, `*_ElfProgramHeaderConstants`
- Extends the ELF loader for processor-specific sections, segments, dynamic entries
- e.g., `PowerPC64_ElfExtension` handles PLT stubs and `.opd` (function descriptor) sections

### 4. Analyzers
`*Analyzer`, `*AddressAnalyzer`, `*PreAnalyzer`, `*SymbolAnalyzer`
- Auto-analysis passes that run on loaded binaries
- e.g., `X86Analyzer` (instruction fixups), `MipsAddressAnalyzer` (GP-relative addressing), `AARCH64PltThunkAnalyzer` (PLT thunk resolution)

### 5. Emulation State Modifiers
`*EmulateInstructionStateModifier`
- Hook into the PCode emulator to handle state that SLEIGH can't model natively
- e.g., handling IT blocks (ARM Thumb2), delay slots (MIPS), CPU mode switching

### 6. Special (JVM only)
96 Java files implementing a full class file parser/loader:
- `ClassFileJava`, `ConstantPoolJava`, `MethodInfoJava`, `AttributeFactory`, etc.
- `PcodeInjectLibraryJava` — provides PCode inject payloads for JVM virtual dispatch
- `JavaLoader` — custom binary loader for `.class` files and JARs
- `JvmSwitchAnalyzer` — tableswitch/lookupswitch recovery

---

## Language Variant System

Each `.ldefs` file can declare multiple **language variants** for one processor family.

**Example — x86** declares 6 language IDs:
- `x86:LE:16:Real Mode` — 16-bit real mode
- `x86:LE:16:Protected Mode` — 16-bit protected mode
- `x86:LE:32:default` — 32-bit (the common one)
- `x86:LE:32:System Management Mode` — SMM
- `x86:LE:64:default` — 64-bit
- `x86:LE:64:compat32` — 64-bit OS running 32-bit code

Language ID format: `<processor>:<endian>:<size>:<variant>`

Each language ID also lists **compiler specs** (calling conventions):
- x86:LE:32 → Visual Studio, gcc, Borland C++, Delphi, golang
- x86:LE:64 → Visual Studio, gcc, golang, Swift
- AARCH64 → AAPCS, AAPCS-VFP (default), Apple iOS, golang, win

---

## Opinion / Auto-Detection System

`.opinion` files map binary format magic values to language IDs, driving Ghidra's automatic "what processor is this?" detection.

```xml
<constraint loader="Executable and Linking Format (ELF)">
  <constraint compilerSpecID="gcc">
    <constraint primary="62" processor="x86" endian="little" size="64" variant="default"/>
    <!-- primary=62 is ELF e_machine EM_X86_64 -->
  </constraint>
</constraint>
```

The **Opinion service** queries all loaded `.opinion` files when opening a binary, ranks matches, and suggests the best language/compiler combination.

---

## Compiler Spec (`.cspec`) Key Sections

| Section | Purpose |
|---------|---------|
| `<data_organization>` | Sizes of primitives: int, long, pointer, float, wchar, alignment |
| `<stackpointer>` | Which register is the stack pointer |
| `<returnaddress>` | Where the return address lives (register or stack slot) |
| `<default_proto>` | Default calling convention with `<input>` and `<output>` param entries |
| `<prototype name="...">` | Named calling conventions (stdcall, fastcall, thiscall, etc.) |
| `<callfixup>` | PCode injection snippets for common library functions (e.g., `__stack_chk_fail`) |
| `<callotherfixup>` | Overrides for CALLOTHER PCode ops |
| `<global>` | Memory ranges and registers treated as global variables |

---

## Processor Spec (`.pspec`) Key Sections

| Section | Purpose |
|---------|---------|
| `<programcounter>` | Which register is PC |
| `<context_data>` | Initial context variable values and tracked register values |
| `<register_data>` | Register display groups (DEBUG, CONTROL, FP, etc.) and hidden registers |
| `<properties>` | Key-value properties for the language (e.g., `assemblyRating`, `useOperandReferenceAnalyzerSwitchTables`) |

---

## Pattern Files

`data/patterns/*.xml` — byte patterns for function prologue recognition.
Used by the auto-analysis "Find Functions" pass to locate function starts in binaries without symbols.

Example (x86): matches `PUSH EBP / MOV EBP, ESP` and similar common prologues.

---

## Special Processors

### Toy
- Fake architecture used by Ghidra's own test infrastructure
- 18 spec files covering: BE/LE, 32/64-bit, Harvard, aligned, stack variants
- Useful as a reference when writing a new processor spec — simplest possible SLEIGH

### DATA
- Not a real processor; represents raw data with no instruction semantics
- Used for data-only sections and binary blobs
- 3 variants: LE-64, BE-64, and pointer-size variants

---

## Adding a New Processor

1. Create `Ghidra/Processors/<NAME>/` following the standard structure
2. Write `.slaspec` / `.sinc` files defining registers, instruction encodings, and PCode semantics
3. Write `.ldefs` registering language IDs
4. Write `.pspec` (PC register, context) and `.cspec` (calling convention)
5. Write `.opinion` for binary format auto-detection
6. Optionally add Java for relocation handlers and analyzers
7. Add `Module.manifest` and `build.gradle` (copy from a simple processor like Z80)
8. The `sleigh` tool compiles `.slaspec` → `.sla` during build; Gradle handles this automatically

**Reference**: Use the `Toy` processor as a minimal working template. The Sleigh documentation PDFs (`sleigh.pdf`, `pcoderef.pdf` — built from the Decompiler module) are the authoritative language reference.

---

## Key Relationships

```
Binary file
    ↓ (loader reads format, checks e_machine / machine type)
Opinion service (*.opinion files)
    ↓ (picks language ID + compiler spec)
SleighLanguage (loads *.sla compiled from *.slaspec)
    ↓ (disassembles bytes → instructions → PCode)
PCode IR (platform-independent)
    ↓
Decompiler C++ core / Emulator
    ↓
Analysis / Decompiled output
```

ELF/COFF/Mach-O relocation handlers (Java) run during loading, before disassembly, to fix up addresses.
Analyzers (Java) run after disassembly to improve analysis quality (resolve indirect calls, GP-relative refs, PLT thunks, etc.).
