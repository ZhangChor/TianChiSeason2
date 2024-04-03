import asyncio
import random

async def work(x):
    await asyncio.sleep(x)
    result = random.randint(1, 9)
    return (x, result)

async def main():
    tasks = [asyncio.create_task(work(random.randint(1, 5))) for _ in range(10)]
    for task in asyncio.as_completed(tasks):
        result = await task
        if result[1] >= 5:
            for t in tasks:
                t.cancel()
            return result
    res = await asyncio.gather(*tasks)
    return res

random.seed(212)
print(asyncio.run(main()))
