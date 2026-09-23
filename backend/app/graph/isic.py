"""ISIC Rev. 4: the 21 sections and the two-digit divisions each contains.

Source: United Nations Statistics Division, *International Standard Industrial
Classification of All Economic Activities (ISIC), Revision 4*, Statistical Papers,
Series M No. 4/Rev.4 (2008). Only this structural table is used. Division numbers that
fall between two sections (04, 34, 40, 44, 48, 54, 57, 67, 76, 83, 89) do not exist in
ISIC Rev. 4, and are reported as unknown rather than guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CLASSIFICATION_SYSTEM = "ISIC Rev. 4"
SOURCE = (
    "United Nations Statistics Division, International Standard Industrial Classification "
    "of All Economic Activities (ISIC), Revision 4 (Statistical Papers, Series M No. 4/Rev.4)"
)

_DIVISION = re.compile(r"^\d{2}$")


@dataclass(frozen=True)
class IsicSection:
    code: str
    title: str
    first_division: int
    last_division: int

    def contains(self, division: int) -> bool:
        return self.first_division <= division <= self.last_division


SECTIONS: tuple[IsicSection, ...] = (
    IsicSection("A", "Agriculture, forestry and fishing", 1, 3),
    IsicSection("B", "Mining and quarrying", 5, 9),
    IsicSection("C", "Manufacturing", 10, 33),
    IsicSection("D", "Electricity, gas, steam and air conditioning supply", 35, 35),
    IsicSection("E", "Water supply; sewerage, waste management and remediation activities", 36, 39),
    IsicSection("F", "Construction", 41, 43),
    IsicSection(
        "G", "Wholesale and retail trade; repair of motor vehicles and motorcycles", 45, 47
    ),
    IsicSection("H", "Transportation and storage", 49, 53),
    IsicSection("I", "Accommodation and food service activities", 55, 56),
    IsicSection("J", "Information and communication", 58, 63),
    IsicSection("K", "Financial and insurance activities", 64, 66),
    IsicSection("L", "Real estate activities", 68, 68),
    IsicSection("M", "Professional, scientific and technical activities", 69, 75),
    IsicSection("N", "Administrative and support service activities", 77, 82),
    IsicSection("O", "Public administration and defence; compulsory social security", 84, 84),
    IsicSection("P", "Education", 85, 85),
    IsicSection("Q", "Human health and social work activities", 86, 88),
    IsicSection("R", "Arts, entertainment and recreation", 90, 93),
    IsicSection("S", "Other service activities", 94, 96),
    IsicSection(
        "T",
        "Activities of households as employers; undifferentiated goods- and "
        "services-producing activities of households for own use",
        97,
        98,
    ),
    IsicSection("U", "Activities of extraterritorial organizations and bodies", 99, 99),
)

SECTIONS_BY_CODE: dict[str, IsicSection] = {section.code: section for section in SECTIONS}


def section_for_division(code: str) -> IsicSection | None:
    """The section containing a two-digit ISIC Rev. 4 division, or ``None`` when the
    code is not a division that exists."""
    if not _DIVISION.match(code):
        return None
    division = int(code)
    return next((section for section in SECTIONS if section.contains(division)), None)
