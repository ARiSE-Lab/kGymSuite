# utils.py
from typing import Literal, Generic, TypeVar, List
from pydantic import BaseModel

from KBDr.kcore import PaginatedResult

JobIDRegex = "^[0-9a-f]{8}$"
SortingModes = Literal['modifiedTime', 'createdTime']

