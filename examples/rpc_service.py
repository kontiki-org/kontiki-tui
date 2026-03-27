import logging

from kontiki.delegate import ServiceDelegate
from kontiki.messaging import rpc, rpc_error


class RpcServiceDelegate(ServiceDelegate):
    async def rpc_example(self, feature):
        if feature == "standard_case":
            return "Standard case"
        elif feature == "user_input_error":
            return rpc_error("USER_INPUT_ERROR", "User input error")
        elif feature == "server_error":
            raise RuntimeError("Unexpected Server error")

    @rpc
    async def rpc_unhandled_exception(self):
        """Example that triggers an unhandled server-side exception."""
        logging.info("rpc_unhandled_exception called, about to raise.")
        error = RuntimeError("Unhandled error in rpc_unhandled_exception")
        await self.publish_exception(
            error, context={"rpc_method": "rpc_unhandled_exception"}
        )
        raise error


class RpcService:
    name = "RpcService"
    delegate = RpcServiceDelegate()

    @rpc
    async def rpc_example(self, feature):
        logging.info("Use delegate to implement business logic.")
        logging.info("Keep the service class clean and focused on the service .")
        return await self.delegate.rpc_example(feature)

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
        """Example that triggers an unhandled server-side exception."""
        logging.info("rpc_unhandled_exception called, about to raise.")
        await self.delegate.rpc_unhandled_exception()
