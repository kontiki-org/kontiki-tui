import logging

from kontiki.delegate import ServiceDelegate
from kontiki.messaging import Messenger, rpc, rpc_error


class RpcServiceDelegate(ServiceDelegate):
    async def rpc_example(self, feature):
        if feature == "standard_case":
            return "Standard case"
        elif feature == "user_input_error":
            return rpc_error("USER_INPUT_ERROR", "User input error")
        elif feature == "server_error":
            raise RuntimeError("Unexpected Server error")

    async def rpc_unhandled_exception(self):
        logging.info("rpc_unhandled_exception called, about to raise.")
        raise RuntimeError("Unhandled error in rpc_unhandled_exception")


class RpcService:
    name = "RpcService"
    delegate = RpcServiceDelegate()
    messenger = Messenger()

    @rpc
    async def rpc_example(self, feature):
        logging.info("Use delegate to implement business logic.")
        logging.info("Keep the service class clean and focused on the service .")
        result = await self.delegate.rpc_example(feature)
        if feature == "standard_case":
            # Context records land in the registry timeline, attached to
            # this execution's hop (Kontiki 2.0). KontikiTUI shows them as
            # annotations of the flow tree.
            await self.delegate.add_context(
                {"feature": feature, "result": "Standard case"}
            )
            await self.messenger.publish("chain.b", {"from": "rpc_example"})
        return result

    @rpc(include_headers=True)
    async def rpc_with_headers(self, _headers):
        return _headers["user_header"]

    @rpc
    async def rpc_may_fail(self, should_fail: bool):
        """Example that returns a client error when should_fail is True."""
        logging.info("rpc_may_fail called with should_fail=%s", should_fail)
        if should_fail:
            return rpc_error("SHOULD_FAIL", "The caller requested a failure.")
        return "All good"

    @rpc
    async def rpc_unhandled_exception(self):
        """Unhandled server-side exception; the registry records it."""
        logging.info("rpc_unhandled_exception called, about to raise.")
        await self.delegate.add_context({"stage": "before the simulated failure"})
        await self.delegate.rpc_unhandled_exception()
