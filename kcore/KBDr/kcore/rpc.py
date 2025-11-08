from aio_pika import Message
from aio_pika.abc import AbstractRobustConnection, AbstractIncomingMessage, AbstractChannel
from pydantic import BaseModel

import asyncio, uuid
from typing import MutableMapping, Callable, Generic, TypeVar

class GeneralRpcClient:

    def __init__(
        self,
        mq_chan: AbstractChannel
    ):
        self._mq_chan = mq_chan
        self._callback_queue = None
        self._futures: MutableMapping[str, asyncio.Future] = {}

    async def start(self):
        if self._callback_queue is not None:
            raise IOError('RPC client started already')
        self._callback_queue = await self._mq_chan.declare_queue(exclusive=True)
        await self._callback_queue.consume(self._on_response, no_ack=True)

    async def _on_response(self, message: AbstractIncomingMessage):
        future = self._futures.pop(message.correlation_id)
        future.set_result(message.body)

    async def __call__(self, rpc_name: str, argument: bytes) -> bytes:
        correlation_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._futures[correlation_id] = future
        await self._mq_chan.default_exchange.publish(
            Message(
                argument,
                correlation_id=correlation_id,
                reply_to=self._callback_queue.name,
            ),
            routing_key=rpc_name,
        )
        return (await future)

_RpcClientArgumentT = TypeVar('_RpcClientArgumentT', bound=BaseModel)
_RpcClientReceiptT = TypeVar('_RpcClientReceiptT', BaseModel, None)

class RpcClient(Generic[_RpcClientArgumentT, _RpcClientReceiptT], GeneralRpcClient):

    def __init__(
        self,
        mq_conn: AbstractRobustConnection,
        rpc_name: str,
        request_type: type[BaseModel],
        receipt_type: type[BaseModel] | None
    ):
        super(RpcClient, self).__init__(None)
        self._mq_conn = mq_conn
        self._rpc_name = rpc_name
        self._request_type = request_type
        self._receipt_type = receipt_type

    async def start(self):
        if self._mq_chan is not None:
            raise IOError('RPC client started already')
        self._mq_chan = await self._mq_conn.channel()
        await super(RpcClient, self).start()

    async def __call__(self, argument: _RpcClientArgumentT) -> _RpcClientReceiptT:
        ret = await super(RpcClient, self).__call__(self._rpc_name, argument.model_dump_json().encode('utf-8'))
        if self._receipt_type is None:
            return None
        else:
            return self._receipt_type.model_validate_json(ret)

_RpcServerArgumentT = TypeVar('_RpcServerArgumentT', bound=BaseModel)
_RpcServerReceiptT = TypeVar('_RpcServerReceiptT', BaseModel, None)

class RpcServer(Generic[_RpcServerArgumentT, _RpcServerReceiptT]):

    _consume_func: Callable[[_RpcServerArgumentT], _RpcServerReceiptT]

    def __init__(
        self, 
        mq_conn: AbstractRobustConnection,
        rpc_name: str,
        consume_func: Callable[[_RpcServerArgumentT], _RpcServerReceiptT],
        request_type: type[BaseModel],
        receipt_type: type[BaseModel] | None
    ):
        self._mq_conn = mq_conn
        self._mq_chan = None
        self._consume_func = consume_func
        self._rpc_name = rpc_name
        self._request_type = request_type
        self._receipt_type = receipt_type

    async def start(self):
        if self._mq_chan is not None:
            raise IOError('RPC server started already')
        self._mq_chan = await self._mq_conn.channel()
        await self._mq_chan.set_qos(prefetch_count=1)
        self._callback_queue = await self._mq_chan.declare_queue(self._rpc_name)
        await self._callback_queue.consume(self._on_invocation)

    async def _on_invocation(self, message: AbstractIncomingMessage):
        async with message.process(requeue=True):
            arg = self._request_type.model_validate_json(message.body)
            ret = await self._consume_func(arg)
            if self._receipt_type is None:
                ret = 'null'
            else:
                ret = self._receipt_type.model_dump_json(ret)
            await self._mq_chan.default_exchange.publish(
                Message(
                    body=ret.encode('utf-8'),
                    correlation_id=message.correlation_id,
                ),
                routing_key=message.reply_to
            )
