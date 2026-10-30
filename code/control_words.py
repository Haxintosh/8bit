# Architecture
# 8bit wide data bus
# 16bit address bus
# A/B/C/D/E/H/L/ALU/RAM/ROM i/o data bus
# BC/DE/HL can pair up and act as a 16bit register, pair out to 16bit address bus
# PC/MAR/SP are 16bits and are split into Low, they output to 16bit address bus
# MMIO - 0x0000 - 0x7FFF -> RAM, 0xF000 - OxFFFF -> ROM
# ALU uses 2x 74181, with physical hardware for RRC/RAR, flags register has NCZV

CONTROL_WORDS = {
    "AI": 0,  # A in
    "BI": 0,  # B in
    "CI": 0,  # C in
    "DI": 0,  # D in
    "EI": 0,  # E in
    "LI": 0,  # L in
    "HI": 0,  # H in
    "MLI": 0,  # MAR L in
    "MHI": 0,  # MAR H in
    "SPLI": 0,  # SP L in
    "SPHI": 0,  # SP H in
    "RI": 0,  # RAM in
    "ALI": 0,  # ALU buffer in
    "OI": 0,  # Output in
    "II": 0,  # IR in
    "TI": 0,  # TEMP in
    "FRI": 0,  # Flags Register in
    "AO": 0,  # A out
    "BO": 0,  # B out
    "CO": 0,  # C out
    "DO": 0,  # D out
    "EO": 0,  # E out
    "LO": 0,  # L out
    "HO": 0,  # H out
    "RO": 0,  # RAM out
    "TO": 0,  # TEMP out
    "ALO": 0,  # ALU out
    "PCLO": 0,  # PC low out
    "PCHO": 0,  # PC high out
    "BCO": 0,  # BC pair out
    "DEO": 0,  # DE pair out
    "HLO": 0,  # HL/M pair out
    "SPO": 0,  # SP out
    "PCO": 0,  # PC out
    "MO": 0,  # MAR out
    "AL0": 0,  # 74LS181 ctrl 0
    "AL1": 0,  # 74LS181 ctrl 1
    "AL2": 0,  # 74LS181 ctrl 2
    "AL3": 0,  # 74LS181 ctrl 3
    "ALM": 0,  # 74LS181 ctrl mode
    "RRC": 0,  # ALU RRC - Does not need ALO / ALU ctrls
    "RAR": 0,  # ALU RAR - Does not need ALO / ALU ctrls
    "INH": 0,  # Increment H
    "DEH": 0,  # Decrement H
    "INS": 0,  # Increment SP
    "INM": 0,  # Increment MAR #TODO: Implement
    "DES": 0,  # Decrement SP
    "JPL": 0,  # PC L in
    "JPH": 0,  # PC H in
    "PCE": 0,  # PC count enable
    "SCR": 0,  # Step Counter Reset
    "HLT": 0,  # Halt
    "ALC": 0,  # ALU carry
    "FLAGS": {},  # NCZV available
}

REGISTER_CODES = {"B": 0, "C": 1, "D": 2, "E": 3, "L": 4, "H": 5, "M": 6, "A": 7}

REGISTER_PAIR_CODES = {"BC": 0, "DE": 1, "HL": 2, "SP": 3}

# Based on the 8080, Parity / AC are not currently implemented...
CARRY_CODES = {
    "NZ": 0,
    "Z": 1,
    "NC": 2,
    "C": 3,
    "PO": 4,
    "PE": 5,
    "P": 6,
    "N": 7,
}

# The number is the input for A0-A3
# 0 is all off
# These output to the data bus
REGISTER_OUT_MUX = {
    "AO": 1,
    "BO": 2,
    "CO": 3,
    "DO": 4,
    "EO": 5,
    "LO": 6,
    "HO": 7,
    "RO": 8,
    "ALO": 9,
    "TO": 10,
    "RRC": 11,
    "RAR": 12,
    "PCLO": 13,
    "PCHO": 14,
}

# A0-A2 (A3 is tied to GND)
# These output to the address bus
REGISTER_PAIR_OUT_MUX = {"BCO": 1, "DEO": 2, "HLO": 3, "SPO": 4, "PCO": 5, "MO": 6}

# A0-A3
REGISTER_IN_MUX = {
    "AI": 1,
    "BI": 2,
    "CI": 3,
    "DI": 4,
    "EI": 5,
    "LI": 6,
    "HI": 7,
    "MLI": 8,
    "MHI": 9,
    "SPLI": 10,
    "SPHI": 11,
    "II": 12,
    "TI": 13,
    "OI": 14,
    "ALI": 15,
}

# EEPROM IN FORMAT
# A0-A7: OPCODE0 - OPCODE 7
# A8-A11: STEP0 - STEP3
# A12: VF
# A13: NF
# A14: CF
# A15: ZF

# EEPROM OUT MAP
# 1ST control EEPROM:
#   D0: HLT
#   D1 - D4: REG_OUT_MUX0 - REG_OUT_MUX3
#   D5 - D7: REG_PAIR_OUT_MUX0 - REG_PAIR_MUX2
# 2ND control EEPROM:
#   D0 - D3: REG_IN_MUX0-REG_IN_MUX3
#   D4: INH
#   D5: DEH
#   D6: INS
#   D7: DES
# 3RD control EEPROM
#   D0 - D3: AL0 - AL3
#   D4: ALM
#   D5: FRI
#   D6: JPL
#   D7: JPH
# 4TH control EEPROM
#   D0: PCE
#   D1: SCR
#   D2: RI
#   D3: ALC
#   D4: INM
#   D5: SCR (duplicate)
