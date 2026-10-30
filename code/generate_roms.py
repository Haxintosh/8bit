import os
import sys

from control_words import (
    CONTROL_WORDS,
    REGISTER_IN_MUX,
    REGISTER_OUT_MUX,
    REGISTER_PAIR_OUT_MUX,
)
from ucode import INSTRUCTION_LIST, FlagCondition, build_opcode_map


def pack_control_words(ctrl: dict[str, int]) -> tuple[int, int, int, int]:
    # ROM 0
    hlt = ctrl.get("HLT", 0) & 1

    reg_out_code = 0
    active_reg_out = []
    for sig, code in REGISTER_OUT_MUX.items():
        if ctrl.get(sig, 0) == 1:
            reg_out_code = code
            active_reg_out.append(sig)
    if len(active_reg_out) > 1:
        raise ValueError(f"Bus contention on data out MUX: {active_reg_out}")

    pair_out_code = 0
    active_pair_out = []
    for sig, code in REGISTER_PAIR_OUT_MUX.items():
        if ctrl.get(sig, 0) == 1:
            pair_out_code = code
            active_pair_out.append(sig)
    if len(active_pair_out) > 1:
        raise ValueError(f"Bus contention on register pair out MUX: {active_pair_out}")

    if ctrl.get("PCO", 0) == 1 and ctrl.get("PCE", 0) == 1:
        raise ValueError("PCO & PCE HIGH at same time")

    byte0 = (hlt & 1) | ((reg_out_code & 0x0F) << 1) | ((pair_out_code & 0x07) << 5)

    # ROM 1
    reg_in_code = 0
    active_reg_in = []
    for sig, code in REGISTER_IN_MUX.items():
        if ctrl.get(sig, 0) == 1:
            reg_in_code = code
            active_reg_in.append(sig)
    if len(active_reg_in) > 1:
        raise ValueError(f"Bus contention on register in MUX: {active_reg_in}")

    inh = ctrl.get("INH", 0) & 1
    deh = ctrl.get("DEH", 0) & 1
    ins = ctrl.get("INS", 0) & 1
    des = ctrl.get("DES", 0) & 1

    byte1 = (reg_in_code & 0x0F) | (inh << 4) | (deh << 5) | (ins << 6) | (des << 7)

    # ROM 2
    al0 = ctrl.get("AL0", 0) & 1
    al1 = ctrl.get("AL1", 0) & 1
    al2 = ctrl.get("AL2", 0) & 1
    al3 = ctrl.get("AL3", 0) & 1
    alm = ctrl.get("ALM", 0) & 1
    fri = ctrl.get("FRI", 0) & 1
    jpl = ctrl.get("JPL", 0) & 1
    jph = ctrl.get("JPH", 0) & 1

    al_code = al0 | (al1 << 1) | (al2 << 2) | (al3 << 3)
    byte2 = (al_code & 0x0F) | (alm << 4) | (fri << 5) | (jpl << 6) | (jph << 7)

    # ROM3
    pce = ctrl.get("PCE", 0) & 1
    scr = ctrl.get("SCR", 0) & 1
    ri = ctrl.get("RI", 0) & 1
    alc = ctrl.get("ALC", 0) & 1
    inm = ctrl.get("INM", 0) & 1

    byte3 = (
        (pce & 1)
        | ((scr & 1) << 1)
        | ((ri & 1) << 2)
        | ((alc & 1) << 3)
        | ((inm & 1) << 4)
        | ((scr & 1) << 5)
    )

    return byte0, byte1, byte2, byte3


def write_logisim_hex(filepath: str, data: bytearray, bytes_per_line: int = 16):
    """Writes a bytearray to Logisim / Digital compatible 'v2.0 raw' hex format."""
    with open(filepath, "w") as f:
        f.write("v2.0 raw\n")
        for i in range(0, len(data), bytes_per_line):
            chunk = data[i : i + bytes_per_line]
            hex_str = " ".join(f"{b:02x}" for b in chunk)
            f.write(hex_str + "\n")


def generate_roms(output_dir: str = "outputs"):
    os.makedirs(output_dir, exist_ok=True)
    opcode_map = build_opcode_map()

    ROM_SIZE = 65536  # 64 KB (A0 - A15)
    roms = [bytearray(ROM_SIZE) for _ in range(4)]

    print(f"Building ROMs for {len(opcode_map)} defined opcodes...")

    # A0-A7: Opcode (0 - 255)
    # A8-A11: Step (0 - 15)
    # A12-A15: Flags (0 - 15: bit0=VF, bit1=NF, bit2=CF, bit3=ZF)
    for opcode in range(256):
        inst_info = opcode_map.get(opcode)

        for step in range(16):
            for flags_val in range(16):
                addr = (flags_val << 12) | (step << 8) | opcode

                if inst_info is not None:
                    inst, variant = inst_info
                    ctrl = inst.resolve_step(variant, step, flags_val)
                else:
                    ctrl = CONTROL_WORDS.copy()
                    ctrl["SCR"] = 1

                b0, b1, b2, b3 = pack_control_words(ctrl)
                roms[0][addr] = b0
                roms[1][addr] = b1
                roms[2][addr] = b2
                roms[3][addr] = b3

    for rom_idx in range(4):
        bin_path = os.path.join(output_dir, f"rom{rom_idx}.bin")
        hex_path = os.path.join(output_dir, f"rom{rom_idx}.hex")

        with open(bin_path, "wb") as f:
            f.write(roms[rom_idx])

        write_logisim_hex(hex_path, roms[rom_idx])
        print(
            f"  Generated ROM {rom_idx}: {bin_path} ({len(roms[rom_idx])} bytes), {hex_path}"
        )


if __name__ == "__main__":
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "outputs"
    generate_roms(out_dir)
