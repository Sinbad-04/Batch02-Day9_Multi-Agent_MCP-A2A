"""End-to-end test client for the Legal Multi-Agent System.

Sends a legal question to the Customer Agent and prints the response.
"""

import asyncio
import os
import sys

import httpx
from dotenv import load_dotenv
from common.a2a_client import _extract_text

load_dotenv()

CUSTOMER_AGENT_URL = os.getenv("CUSTOMER_AGENT_URL", "http://localhost:10100")

QUESTION = (
    "If a company breaks a contract and avoids taxes, "
    "what are the legal and regulatory consequences?"
)


async def main() -> None:
    print(f"Connecting to Customer Agent at {CUSTOMER_AGENT_URL}")
    print(f"Question: {QUESTION}")
    print("-" * 60)

    async with httpx.AsyncClient(timeout=300.0) as http_client:
        # Resolve agent card
        card_url = f"{CUSTOMER_AGENT_URL}/.well-known/agent.json"
        try:
            card_resp = await http_client.get(card_url)
            card_resp.raise_for_status()
        except Exception as e:
            print(f"ERROR: Could not reach Customer Agent at {card_url}")
            print(f"  {e}")
            print("Make sure all services are running (./start_all.sh)")
            sys.exit(1)

        from uuid import uuid4
        from a2a.client import ClientFactory, ClientConfig
        from a2a.types import AgentCard, Message, Part, Role, TextPart

        agent_card = AgentCard.model_validate(card_resp.json())
        print(f"Connected to agent: {agent_card.name} v{agent_card.version}")
        print("-" * 60)

        config = ClientConfig(httpx_client=http_client, streaming=False)
        factory = ClientFactory(config)
        client = factory.create(agent_card)

        message = Message(
            role=Role.user,
            parts=[Part(root=TextPart(text=QUESTION))],
            message_id=str(uuid4()),
        )

        print("Sending request (this may take 30-60s while agents chain)...\n")

        result_text = ""
        final_result = None
        async for event in client.send_message(message):
            # event is ClientEvent (Task, update) or Message
            if isinstance(event, tuple):
                task, update = event
                final_result = task
            else:
                # Message
                final_result = event

        if final_result is not None:
            result_text = _extract_text(final_result)

        if result_text:
            print("RESPONSE:")
            print("=" * 60)
            print(result_text)
            print("=" * 60)
        else:
            print("No text response received. Raw response:")
            print(final_result)


if __name__ == "__main__":
    asyncio.run(main())