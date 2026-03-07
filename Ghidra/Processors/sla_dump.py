#!/usr/bin/env python3
"""
sla_dump.py — Human-readable dump of SLEIGH PCode from a compiled .sla.xml file.

Renders each top-level instruction constructor as:

  # src/file.sinc:1234
  # encoding: F6 /2  [vexMode=0]
  NOT rm8
    rm8 = INT_NEGATE rm8

Usage:
    python3 sla_dump.py <target> [options]

Arguments:
    <target>   A .sla.xml file, a processor directory, or a directory to search
               recursively for .sla.xml files.

               Examples:
                 python3 sla_dump.py x86/data/languages/x86.sla.xml
                 python3 sla_dump.py x86/
                 python3 sla_dump.py .          # all processors under current dir

Options:
    --filter SUBSTR   Only print constructors whose mnemonic contains SUBSTR
    --source N        Only print constructors from source file index N
    --no-build        Hide BUILD ops (sub-operand expansions)
    --no-source       Hide source file/line annotations
    --no-encoding     Hide byte encoding comments
    --subtables       Also dump non-instruction subtable constructors
"""

import sys
import os
import glob
import xml.etree.ElementTree as ET

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
        # id -> subsym_id  operand_sym bodies
        self.operand_subsym = {}
        self.operand_index = {}   # id -> build_index (the index= attr on operand_sym)
        # id -> name  for subtable_syms
        self.subtable_names = {}
        # register space: offset -> name  (built from varnodes in register space)
        self.reg_by_offset = {}
        # context fields: name -> (low_bit, high_bit)
        self.context_fields = {}

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
                name = self.names.get(sid, 'userop_%s' % index)
                self.userop_names[int(index)] = name

            elif tag == 'operand_sym':
                subsym = elem.get('subsym')
                if subsym:
                    self.operand_subsym[sid] = subsym
                idx = elem.get('index')
                if idx is not None:
                    self.operand_index[sid] = int(idx)

            elif tag == 'context_sym':
                low = elem.get('low')
                high = elem.get('high')
                name = self.names.get(sid)
                if name and low is not None and high is not None:
                    self.context_fields[name] = (int(low), int(high))

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
                return '%s[%d:%d]' % (n, offset_int - off, size_int)
        return 'reg[0x%x:%d]' % (offset_int, size_int)

    def subtable_name(self, sid):
        return self.subtable_names.get(sid, self.names.get(sid, 'subtable_%s' % sid))

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
        _tmp_map[key] = 'TMP%d' % _tmp_counter[0]
    return _tmp_map[key]

def render_varnode(vn, sym, operand_names, show_size=True):
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
        op_name = operand_names[op_idx] if op_idx < len(operand_names) else 'op%d' % op_idx
        space = '@%s.space' % op_name
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
        op_name = operand_names[op_idx] if op_idx < len(operand_names) else 'op%d' % op_idx
        size_str = '%s.size' % op_name

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
                return '%s:%s' % (name, size_str)
            return name
        else:
            off_str = hex(off_val)
    elif off_el.tag == 'const_handle':
        op_idx = int(off_el.get('val', '0'))
        op_name = operand_names[op_idx] if op_idx < len(operand_names) else 'op%d' % op_idx
        # This is the operand itself (space=handle.space, offset=handle.offset)
        if show_size and size_str:
            return '%s:%s' % (op_name, size_str)
        return op_name
    elif off_el.tag == 'const_relative':
        return 'label[%s]' % off_el.get('val', '?')
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
        off_str = '?off(%s)' % off_el.tag

    # Fallback for ram/other spaces
    if off_str is None:
        off_str = '?'
    if show_size and size_str:
        return '[%s:%s:%s]' % (space, off_str, size_str)
    return '[%s:%s]' % (space, off_str)

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

def render_op(op_el, sym, display_names, build_names,
              userop_index_map, indent='  ', show_build=True):
    """Render a single <op_tpl> to a list of output lines."""
    code = op_el.get('code', '?')
    children = list(op_el)  # first child is output varnode (or <null/>)

    if not children:
        return ['%s%s' % (indent, code)]

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
            name = build_names.get(build_idx, 'op%d' % build_idx)
            return ['%s# BUILD %s' % (indent, name)]
        return ['%s# BUILD ?' % indent]

    # --- LABEL: internal branch target ---
    if code == 'LABEL':
        if inputs:
            lv = inputs[0].find('const_real')
            return ['%slabel[%s]:' % (indent, lv.get('val', '?') if lv is not None else '?')]
        return ['%slabel:' % indent]

    # --- BRANCH / CBRANCH / BRANCHIND ---
    if code == 'BRANCH':
        dest = rv(inputs[0]) if inputs else '?'
        return ['%sgoto %s' % (indent, dest)]
    if code == 'CBRANCH':
        dest = rv(inputs[0]) if len(inputs) > 0 else '?'
        cond = rv(inputs[1]) if len(inputs) > 1 else '?'
        return ['%sif (%s) goto %s' % (indent, cond, dest)]
    if code == 'BRANCHIND':
        dest = rv(inputs[0]) if inputs else '?'
        return ['%sgoto [%s]' % (indent, dest)]

    # --- CALL / CALLIND / RETURN ---
    if code == 'CALL':
        dest = rv(inputs[0]) if inputs else '?'
        return ['%scall %s' % (indent, dest)]
    if code == 'CALLIND':
        dest = rv(inputs[0]) if inputs else '?'
        return ['%scall [%s]' % (indent, dest)]
    if code == 'RETURN':
        dest = rv(inputs[0]) if inputs else '?'
        return ['%sreturn %s' % (indent, dest)]

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
                    userop_name = sym.userop_names.get(idx, 'userop_%d' % idx)
        args = ', '.join(rv(i) for i in inputs[1:])
        out_str = rv(out_el) if out_el.tag != 'null' else None
        if out_str:
            return ['%s%s = %s(%s)' % (indent, out_str, userop_name, args)]
        return ['%s%s(%s)' % (indent, userop_name, args)]

    # --- STORE ---
    if code == 'STORE':
        # inputs: [space_id, ptr_addr, value]
        ptr  = rv(inputs[1]) if len(inputs) > 1 else '?'
        val  = rv(inputs[2]) if len(inputs) > 2 else '?'
        return ['%s*%s = %s' % (indent, ptr, val)]

    # --- LOAD ---
    if code == 'LOAD':
        # inputs: [space_id, ptr_addr]
        out_str = rv(out_el) if out_el.tag != 'null' else '?tmp'
        ptr = rv(inputs[1]) if len(inputs) > 1 else '?'
        return ['%s%s = *%s' % (indent, out_str, ptr)]

    # --- Standard unary / binary ---
    out_str = rv(out_el) if out_el.tag != 'null' else None

    if code in UNARY_OPS and inputs:
        rhs = '%s %s' % (code, rv(inputs[0]))
    elif code in BINARY_OPS and len(inputs) >= 2:
        rhs = '%s %s, %s' % (code, rv(inputs[0]), rv(inputs[1]))
    else:
        # Fallback: show all inputs
        args_str = ', '.join(rv(i) for i in inputs)
        rhs = '%s %s' % (code, args_str)

    if out_str:
        return ['%s%s = %s' % (indent, out_str, rhs)]
    return ['%s%s' % (indent, rhs)]

# ---------------------------------------------------------------------------
# Pattern decoding
# ---------------------------------------------------------------------------

def _decode_mask_val_bytes(mask_int, val_int, off, nonzero):
    """
    Decode a mask_word element into a list of (byte_offset, mask_byte, val_byte).
    The mask/val are packed 4 bytes big-endian; only 'nonzero' bytes are significant.
    """
    result = []
    for i in range(nonzero):
        m = (mask_int >> ((3 - i) * 8)) & 0xff
        v = (val_int >> ((3 - i) * 8)) & 0xff
        if m != 0:
            result.append((off + i, m, v))
    return result


def _collect_pat_bytes(pat_el):
    """
    Collect all (byte_offset, mask_byte, val_byte) tuples from an instruct_pat
    or context_pat element (which contains pat_block > mask_word children).

    A pat_block can have multiple mask_word elements; each covers 4 bytes
    sequentially starting at the block's byte offset.  'nonzero' is the total
    number of significant bytes across all mask_words in the block.
    """
    result = []
    for pb in pat_el.findall('pat_block'):
        off = int(pb.get('off', '0'))
        nonzero = int(pb.get('nonzero', '0'))
        remaining = nonzero
        cur_off = off
        for mw in pb.findall('mask_word'):
            chunk = min(remaining, 4)
            mask = int(mw.get('mask', '0'), 0)
            val  = int(mw.get('val',  '0'), 0)
            result.extend(_decode_mask_val_bytes(mask, val, cur_off, chunk))
            cur_off += 4
            remaining -= chunk
            if remaining <= 0:
                break
    return result


def _format_instr_bytes(instr_bytes):
    """
    Format instruction byte constraints as a human-readable encoding string.

    Each element is (byte_offset, mask_byte, val_byte).
    - Exact byte (mask=0xFF): shown as hex, e.g. "F6"
    - ModRM reg field only (mask=0x38): shown as "/N"
    - ModRM mod+rm constrained, reg free: shown as "/r"
    - Other partial: shown as "byte[N]&MM=VV"
    """
    if not instr_bytes:
        return None

    # Group by byte offset, consolidate masks
    by_off = {}
    for off, m, v in instr_bytes:
        if off not in by_off:
            by_off[off] = (m, v)
        else:
            pm, pv = by_off[off]
            by_off[off] = (pm | m, pv | (v & m))

    parts = []
    for off in sorted(by_off):
        m, v = by_off[off]
        if m == 0xff:
            parts.append('%02X' % v)
        else:
            # ModRM reg field (bits 5:3 = mask 0x38), mod+rm unconstrained
            if (m & 0x38) == 0x38 and (m & 0xc7) == 0:
                reg_val = (v >> 3) & 7
                parts.append('/%d' % reg_val)
            # ModRM: mod+rm constrained, reg field free -> /r
            elif (m & 0xc7) == 0xc7 and (m & 0x38) == 0:
                parts.append('/r')
            # ModRM: full reg field + some mod/rm bits
            elif (m & 0x38) == 0x38:
                reg_val = (v >> 3) & 7
                modrm_m = m & 0xc7
                modrm_v = v & 0xc7
                if modrm_m == 0xc0 and modrm_v == 0xc0:
                    # mod=11 (register mode), rm varies -> register-only form
                    parts.append('/%d(reg)' % reg_val)
                elif (~m & 0xff) == 0x07:
                    # Only low 3 bits free: opcode byte with embedded register
                    # e.g. 0x50+rd (PUSH), 0x58+rd (POP), 0xB8+rd (MOV reg,imm)
                    parts.append('%02X+r' % v)
                else:
                    parts.append('byte[%d]&%02X=%02X' % (off, m, v))
            else:
                # Generic partial
                parts.append('byte[%d]&%02X=%02X' % (off, m, v))
    return ' '.join(parts) if parts else None


def _decode_context_constraints(ctx_bytes, context_fields):
    """
    Decode context byte constraints to field=value pairs.
    Returns dict: field_name -> value (int), only for fully-constrained fields.
    """
    # Build a map: context_bit_num -> constrained_value (0 or 1)
    constrained_bits = {}
    for byte_off, m, v in ctx_bytes:
        for bit_in_byte in range(8):
            if (m >> bit_in_byte) & 1:
                # bit_in_byte 7 = MSB of byte = context bit byte_off*8 + 0
                ctx_bit = byte_off * 8 + (7 - bit_in_byte)
                constrained_bits[ctx_bit] = (v >> bit_in_byte) & 1

    # Map constrained bits back to fields
    field_vals = {}
    for name, (low, high) in context_fields.items():
        field_val = 0
        all_present = True
        for b in range(low, high + 1):
            if b not in constrained_bits:
                all_present = False
                break
            field_val |= constrained_bits[b] << (b - low)
        if all_present:
            field_vals[name] = field_val

    return field_vals


# Context fields that are uninteresting when =0 (they're "not active" flags)
_CONTEXT_NOISE_ZERO = {
    'vexMode', 'rexprefix', 'rexWprefix', 'rexRprefix', 'rexXprefix', 'rexBprefix',
    'rexWRXBprefix', 'prefix_66', 'prefix_f2', 'prefix_f3',
    'repneprefx', 'repprefx', 'mandover', 'segover', 'highseg',
    'xacquireprefx', 'xreleaseprefx', 'lockprefx',
    'evexMode', 'instrPhase', 'suffix3D',
}


def _format_context(ctx_constraints):
    """
    Format context constraints as a readable string.
    Suppresses fields that are trivially zero (no special prefix active).
    """
    parts = []
    for name, val in sorted(ctx_constraints.items()):
        # Skip noise: fields that just mean "no prefix" when zero
        if val == 0 and name in _CONTEXT_NOISE_ZERO:
            continue
        parts.append('%s=%d' % (name, val))
    return parts


def build_pattern_map(subtable_elem, context_fields):
    """
    Walk the <decision> tree of a subtable_sym and build a dict:
      ctor_ordinal (int) -> (instr_encoding_str | None, context_parts list)

    The <pair id=N> in the decision tree refers to the Nth constructor (0-indexed)
    in document order within the subtable_sym.
    """
    result = {}
    dec = subtable_elem.find('decision')
    if dec is None:
        return result

    for pair in dec.findall('.//pair'):
        ctor_idx = int(pair.get('id', '-1'))
        if ctor_idx < 0:
            continue

        children = list(pair)
        if not children:
            continue

        pat_el = children[0]
        instr_bytes = []
        ctx_bytes = []

        if pat_el.tag == 'instruct_pat':
            instr_bytes = _collect_pat_bytes(pat_el)
        elif pat_el.tag == 'context_pat':
            ctx_bytes = _collect_pat_bytes(pat_el)
        elif pat_el.tag == 'combine_pat':
            for child in pat_el:
                if child.tag == 'instruct_pat':
                    instr_bytes = _collect_pat_bytes(child)
                elif child.tag == 'context_pat':
                    ctx_bytes = _collect_pat_bytes(child)

        enc_str = _format_instr_bytes(instr_bytes)
        ctx_map = _decode_context_constraints(ctx_bytes, context_fields)
        ctx_parts = _format_context(ctx_map)

        result[ctor_idx] = (enc_str, ctx_parts)

    return result

# ---------------------------------------------------------------------------
# Constructor rendering
# ---------------------------------------------------------------------------

def get_operand_names(ctor_el, sym):
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
        name = sym.names.get(oid, 'op%d' % len(display_names))
        display_names.append(name)
        build_idx = sym.operand_index.get(oid)
        if build_idx is not None:
            build_names[build_idx] = name
    return display_names, build_names

def render_constructor(ctor_el, sym, source_names, pattern_info,
                       show_build=True, show_source=True, show_encoding=True):
    """Render one constructor to a list of lines."""
    lines = []

    display_names, build_names = get_operand_names(ctor_el, sym)
    source_idx = ctor_el.get('source', '0')
    line_no = ctor_el.get('line', '?')
    src_file = source_names.get(source_idx, 'source_%s' % source_idx)

    # Build mnemonic string using opprint id= which refers to build_index
    parts = []
    for child in ctor_el:
        if child.tag == 'print':
            parts.append(child.get('piece', ''))
        elif child.tag == 'opprint':
            idx = int(child.get('id', '0'))
            name = build_names.get(idx, 'op%d' % idx)
            parts.append(name)
    mnemonic = ''.join(parts)

    if show_source:
        lines.append('# %s:%s' % (src_file, line_no))

    if show_encoding and pattern_info is not None:
        enc_str, ctx_parts = pattern_info
        if enc_str or ctx_parts:
            enc_comment = '# encoding:'
            if enc_str:
                enc_comment += ' ' + enc_str
            if ctx_parts:
                enc_comment += '  [' + ', '.join(ctx_parts) + ']'
            lines.append(enc_comment)

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
        lines.append('  # exports handle: %s' % _describe_handle(hc, sym, display_names))

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
        if el.tag == 'const_spaceid': return el.get('space', '?')
        if el.tag == 'const_real': return hex_str(el.get('val', '0'))
        if el.tag == 'const_handle':
            op_idx = int(el.get('val', '0'))
            op = display_names[op_idx] if op_idx < len(display_names) else 'op%d' % op_idx
            return '%s.s%s' % (op, el.get('s', '?'))
        return el.tag
    if len(hc) >= 7:
        space = _rv(hc[3])
        off   = _rv(hc[4])
        size  = _rv(hc[5])
        return '(%s, %s, %s)' % (space, off, size)
    return '(incomplete)'

# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def find_sla_xml_files(target):
    """
    Given a path that is either:
      - a .sla.xml file  -> return [that file]
      - a directory      -> return all .sla.xml files found recursively within it
    """
    if os.path.isfile(target):
        return [target]
    if os.path.isdir(target):
        found = sorted(glob.glob(os.path.join(target, '**', '*.sla.xml'), recursive=True))
        if not found:
            print('No .sla.xml files found under %s' % target, file=sys.stderr)
        return found
    print('Error: %r is not a file or directory' % target, file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Per-file processing
# ---------------------------------------------------------------------------

def process_file(sla_xml, args):
    print('=== %s ===' % sla_xml, file=sys.stderr)

    tree = ET.parse(sla_xml)
    root = tree.getroot()

    # Build source file index
    source_names = {}
    for sf in root.findall('sourcefiles/sourcefile'):
        source_names[sf.get('index', '0')] = sf.get('name', '?')

    sym = SymbolTable()
    sym.build(root)

    sym_table = root.find('symbol_table')

    filter_str = args.filter.lower() if args.filter else None
    show_build    = not args.no_build
    show_source   = not args.no_source
    show_encoding = not args.no_encoding

    # parent="0x0" = instruction table; others = subtables
    target_parents = None if args.subtables else {'0x0'}

    # Build pattern maps for each subtable that we'll visit
    # Maps: subtable_sym_id -> {ctor_ordinal -> (enc_str, ctx_parts)}
    pattern_maps = {}
    if show_encoding:
        for elem in sym_table:
            if elem.tag == 'subtable_sym':
                sid = elem.get('id', '')
                if target_parents is None or sid in target_parents:
                    pattern_maps[sid] = build_pattern_map(elem, sym.context_fields)

    count = 0
    for elem in sym_table:
        if elem.tag != 'subtable_sym':
            continue
        sid = elem.get('id', '')
        if target_parents is not None and sid not in target_parents:
            continue

        pat_map = pattern_maps.get(sid, {})

        for ctor_ordinal, ctor in enumerate(elem.findall('constructor')):
            src_idx = ctor.get('source', '0')
            if args.source is not None and int(src_idx) != args.source:
                continue

            pattern_info = pat_map.get(ctor_ordinal) if show_encoding else None

            rendered = render_constructor(ctor, sym, source_names, pattern_info,
                                         show_build=show_build,
                                         show_source=show_source,
                                         show_encoding=show_encoding)

            if filter_str:
                # Find the mnemonic line (first non-comment line)
                mnemonic_line = ''
                for line in rendered:
                    if not line.startswith('#'):
                        mnemonic_line = line
                        break
                if filter_str not in mnemonic_line.lower():
                    continue

            print()
            print('\n'.join(rendered))
            count += 1

    print('# %d constructors rendered from %s' % (count, os.path.basename(sla_xml)),
          file=sys.stderr)
    return count

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description='Dump SLEIGH PCode from .sla.xml files in human-readable form')
    parser.add_argument('target', nargs='?', default='.',
                        help='A .sla.xml file, a processor directory, or a parent '
                             'directory to search recursively (default: current directory)')
    parser.add_argument('--filter', '-f', metavar='SUBSTR',
                        help='Only show constructors whose mnemonic contains SUBSTR '
                             '(case-insensitive)')
    parser.add_argument('--source', '-s', metavar='N', type=int, default=None,
                        help='Only show constructors from source file index N')
    parser.add_argument('--no-build', action='store_true',
                        help='Hide BUILD ops')
    parser.add_argument('--no-source', action='store_true',
                        help='Hide source file/line annotations')
    parser.add_argument('--no-encoding', action='store_true',
                        help='Hide byte encoding comments')
    parser.add_argument('--subtables', action='store_true',
                        help='Also dump non-instruction subtable constructors')
    args = parser.parse_args()

    files = find_sla_xml_files(args.target)
    if not files:
        sys.exit(1)

    total = 0
    for f in files:
        total += process_file(f, args)

    if len(files) > 1:
        print('\n# Total: %d constructors across %d files' % (total, len(files)),
              file=sys.stderr)

if __name__ == '__main__':
    main()
