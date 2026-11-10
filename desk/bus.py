"""In-process bus between agents (asyncio queues). Scanner -> auditor -> analyst -> executor -> risk."""
import asyncio
auditor = asyncio.Queue()
analyst = asyncio.Queue()
executor = asyncio.Queue()
