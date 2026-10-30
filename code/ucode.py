import json

from control_words import (
    CARRY_CODES,
    CONTROL_WORDS,
    REGISTER_CODES,
    REGISTER_PAIR_CODES,
)

REGISTERS = REGISTER_CODES.keys()
RP_PAIRS = REGISTER_PAIR_CODES.keys()


class FlagCondition:
    VF_MASK = 1 << 0  # 0b0001
    NF_MASK = 1 << 1  # 0b0010
    CF_MASK = 1 << 2  # 0b0100
    ZF_MASK = 1 << 3  # 0b1000

    @classmethod
    def matches(cls, condition_name: str, flag_val: int) -> bool:
        vf = (flag_val & cls.VF_MASK) != 0
        nf = (flag_val & cls.NF_MASK) != 0
        cf = (flag_val & cls.CF_MASK) != 0
        zf = (flag_val & cls.ZF_MASK) != 0

        cond = condition_name.upper()
        if cond in ("C", "JC", "RC", "CC"):
            return cf
        elif cond in ("NC", "JNC", "RNC", "CNC"):
            return not cf
        elif cond in ("Z", "JZ", "RZ", "CZ"):
            return zf
        elif cond in ("NZ", "JNZ", "RNZ", "CNZ"):
            return not zf
        elif cond in ("N", "JM", "RM", "CM", "M", "S"):
            return nf
        elif cond in ("P", "JP", "RP", "CP", "NS"):
            return not nf
        elif cond in ("V", "PE", "JPE", "RPE", "CPE"):
            return vf
        elif cond in ("NV", "PO", "JPO", "RPO", "CPO"):
            return not vf
        elif cond in ("DEFAULT", "ALWAYS", "NONE", "N"):
            return True
        else:
            return False


class Instruction:
    def __init__(self, mnemonic: str, operand_type: str, bytes: int):
        self.mnemonic = mnemonic
        self.operand_type = operand_type
        self.bytes = bytes
        self.ucode: dict[str, dict[int, dict]] = {}
        self.cond: dict[str, dict[int, dict[str, dict]]] = {}
        self.branches: dict[str, dict[str, dict[int, dict]]] = {}

        INSTRUCTION_LIST[mnemonic] = self

    def set_cond(self, variant: str, step: int, condition: str, overlay: dict):
        self.cond.setdefault(variant, {}).setdefault(step, {})[condition] = overlay

    def set_branch(self, variant: str, condition: str, steps: dict[int, dict]):
        self.branches.setdefault(variant, {})[condition] = steps

    def get_step_control_words(
        self, variant: str, step: int, flag_val: int = 0
    ) -> dict:
        if variant in self.branches:
            for cond_name, branch_steps in self.branches[variant].items():
                if FlagCondition.matches(cond_name, flag_val):
                    if step in branch_steps:
                        return branch_steps[step].copy()

        v_dict = self.ucode.get(variant, {})
        base_ctrl = v_dict.get(step, {}).copy()

        if variant in self.cond and step in self.cond[variant]:
            for cond_name, overlay in self.cond[variant][step].items():
                if FlagCondition.matches(cond_name, flag_val):
                    for sig, val in overlay.items():
                        base_ctrl[sig] = val

        return base_ctrl

    resolve_step = get_step_control_words

    def __str__(self):
        txt = f"{self.mnemonic} - {self.bytes} Bytes ({self.operand_type}):\n"
        for k, v in self.ucode.items():
            ucodes = ""
            for i in sorted([step for step in v.keys() if step != 256]):
                j = v[i]
                if isinstance(j, dict):
                    l = " ".join([s for s, w in j.items() if w == 1])
                    cond_info = ""
                    if k in self.cond and i in self.cond[k]:
                        cond_parts = []
                        for c_name, c_overlay in self.cond[k][i].items():
                            c_sigs = " ".join(
                                [s for s, w in c_overlay.items() if w == 1]
                            )
                            cond_parts.append(f"[{c_name}: {c_sigs}]")
                        cond_info = " " + " ".join(cond_parts)
                    ucodes += f"\t{i} {l}{cond_info}\n"

            if k in self.branches:
                for c_name, b_steps in self.branches[k].items():
                    ucodes += f"\tBranch if {c_name}:\n"
                    for b_i in sorted(b_steps.keys()):
                        b_l = " ".join([s for s, w in b_steps[b_i].items() if w == 1])
                        ucodes += f"\t  {b_i} {b_l}\n"

            opcode_str = f"{v[256]:08b}" if 256 in v else "Unassigned"
            txt += f"    {k} - {opcode_str} :\n{ucodes}\n"
        return txt


INSTRUCTION_LIST: dict[str, Instruction] = {}

# NOP - No operation
NOP = Instruction("NOP", "N", 1)
NOP.ucode.setdefault("N", {})
NOP_UCODE = NOP.ucode["N"]
NOP_UCODE[256] = 0b00000000

NOP_UCODE[0] = CONTROL_WORDS.copy()
NOP_UCODE[0]["PCO"] = 1
NOP_UCODE[0]["RO"] = 1
NOP_UCODE[0]["II"] = 1

NOP_UCODE[1] = CONTROL_WORDS.copy()
NOP_UCODE[1]["PCE"] = 1

NOP_UCODE[2] = CONTROL_WORDS.copy()
NOP_UCODE[2]["SCR"] = 1

# LXI - Load extended immediate (rp = data16, little-endian: low byte first, high byte second)
LXI = Instruction("LXI", "rp, data", 3)
for i in RP_PAIRS:
    LXI.ucode.setdefault(i, {})
    LXI_UCODE = LXI.ucode[i]
    LXI_UCODE[256] = int(f"00{REGISTER_PAIR_CODES[i]:02b}0001", 2)

    if i == "SP":
        CTRL_L_I = "SPLI"
        CTRL_H_I = "SPHI"
    elif i == "HL":
        CTRL_L_I = "LI"
        CTRL_H_I = "HI"
    else:
        # Low register is 2nd char (C/E/L), High register is 1st char (B/D/H)
        CTRL_L_I = i[1:] + "I"
        CTRL_H_I = i[:1] + "I"

    LXI_UCODE[0] = CONTROL_WORDS.copy()
    LXI_UCODE[0]["PCO"] = 1
    LXI_UCODE[0]["RO"] = 1
    LXI_UCODE[0]["II"] = 1

    LXI_UCODE[1] = CONTROL_WORDS.copy()
    LXI_UCODE[1]["PCE"] = 1

    LXI_UCODE[2] = CONTROL_WORDS.copy()
    LXI_UCODE[2]["PCO"] = 1
    LXI_UCODE[2]["RO"] = 1
    LXI_UCODE[2][CTRL_L_I] = 1

    LXI_UCODE[3] = CONTROL_WORDS.copy()
    LXI_UCODE[3]["PCE"] = 1

    LXI_UCODE[4] = CONTROL_WORDS.copy()
    LXI_UCODE[4]["PCO"] = 1
    LXI_UCODE[4]["RO"] = 1
    LXI_UCODE[4][CTRL_H_I] = 1

    LXI_UCODE[5] = CONTROL_WORDS.copy()
    LXI_UCODE[5]["PCE"] = 1

    LXI_UCODE[6] = CONTROL_WORDS.copy()
    LXI_UCODE[6]["SCR"] = 1

# STAX - Store accumulator indirect
STAX = Instruction("STAX", "rp", 1)
for i in ["BC", "DE"]:
    STAX.ucode.setdefault(i, {})
    STAX_UCODE = STAX.ucode[i]
    STAX_UCODE[256] = int(f"00{REGISTER_PAIR_CODES[i]:02b}0010", 2)
    CTRL_OUT_PAIR = i + "O"

    STAX_UCODE[0] = CONTROL_WORDS.copy()
    STAX_UCODE[0]["PCO"] = 1
    STAX_UCODE[0]["RO"] = 1
    STAX_UCODE[0]["II"] = 1

    STAX_UCODE[1] = CONTROL_WORDS.copy()
    STAX_UCODE[1][CTRL_OUT_PAIR] = 1
    STAX_UCODE[1]["AO"] = 1
    STAX_UCODE[1]["RI"] = 1
    STAX_UCODE[1]["PCE"] = 1

    STAX_UCODE[2] = CONTROL_WORDS.copy()
    STAX_UCODE[2]["SCR"] = 1

# MVI - Move immediate
MVI = Instruction("MVI", "r, data", 2)
for i in REGISTERS:
    MVI.ucode.setdefault(i, {})
    MVI_UCODE = MVI.ucode[i]
    MVI_UCODE[256] = int(f"00{REGISTER_CODES[i]:03b}110", 2)

    MVI_UCODE[0] = CONTROL_WORDS.copy()
    MVI_UCODE[0]["PCO"] = 1
    MVI_UCODE[0]["RO"] = 1
    MVI_UCODE[0]["II"] = 1

    if i != "M":
        CTRL_IN_REGISTER = i + "I"
        MVI_UCODE[1] = CONTROL_WORDS.copy()
        MVI_UCODE[1]["PCE"] = 1

        MVI_UCODE[2] = CONTROL_WORDS.copy()
        MVI_UCODE[2]["PCO"] = 1
        MVI_UCODE[2]["RO"] = 1
        MVI_UCODE[2][CTRL_IN_REGISTER] = 1

        MVI_UCODE[3] = CONTROL_WORDS.copy()
        MVI_UCODE[3]["PCE"] = 1

        MVI_UCODE[4] = CONTROL_WORDS.copy()
        MVI_UCODE[4]["SCR"] = 1
    else:
        MVI_UCODE[1] = CONTROL_WORDS.copy()
        MVI_UCODE[1]["PCE"] = 1

        MVI_UCODE[2] = CONTROL_WORDS.copy()
        MVI_UCODE[2]["PCO"] = 1
        MVI_UCODE[2]["RO"] = 1
        MVI_UCODE[2]["TI"] = 1

        MVI_UCODE[3] = CONTROL_WORDS.copy()
        MVI_UCODE[3]["PCE"] = 1

        MVI_UCODE[4] = CONTROL_WORDS.copy()
        MVI_UCODE[4]["HLO"] = 1
        MVI_UCODE[4]["TO"] = 1
        MVI_UCODE[4]["RI"] = 1

        MVI_UCODE[5] = CONTROL_WORDS.copy()
        MVI_UCODE[5]["SCR"] = 1

# DAD - Double add (HL = HL + RP)
DAD = Instruction("DAD", "rp", 1)
for i in RP_PAIRS:
    if i == "SP":
        continue
    DAD.ucode.setdefault(i, {})
    DAD_UCODE = DAD.ucode[i]
    DAD_UCODE[256] = int(f"00{REGISTER_PAIR_CODES[i]:02b}1001", 2)

    CTRL_T_L_O = i[1:] + "O"  # Low register (C/E/L)
    CTRL_T_H_O = i[:1] + "O"  # High register (B/D/H)

    DAD_UCODE[0] = CONTROL_WORDS.copy()
    DAD_UCODE[0]["PCO"] = 1
    DAD_UCODE[0]["RO"] = 1
    DAD_UCODE[0]["II"] = 1

    DAD_UCODE[1] = CONTROL_WORDS.copy()
    DAD_UCODE[1][CTRL_T_L_O] = 1
    DAD_UCODE[1]["AI"] = 1
    DAD_UCODE[1]["PCE"] = 1

    DAD_UCODE[2] = CONTROL_WORDS.copy()
    DAD_UCODE[2]["LO"] = 1
    DAD_UCODE[2]["ALI"] = 1

    DAD_UCODE[3] = CONTROL_WORDS.copy()
    DAD_UCODE[3]["ALO"] = 1
    DAD_UCODE[3]["AL0"] = 1
    DAD_UCODE[3]["AL3"] = 1
    DAD_UCODE[3]["FRI"] = 1
    DAD_UCODE[3]["LI"] = 1

    DAD_UCODE[4] = CONTROL_WORDS.copy()
    DAD_UCODE[4][CTRL_T_H_O] = 1
    DAD_UCODE[4]["AI"] = 1

    DAD_UCODE[5] = CONTROL_WORDS.copy()
    DAD_UCODE[5]["HO"] = 1
    DAD_UCODE[5]["ALI"] = 1

    DAD_UCODE[6] = CONTROL_WORDS.copy()
    DAD_UCODE[6]["ALO"] = 1
    DAD_UCODE[6]["AL0"] = 1
    DAD_UCODE[6]["AL3"] = 1
    DAD_UCODE[6]["FRI"] = 1
    DAD_UCODE[6]["HI"] = 1
    DAD.set_cond(i, 6, "C", {"ALC": 1})

    DAD_UCODE[7] = CONTROL_WORDS.copy()
    DAD_UCODE[7]["SCR"] = 1

# LDAX - Load A indirect
LDAX = Instruction("LDAX", "rp", 1)
for i in ["BC", "DE"]:
    LDAX.ucode.setdefault(i, {})
    LDAX_UCODE = LDAX.ucode[i]
    LDAX_UCODE[256] = int(f"00{REGISTER_PAIR_CODES[i]:02b}1010", 2)
    CTRL_OUT_PAIR = i + "O"

    LDAX_UCODE[0] = CONTROL_WORDS.copy()
    LDAX_UCODE[0]["PCO"] = 1
    LDAX_UCODE[0]["RO"] = 1
    LDAX_UCODE[0]["II"] = 1

    LDAX_UCODE[1] = CONTROL_WORDS.copy()
    LDAX_UCODE[1][CTRL_OUT_PAIR] = 1
    LDAX_UCODE[1]["AI"] = 1
    LDAX_UCODE[1]["RO"] = 1
    LDAX_UCODE[1]["PCE"] = 1

    LDAX_UCODE[2] = CONTROL_WORDS.copy()
    LDAX_UCODE[2]["SCR"] = 1

# RLC - Rotate left circular
RLC = Instruction("RLC", "N", 1)
RLC.ucode.setdefault("N", {})
RLC_UCODE = RLC.ucode["N"]
RLC_UCODE[256] = int("00000111", 2)

RLC_UCODE[0] = CONTROL_WORDS.copy()
RLC_UCODE[0]["PCO"] = 1
RLC_UCODE[0]["RO"] = 1
RLC_UCODE[0]["II"] = 1

RLC_UCODE[1] = CONTROL_WORDS.copy()
RLC_UCODE[1]["AL2"] = 1  # A + A
RLC_UCODE[1]["AL3"] = 1
RLC_UCODE[1]["FRI"] = 1  # Latch bit 7 of A into CF
RLC_UCODE[1]["PCE"] = 1

RLC_UCODE[2] = CONTROL_WORDS.copy()
RLC_UCODE[2]["AL2"] = 1  # A + A
RLC_UCODE[2]["AL3"] = 1
RLC_UCODE[2]["ALO"] = 1
RLC_UCODE[2]["AI"] = 1
RLC.set_cond("N", 2, "C", {"ALC": 1})

RLC_UCODE[3] = CONTROL_WORDS.copy()
RLC_UCODE[3]["SCR"] = 1

# RRC - Rotate right circular
RRC = Instruction("RRC", "N", 1)
RRC.ucode.setdefault("N", {})
RRC_UCODE = RRC.ucode["N"]
RRC_UCODE[256] = int("00001111", 2)

RRC_UCODE[0] = CONTROL_WORDS.copy()
RRC_UCODE[0]["PCO"] = 1
RRC_UCODE[0]["RO"] = 1
RRC_UCODE[0]["II"] = 1

RRC_UCODE[1] = CONTROL_WORDS.copy()
RRC_UCODE[1]["RRC"] = 1
RRC_UCODE[1]["AI"] = 1
RRC_UCODE[1]["FRI"] = 1
RRC_UCODE[1]["PCE"] = 1

RRC_UCODE[2] = CONTROL_WORDS.copy()
RRC_UCODE[2]["SCR"] = 1

# RAL - Rotate A Left through carry
RAL = Instruction("RAL", "N", 1)
RAL.ucode.setdefault("N", {})
RAL_UCODE = RAL.ucode["N"]
RAL_UCODE[256] = int("00010111", 2)

RAL_UCODE[0] = CONTROL_WORDS.copy()
RAL_UCODE[0]["PCO"] = 1
RAL_UCODE[0]["RO"] = 1
RAL_UCODE[0]["II"] = 1

RAL_UCODE[1] = CONTROL_WORDS.copy()
RAL_UCODE[1]["AL2"] = 1  # A + A
RAL_UCODE[1]["AL3"] = 1
RAL_UCODE[1]["FRI"] = 1
RAL_UCODE[1]["PCE"] = 1
RAL.set_cond("N", 1, "C", {"ALC": 1})

RAL_UCODE[2] = CONTROL_WORDS.copy()
RAL_UCODE[2]["ALO"] = 1
RAL_UCODE[2]["AI"] = 1

RAL_UCODE[3] = CONTROL_WORDS.copy()
RAL_UCODE[3]["SCR"] = 1

# RAR - Rotate A right through carry
RAR = Instruction("RAR", "N", 1)
RAR.ucode.setdefault("N", {})
RAR_UCODE = RAR.ucode["N"]
RAR_UCODE[256] = int("00011111", 2)

RAR_UCODE[0] = CONTROL_WORDS.copy()
RAR_UCODE[0]["PCO"] = 1
RAR_UCODE[0]["RO"] = 1
RAR_UCODE[0]["II"] = 1

RAR_UCODE[1] = CONTROL_WORDS.copy()
RAR_UCODE[1]["RAR"] = 1
RAR_UCODE[1]["FRI"] = 1
RAR_UCODE[1]["AI"] = 1
RAR_UCODE[1]["PCE"] = 1
RAR.set_cond("N", 1, "C", {"ALC": 1})

RAR_UCODE[2] = CONTROL_WORDS.copy()
RAR_UCODE[2]["SCR"] = 1

# SHLD - Store HL into [addr16]
SHLD = Instruction("SHLD", "addr16", 3)
SHLD.ucode.setdefault("addr16", {})
SHLD_UCODE = SHLD.ucode["addr16"]
SHLD_UCODE[256] = int("00100010", 2)

SHLD_UCODE[0] = CONTROL_WORDS.copy()
SHLD_UCODE[0]["PCO"] = 1
SHLD_UCODE[0]["RO"] = 1
SHLD_UCODE[0]["II"] = 1

SHLD_UCODE[1] = CONTROL_WORDS.copy()
SHLD_UCODE[1]["PCE"] = 1

SHLD_UCODE[2] = CONTROL_WORDS.copy()
SHLD_UCODE[2]["PCO"] = 1
SHLD_UCODE[2]["RO"] = 1
SHLD_UCODE[2]["MLI"] = 1

SHLD_UCODE[3] = CONTROL_WORDS.copy()
SHLD_UCODE[3]["PCE"] = 1

SHLD_UCODE[4] = CONTROL_WORDS.copy()
SHLD_UCODE[4]["PCO"] = 1
SHLD_UCODE[4]["RO"] = 1
SHLD_UCODE[4]["MHI"] = 1

SHLD_UCODE[5] = CONTROL_WORDS.copy()
SHLD_UCODE[5]["PCE"] = 1

SHLD_UCODE[6] = CONTROL_WORDS.copy()
SHLD_UCODE[6]["MO"] = 1
SHLD_UCODE[6]["LO"] = 1
SHLD_UCODE[6]["RI"] = 1

SHLD_UCODE[7] = CONTROL_WORDS.copy()
SHLD_UCODE[7]["INM"] = 1

SHLD_UCODE[8] = CONTROL_WORDS.copy()
SHLD_UCODE[8]["MO"] = 1
SHLD_UCODE[8]["HO"] = 1
SHLD_UCODE[8]["RI"] = 1

SHLD_UCODE[9] = CONTROL_WORDS.copy()
SHLD_UCODE[9]["SCR"] = 1

# LHLD - Load mem at addr16 into HL
LHLD = Instruction("LHLD", "addr16", 3)
LHLD.ucode.setdefault("addr16", {})
LHLD_UCODE = LHLD.ucode["addr16"]
LHLD_UCODE[256] = int("00101010", 2)

LHLD_UCODE[0] = CONTROL_WORDS.copy()
LHLD_UCODE[0]["PCO"] = 1
LHLD_UCODE[0]["RO"] = 1
LHLD_UCODE[0]["II"] = 1

LHLD_UCODE[1] = CONTROL_WORDS.copy()
LHLD_UCODE[1]["PCE"] = 1

LHLD_UCODE[2] = CONTROL_WORDS.copy()
LHLD_UCODE[2]["PCO"] = 1
LHLD_UCODE[2]["RO"] = 1
LHLD_UCODE[2]["MLI"] = 1

LHLD_UCODE[3] = CONTROL_WORDS.copy()
LHLD_UCODE[3]["PCE"] = 1

LHLD_UCODE[4] = CONTROL_WORDS.copy()
LHLD_UCODE[4]["PCO"] = 1
LHLD_UCODE[4]["RO"] = 1
LHLD_UCODE[4]["MHI"] = 1

LHLD_UCODE[5] = CONTROL_WORDS.copy()
LHLD_UCODE[5]["PCE"] = 1

LHLD_UCODE[6] = CONTROL_WORDS.copy()
LHLD_UCODE[6]["MO"] = 1
LHLD_UCODE[6]["RO"] = 1
LHLD_UCODE[6]["LI"] = 1

LHLD_UCODE[7] = CONTROL_WORDS.copy()
LHLD_UCODE[7]["INM"] = 1

LHLD_UCODE[8] = CONTROL_WORDS.copy()
LHLD_UCODE[8]["MO"] = 1
LHLD_UCODE[8]["RO"] = 1
LHLD_UCODE[8]["HI"] = 1

LHLD_UCODE[9] = CONTROL_WORDS.copy()
LHLD_UCODE[9]["SCR"] = 1

# CMA - Complement A
CMA = Instruction("CMA", "N", 1)
CMA.ucode.setdefault("N", {})
CMA_UCODE = CMA.ucode["N"]
CMA_UCODE[256] = int("00101111", 2)

CMA_UCODE[0] = CONTROL_WORDS.copy()
CMA_UCODE[0]["PCO"] = 1
CMA_UCODE[0]["RO"] = 1
CMA_UCODE[0]["II"] = 1

CMA_UCODE[1] = CONTROL_WORDS.copy()
CMA_UCODE[1]["ALM"] = 1  # set 181 to logic
CMA_UCODE[1]["ALO"] = 1
CMA_UCODE[1]["AI"] = 1
CMA_UCODE[1]["PCE"] = 1

CMA_UCODE[2] = CONTROL_WORDS.copy()
CMA_UCODE[2]["SCR"] = 1

# STA - Store A at addr16
STA = Instruction("STA", "addr16", 3)
STA.ucode.setdefault("addr16", {})
STA_UCODE = STA.ucode["addr16"]
STA_UCODE[256] = int("00110010", 2)

STA_UCODE[0] = CONTROL_WORDS.copy()
STA_UCODE[0]["PCO"] = 1
STA_UCODE[0]["RO"] = 1
STA_UCODE[0]["II"] = 1

STA_UCODE[1] = CONTROL_WORDS.copy()
STA_UCODE[1]["PCE"] = 1

STA_UCODE[2] = CONTROL_WORDS.copy()
STA_UCODE[2]["PCO"] = 1
STA_UCODE[2]["RO"] = 1
STA_UCODE[2]["MLI"] = 1

STA_UCODE[3] = CONTROL_WORDS.copy()
STA_UCODE[3]["PCE"] = 1

STA_UCODE[4] = CONTROL_WORDS.copy()
STA_UCODE[4]["PCO"] = 1
STA_UCODE[4]["RO"] = 1
STA_UCODE[4]["MHI"] = 1

STA_UCODE[5] = CONTROL_WORDS.copy()
STA_UCODE[5]["PCE"] = 1

STA_UCODE[6] = CONTROL_WORDS.copy()
STA_UCODE[6]["MO"] = 1
STA_UCODE[6]["AO"] = 1
STA_UCODE[6]["RI"] = 1

STA_UCODE[7] = CONTROL_WORDS.copy()
STA_UCODE[7]["SCR"] = 1

# LDA - Load A from ram
LDA = Instruction("LDA", "addr16", 3)
LDA.ucode.setdefault("addr16", {})
LDA_UCODE = LDA.ucode["addr16"]
LDA_UCODE[256] = int("00111010", 2)

LDA_UCODE[0] = CONTROL_WORDS.copy()
LDA_UCODE[0]["PCO"] = 1
LDA_UCODE[0]["RO"] = 1
LDA_UCODE[0]["II"] = 1

LDA_UCODE[1] = CONTROL_WORDS.copy()
LDA_UCODE[1]["PCE"] = 1

LDA_UCODE[2] = CONTROL_WORDS.copy()
LDA_UCODE[2]["PCO"] = 1
LDA_UCODE[2]["RO"] = 1
LDA_UCODE[2]["MLI"] = 1

LDA_UCODE[3] = CONTROL_WORDS.copy()
LDA_UCODE[3]["PCE"] = 1

LDA_UCODE[4] = CONTROL_WORDS.copy()
LDA_UCODE[4]["PCO"] = 1
LDA_UCODE[4]["RO"] = 1
LDA_UCODE[4]["MHI"] = 1

LDA_UCODE[5] = CONTROL_WORDS.copy()
LDA_UCODE[5]["PCE"] = 1

LDA_UCODE[6] = CONTROL_WORDS.copy()
LDA_UCODE[6]["MO"] = 1
LDA_UCODE[6]["RO"] = 1
LDA_UCODE[6]["AI"] = 1

LDA_UCODE[7] = CONTROL_WORDS.copy()
LDA_UCODE[7]["SCR"] = 1

# MOV - Move
MOV = Instruction("MOV", "d, s", 1)
for d in REGISTERS:
    for s in REGISTERS:
        if s == d:
            continue
        MOV.ucode.setdefault(d + s, {})
        MOV_UCODE = MOV.ucode[d + s]
        MOV_UCODE[256] = int(f"01{REGISTER_CODES[d]:03b}{REGISTER_CODES[s]:03b}", 2)

        MOV_UCODE[0] = CONTROL_WORDS.copy()
        MOV_UCODE[0]["PCO"] = 1
        MOV_UCODE[0]["RO"] = 1
        MOV_UCODE[0]["II"] = 1

        MOV_UCODE[1] = CONTROL_WORDS.copy()
        if s == "M":
            MOV_UCODE[1]["HLO"] = 1
            MOV_UCODE[1]["RO"] = 1
        else:
            MOV_UCODE[1][s + "O"] = 1

        if d == "M":
            MOV_UCODE[1]["HLO"] = 1
            MOV_UCODE[1]["RI"] = 1
        else:
            MOV_UCODE[1][d + "I"] = 1
        MOV_UCODE[1]["PCE"] = 1

        MOV_UCODE[2] = CONTROL_WORDS.copy()
        MOV_UCODE[2]["SCR"] = 1

# HLT - Halt
HLT = Instruction("HLT", "N", 1)
HLT.ucode.setdefault("N", {})
HLT_UCODE = HLT.ucode["N"]
HLT_UCODE[256] = int(f"01{REGISTER_CODES['M']:03b}{REGISTER_CODES['M']:03b}", 2)

HLT_UCODE[0] = CONTROL_WORDS.copy()
HLT_UCODE[0]["PCO"] = 1
HLT_UCODE[0]["RO"] = 1
HLT_UCODE[0]["II"] = 1

HLT_UCODE[1] = CONTROL_WORDS.copy()
HLT_UCODE[1]["HLT"] = 1
HLT_UCODE[1]["PCE"] = 1

HLT_UCODE[2] = CONTROL_WORDS.copy()
HLT_UCODE[2]["SCR"] = 1

# OUTA - Outputs A (this is more for like interop w/ sap1)
OUTA = Instruction("OUTA", "N", 1)
OUTA.ucode.setdefault("N", {})
OUTA_UCODE = OUTA.ucode["N"]
OUTA_UCODE[256] = int(f"01{REGISTER_CODES['H']:03b}{REGISTER_CODES['H']:03b}", 2)

OUTA_UCODE[0] = CONTROL_WORDS.copy()
OUTA_UCODE[0]["PCO"] = 1
OUTA_UCODE[0]["RO"] = 1
OUTA_UCODE[0]["II"] = 1

OUTA_UCODE[1] = CONTROL_WORDS.copy()
OUTA_UCODE[1]["AO"] = 1
OUTA_UCODE[1]["OI"] = 1
OUTA_UCODE[1]["PCE"] = 1

OUTA_UCODE[2] = CONTROL_WORDS.copy()
OUTA_UCODE[2]["SCR"] = 1

# ADD - Add
ADD = Instruction("ADD", "r", 1)
for i in REGISTERS:
    ADD.ucode.setdefault(i, {})
    ADD_UCODE = ADD.ucode[i]
    ADD_UCODE[256] = int(f"10000{REGISTER_CODES[i]:03b}", 2)

    ADD_UCODE[0] = CONTROL_WORDS.copy()
    ADD_UCODE[0]["PCO"] = 1
    ADD_UCODE[0]["RO"] = 1
    ADD_UCODE[0]["II"] = 1

    ADD_UCODE[1] = CONTROL_WORDS.copy()
    if i == "M":
        ADD_UCODE[1]["HLO"] = 1
        ADD_UCODE[1]["RO"] = 1
    else:
        ADD_UCODE[1][i + "O"] = 1
    ADD_UCODE[1]["ALI"] = 1
    ADD_UCODE[1]["PCE"] = 1

    ADD_UCODE[2] = CONTROL_WORDS.copy()
    ADD_UCODE[2]["AL0"] = 1
    ADD_UCODE[2]["AL3"] = 1
    ADD_UCODE[2]["ALO"] = 1
    ADD_UCODE[2]["AI"] = 1
    ADD_UCODE[2]["FRI"] = 1

    ADD_UCODE[3] = CONTROL_WORDS.copy()
    ADD_UCODE[3]["SCR"] = 1

# ADC - Add with carry
ADC = Instruction("ADC", "r", 1)
for i in REGISTERS:
    ADC.ucode.setdefault(i, {})
    ADC_UCODE = ADC.ucode[i]
    ADC_UCODE[256] = int(f"10001{REGISTER_CODES[i]:03b}", 2)

    ADC_UCODE[0] = CONTROL_WORDS.copy()
    ADC_UCODE[0]["PCO"] = 1
    ADC_UCODE[0]["RO"] = 1
    ADC_UCODE[0]["II"] = 1

    ADC_UCODE[1] = CONTROL_WORDS.copy()
    if i == "M":
        ADC_UCODE[1]["HLO"] = 1
        ADC_UCODE[1]["RO"] = 1
    else:
        ADC_UCODE[1][i + "O"] = 1
    ADC_UCODE[1]["ALI"] = 1
    ADC_UCODE[1]["PCE"] = 1

    ADC_UCODE[2] = CONTROL_WORDS.copy()
    ADC_UCODE[2]["AL0"] = 1
    ADC_UCODE[2]["AL3"] = 1
    ADC_UCODE[2]["ALO"] = 1
    ADC_UCODE[2]["AI"] = 1
    ADC_UCODE[2]["FRI"] = 1
    ADC.set_cond(i, 2, "C", {"ALC": 1})

    ADC_UCODE[3] = CONTROL_WORDS.copy()
    ADC_UCODE[3]["SCR"] = 1

# SUB - Subtract
SUB = Instruction("SUB", "r", 1)
for i in REGISTERS:
    SUB.ucode.setdefault(i, {})
    SUB_UCODE = SUB.ucode[i]
    SUB_UCODE[256] = int(f"10010{REGISTER_CODES[i]:03b}", 2)

    SUB_UCODE[0] = CONTROL_WORDS.copy()
    SUB_UCODE[0]["PCO"] = 1
    SUB_UCODE[0]["RO"] = 1
    SUB_UCODE[0]["II"] = 1

    SUB_UCODE[1] = CONTROL_WORDS.copy()
    if i == "M":
        SUB_UCODE[1]["HLO"] = 1
        SUB_UCODE[1]["RO"] = 1
    else:
        SUB_UCODE[1][i + "O"] = 1
    SUB_UCODE[1]["ALI"] = 1
    SUB_UCODE[1]["PCE"] = 1

    SUB_UCODE[2] = CONTROL_WORDS.copy()
    SUB_UCODE[2]["AL1"] = 1
    SUB_UCODE[2]["AL2"] = 1
    SUB_UCODE[2]["ALO"] = 1
    SUB_UCODE[2]["AI"] = 1
    SUB_UCODE[2]["FRI"] = 1

    SUB_UCODE[3] = CONTROL_WORDS.copy()
    SUB_UCODE[3]["SCR"] = 1

# SBB - Subtract with borrow
SBB = Instruction("SBB", "r", 1)
for i in REGISTERS:
    SBB.ucode.setdefault(i, {})
    SBB_UCODE = SBB.ucode[i]
    SBB_UCODE[256] = int(f"10011{REGISTER_CODES[i]:03b}", 2)

    SBB_UCODE[0] = CONTROL_WORDS.copy()
    SBB_UCODE[0]["PCO"] = 1
    SBB_UCODE[0]["RO"] = 1
    SBB_UCODE[0]["II"] = 1

    SBB_UCODE[1] = CONTROL_WORDS.copy()
    if i == "M":
        SBB_UCODE[1]["HLO"] = 1
        SBB_UCODE[1]["RO"] = 1
    else:
        SBB_UCODE[1][i + "O"] = 1
    SBB_UCODE[1]["ALI"] = 1
    SBB_UCODE[1]["PCE"] = 1

    SBB_UCODE[2] = CONTROL_WORDS.copy()
    SBB_UCODE[2]["AL1"] = 1
    SBB_UCODE[2]["AL2"] = 1
    SBB_UCODE[2]["ALO"] = 1
    SBB_UCODE[2]["AI"] = 1
    SBB_UCODE[2]["FRI"] = 1
    SBB.set_cond(i, 2, "C", {"ALC": 1})

    SBB_UCODE[3] = CONTROL_WORDS.copy()
    SBB_UCODE[3]["SCR"] = 1

# ANA - AND A
ANA = Instruction("ANA", "r", 1)
for i in REGISTERS:
    ANA.ucode.setdefault(i, {})
    ANA_UCODE = ANA.ucode[i]
    ANA_UCODE[256] = int(f"10100{REGISTER_CODES[i]:03b}", 2)

    ANA_UCODE[0] = CONTROL_WORDS.copy()
    ANA_UCODE[0]["PCO"] = 1
    ANA_UCODE[0]["RO"] = 1
    ANA_UCODE[0]["II"] = 1

    ANA_UCODE[1] = CONTROL_WORDS.copy()
    if i == "M":
        ANA_UCODE[1]["HLO"] = 1
        ANA_UCODE[1]["RO"] = 1
    else:
        ANA_UCODE[1][i + "O"] = 1
    ANA_UCODE[1]["ALI"] = 1
    ANA_UCODE[1]["PCE"] = 1

    ANA_UCODE[2] = CONTROL_WORDS.copy()
    ANA_UCODE[2]["ALM"] = 1
    ANA_UCODE[2]["AL0"] = 1
    ANA_UCODE[2]["AL1"] = 1
    ANA_UCODE[2]["AL3"] = 1
    ANA_UCODE[2]["ALO"] = 1
    ANA_UCODE[2]["AI"] = 1
    ANA_UCODE[2]["FRI"] = 1

    ANA_UCODE[3] = CONTROL_WORDS.copy()
    ANA_UCODE[3]["SCR"] = 1

# XRA - XOR A
XRA = Instruction("XRA", "r", 1)
for i in REGISTERS:
    XRA.ucode.setdefault(i, {})
    XRA_UCODE = XRA.ucode[i]
    XRA_UCODE[256] = int(f"10101{REGISTER_CODES[i]:03b}", 2)

    XRA_UCODE[0] = CONTROL_WORDS.copy()
    XRA_UCODE[0]["PCO"] = 1
    XRA_UCODE[0]["RO"] = 1
    XRA_UCODE[0]["II"] = 1

    XRA_UCODE[1] = CONTROL_WORDS.copy()
    if i == "M":
        XRA_UCODE[1]["HLO"] = 1
        XRA_UCODE[1]["RO"] = 1
    else:
        XRA_UCODE[1][i + "O"] = 1
    XRA_UCODE[1]["ALI"] = 1
    XRA_UCODE[1]["PCE"] = 1

    XRA_UCODE[2] = CONTROL_WORDS.copy()
    XRA_UCODE[2]["ALM"] = 1
    XRA_UCODE[2]["AL0"] = 1
    XRA_UCODE[2]["AL3"] = 1
    XRA_UCODE[2]["ALO"] = 1
    XRA_UCODE[2]["AI"] = 1
    XRA_UCODE[2]["FRI"] = 1

    XRA_UCODE[3] = CONTROL_WORDS.copy()
    XRA_UCODE[3]["SCR"] = 1

# ORA - OR A
ORA = Instruction("ORA", "r", 1)
for i in REGISTERS:
    ORA.ucode.setdefault(i, {})
    ORA_UCODE = ORA.ucode[i]
    ORA_UCODE[256] = int(f"10110{REGISTER_CODES[i]:03b}", 2)

    ORA_UCODE[0] = CONTROL_WORDS.copy()
    ORA_UCODE[0]["PCO"] = 1
    ORA_UCODE[0]["RO"] = 1
    ORA_UCODE[0]["II"] = 1

    ORA_UCODE[1] = CONTROL_WORDS.copy()
    if i == "M":
        ORA_UCODE[1]["HLO"] = 1
        ORA_UCODE[1]["RO"] = 1
    else:
        ORA_UCODE[1][i + "O"] = 1
    ORA_UCODE[1]["ALI"] = 1
    ORA_UCODE[1]["PCE"] = 1

    ORA_UCODE[2] = CONTROL_WORDS.copy()
    ORA_UCODE[2]["ALM"] = 1
    ORA_UCODE[2]["AL0"] = 1
    ORA_UCODE[2]["AL1"] = 1
    ORA_UCODE[2]["AL3"] = 1
    ORA_UCODE[2]["ALO"] = 1
    ORA_UCODE[2]["AI"] = 1
    ORA_UCODE[2]["FRI"] = 1

    ORA_UCODE[3] = CONTROL_WORDS.copy()
    ORA_UCODE[3]["SCR"] = 1

# CMP - Compare
CMP = Instruction("CMP", "r", 1)
for i in REGISTERS:
    CMP.ucode.setdefault(i, {})
    CMP_UCODE = CMP.ucode[i]
    CMP_UCODE[256] = int(f"10111{REGISTER_CODES[i]:03b}", 2)

    CMP_UCODE[0] = CONTROL_WORDS.copy()
    CMP_UCODE[0]["PCO"] = 1
    CMP_UCODE[0]["RO"] = 1
    CMP_UCODE[0]["II"] = 1

    CMP_UCODE[1] = CONTROL_WORDS.copy()
    if i == "M":
        CMP_UCODE[1]["HLO"] = 1
        CMP_UCODE[1]["RO"] = 1
    else:
        CMP_UCODE[1][i + "O"] = 1
    CMP_UCODE[1]["ALI"] = 1
    CMP_UCODE[1]["PCE"] = 1

    CMP_UCODE[2] = CONTROL_WORDS.copy()
    CMP_UCODE[2]["AL1"] = 1
    CMP_UCODE[2]["AL2"] = 1
    CMP_UCODE[2]["FRI"] = 1

    CMP_UCODE[3] = CONTROL_WORDS.copy()
    CMP_UCODE[3]["SCR"] = 1

# ADI - Add Immediate
ADI = Instruction("ADI", "data", 2)
ADI.ucode.setdefault("data", {})
ADI_UCODE = ADI.ucode["data"]
ADI_UCODE[256] = int("11000110", 2)

ADI_UCODE[0] = CONTROL_WORDS.copy()
ADI_UCODE[0]["PCO"] = 1
ADI_UCODE[0]["RO"] = 1
ADI_UCODE[0]["II"] = 1

ADI_UCODE[1] = CONTROL_WORDS.copy()
ADI_UCODE[1]["PCE"] = 1

ADI_UCODE[2] = CONTROL_WORDS.copy()
ADI_UCODE[2]["PCO"] = 1
ADI_UCODE[2]["RO"] = 1
ADI_UCODE[2]["ALI"] = 1

ADI_UCODE[3] = CONTROL_WORDS.copy()
ADI_UCODE[3]["PCE"] = 1

ADI_UCODE[4] = CONTROL_WORDS.copy()
ADI_UCODE[4]["AL0"] = 1
ADI_UCODE[4]["AL3"] = 1
ADI_UCODE[4]["ALO"] = 1
ADI_UCODE[4]["AI"] = 1
ADI_UCODE[4]["FRI"] = 1

ADI_UCODE[5] = CONTROL_WORDS.copy()
ADI_UCODE[5]["SCR"] = 1

# ACI - Add Carry Immediate
ACI = Instruction("ACI", "data", 2)
ACI.ucode.setdefault("data", {})
ACI_UCODE = ACI.ucode["data"]
ACI_UCODE[256] = int("11001110", 2)

ACI_UCODE[0] = CONTROL_WORDS.copy()
ACI_UCODE[0]["PCO"] = 1
ACI_UCODE[0]["RO"] = 1
ACI_UCODE[0]["II"] = 1

ACI_UCODE[1] = CONTROL_WORDS.copy()
ACI_UCODE[1]["PCE"] = 1

ACI_UCODE[2] = CONTROL_WORDS.copy()
ACI_UCODE[2]["PCO"] = 1
ACI_UCODE[2]["RO"] = 1
ACI_UCODE[2]["ALI"] = 1

ACI_UCODE[3] = CONTROL_WORDS.copy()
ACI_UCODE[3]["PCE"] = 1

ACI_UCODE[4] = CONTROL_WORDS.copy()
ACI_UCODE[4]["AL0"] = 1
ACI_UCODE[4]["AL3"] = 1
ACI_UCODE[4]["ALO"] = 1
ACI_UCODE[4]["AI"] = 1
ACI_UCODE[4]["FRI"] = 1
ACI.set_cond("data", 4, "C", {"ALC": 1})

ACI_UCODE[5] = CONTROL_WORDS.copy()
ACI_UCODE[5]["SCR"] = 1

# SUI - Subtract immediate
SUI = Instruction("SUI", "data", 2)
SUI.ucode.setdefault("data", {})
SUI_UCODE = SUI.ucode["data"]
SUI_UCODE[256] = int("11010110", 2)

SUI_UCODE[0] = CONTROL_WORDS.copy()
SUI_UCODE[0]["PCO"] = 1
SUI_UCODE[0]["RO"] = 1
SUI_UCODE[0]["II"] = 1

SUI_UCODE[1] = CONTROL_WORDS.copy()
SUI_UCODE[1]["PCE"] = 1

SUI_UCODE[2] = CONTROL_WORDS.copy()
SUI_UCODE[2]["PCO"] = 1
SUI_UCODE[2]["RO"] = 1
SUI_UCODE[2]["ALI"] = 1

SUI_UCODE[3] = CONTROL_WORDS.copy()
SUI_UCODE[3]["PCE"] = 1

SUI_UCODE[4] = CONTROL_WORDS.copy()
SUI_UCODE[4]["AL1"] = 1
SUI_UCODE[4]["AL2"] = 1
SUI_UCODE[4]["ALO"] = 1
SUI_UCODE[4]["AI"] = 1
SUI_UCODE[4]["FRI"] = 1

SUI_UCODE[5] = CONTROL_WORDS.copy()
SUI_UCODE[5]["SCR"] = 1

# SBI - Subtract borrow immediate
SBI = Instruction("SBI", "data", 2)
SBI.ucode.setdefault("data", {})
SBI_UCODE = SBI.ucode["data"]
SBI_UCODE[256] = int("11011110", 2)

SBI_UCODE[0] = CONTROL_WORDS.copy()
SBI_UCODE[0]["PCO"] = 1
SBI_UCODE[0]["RO"] = 1
SBI_UCODE[0]["II"] = 1

SBI_UCODE[1] = CONTROL_WORDS.copy()
SBI_UCODE[1]["PCE"] = 1

SBI_UCODE[2] = CONTROL_WORDS.copy()
SBI_UCODE[2]["PCO"] = 1
SBI_UCODE[2]["RO"] = 1
SBI_UCODE[2]["ALI"] = 1

SBI_UCODE[3] = CONTROL_WORDS.copy()
SBI_UCODE[3]["PCE"] = 1

SBI_UCODE[4] = CONTROL_WORDS.copy()
SBI_UCODE[4]["AL1"] = 1
SBI_UCODE[4]["AL2"] = 1
SBI_UCODE[4]["ALO"] = 1
SBI_UCODE[4]["AI"] = 1
SBI_UCODE[4]["FRI"] = 1
SBI.set_cond("data", 4, "C", {"ALC": 1})

SBI_UCODE[5] = CONTROL_WORDS.copy()
SBI_UCODE[5]["SCR"] = 1

# ANI - AND A Immediate
ANI = Instruction("ANI", "data", 2)
ANI.ucode.setdefault("data", {})
ANI_UCODE = ANI.ucode["data"]
ANI_UCODE[256] = int("11100110", 2)

ANI_UCODE[0] = CONTROL_WORDS.copy()
ANI_UCODE[0]["PCO"] = 1
ANI_UCODE[0]["RO"] = 1
ANI_UCODE[0]["II"] = 1

ANI_UCODE[1] = CONTROL_WORDS.copy()
ANI_UCODE[1]["PCE"] = 1

ANI_UCODE[2] = CONTROL_WORDS.copy()
ANI_UCODE[2]["PCO"] = 1
ANI_UCODE[2]["RO"] = 1
ANI_UCODE[2]["ALI"] = 1

ANI_UCODE[3] = CONTROL_WORDS.copy()
ANI_UCODE[3]["PCE"] = 1

ANI_UCODE[4] = CONTROL_WORDS.copy()
ANI_UCODE[4]["ALM"] = 1
ANI_UCODE[4]["AL0"] = 1
ANI_UCODE[4]["AL1"] = 1
ANI_UCODE[4]["AL3"] = 1
ANI_UCODE[4]["ALO"] = 1
ANI_UCODE[4]["AI"] = 1
ANI_UCODE[4]["FRI"] = 1

ANI_UCODE[5] = CONTROL_WORDS.copy()
ANI_UCODE[5]["SCR"] = 1

# XRI - XOR A Immediate
XRI = Instruction("XRI", "data", 2)
XRI.ucode.setdefault("data", {})
XRI_UCODE = XRI.ucode["data"]
XRI_UCODE[256] = int("11101110", 2)

XRI_UCODE[0] = CONTROL_WORDS.copy()
XRI_UCODE[0]["PCO"] = 1
XRI_UCODE[0]["RO"] = 1
XRI_UCODE[0]["II"] = 1

XRI_UCODE[1] = CONTROL_WORDS.copy()
XRI_UCODE[1]["PCE"] = 1

XRI_UCODE[2] = CONTROL_WORDS.copy()
XRI_UCODE[2]["PCO"] = 1
XRI_UCODE[2]["RO"] = 1
XRI_UCODE[2]["ALI"] = 1

XRI_UCODE[3] = CONTROL_WORDS.copy()
XRI_UCODE[3]["PCE"] = 1

XRI_UCODE[4] = CONTROL_WORDS.copy()
XRI_UCODE[4]["ALM"] = 1
XRI_UCODE[4]["AL0"] = 1
XRI_UCODE[4]["AL3"] = 1
XRI_UCODE[4]["ALO"] = 1
XRI_UCODE[4]["AI"] = 1
XRI_UCODE[4]["FRI"] = 1

XRI_UCODE[5] = CONTROL_WORDS.copy()
XRI_UCODE[5]["SCR"] = 1

# ORI - OR A Immediate
ORI = Instruction("ORI", "data", 2)
ORI.ucode.setdefault("data", {})
ORI_UCODE = ORI.ucode["data"]
ORI_UCODE[256] = int("11110110", 2)

ORI_UCODE[0] = CONTROL_WORDS.copy()
ORI_UCODE[0]["PCO"] = 1
ORI_UCODE[0]["RO"] = 1
ORI_UCODE[0]["II"] = 1

ORI_UCODE[1] = CONTROL_WORDS.copy()
ORI_UCODE[1]["PCE"] = 1

ORI_UCODE[2] = CONTROL_WORDS.copy()
ORI_UCODE[2]["PCO"] = 1
ORI_UCODE[2]["RO"] = 1
ORI_UCODE[2]["ALI"] = 1

ORI_UCODE[3] = CONTROL_WORDS.copy()
ORI_UCODE[3]["PCE"] = 1

ORI_UCODE[4] = CONTROL_WORDS.copy()
ORI_UCODE[4]["ALM"] = 1
ORI_UCODE[4]["AL0"] = 1
ORI_UCODE[4]["AL1"] = 1
ORI_UCODE[4]["AL3"] = 1
ORI_UCODE[4]["ALO"] = 1
ORI_UCODE[4]["AI"] = 1
ORI_UCODE[4]["FRI"] = 1

ORI_UCODE[5] = CONTROL_WORDS.copy()
ORI_UCODE[5]["SCR"] = 1

# CPI - Compare A immediate
CPI = Instruction("CPI", "data", 2)
CPI.ucode.setdefault("data", {})
CPI_UCODE = CPI.ucode["data"]
CPI_UCODE[256] = int("11111110", 2)

CPI_UCODE[0] = CONTROL_WORDS.copy()
CPI_UCODE[0]["PCO"] = 1
CPI_UCODE[0]["RO"] = 1
CPI_UCODE[0]["II"] = 1

CPI_UCODE[1] = CONTROL_WORDS.copy()
CPI_UCODE[1]["PCE"] = 1

CPI_UCODE[2] = CONTROL_WORDS.copy()
CPI_UCODE[2]["PCO"] = 1
CPI_UCODE[2]["RO"] = 1
CPI_UCODE[2]["ALI"] = 1

CPI_UCODE[3] = CONTROL_WORDS.copy()
CPI_UCODE[3]["PCE"] = 1

CPI_UCODE[4] = CONTROL_WORDS.copy()
CPI_UCODE[4]["AL1"] = 1
CPI_UCODE[4]["AL2"] = 1
CPI_UCODE[4]["FRI"] = 1

CPI_UCODE[5] = CONTROL_WORDS.copy()
CPI_UCODE[5]["SCR"] = 1

# JMP - Unconditional Jump (loads target 16-bit address into PC)
JMP = Instruction("JMP", "addr16", 3)
JMP.ucode.setdefault("addr16", {})
JMP_UCODE = JMP.ucode["addr16"]
JMP_UCODE[256] = int("11000011", 2)

JMP_UCODE[0] = CONTROL_WORDS.copy()
JMP_UCODE[0]["PCO"] = 1
JMP_UCODE[0]["RO"] = 1
JMP_UCODE[0]["II"] = 1

JMP_UCODE[1] = CONTROL_WORDS.copy()
JMP_UCODE[1]["PCE"] = 1

JMP_UCODE[2] = CONTROL_WORDS.copy()
JMP_UCODE[2]["PCO"] = 1
JMP_UCODE[2]["RO"] = 1
JMP_UCODE[2]["TI"] = 1

JMP_UCODE[3] = CONTROL_WORDS.copy()
JMP_UCODE[3]["PCE"] = 1

JMP_UCODE[4] = CONTROL_WORDS.copy()
JMP_UCODE[4]["PCO"] = 1
JMP_UCODE[4]["RO"] = 1
JMP_UCODE[4]["JPH"] = 1

JMP_UCODE[5] = CONTROL_WORDS.copy()
JMP_UCODE[5]["TO"] = 1
JMP_UCODE[5]["JPL"] = 1

JMP_UCODE[6] = CONTROL_WORDS.copy()
JMP_UCODE[6]["SCR"] = 1

# J<cond> - Conditional Jumps (JNZ, JZ, JNC, JC, JPO, JPE, JP, JM)
COND_JUMPS = {
    "JNZ": ("NZ", 0b000),
    "JZ": ("Z", 0b001),
    "JNC": ("NC", 0b010),
    "JC": ("C", 0b011),
    "JPO": ("PO", 0b100),
    "JPE": ("PE", 0b101),
    "JP": ("P", 0b110),
    "JM": ("N", 0b111),
}

for j_mnemonic, (cond_code, ccc) in COND_JUMPS.items():
    j_inst = Instruction(j_mnemonic, "addr16", 3)
    j_inst.ucode.setdefault("addr16", {})
    j_ucode = j_inst.ucode["addr16"]
    j_ucode[256] = int(f"11{ccc:03b}010", 2)

    # Step 0: Fetch opcode
    j_ucode[0] = CONTROL_WORDS.copy()
    j_ucode[0]["PCO"] = 1
    j_ucode[0]["RO"] = 1
    j_ucode[0]["II"] = 1

    # False -> NO target address
    j_ucode[1] = CONTROL_WORDS.copy()
    j_ucode[1]["PCE"] = 1

    j_ucode[2] = CONTROL_WORDS.copy()
    j_ucode[2]["PCE"] = 1

    j_ucode[3] = CONTROL_WORDS.copy()
    j_ucode[3]["PCE"] = 1

    j_ucode[4] = CONTROL_WORDS.copy()
    j_ucode[4]["SCR"] = 1

    # True -> target address -> PC
    taken_steps = {
        1: CONTROL_WORDS.copy(),
        2: CONTROL_WORDS.copy(),
        3: CONTROL_WORDS.copy(),
        4: CONTROL_WORDS.copy(),
        5: CONTROL_WORDS.copy(),
        6: CONTROL_WORDS.copy(),
    }
    taken_steps[1]["PCE"] = 1

    taken_steps[2]["PCO"] = 1
    taken_steps[2]["RO"] = 1
    taken_steps[2]["TI"] = 1

    taken_steps[3]["PCE"] = 1

    taken_steps[4]["PCO"] = 1
    taken_steps[4]["RO"] = 1
    taken_steps[4]["JPH"] = 1

    taken_steps[5]["TO"] = 1
    taken_steps[5]["JPL"] = 1

    taken_steps[6]["SCR"] = 1

    j_inst.set_branch("addr16", cond_code, taken_steps)


# CALL - Call Subroutine (PC -> stack, jmp to target)
CALL = Instruction("CALL", "addr16", 3)
CALL.ucode.setdefault("addr16", {})
CALL_UCODE = CALL.ucode["addr16"]
CALL_UCODE[256] = int("11001101", 2)  # 0xCD

CALL_UCODE[0] = CONTROL_WORDS.copy()
CALL_UCODE[0]["PCO"] = 1
CALL_UCODE[0]["RO"] = 1
CALL_UCODE[0]["II"] = 1

CALL_UCODE[1] = CONTROL_WORDS.copy()
CALL_UCODE[1]["PCE"] = 1

CALL_UCODE[2] = CONTROL_WORDS.copy()
CALL_UCODE[2]["PCO"] = 1
CALL_UCODE[2]["RO"] = 1
CALL_UCODE[2]["TI"] = 1

CALL_UCODE[3] = CONTROL_WORDS.copy()
CALL_UCODE[3]["PCE"] = 1

CALL_UCODE[4] = CONTROL_WORDS.copy()
CALL_UCODE[4]["PCO"] = 1
CALL_UCODE[4]["RO"] = 1
CALL_UCODE[4]["ALI"] = 1

CALL_UCODE[5] = CONTROL_WORDS.copy()
CALL_UCODE[5]["PCE"] = 1

CALL_UCODE[6] = CONTROL_WORDS.copy()
CALL_UCODE[6]["DES"] = 1

CALL_UCODE[7] = CONTROL_WORDS.copy()
CALL_UCODE[7]["SPO"] = 1
CALL_UCODE[7]["PCHO"] = 1
CALL_UCODE[7]["RI"] = 1

CALL_UCODE[8] = CONTROL_WORDS.copy()
CALL_UCODE[8]["DES"] = 1

CALL_UCODE[9] = CONTROL_WORDS.copy()
CALL_UCODE[9]["SPO"] = 1
CALL_UCODE[9]["PCLO"] = 1
CALL_UCODE[9]["RI"] = 1

CALL_UCODE[10] = CONTROL_WORDS.copy()
CALL_UCODE[10]["ALM"] = 1
CALL_UCODE[10]["AL1"] = 1
CALL_UCODE[10]["AL3"] = 1
CALL_UCODE[10]["ALO"] = 1
CALL_UCODE[10]["JPH"] = 1

CALL_UCODE[11] = CONTROL_WORDS.copy()
CALL_UCODE[11]["TO"] = 1
CALL_UCODE[11]["JPL"] = 1

CALL_UCODE[12] = CONTROL_WORDS.copy()
CALL_UCODE[12]["SCR"] = 1

# RET - Return subroutine (Pop PC stack)
RET = Instruction("RET", "N", 1)
RET.ucode.setdefault("N", {})
RET_UCODE = RET.ucode["N"]
RET_UCODE[256] = int("11001001", 2)  # 0xC9

RET_UCODE[0] = CONTROL_WORDS.copy()
RET_UCODE[0]["PCO"] = 1
RET_UCODE[0]["RO"] = 1
RET_UCODE[0]["II"] = 1

RET_UCODE[1] = CONTROL_WORDS.copy()
RET_UCODE[1]["SPO"] = 1
RET_UCODE[1]["RO"] = 1
RET_UCODE[1]["JPL"] = 1  # Pop return address Low byte into JPL

RET_UCODE[2] = CONTROL_WORDS.copy()
RET_UCODE[2]["INS"] = 1  # SP = SP + 1

RET_UCODE[3] = CONTROL_WORDS.copy()
RET_UCODE[3]["SPO"] = 1
RET_UCODE[3]["RO"] = 1
RET_UCODE[3]["JPH"] = 1

RET_UCODE[4] = CONTROL_WORDS.copy()
RET_UCODE[4]["INS"] = 1

RET_UCODE[5] = CONTROL_WORDS.copy()
RET_UCODE[5]["SCR"] = 1

# C<cond> - Call conditional (CNZ, CZ, CNC, CC, CPO, CPE, CP, CM)
COND_CALLS = {
    "CNZ": ("NZ", 0b000),
    "CZ": ("Z", 0b001),
    "CNC": ("NC", 0b010),
    "CC": ("C", 0b011),
    "CPO": ("PO", 0b100),
    "CPE": ("PE", 0b101),
    "CP": ("P", 0b110),
    "CM": ("N", 0b111),
}

for c_mnemonic, (cond_code, ccc) in COND_CALLS.items():
    c_inst = Instruction(c_mnemonic, "addr16", 3)
    c_inst.ucode.setdefault("addr16", {})
    c_ucode = c_inst.ucode["addr16"]
    c_ucode[256] = int(f"11{ccc:03b}100", 2)

    # Step 0: Fetch opcode
    c_ucode[0] = CONTROL_WORDS.copy()
    c_ucode[0]["PCO"] = 1
    c_ucode[0]["RO"] = 1
    c_ucode[0]["II"] = 1

    # False -> NO target address
    c_ucode[1] = CONTROL_WORDS.copy()
    c_ucode[1]["PCE"] = 1

    c_ucode[2] = CONTROL_WORDS.copy()
    c_ucode[2]["PCE"] = 1

    c_ucode[3] = CONTROL_WORDS.copy()
    c_ucode[3]["PCE"] = 1

    c_ucode[4] = CONTROL_WORDS.copy()
    c_ucode[4]["SCR"] = 1

    # True -> Call
    c_taken_steps = {
        1: CONTROL_WORDS.copy(),
        2: CONTROL_WORDS.copy(),
        3: CONTROL_WORDS.copy(),
        4: CONTROL_WORDS.copy(),
        5: CONTROL_WORDS.copy(),
        6: CONTROL_WORDS.copy(),
        7: CONTROL_WORDS.copy(),
        8: CONTROL_WORDS.copy(),
        9: CONTROL_WORDS.copy(),
        10: CONTROL_WORDS.copy(),
        11: CONTROL_WORDS.copy(),
        12: CONTROL_WORDS.copy(),
    }
    c_taken_steps[1]["PCE"] = 1

    c_taken_steps[2]["PCO"] = 1
    c_taken_steps[2]["RO"] = 1
    c_taken_steps[2]["TI"] = 1

    c_taken_steps[3]["PCE"] = 1

    c_taken_steps[4]["PCO"] = 1
    c_taken_steps[4]["RO"] = 1
    c_taken_steps[4]["ALI"] = 1

    c_taken_steps[5]["PCE"] = 1

    c_taken_steps[6]["DES"] = 1

    c_taken_steps[7]["SPO"] = 1
    c_taken_steps[7]["PCHO"] = 1
    c_taken_steps[7]["RI"] = 1

    c_taken_steps[8]["DES"] = 1

    c_taken_steps[9]["SPO"] = 1
    c_taken_steps[9]["PCLO"] = 1
    c_taken_steps[9]["RI"] = 1

    c_taken_steps[10]["ALM"] = 1
    c_taken_steps[10]["AL1"] = 1
    c_taken_steps[10]["AL3"] = 1
    c_taken_steps[10]["ALO"] = 1
    c_taken_steps[10]["JPH"] = 1

    c_taken_steps[11]["TO"] = 1
    c_taken_steps[11]["JPL"] = 1

    c_taken_steps[12]["SCR"] = 1

    c_inst.set_branch("addr16", cond_code, c_taken_steps)

# R<cond> - Return on cond (RNZ, RZ, RNC, RC, RPO, RPE, RP, RM)
COND_RETS = {
    "RNZ": ("NZ", 0b000),
    "RZ": ("Z", 0b001),
    "RNC": ("NC", 0b010),
    "RC": ("C", 0b011),
    "RPO": ("PO", 0b100),
    "RPE": ("PE", 0b101),
    "RP": ("P", 0b110),
    "RM": ("N", 0b111),
}

for r_mnemonic, (cond_code, ccc) in COND_RETS.items():
    r_inst = Instruction(r_mnemonic, "N", 1)
    r_inst.ucode.setdefault("N", {})
    r_ucode = r_inst.ucode["N"]
    r_ucode[256] = int(f"11{ccc:03b}000", 2)

    r_ucode[0] = CONTROL_WORDS.copy()
    r_ucode[0]["PCO"] = 1
    r_ucode[0]["RO"] = 1
    r_ucode[0]["II"] = 1

    # False -> continue
    r_ucode[1] = CONTROL_WORDS.copy()
    r_ucode[1]["PCE"] = 1

    r_ucode[2] = CONTROL_WORDS.copy()
    r_ucode[2]["SCR"] = 1

    # True -> Return
    r_taken_steps = {
        1: CONTROL_WORDS.copy(),
        2: CONTROL_WORDS.copy(),
        3: CONTROL_WORDS.copy(),
        4: CONTROL_WORDS.copy(),
        5: CONTROL_WORDS.copy(),
    }
    r_taken_steps[1]["SPO"] = 1
    r_taken_steps[1]["RO"] = 1
    r_taken_steps[1]["JPL"] = 1

    r_taken_steps[2]["INS"] = 1

    r_taken_steps[3]["SPO"] = 1
    r_taken_steps[3]["RO"] = 1
    r_taken_steps[3]["JPH"] = 1

    r_taken_steps[4]["INS"] = 1

    r_taken_steps[5]["SCR"] = 1

    r_inst.set_branch("N", cond_code, r_taken_steps)

# PUSH rp (BC, DE, HL)
PUSH = Instruction("PUSH", "rp", 1)
for i in ["BC", "DE", "HL"]:
    PUSH.ucode.setdefault(i, {})
    PUSH_UCODE = PUSH.ucode[i]
    PUSH_UCODE[256] = int(f"11{REGISTER_PAIR_CODES[i]:02b}0101", 2)

    CTRL_T_L_O = i[1:] + "O"
    CTRL_T_H_O = i[:1] + "O"

    PUSH_UCODE[0] = CONTROL_WORDS.copy()
    PUSH_UCODE[0]["PCO"] = 1
    PUSH_UCODE[0]["RO"] = 1
    PUSH_UCODE[0]["II"] = 1

    PUSH_UCODE[1] = CONTROL_WORDS.copy()
    PUSH_UCODE[1]["DES"] = 1
    PUSH_UCODE[1]["PCE"] = 1

    PUSH_UCODE[2] = CONTROL_WORDS.copy()
    PUSH_UCODE[2]["SPO"] = 1
    PUSH_UCODE[2][CTRL_T_H_O] = 1
    PUSH_UCODE[2]["RI"] = 1

    PUSH_UCODE[3] = CONTROL_WORDS.copy()
    PUSH_UCODE[3]["DES"] = 1

    PUSH_UCODE[4] = CONTROL_WORDS.copy()
    PUSH_UCODE[4]["SPO"] = 1
    PUSH_UCODE[4][CTRL_T_L_O] = 1
    PUSH_UCODE[4]["RI"] = 1

    PUSH_UCODE[5] = CONTROL_WORDS.copy()
    PUSH_UCODE[5]["SCR"] = 1

# POP rp (BC, DE, HL)
POP = Instruction("POP", "rp", 1)
for i in ["BC", "DE", "HL"]:
    POP.ucode.setdefault(i, {})
    POP_UCODE = POP.ucode[i]
    POP_UCODE[256] = int(f"11{REGISTER_PAIR_CODES[i]:02b}0001", 2)

    CTRL_L_I = i[1:] + "I"
    CTRL_H_I = i[:1] + "I"

    POP_UCODE[0] = CONTROL_WORDS.copy()
    POP_UCODE[0]["PCO"] = 1
    POP_UCODE[0]["RO"] = 1
    POP_UCODE[0]["II"] = 1

    POP_UCODE[1] = CONTROL_WORDS.copy()
    POP_UCODE[1]["SPO"] = 1
    POP_UCODE[1]["RO"] = 1
    POP_UCODE[1][CTRL_L_I] = 1
    POP_UCODE[1]["PCE"] = 1

    POP_UCODE[2] = CONTROL_WORDS.copy()
    POP_UCODE[2]["INS"] = 1

    POP_UCODE[3] = CONTROL_WORDS.copy()
    POP_UCODE[3]["SPO"] = 1
    POP_UCODE[3]["RO"] = 1
    POP_UCODE[3][CTRL_H_I] = 1

    POP_UCODE[4] = CONTROL_WORDS.copy()
    POP_UCODE[4]["INS"] = 1

    POP_UCODE[5] = CONTROL_WORDS.copy()
    POP_UCODE[5]["SCR"] = 1


def build_opcode_map() -> dict[int, tuple[Instruction, str]]:
    opcode_map: dict[int, tuple[Instruction, str]] = {}
    for inst in INSTRUCTION_LIST.values():
        for variant, v_dict in inst.ucode.items():
            if 256 in v_dict:
                op = v_dict[256]
                if op in opcode_map:
                    prev_inst, prev_var = opcode_map[op]
                    raise ValueError(
                        f"Opcode collision 0x{op:02X} ({op:08b}): "
                        f"{inst.mnemonic} ({variant}) AND {prev_inst.mnemonic} ({prev_var})"
                    )
                opcode_map[op] = (inst, variant)
    return opcode_map


if __name__ == "__main__":
    for inst in INSTRUCTION_LIST.values():
        print(inst)
    op_map = build_opcode_map()
    print(f"\nTOTAL: {len(op_map)} / 256")
