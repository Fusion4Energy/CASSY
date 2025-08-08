from dataclasses import dataclass


@dataclass
class TableFormatting:
    name: str  # name of the table type
    col_order: list[str]  # order of columns in the table
    formats: dict[int, str]  # formats to be applied in the columns
    block_identifier: str  # column limit for merging blocks
    max_col_merge: int  # col index where to stop merging


# Define instances for each table type
damage_recap_table = TableFormatting(
    name="damage recap",
    col_order=[
        "Submodel",
        "Path",
        "Path Type",
        "Assessment",
        "Reference Event",
        "Service lvl",
        "Rule",
        "Safety Margin",
    ],
    formats={},
    block_identifier="",
    max_col_merge=0,
)

fatigue_recap_table = TableFormatting(
    name="fatigue recap",
    col_order=["Submodel", "ID", "Assessment", "Total Usage Fraction [%]"],
    formats={},
    block_identifier="",
    max_col_merge=0,
)

bolt_immediate_table = TableFormatting(
    name="immediate bolts",
    col_order=[
        "ID",
        "Operating Conditions",
        "Initiating Event",
        "Concatenated Event",
        "Loading Category",
        "Service Level",
        "Rule Extended Description",
        "Rule ID",
        "Sub-Rule",
        "T [°C]",
        "DPA",
        "Applied [MPa]",
        "Allowable [MPa]",
        "Result",
        "Safety Margin",
    ],
    formats={
        9: "{:.0f}",
        10: "{:.1e}",
        11: "{:.0f}",
        12: "{:.0f}",
        14: "{:.1f}",
    },
    block_identifier="ID",
    max_col_merge=8,
)

bolt_input_table = TableFormatting(
    name="input bolts",
    col_order=[
        "RE ID",
        "Operating Conditions",
        "Initiating Event",
        "Concatenated Event",
        "Type of Load",
        "N",
        "T",
        "M",
    ],
    formats={5: "{:.2e}", 6: "{:.2e}", 7: "{:.2e}"},
    block_identifier="RE ID",
    max_col_merge=3,
)

path_input_table = TableFormatting(
    name="input paths",
    col_order=[
        "Load Condition",
        "Stress breakdown",
        "stress_type",
        "Sx",
        "Sy",
        "Sz",
        "Sxy",
        "Sxz",
        "Syz",
    ],
    formats={
        3: "{:.0f}",
        4: "{:.0f}",
        5: "{:.0f}",
        6: "{:.0f}",
        7: "{:.0f}",
        8: "{:.0f}",
    },
    block_identifier="Load Condition",
    max_col_merge=1,
)

bolt_fatigue_sdcic_table = TableFormatting(
    name="fatigue SDCIC bolts",
    col_order=[
        "ID",
        "Operating conditions",
        "Range",
        "ctg",
        "lvl",
        "T",
        "dpa",
        "sigma N",
        "epsilon N",
        "n",
        "Kf",
        "sigma bar",
        "epsilon bar",
        "sigma pre",
        "N",
        "Vj",
    ],
    formats={
        5: "{:.0f}",
        6: "{:.1e}",
        7: "{:.0f}",
        8: "{:.4%}",
        9: "{:.2e}",
        11: "{:.0f}",
        12: "{:.4%}",
        13: "{:.0f}",
        14: "{:.2e}",
        15: "{:.2%}",
    },
    block_identifier="Load Condition",
    max_col_merge=0,
)

bolt_fatigue_table = TableFormatting(
    name="fatigue bolts",
    col_order=[
        "ID",
        "Operating conditions",
        "Range",
        "ctg",
        "lvl",
        "T",
        "dpa",
        "sigma tot",
        "n",
        "de1",
        "de2",
        "de3",
        "de4",
        "de tot",
        "N",
        "Vj",
    ],
    formats={
        5: "{:.0f}",
        6: "{:.1e}",
        7: "{:.0f}",
        8: "{:.2e}",
        9: "{:.4%}",
        11: "{:.4%}",
        12: "{:.4%}",
        13: "{:.4%}",
        14: "{:.2e}",
        15: "{:.2%}",
    },
    block_identifier="ID",
    max_col_merge=0,
)

TABLES_LOCATION: dict[int, TableFormatting] = {
    0: damage_recap_table,
    1: fatigue_recap_table,
    2: bolt_input_table,
    3: path_input_table,
    4: bolt_immediate_table,
    5: bolt_fatigue_table,
    6: bolt_fatigue_sdcic_table,
}
