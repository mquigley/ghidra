#!/usr/bin/env python3
"""
sla_dump.py — Human-readable dump of x86 PCode from x86.sla.xml

Renders each top-level instruction constructor as:

  MNEMONIC operand1, operand2
    TMP1 = OP arg, arg
    REG  = OP arg, arg
    ...

Usage:
    python3 sla_dump.py [x86.sla.xml] [options]

Options:
    --filter SUBSTR   Only print constructors whose mnemonic contains SUBSTR
    --source N        Only print constructors from source file index N
    --no-build        Hide BUILD ops (sub-operand expansions)




BUILD annotations
A BUILD in the pcode template means "execute this operand's own pcode here before continuing". It's the mechanism for sub-table operands — operands that aren't simple registers but are themselves defined by a SLEIGH sub-table with their own pcode.

In SHR rm16,n1, the two operands are defined as sub-tables in SLEIGH source:


# ia.sinc:1484
rm16: Rmr16     is mod=3 & Rmr16    { export Rmr16; }      ← register variant
rm16: "word ptr" Mem  is Mem        { export *:2 Mem; }    ← memory variant

# ia.sinc:1495
n1: one   is epsilon  [ one=1; ]    { export *[const]:1 one; }
So rm16 is a sub-table that resolves to either a register or a memory dereference — it has pcode of its own (a LOAD, in the memory case). The BUILD rm16 and BUILD n1 lines in the dump mean: "at this point in execution, evaluate whichever rm16 variant matched, and splice in its pcode."

What BUILD lines mean in practice for SHR rm16,n1:


SHR rm16,n1
  # BUILD 1         ← evaluate n1's pcode (constant 1, no-op in register case)
  # BUILD 0         ← evaluate rm16's pcode (no-op for register, or LOAD for memory)
  TMP1 = INT_AND rm16, 1      ← after BUILD, rm16 is available as a value
  CF = INT_NOTEQUAL TMP1, 0
  ...
If the instruction encodes a memory operand (e.g. SHR [SI], 1), the BUILD for rm16 would have actually emitted a LOAD op to bring the memory value into a temp before this code runs. The parametric dump can't show that because which variant matched is only known at decode time — that's the fundamental limit of Approach A.


"""

import sys
import re
import xml.etree.ElementTree as ET
from collections import defaultdict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def hex_str(val, size=None):
    v = int(val, 0)
    if size is not None:
        s = int(size, 0)
        if s == 1 and v > 127:
            v -= 256
        elif s == 2 and v > 32767:
            v -= 65536
    if -16 < v < 16:
        return str(v)
    return hex(v)

# ---------------------------------------------------------------------------
# Symbol tables built from <symbol_table> section
# ---------------------------------------------------------------------------

class SymbolTable:
    def __init__(self):
        # id -> name  (for any named symbol)
        self.names = {}
        # id -> (space, offset, size)  varnode_sym bodies
        self.varnodes = {}
        # id -> index  userop bodies
        self.userops = {}
        # userop index -> name
        self.userop_names = {}
        # id -> (subsym_id, build_index)  operand_sym bodies
        self.operand_subsym = {}
        self.operand_index = {}   # id -> build_index (the index= attr on operand_sym)
        # id -> name  for subtable_syms
        self.subtable_names = {}
        # register space: offset -> name  (built from varnodes in register space)
        self.reg_by_offset = {}

    def build(self, root):
        sym_table = root.find('symbol_table')

        # --- Pass 1: _head elements give us names ---
        for elem in sym_table:
            tag = elem.tag
            if tag.endswith('_head') or tag.endswith('_sym_head'):
                name = elem.get('name')
                sid = elem.get('id')
                if name and sid:
                    self.names[sid] = name
                    if 'subtable' in tag:
                        self.subtable_names[sid] = name

        # --- Pass 2: body elements give us data ---
        for elem in sym_table:
            tag = elem.tag
            sid = elem.get('id')
            if not sid:
                continue

            if tag == 'varnode_sym':
                space = elem.get('space', '?')
                off   = elem.get('off', '0x0')
                size  = elem.get('size', '0')
                self.varnodes[sid] = (space, off, size)
                if space == 'register':
                    name = self.names.get(sid)
                    if name:
                        self.reg_by_offset[int(off, 0)] = name

            elif tag == 'userop':
                index = elem.get('index', '0')
                self.userops[sid] = int(index)
                name = self.names.get(sid, f'userop_{index}')
                self.userop_names[int(index)] = name

            elif tag == 'operand_sym':
                subsym = elem.get('subsym')
                if subsym:
                    self.operand_subsym[sid] = subsym
                idx = elem.get('index')
                if idx is not None:
                    self.operand_index[sid] = int(idx)

    def reg_name(self, offset_int, size_int):
        """Return register name for (offset, size), trying exact then containing."""
        name = self.reg_by_offset.get(offset_int)
        if name:
            return name
        # Fallback: find a register that contains this offset+size
        for off, n in self.reg_by_offset.items():
            voff, vsize = off, None
            for sid, (sp, vo, vs) in self.varnodes.items():
                if sp == 'register' and int(vo, 0) == off:
                    vsize = int(vs, 0)
                    break
            if vsize and offset_int >= off and offset_int + size_int <= off + vsize:
                return f'{n}[{offset_int - off}:{size_int}]'
        return f'reg[0x{offset_int:x}:{size_int}]'

    def subtable_name(self, sid):
        return self.subtable_names.get(sid, self.names.get(sid, f'subtable_{sid}'))

# ---------------------------------------------------------------------------
# Varnode rendering
# ---------------------------------------------------------------------------

# Unique space temporaries: offset -> friendly name (assigned lazily)
_tmp_counter = [0]
_tmp_map = {}

def reset_tmps():
    _tmp_counter[0] = 0
    _tmp_map.clear()

def tmp_name(offset_str):
    key = int(offset_str, 0)
    if key not in _tmp_map:
        _tmp_counter[0] += 1
        _tmp_map[key] = f'TMP{_tmp_counter[0]}'
    return _tmp_map[key]

def render_varnode(vn, sym: SymbolTable, operand_names: list, show_size=True):
    """
    Render a <varnode_tpl> element to a string.

    A varnode_tpl has exactly 3 child elements:
      child[0] = space  (const_spaceid | const_handle s="0")
      child[1] = offset (const_real | const_handle s="1" | const_relative | intb)
      child[2] = size   (const_real | const_handle s="2")

    const_handle val="N" s="F" means: take field F from operand N's handle.
      s=0 -> space, s=1 -> offset, s=2 -> size
    """
    children = list(vn)
    if len(children) < 3:
        return '?'

    space_el, off_el, size_el = children[0], children[1], children[2]

    # --- resolve space ---
    space = None
    if space_el.tag == 'const_spaceid':
        space = space_el.get('space', 'ram')
    elif space_el.tag == 'const_handle':
        op_idx = int(space_el.get('val', '0'))
        op_name = operand_names[op_idx] if op_idx < len(operand_names) else f'op{op_idx}'
        space = f'@{op_name}.space'
    else:
        space = '?space'

    # --- resolve size (needed for register lookup and display) ---
    size_val = None
    size_str = None
    if size_el.tag == 'const_real':
        size_val = int(size_el.get('val', '0'), 0)
        size_str = str(size_val)
    elif size_el.tag == 'const_handle':
        op_idx = int(size_el.get('val', '0'))
        op_name = operand_names[op_idx] if op_idx < len(operand_names) else f'op{op_idx}'
        size_str = f'{op_name}.size'

    # --- resolve offset ---
    off_str = None
    if off_el.tag == 'const_real':
        off_val = int(off_el.get('val', '0'), 0)
        if space == 'register':
            name = sym.reg_name(off_val, size_val or 0)
            return name
        elif space == 'const':
            # Literal constant value
            v = off_val
            if size_val and size_val < 8:
                # sign-extend if needed based on size
                bits = size_val * 8
                if v >= (1 << (bits - 1)):
                    v -= (1 << bits)
            return hex_str(hex(v)) if v != off_val else hex_str(off_el.get('val'))
        elif space == 'unique':
            name = tmp_name(off_el.get('val'))
            if show_size and size_str:
                return f'{name}:{size_str}'
            return name
        else:
            off_str = hex(off_val)
    elif off_el.tag == 'const_handle':
        op_idx = int(off_el.get('val', '0'))
        op_name = operand_names[op_idx] if op_idx < len(operand_names) else f'op{op_idx}'
        # This is the operand itself (space=handle.space, offset=handle.offset)
        if show_size and size_str:
            return f'{op_name}:{size_str}'
        return op_name
    elif off_el.tag == 'const_relative':
        return f'label[{off_el.get("val", "?")}]'
    elif off_el.tag == 'const_start':
        return 'inst_start'
    elif off_el.tag == 'const_next':
        return 'inst_next'
    elif off_el.tag == 'const_next2':
        return 'inst_next2'
    elif off_el.tag == 'const_flowref':
        return 'flowref'
    elif off_el.tag == 'const_flowdest':
        return 'flowdest'
    elif off_el.tag == 'intb':
        v = int(off_el.get('val', '0'), 0)
        return hex_str(hex(v))
    else:
        off_str = f'?off({off_el.tag})'

    # Fallback for ram/other spaces
    if off_str is None:
        off_str = '?'
    if show_size and size_str:
        return f'[{space}:{off_str}:{size_str}]'
    return f'[{space}:{off_str}]'

# ---------------------------------------------------------------------------
# Op rendering
# ---------------------------------------------------------------------------

UNARY_OPS  = {'COPY', 'INT_ZEXT', 'INT_SEXT', 'INT_NEGATE', 'BOOL_NEGATE',
               'FLOAT_NEG', 'FLOAT_ABS', 'FLOAT_SQRT', 'FLOAT_CEIL',
               'FLOAT_FLOOR', 'FLOAT_ROUND', 'FLOAT_NAN', 'POPCOUNT', 'TRUNC',
               'INT_2COMP', 'FLOAT_INT2FLOAT', 'FLOAT_FLOAT2FLOAT',
               'FLOAT_TRUNC', 'LZCOUNT'}
BINARY_OPS = {'INT_ADD', 'INT_SUB', 'INT_MULT', 'INT_DIV', 'INT_SDIV',
               'INT_REM', 'INT_SREM', 'INT_AND', 'INT_OR', 'INT_XOR',
               'INT_LEFT', 'INT_RIGHT', 'INT_SRIGHT',
               'INT_EQUAL', 'INT_NOTEQUAL', 'INT_LESS', 'INT_SLESS',
               'INT_LESSEQUAL', 'INT_SLESSEQUAL',
               'INT_CARRY', 'INT_SCARRY', 'INT_SBORROW',
               'BOOL_AND', 'BOOL_OR', 'BOOL_XOR',
               'FLOAT_ADD', 'FLOAT_SUB', 'FLOAT_MULT', 'FLOAT_DIV',
               'FLOAT_EQUAL', 'FLOAT_NOTEQUAL', 'FLOAT_LESS', 'FLOAT_LESSEQUAL',
               'SUBPIECE'}

def render_op(op_el, sym: SymbolTable, display_names: list, build_names: dict,
              userop_index_map: dict, indent='  ', show_build=True):
    """Render a single <op_tpl> to a list of output lines."""
    code = op_el.get('code', '?')
    children = list(op_el)  # first child is output varnode (or <null/>)

    if not children:
        return [f'{indent}{code}']

    out_el = children[0]
    inputs = children[1:]

    def rv(el, show_size=True):
        return render_varnode(el, sym, display_names, show_size)

    # --- BUILD: sub-operand expansion marker ---
    if code == 'BUILD':
        if not show_build:
            return []
        # BUILD encodes the operand's build_index as a const value
        build_idx = None
        if inputs:
            vn_children = list(inputs[0])
            if len(vn_children) >= 2 and vn_children[1].tag == 'const_real':
                build_idx = int(vn_children[1].get('val', '0'), 0)
        if build_idx is not None:
            name = build_names.get(build_idx, f'op{build_idx}')
            return [f'{indent}# BUILD {name}']
        return [f'{indent}# BUILD ?']

    # --- LABEL: internal branch target ---
    if code == 'LABEL':
        if inputs:
            return [f'{indent}label[{inputs[0].find("const_real").get("val", "?")}]:']
        return [f'{indent}label:']

    # --- BRANCH / CBRANCH / BRANCHIND ---
    if code == 'BRANCH':
        dest = rv(inputs[0]) if inputs else '?'
        return [f'{indent}goto {dest}']
    if code == 'CBRANCH':
        dest = rv(inputs[0]) if len(inputs) > 0 else '?'
        cond = rv(inputs[1]) if len(inputs) > 1 else '?'
        return [f'{indent}if ({cond}) goto {dest}']
    if code == 'BRANCHIND':
        dest = rv(inputs[0]) if inputs else '?'
        return [f'{indent}goto [{dest}]']

    # --- CALL / CALLIND / RETURN ---
    if code == 'CALL':
        dest = rv(inputs[0]) if inputs else '?'
        return [f'{indent}call {dest}']
    if code == 'CALLIND':
        dest = rv(inputs[0]) if inputs else '?'
        return [f'{indent}call [{dest}]']
    if code == 'RETURN':
        dest = rv(inputs[0]) if inputs else '?'
        return [f'{indent}return {dest}']

    # --- CALLOTHER: user-defined op ---
    if code == 'CALLOTHER':
        # inputs[0] = const index of the userop
        userop_name = '?userop'
        if inputs:
            idx_el = inputs[0]
            if idx_el.tag == 'varnode_tpl':
                idx_children = list(idx_el)
                if len(idx_children) >= 2 and idx_children[1].tag == 'const_real':
                    idx = int(idx_children[1].get('val', '0'), 0)
                    userop_name = sym.userop_names.get(idx, f'userop_{idx}')
        args = ', '.join(rv(i) for i in inputs[1:])
        out_str = rv(out_el) if out_el.tag != 'null' else None
        if out_str:
            return [f'{indent}{out_str} = {userop_name}({args})']
        return [f'{indent}{userop_name}({args})']

    # --- STORE ---
    if code == 'STORE':
        # inputs: [space_id, ptr_addr, value]
        # out_el is null for STORE
        ptr  = rv(inputs[1]) if len(inputs) > 1 else '?'
        val  = rv(inputs[2]) if len(inputs) > 2 else '?'
        return [f'{indent}*{ptr} = {val}']

    # --- LOAD ---
    if code == 'LOAD':
        # inputs: [space_id, ptr_addr]
        out_str = rv(out_el) if out_el.tag != 'null' else '?tmp'
        ptr = rv(inputs[1]) if len(inputs) > 1 else '?'
        return [f'{indent}{out_str} = *{ptr}']

    # --- Standard unary / binary ---
    out_str = rv(out_el) if out_el.tag != 'null' else None

    if code in UNARY_OPS and inputs:
        rhs = f'{code} {rv(inputs[0])}'
    elif code in BINARY_OPS and len(inputs) >= 2:
        rhs = f'{code} {rv(inputs[0])}, {rv(inputs[1])}'
    else:
        # Fallback: show all inputs
        args_str = ', '.join(rv(i) for i in inputs)
        rhs = f'{code} {args_str}'

    if out_str:
        return [f'{indent}{out_str} = {rhs}']
    return [f'{indent}{rhs}']

# ---------------------------------------------------------------------------
# Constructor rendering
# ---------------------------------------------------------------------------

def get_operand_names(ctor_el, sym: SymbolTable):
    """
    Return two things:
      - display_names: list in <oper> declaration order, used for const_handle resolution
        (const_handle val="N" uses the order operands appear in the oper list)
      - build_names: dict {build_index -> name}, used for BUILD op rendering
        (BUILD val="N" uses the index= attribute from operand_sym, which can differ)
    """
    display_names = []
    build_names = {}
    for oper in ctor_el.findall('oper'):
        oid = oper.get('id')
        name = sym.names.get(oid, f'op{len(display_names)}')
        display_names.append(name)
        build_idx = sym.operand_index.get(oid)
        if build_idx is not None:
            build_names[build_idx] = name
    return display_names, build_names

def get_print_string(ctor_el):
    """
    Reconstruct the mnemonic+operand display string from <print> and <opprint> elements.
    """
    parts = []
    for child in ctor_el:
        if child.tag == 'print':
            parts.append(child.get('piece', ''))
        elif child.tag == 'opprint':
            parts.append(f'<op{child.get("id", "?")}>') # placeholder resolved below
    return ''.join(parts)

def render_constructor(ctor_el, sym: SymbolTable, source_names: dict,
                       show_build=True, show_source=True):
    """Render one constructor to a list of lines."""
    lines = []

    display_names, build_names = get_operand_names(ctor_el, sym)
    source_idx = ctor_el.get('source', '0')
    line_no = ctor_el.get('line', '?')
    src_file = source_names.get(source_idx, f'source_{source_idx}')

    # Build mnemonic string using opprint id= which refers to build_index
    parts = []
    for child in ctor_el:
        if child.tag == 'print':
            parts.append(child.get('piece', ''))
        elif child.tag == 'opprint':
            idx = int(child.get('id', '0'))
            name = build_names.get(idx, f'op{idx}')
            parts.append(name)
    mnemonic = ''.join(parts)

    if show_source:
        lines.append(f'# {src_file}:{line_no}')
    lines.append(mnemonic)

    # Reset temp name map for each constructor
    reset_tmps()

    # Walk construct_tpl
    ctpl = ctor_el.find('construct_tpl')
    if ctpl is None:
        lines.append('  # (no pcode)')
        return lines

    ctpl_children = list(ctpl)
    if not ctpl_children:
        lines.append('  # (empty)')
        return lines

    # First child is handle_tpl (subtable) or null (instruction table)
    first = ctpl_children[0]
    op_tpls = ctpl_children[1:]

    if first.tag == 'handle_tpl':
        # Subtable constructor — show the handle it exports
        hc = list(first)
        lines.append(f'  # exports handle: {_describe_handle(hc, sym, display_names)}')

    if not op_tpls:
        lines.append('  # (no ops)')
        return lines

    for op_el in op_tpls:
        if op_el.tag != 'op_tpl':
            continue
        rendered = render_op(op_el, sym, display_names, build_names,
                             sym.userop_names,
                             indent='  ',
                             show_build=show_build)
        lines.extend(rendered)

    return lines

def _describe_handle(hc, sym, display_names):
    """Brief description of what a handle_tpl exports."""
    # handle has 7 fields: ptrspace ptrsize ptroffset space offset size temp
    # We care about space (index 3), offset (4), size (5)
    def _rv(el):
        if el is None: return '?'
        if el.tag == 'const_spaceid': return el.get('space','?')
        if el.tag == 'const_real': return hex_str(el.get('val','0'))
        if el.tag == 'const_handle':
            op_idx = int(el.get('val','0'))
            op = display_names[op_idx] if op_idx < len(display_names) else f'op{op_idx}'
            return f'{op}.s{el.get("s","?")}'
        return el.tag
    if len(hc) >= 7:
        space = _rv(hc[3])
        off   = _rv(hc[4])
        size  = _rv(hc[5])
        return f'({space}, {off}, {size})'
    return '(incomplete)'

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Dump x86.sla.xml PCode in human-readable form')
    parser.add_argument('sla_xml', nargs='?',
                        default='x86.sla.xml',
                        help='Path to x86.sla.xml (default: x86.sla.xml)')
    parser.add_argument('--filter', '-f', metavar='SUBSTR',
                        help='Only show constructors whose mnemonic contains SUBSTR (case-insensitive)')
    parser.add_argument('--source', '-s', metavar='N', type=int, default=None,
                        help='Only show constructors from source file index N')
    parser.add_argument('--no-build', action='store_true',
                        help='Hide BUILD ops')
    parser.add_argument('--no-source', action='store_true',
                        help='Hide source file/line annotations')
    parser.add_argument('--subtables', action='store_true',
                        help='Also dump non-instruction subtable constructors')
    args = parser.parse_args()

    print(f'Parsing {args.sla_xml}...', file=sys.stderr)
    tree = ET.parse(args.sla_xml)
    root = tree.getroot()

    # Build source file index
    source_names = {}
    for sf in root.findall('sourcefiles/sourcefile'):
        source_names[sf.get('index', '0')] = sf.get('name', '?')

    print('Building symbol table...', file=sys.stderr)
    sym = SymbolTable()
    sym.build(root)

    sym_table = root.find('symbol_table')

    filter_str = args.filter.lower() if args.filter else None
    show_build  = not args.no_build
    show_source = not args.no_source

    # Decide which parents to include
    # parent="0x0" = instruction table; others = subtables
    if args.subtables:
        target_parents = None  # all
    else:
        target_parents = {'0x0'}

    print('Rendering constructors...', file=sys.stderr)
    count = 0
    for ctor in sym_table.iter('constructor'):
        parent = ctor.get('parent', '')
        if target_parents is not None and parent not in target_parents:
            continue

        src_idx = ctor.get('source', '0')
        if args.source is not None and int(src_idx) != args.source:
            continue

        rendered = render_constructor(ctor, sym, source_names,
                                     show_build=show_build,
                                     show_source=show_source)

        if filter_str:
            # Check mnemonic line (index 1 if source shown, else 0)
            mnemonic_line = rendered[1] if show_source and len(rendered) > 1 else rendered[0]
            if filter_str not in mnemonic_line.lower():
                continue

        print()
        print('\n'.join(rendered))
        count += 1

    print(f'\n# {count} constructors rendered', file=sys.stderr)

if __name__ == '__main__':
    main()
