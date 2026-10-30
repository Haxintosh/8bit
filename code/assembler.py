#!/usr/bin/env python3
"""
AI DISCLOSURE: This file was vibecoded...
Ran out of time to actually learn how to make it myself
But you don't have to use an assembler to write functional code

Simple 8-bit Computer Assembler.

Supports:
  - 8080-style mnemonics mapped to the custom 8-bit architecture.
  - Labels, constants (EQU), and memory origins (ORG).
  - Data directives: DB, DW, DS.
  - Output formats: Binary (.bin), Intel HEX (.hex), Logisim/Digital Hex (.logisim.hex), and Listing (.lst).
"""

import argparse
import os
import re
import sys

from control_words import REGISTER_CODES, REGISTER_PAIR_CODES

# Normalize register pair aliases (e.g. B -> BC, D -> DE, H -> HL)
RP_ALIASES = {
    "B": "BC",
    "BC": "BC",
    "D": "DE",
    "DE": "DE",
    "H": "HL",
    "HL": "HL",
    "SP": "SP",
}

# Instruction Opcode Lookup Tables
REGISTER_INSTRUCTIONS = {
    # Mnemonic -> Base Opcode (lower 3 bits = register code)
    "ADD": 0x80,
    "ADC": 0x88,
    "SUB": 0x90,
    "SBB": 0x98,
    "ANA": 0xA0,
    "XRA": 0xA8,
    "ORA": 0xB0,
    "CMP": 0xB8,
}

IMM8_INSTRUCTIONS = {
    # Mnemonic -> Opcode
    "ADI": 0xC6,
    "ACI": 0xCE,
    "SUI": 0xD6,
    "SBI": 0xDE,
    "ANI": 0xE6,
    "XRI": 0xEE,
    "ORI": 0xF6,
    "CPI": 0xFE,
}

IMM16_INSTRUCTIONS = {
    # Mnemonic -> Opcode
    "SHLD": 0x22,
    "LHLD": 0x2A,
    "STA": 0x32,
    "LDA": 0x3A,
    "JMP": 0xC3,
    "JNZ": 0xC2,
    "JZ": 0xCA,
    "JNC": 0xD2,
    "JC": 0xDA,
    "JPO": 0xE2,
    "JPE": 0xEA,
    "JP": 0xF2,
    "JM": 0xFA,
    "CALL": 0xCD,
    "CNZ": 0xC4,
    "CZ": 0xCC,
    "CNC": 0xD4,
    "CC": 0xDC,
    "CPO": 0xE4,
    "CPE": 0xEC,
    "CP": 0xF4,
    "CM": 0xFC,
}

RP_INSTRUCTIONS = {
    # Mnemonic -> {RP: Opcode}
    "STAX": {"BC": 0x02, "DE": 0x12},
    "LDAX": {"BC": 0x0A, "DE": 0x1A},
    "DAD": {"BC": 0x09, "DE": 0x19, "HL": 0x29},
    "PUSH": {"BC": 0xC5, "DE": 0xD5, "HL": 0xE5},
    "POP": {"BC": 0xC1, "DE": 0xD1, "HL": 0xE1},
}

SIMPLE_INSTRUCTIONS = {
    "NOP": 0x00,
    "RLC": 0x07,
    "RRC": 0x0F,
    "RAL": 0x17,
    "RAR": 0x1F,
    "CMA": 0x2F,
    "HLT": 0x76,
    "OUTA": 0x6D,
    "OUT": 0x6D,
    "RET": 0xC9,
    "RNZ": 0xC0,
    "RZ": 0xC8,
    "RNC": 0xD0,
    "RC": 0xD8,
    "RPO": 0xE0,
    "RPE": 0xE8,
    "RP": 0xF0,
    "RM": 0xF8,
}


class AssemblerError(Exception):
    def __init__(self, line_num: int, line_text: str, message: str):
        super().__init__(f"Line {line_num}: {message}\n  -> {line_text.strip()}")
        self.line_num = line_num
        self.line_text = line_text
        self.message = message


def parse_number(token: str, symbols: dict[str, int]) -> int:
    """Parses a number literal, symbol, or simple arithmetic expression."""
    token = token.strip()
    if not token:
        raise ValueError("Empty expression")

    # High / Low byte functions
    if token.upper().startswith("HIGH(") and token.endswith(")"):
        inner = token[5:-1].strip()
        return (parse_number(inner, symbols) >> 8) & 0xFF
    if token.upper().startswith("LOW(") and token.endswith(")"):
        inner = token[4:-1].strip()
        return parse_number(inner, symbols) & 0xFF
    if token.startswith(">"):
        return (parse_number(token[1:], symbols) >> 8) & 0xFF
    if token.startswith("<"):
        return parse_number(token[1:], symbols) & 0xFF

    # Character literal: 'A'
    if (token.startswith("'") and token.endswith("'")) and len(token) == 3:
        return ord(token[1])

    # Hexadecimal formats: 0x12, $12, 12H, 12h
    if token.startswith("0x") or token.startswith("0X"):
        return int(token[2:], 16)
    if token.startswith("$"):
        return int(token[1:], 16)
    if (token.endswith("H") or token.endswith("h")) and re.match(
        r"^[0-9A-Fa-f]+[Hh]$", token
    ):
        return int(token[:-1], 16)

    # Binary formats: 0b1010, %1010, 1010B, 1010b
    if token.startswith("0b") or token.startswith("0B"):
        return int(token[2:], 2)
    if token.startswith("%"):
        return int(token[1:], 2)
    if (token.endswith("B") or token.endswith("b")) and re.match(r"^[01]+[Bb]$", token):
        return int(token[:-1], 2)

    # Decimal
    if re.match(r"^-?[0-9]+$", token):
        return int(token, 10)

    # Symbol lookup
    if token in symbols:
        return symbols[token]

    # Handle simple arithmetic: A + B, A - B
    for op in ["+", "-", "*", "/", "&", "|", "^"]:
        if op in token:
            parts = token.split(op, 1)
            left = parse_number(parts[0], symbols)
            right = parse_number(parts[1], symbols)
            if op == "+":
                return left + right
            elif op == "-":
                return left - right
            elif op == "*":
                return left * right
            elif op == "/":
                return left // right
            elif op == "&":
                return left & right
            elif op == "|":
                return left | right
            elif op == "^":
                return left ^ right

    raise ValueError(f"Unknown symbol or number format: '{token}'")


def split_operands(op_str: str) -> list[str]:
    """Splits comma-separated operands while respecting quotes."""
    operands = []
    current = []
    in_quote = False
    quote_char = ""

    for char in op_str:
        if char in ('"', "'"):
            if not in_quote:
                in_quote = True
                quote_char = char
            elif quote_char == char:
                in_quote = False
            current.append(char)
        elif char == "," and not in_quote:
            operands.append("".join(current).strip())
            current = []
        else:
            current.append(char)

    if current:
        operands.append("".join(current).strip())
    return [op for op in operands if op]


class Assembler:
    def __init__(self):
        self.symbols: dict[str, int] = {}
        self.lines: list[tuple[int, str]] = []

    def assemble(
        self, source_text: str
    ) -> tuple[dict[int, int], int, list[tuple[int, int, list[int], str]]]:
        """Performs two-pass assembly.

        Returns:
          - memory: dict[address, byte]
          - start_address: minimum address defined
          - listing_info: list of (line_num, address, bytes_emitted, line_text)
        """
        self.symbols.clear()
        raw_lines = source_text.splitlines()
        self.lines = [(i + 1, line) for i, line in enumerate(raw_lines)]

        # --- PASS 1: Symbol Definition and Address Tracking ---
        pc = 0x0000
        for line_num, line in self.lines:
            cleaned = self._clean_line(line)
            if not cleaned:
                continue

            # Check for EQU directive: LABEL EQU VALUE
            equ_match = re.match(
                r"^([A-Za-z_][A-Za-z0-9_]*)\s+EQU\s+(.+)$", cleaned, re.IGNORECASE
            )
            if equ_match:
                label_name, expr = equ_match.groups()
                try:
                    val = parse_number(expr, self.symbols)
                    self.symbols[label_name] = val
                except ValueError as e:
                    raise AssemblerError(line_num, line, f"Cannot evaluate EQU: {e}")
                continue

            # Check for label at start of line
            label_match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):(.*)$", cleaned)
            if label_match:
                label_name, rest = label_match.groups()
                self.symbols[label_name] = pc
                cleaned = rest.strip()
                if not cleaned:
                    continue

            # Process Directives or Instructions to advance PC
            parts = cleaned.split(maxsplit=1)
            mnemonic = parts[0].upper()
            operands_str = parts[1] if len(parts) > 1 else ""

            if mnemonic == "ORG":
                try:
                    pc = parse_number(operands_str, self.symbols) & 0xFFFF
                except ValueError as e:
                    raise AssemblerError(line_num, line, f"Invalid ORG address: {e}")
            elif mnemonic == "DB":
                ops = split_operands(operands_str)
                for op in ops:
                    if (op.startswith('"') and op.endswith('"')) or (
                        op.startswith("'") and op.endswith("'")
                    ):
                        pc += len(op[1:-1])
                    else:
                        pc += 1
            elif mnemonic == "DW":
                ops = split_operands(operands_str)
                pc += len(ops) * 2
            elif mnemonic == "DS":
                ops = split_operands(operands_str)
                count = parse_number(ops[0], self.symbols) if ops else 1
                pc += count
            elif mnemonic == "END":
                break
            else:
                inst_len = self._estimate_instruction_len(
                    mnemonic, operands_str, line_num, line
                )
                pc += inst_len

        # --- PASS 2: Code Generation ---
        memory: dict[int, int] = {}
        listing_info = []
        pc = 0x0000
        start_addr = None

        for line_num, line in self.lines:
            cleaned = self._clean_line(line)
            if not cleaned:
                listing_info.append((line_num, pc, [], line))
                continue

            # Check for EQU
            equ_match = re.match(
                r"^([A-Za-z_][A-Za-z0-9_]*)\s+EQU\s+(.+)$", cleaned, re.IGNORECASE
            )
            if equ_match:
                listing_info.append(
                    (line_num, self.symbols[equ_match.group(1)], [], line)
                )
                continue

            # Check for label
            label_match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):(.*)$", cleaned)
            if label_match:
                cleaned = label_match.group(2).strip()
                if not cleaned:
                    listing_info.append((line_num, pc, [], line))
                    continue

            parts = cleaned.split(maxsplit=1)
            mnemonic = parts[0].upper()
            operands_str = parts[1] if len(parts) > 1 else ""

            if mnemonic == "ORG":
                pc = parse_number(operands_str, self.symbols) & 0xFFFF
                if start_addr is None:
                    start_addr = pc
                listing_info.append((line_num, pc, [], line))
            elif mnemonic == "DB":
                emitted = []
                ops = split_operands(operands_str)
                for op in ops:
                    if (op.startswith('"') and op.endswith('"')) or (
                        op.startswith("'") and op.endswith("'")
                    ):
                        for ch in op[1:-1]:
                            b = ord(ch) & 0xFF
                            memory[pc] = b
                            emitted.append(b)
                            pc = (pc + 1) & 0xFFFF
                    else:
                        try:
                            b = parse_number(op, self.symbols) & 0xFF
                        except ValueError as e:
                            raise AssemblerError(
                                line_num, line, f"Invalid DB expression '{op}': {e}"
                            )
                        memory[pc] = b
                        emitted.append(b)
                        pc = (pc + 1) & 0xFFFF
                listing_info.append((line_num, pc - len(emitted), emitted, line))
            elif mnemonic == "DW":
                emitted = []
                ops = split_operands(operands_str)
                for op in ops:
                    try:
                        w = parse_number(op, self.symbols) & 0xFFFF
                    except ValueError as e:
                        raise AssemblerError(
                            line_num, line, f"Invalid DW expression '{op}': {e}"
                        )
                    low_b = w & 0xFF
                    high_b = (w >> 8) & 0xFF
                    memory[pc] = low_b
                    memory[(pc + 1) & 0xFFFF] = high_b
                    emitted.extend([low_b, high_b])
                    pc = (pc + 2) & 0xFFFF
                listing_info.append((line_num, pc - len(emitted), emitted, line))
            elif mnemonic == "DS":
                ops = split_operands(operands_str)
                count = parse_number(ops[0], self.symbols)
                fill_val = (
                    parse_number(ops[1], self.symbols) & 0xFF if len(ops) > 1 else 0x00
                )
                emitted = []
                for _ in range(count):
                    memory[pc] = fill_val
                    emitted.append(fill_val)
                    pc = (pc + 1) & 0xFFFF
                listing_info.append((line_num, pc - count, emitted, line))
            elif mnemonic == "END":
                listing_info.append((line_num, pc, [], line))
                break
            else:
                emitted = self._encode_instruction(
                    mnemonic, operands_str, line_num, line
                )
                if start_addr is None:
                    start_addr = pc
                for b in emitted:
                    memory[pc] = b
                    pc = (pc + 1) & 0xFFFF
                listing_info.append((line_num, pc - len(emitted), emitted, line))

        if start_addr is None:
            start_addr = 0x0000

        return memory, start_addr, listing_info

    def _clean_line(self, line: str) -> str:
        """Removes comments and extraneous whitespace."""
        # Strip comments: ; // #
        line = re.sub(r"(;.*|//.*|#.*)$", "", line)
        return line.strip()

    def _estimate_instruction_len(
        self, mnemonic: str, operands_str: str, line_num: int, line: str
    ) -> int:
        """Estimates the byte length of an instruction during Pass 1."""
        if (
            mnemonic in SIMPLE_INSTRUCTIONS
            or mnemonic in REGISTER_INSTRUCTIONS
            or mnemonic in RP_INSTRUCTIONS
        ):
            return 1
        if mnemonic == "MOV":
            return 1
        if mnemonic in IMM8_INSTRUCTIONS or mnemonic == "MVI":
            return 2
        if mnemonic in IMM16_INSTRUCTIONS or mnemonic == "LXI":
            return 3
        raise AssemblerError(line_num, line, f"Unknown mnemonic: '{mnemonic}'")

    def _encode_instruction(
        self, mnemonic: str, operands_str: str, line_num: int, line: str
    ) -> list[int]:
        """Encodes an instruction into machine code bytes during Pass 2."""
        ops = split_operands(operands_str)

        # 1. Simple 1-byte Instructions
        if mnemonic in SIMPLE_INSTRUCTIONS:
            if mnemonic in ("OUTA", "OUT") and ops:
                if len(ops) == 1 and ops[0].upper() == "A":
                    pass
                else:
                    raise AssemblerError(
                        line_num,
                        line,
                        f"{mnemonic} only supports operand 'A' or no operand, got '{operands_str}'",
                    )
            elif ops:
                raise AssemblerError(
                    line_num,
                    line,
                    f"{mnemonic} does not take operands, got '{operands_str}'",
                )
            return [
                0x6D if mnemonic in ("OUTA", "OUT") else SIMPLE_INSTRUCTIONS[mnemonic]
            ]

        # 2. Register ALU Operations (ADD r, SUB r, etc.)
        if mnemonic in REGISTER_INSTRUCTIONS:
            if len(ops) != 1:
                raise AssemblerError(
                    line_num,
                    line,
                    f"{mnemonic} expects 1 register operand, got {len(ops)}",
                )
            reg = ops[0].upper()
            if reg not in REGISTER_CODES:
                raise AssemblerError(
                    line_num,
                    line,
                    f"Invalid register '{reg}'. Expected B,C,D,E,H,L,M,A",
                )
            return [REGISTER_INSTRUCTIONS[mnemonic] | REGISTER_CODES[reg]]

        # 3. MOV d, s
        if mnemonic == "MOV":
            if len(ops) != 2:
                raise AssemblerError(
                    line_num,
                    line,
                    f"MOV expects 2 operands (dest, src), got {len(ops)}",
                )
            dest = ops[0].upper()
            src = ops[1].upper()
            if dest not in REGISTER_CODES or src not in REGISTER_CODES:
                raise AssemblerError(
                    line_num, line, f"Invalid registers for MOV '{dest}, {src}'"
                )
            if dest == "M" and src == "M":
                # MOV M, M is HLT (0x76)
                return [0x76]
            return [0x40 | (REGISTER_CODES[dest] << 3) | REGISTER_CODES[src]]

        # 4. MVI r, data8
        if mnemonic == "MVI":
            if len(ops) != 2:
                raise AssemblerError(
                    line_num,
                    line,
                    f"MVI expects 2 operands (reg, data), got {len(ops)}",
                )
            reg = ops[0].upper()
            if reg not in REGISTER_CODES:
                raise AssemblerError(
                    line_num, line, f"Invalid register '{reg}' for MVI"
                )
            try:
                val = parse_number(ops[1], self.symbols) & 0xFF
            except ValueError as e:
                raise AssemblerError(
                    line_num, line, f"Invalid 8-bit immediate value '{ops[1]}': {e}"
                )
            opcode = 0x06 | (REGISTER_CODES[reg] << 3)
            return [opcode, val]

        # 5. Immediate 8-bit ALU Operations (ADI, SUI, etc.)
        if mnemonic in IMM8_INSTRUCTIONS:
            if len(ops) != 1:
                raise AssemblerError(
                    line_num,
                    line,
                    f"{mnemonic} expects 1 immediate operand, got {len(ops)}",
                )
            try:
                val = parse_number(ops[0], self.symbols) & 0xFF
            except ValueError as e:
                raise AssemblerError(
                    line_num, line, f"Invalid immediate value '{ops[0]}': {e}"
                )
            return [IMM8_INSTRUCTIONS[mnemonic], val]

        # 6. Register Pair Instructions (STAX, LDAX, DAD)
        if mnemonic in RP_INSTRUCTIONS:
            if len(ops) != 1:
                raise AssemblerError(
                    line_num,
                    line,
                    f"{mnemonic} expects 1 register pair operand, got {len(ops)}",
                )
            rp = RP_ALIASES.get(ops[0].upper())
            if rp not in RP_INSTRUCTIONS[mnemonic]:
                valid_rps = ", ".join(RP_INSTRUCTIONS[mnemonic].keys())
                raise AssemblerError(
                    line_num,
                    line,
                    f"Invalid register pair '{ops[0]}' for {mnemonic}. Valid: {valid_rps}",
                )
            return [RP_INSTRUCTIONS[mnemonic][rp]]

        # 7. LXI rp, data16
        if mnemonic == "LXI":
            if len(ops) != 2:
                raise AssemblerError(
                    line_num,
                    line,
                    f"LXI expects 2 operands (rp, data16), got {len(ops)}",
                )
            rp = RP_ALIASES.get(ops[0].upper())
            if rp not in REGISTER_PAIR_CODES:
                raise AssemblerError(
                    line_num,
                    line,
                    f"Invalid register pair '{ops[0]}' for LXI. Valid: BC, DE, HL, SP",
                )
            try:
                addr16 = parse_number(ops[1], self.symbols) & 0xFFFF
            except ValueError as e:
                raise AssemblerError(
                    line_num, line, f"Invalid 16-bit address/immediate '{ops[1]}': {e}"
                )
            opcode = 0x01 | (REGISTER_PAIR_CODES[rp] << 4)
            low_b = addr16 & 0xFF
            high_b = (addr16 >> 8) & 0xFF
            return [opcode, low_b, high_b]

        # 8. 16-bit Address Operations (STA, LDA, JMP, J<cond>)
        if mnemonic in IMM16_INSTRUCTIONS:
            if len(ops) != 1:
                raise AssemblerError(
                    line_num,
                    line,
                    f"{mnemonic} expects 1 address operand, got {len(ops)}",
                )
            try:
                addr16 = parse_number(ops[0], self.symbols) & 0xFFFF
            except ValueError as e:
                raise AssemblerError(
                    line_num, line, f"Invalid 16-bit address '{ops[0]}': {e}"
                )
            opcode = IMM16_INSTRUCTIONS[mnemonic]
            low_b = addr16 & 0xFF
            high_b = (addr16 >> 8) & 0xFF
            return [opcode, low_b, high_b]

        raise AssemblerError(line_num, line, f"Unrecognized instruction '{mnemonic}'")


def write_intel_hex(filepath: str, memory: dict[int, int], bytes_per_record: int = 16):
    """Generates standard Intel HEX format (.hex)."""
    with open(filepath, "w") as f:
        if not memory:
            f.write(":00000001FF\n")
            return

        sorted_addrs = sorted(memory.keys())
        # Break into contiguous chunks
        chunks: list[list[int]] = []
        current_chunk: list[int] = []

        for addr in sorted_addrs:
            if not current_chunk:
                current_chunk.append(addr)
            elif (
                addr == current_chunk[-1] + 1 and len(current_chunk) < bytes_per_record
            ):
                current_chunk.append(addr)
            else:
                chunks.append(current_chunk)
                current_chunk = [addr]
        if current_chunk:
            chunks.append(current_chunk)

        for chunk in chunks:
            addr = chunk[0]
            count = len(chunk)
            data_bytes = [memory[a] for a in chunk]
            rec_type = 0x00  # Data Record

            # Checksum = 2's complement of (Count + AddrHigh + AddrLow + RecType + Data)
            checksum = (
                count + (addr >> 8) + (addr & 0xFF) + rec_type + sum(data_bytes)
            ) & 0xFF
            checksum = (~checksum + 1) & 0xFF

            data_str = "".join(f"{b:02X}" for b in data_bytes)
            f.write(f":{count:02X}{addr:04X}{rec_type:02X}{data_str}{checksum:02X}\n")

        # End of File Record
        f.write(":00000001FF\n")


def write_logisim_hex(
    filepath: str,
    memory: dict[int, int],
    start_addr: int,
    max_addr: int = None,
    bytes_per_line: int = 16,
):
    """Generates Logisim / Digital compatible 'v2.0 raw' hex format."""
    if max_addr is None:
        max_addr = max(memory.keys()) if memory else start_addr
    with open(filepath, "w") as f:
        f.write("v2.0 raw\n")
        data = [memory.get(a, 0x00) for a in range(start_addr, max_addr + 1)]
        for i in range(0, len(data), bytes_per_line):
            chunk = data[i : i + bytes_per_line]
            hex_str = " ".join(f"{b:02x}" for b in chunk)
            f.write(hex_str + "\n")


def write_binary(
    filepath: str, memory: dict[int, int], start_addr: int, fixed_size: int = None
):
    """Generates raw binary image (.bin)."""
    if not memory:
        data = bytearray(fixed_size if fixed_size else 0)
    elif fixed_size:
        data = bytearray(fixed_size)
        for addr, b in memory.items():
            if 0 <= addr < fixed_size:
                data[addr] = b
    else:
        min_addr = min(memory.keys())
        max_addr = max(memory.keys())
        data = bytearray(max_addr - min_addr + 1)
        for addr, b in memory.items():
            data[addr - min_addr] = b

    with open(filepath, "wb") as f:
        f.write(data)


def write_listing(
    filepath: str,
    listing_info: list[tuple[int, int, list[int], str]],
    symbols: dict[str, int],
):
    """Generates a detailed assembly listing (.lst)."""
    with open(filepath, "w") as f:
        f.write("=" * 80 + "\n")
        f.write("8-BIT COMPUTER ASSEMBLY LISTING\n")
        f.write("=" * 80 + "\n\n")

        for line_num, addr, emitted, line in listing_info:
            if emitted:
                hex_bytes = " ".join(f"{b:02X}" for b in emitted)
                f.write(
                    f"{line_num:4d}  {addr:04X}:  {hex_bytes:<12}  {line.rstrip()}\n"
                )
            else:
                f.write(f"{line_num:4d}  {addr:04X}:  {'':<12}  {line.rstrip()}\n")

        f.write("\n" + "=" * 80 + "\n")
        f.write("SYMBOL TABLE\n")
        f.write("=" * 80 + "\n")
        for sym, val in sorted(symbols.items()):
            f.write(f"  {sym:<20} = 0x{val:04X} ({val})\n")


def main():
    parser = argparse.ArgumentParser(
        description="Assemble 8-bit CPU assembly source into .bin and .hex files."
    )
    parser.add_argument("input", help="Input assembly source file (.asm)")
    parser.add_argument("-o", "--out", help="Output binary file (.bin)")
    parser.add_argument("--hex", help="Output Intel HEX file (.hex)")
    parser.add_argument("--logisim", help="Output Logisim/Digital raw hex file (.hex)")
    parser.add_argument("--lst", help="Output listing file (.lst)")
    parser.add_argument(
        "--fixed-size",
        type=int,
        default=None,
        help="Fixed binary ROM size in bytes (e.g. 65536 or 32768)",
    )

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: File '{args.input}' not found.", file=sys.stderr)
        sys.exit(1)

    with open(args.input, "r") as f:
        source_text = f.read()

    base_name = os.path.splitext(args.input)[0]
    out_bin = args.out or f"{base_name}.bin"
    out_hex = args.hex or f"{base_name}.hex"
    out_logisim = args.logisim or f"{base_name}.logisim.hex"
    out_lst = args.lst or f"{base_name}.lst"

    asm = Assembler()
    try:
        memory, start_addr, listing_info = asm.assemble(source_text)
    except AssemblerError as e:
        print(f"Assembly Error:\n{e}", file=sys.stderr)
        sys.exit(1)

    # Write files
    write_binary(out_bin, memory, start_addr, args.fixed_size)
    write_intel_hex(out_hex, memory)
    write_logisim_hex(out_logisim, memory, start_addr)
    write_listing(out_lst, listing_info, asm.symbols)

    total_bytes = len(memory)
    min_addr = min(memory.keys()) if memory else 0
    max_addr = max(memory.keys()) if memory else 0
    print(f"Assembly completed successfully!")
    print(
        f"  Emitted: {total_bytes} bytes (Address range: 0x{min_addr:04X} - 0x{max_addr:04X})"
    )
    print(f"  Binary:  {out_bin}")
    print(f"  Intel Hex: {out_hex}")
    print(f"  Logisim:   {out_logisim}")
    print(f"  Listing:   {out_lst}")


if __name__ == "__main__":
    main()
