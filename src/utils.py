import sys
import asyncio


async def ainput(string: str) -> str:
    await asyncio.get_event_loop().run_in_executor(
        None, lambda s=string: print(s+'', end='', flush=True))
    return await asyncio.get_event_loop().run_in_executor(
        None, sys.stdin.readline)
