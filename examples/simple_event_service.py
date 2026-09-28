import logging

from kontiki.messaging import Messenger, RpcProxy, on_event


class SimpleEventService:
    messenger = Messenger()

    @on_event("simple_event")
    async def handle_simple_event(self, payload):
        logging.info("Service received simple_event: %s", payload)
        result = await RpcProxy(self.messenger, service_name="RpcService").rpc_example(
            "standard_case"
        )
        logging.info("RpcService.rpc_example returned: %s", result)

    @on_event("chain.b")
    async def handle_chain_b(self, payload):
        logging.info("Service received chain.b: %s", payload)
        await self.messenger.publish("chain.c", payload)

    @on_event("public.event.name", use_config=True)
    async def handle_dynamic_event_name(self, payload):
        logging.info("Service received event.name: %s", payload)

    @on_event("bounded_retry_event", max_attempts=2)
    async def handle_bounded_retry(self, payload):
        logging.info("Service received bounded_retry_event: %s", payload)
        logging.info(
            "The handler raises: the broker redelivers once "
            "(max_attempts=2), then drops the message at its delivery limit."
        )
        raise RuntimeError("Simulated error for the max_attempts example")
