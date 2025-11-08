# utils.py
from typing import Any, Callable, Generic, List, TypeVar
import asyncio, functools
from pydantic import BaseModel

async def run_async(func: Callable, *args: Any, **kwargs: Any):
    return await asyncio.get_running_loop().run_in_executor(
        None,
        functools.partial(func, *args, **kwargs)
    )

def get_type_fullname(typ):
    return '.'.join([typ.__module__, typ.__name__])

_T = TypeVar('_T')

class PaginatedResult(BaseModel, Generic[_T]):
    page: List[_T]
    pageSize: int
    offsetNextPage: int
    total: int

