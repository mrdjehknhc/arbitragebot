"""
Async utilities for concurrent API requests
Professional-grade async helpers with rate limiting and error handling
"""
import asyncio
from typing import List, Callable, TypeVar, Optional, Dict, Any
from functools import wraps
import time
from ..utils.logger import get_logger

logger = get_logger()

T = TypeVar('T')


class RateLimiter:
    """
    Rate limiter for API calls
    Ensures we don't exceed exchange rate limits
    """
    
    def __init__(self, calls_per_second: float = 10):
        self.calls_per_second = calls_per_second
        self.min_interval = 1.0 / calls_per_second
        self.last_call = 0.0
        self._lock = asyncio.Lock()
    
    async def acquire(self):
        """Wait if necessary to respect rate limit"""
        async with self._lock:
            now = time.time()
            time_since_last = now - self.last_call
            
            if time_since_last < self.min_interval:
                wait_time = self.min_interval - time_since_last
                await asyncio.sleep(wait_time)
            
            self.last_call = time.time()


class AsyncBatch:
    """
    Batch processor for async operations
    Handles concurrent execution with proper error handling
    """
    
    def __init__(self, max_concurrent: int = 10):
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
    
    async def run(
        self,
        func: Callable,
        items: List[Any],
        return_exceptions: bool = True
    ) -> List[Any]:
        """
        Run function on all items concurrently
        
        Args:
            func: Async function to execute
            items: List of items to process
            return_exceptions: If True, return exceptions instead of raising
        
        Returns:
            List of results (or exceptions if return_exceptions=True)
        """
        async def _run_one(item):
            async with self.semaphore:
                try:
                    return await func(item)
                except Exception as e:
                    if return_exceptions:
                        logger.warning(f"Error processing {item}: {e}")
                        return e
                    else:
                        raise
        
        tasks = [_run_one(item) for item in items]
        return await asyncio.gather(*tasks, return_exceptions=return_exceptions)


async def async_map(
    func: Callable[[T], Any],
    items: List[T],
    max_concurrent: int = 10,
    rate_limit: Optional[float] = None
) -> List[Any]:
    """
    Map async function over list of items with concurrency control
    
    Args:
        func: Async function to apply
        items: Items to process
        max_concurrent: Max concurrent executions
        rate_limit: Optional rate limit (calls per second)
    
    Returns:
        List of results
    
    Example:
        results = await async_map(fetch_ticker, ['BTC/USDT', 'ETH/USDT'])
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    limiter = RateLimiter(rate_limit) if rate_limit else None
    
    async def _process(item):
        async with semaphore:
            if limiter:
                await limiter.acquire()
            return await func(item)
    
    return await asyncio.gather(*[_process(item) for item in items])


async def async_retry(
    func: Callable,
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,)
) -> Any:
    """
    Retry async function with exponential backoff
    
    Args:
        func: Async function to retry
        max_attempts: Maximum retry attempts
        delay: Initial delay between retries
        backoff: Backoff multiplier
        exceptions: Exceptions to catch and retry
    
    Returns:
        Function result
    
    Raises:
        Last exception if all retries fail
    """
    last_exception = None
    current_delay = delay
    
    for attempt in range(max_attempts):
        try:
            return await func()
        except exceptions as e:
            last_exception = e
            if attempt < max_attempts - 1:
                logger.warning(
                    f"Attempt {attempt + 1}/{max_attempts} failed: {e}. "
                    f"Retrying in {current_delay:.1f}s..."
                )
                await asyncio.sleep(current_delay)
                current_delay *= backoff
            else:
                logger.error(f"All {max_attempts} attempts failed")
    
    raise last_exception


def async_timeout(seconds: float):
    """
    Decorator to add timeout to async function
    
    Usage:
        @async_timeout(5.0)
        async def slow_function():
            await asyncio.sleep(10)
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=seconds
                )
            except asyncio.TimeoutError:
                logger.error(f"{func.__name__} timed out after {seconds}s")
                raise
        return wrapper
    return decorator


async def run_with_timeout(
    coro,
    timeout: float,
    default=None
) -> Any:
    """
    Run coroutine with timeout, return default on timeout
    
    Args:
        coro: Coroutine to run
        timeout: Timeout in seconds
        default: Default value to return on timeout
    
    Returns:
        Result or default
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(f"Timeout after {timeout}s, returning default")
        return default


class AsyncCache:
    """
    Simple async cache with TTL
    Useful for caching API responses
    """
    
    def __init__(self, ttl: float = 60.0):
        self.ttl = ttl
        self._cache: Dict[str, tuple] = {}  # key -> (value, timestamp)
        self._lock = asyncio.Lock()
    
    async def get(self, key: str) -> Optional[Any]:
        """Get cached value if not expired"""
        async with self._lock:
            if key in self._cache:
                value, timestamp = self._cache[key]
                if time.time() - timestamp < self.ttl:
                    return value
                else:
                    del self._cache[key]
            return None
    
    async def set(self, key: str, value: Any):
        """Set cached value with current timestamp"""
        async with self._lock:
            self._cache[key] = (value, time.time())
    
    async def clear(self):
        """Clear all cached values"""
        async with self._lock:
            self._cache.clear()
    
    async def get_or_fetch(
        self,
        key: str,
        fetch_func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Get from cache or fetch if not present/expired
        
        Example:
            value = await cache.get_or_fetch(
                'BTC_price',
                fetch_ticker,
                'BTC/USDT'
            )
        """
        cached = await self.get(key)
        if cached is not None:
            return cached
        
        value = await fetch_func(*args, **kwargs)
        await self.set(key, value)
        return value


async def gather_with_limit(
    *coros,
    limit: int = 10,
    return_exceptions: bool = True
) -> List[Any]:
    """
    Gather coroutines with concurrency limit
    
    Args:
        *coros: Coroutines to execute
        limit: Max concurrent executions
        return_exceptions: Return exceptions instead of raising
    
    Returns:
        List of results
    """
    semaphore = asyncio.Semaphore(limit)
    
    async def _run(coro):
        async with semaphore:
            return await coro
    
    return await asyncio.gather(
        *[_run(coro) for coro in coros],
        return_exceptions=return_exceptions
    )


class AsyncPool:
    """
    Worker pool for async tasks
    Maintains fixed number of workers processing queue
    """
    
    def __init__(self, workers: int = 5):
        self.workers = workers
        self.queue: asyncio.Queue = asyncio.Queue()
        self.results: List[Any] = []
        self._workers: List[asyncio.Task] = []
    
    async def _worker(self):
        """Worker coroutine"""
        while True:
            try:
                func, args, kwargs = await self.queue.get()
                if func is None:  # Poison pill
                    break
                
                result = await func(*args, **kwargs)
                self.results.append(result)
            except Exception as e:
                logger.error(f"Worker error: {e}")
            finally:
                self.queue.task_done()
    
    async def start(self):
        """Start worker pool"""
        self._workers = [
            asyncio.create_task(self._worker())
            for _ in range(self.workers)
        ]
    
    async def submit(self, func: Callable, *args, **kwargs):
        """Submit task to pool"""
        await self.queue.put((func, args, kwargs))
    
    async def join(self):
        """Wait for all tasks to complete"""
        await self.queue.join()
    
    async def stop(self):
        """Stop all workers"""
        for _ in self._workers:
            await self.queue.put((None, None, None))
        
        await asyncio.gather(*self._workers)


# Utility function for backward compatibility with sync code
def run_async(coro):
    """
    Run async coroutine in sync context
    
    Usage:
        result = run_async(async_function())
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(coro)


async def batch_with_rate_limit(
    items: List[Any],
    func: Callable,
    batch_size: int = 10,
    delay_between_batches: float = 1.0
) -> List[Any]:
    """
    Process items in batches with delay between batches
    Useful for strict rate limits
    
    Args:
        items: Items to process
        func: Async function to apply
        batch_size: Size of each batch
        delay_between_batches: Delay between batches in seconds
    
    Returns:
        List of all results
    """
    results = []
    
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        batch_results = await asyncio.gather(*[func(item) for item in batch])
        results.extend(batch_results)
        
        # Delay before next batch (except for last batch)
        if i + batch_size < len(items):
            await asyncio.sleep(delay_between_batches)
    
    return results