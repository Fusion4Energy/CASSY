from cassy.designcodes.rccmr import RCC_MR
from cassy.designcodes.rccmr_bolts import RCCMR_Bolts
from cassy.designcodes.rccmrx import RCC_MRx
from cassy.designcodes.rccmrx_bolts_nl import RCCMRx_Bolts
from cassy.designcodes.sdcic import SDC_IC
from cassy.designcodes.sdcic_bolts import SDC_IC_Bolts
from cassy.designcodes.sdcic_ml import SDC_IC_ML

BOLT_CODES = {
    "SDC-IC": SDC_IC_Bolts(),
    "RCC-MR": RCCMR_Bolts(),
    "RCC-MRx": RCCMRx_Bolts(),
}

PATH_CODES = {
    "SDC-IC": SDC_IC(),
    "RCC-MR": RCC_MR(),
    "SDC-IC multilayer": SDC_IC_ML(),
    "RCC-MRx": RCC_MRx(),
}
