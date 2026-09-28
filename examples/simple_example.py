import asyncio

from kontiki.messaging import Messenger
from kontiki.messaging.flow import generate_flow_id


async def main():
    amqp_url = "amqp://guest:guest@localhost"
    async with Messenger(amqp_url=amqp_url, standalone=True) as messenger:
        print("Publishing simple_event...")
        await messenger.publish(
            "simple_event",
            {"message": "Hello from simple event"},
            flow_id=generate_flow_id(),
        )
        print("simple_event published.")

        print("Publishing dynamic_event_name...")
        await messenger.publish(
            "dynamic_event_name",
            {"message": "Hello from dynamic event name"},
            flow_id=generate_flow_id(),
        )
        print("dynamic_event_name published.")

        print(
            "Publishing bounded_retry_event (the handler fails; the broker "
            "redelivers once, then drops it at its delivery limit)..."
        )
        await messenger.publish(
            "bounded_retry_event",
            {"message": "This will be redelivered once, then dropped by the broker"},
            flow_id=generate_flow_id(),
        )
        print("bounded_retry_event published.")


if __name__ == "__main__":
    asyncio.run(main())
