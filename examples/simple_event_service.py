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

    @on_event(
        "retry_then_reject_event", requeue_on_error=True, reject_on_redelivered=True
    )
    async def handle_retry_then_reject(self, payload):
        logging.info("Service received retry_then_reject_event: %s", payload)
        logging.info(
            "First delivery will be requeued on error; "
            "a redelivered message will be rejected instead of requeued."
        )
        raise RuntimeError(
            "Simulated error for requeue_on_error/reject_on_redelivered example"
        )
